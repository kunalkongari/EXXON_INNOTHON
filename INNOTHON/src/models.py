"""
models.py - forecasting models used in Phase 3 (all univariate on monthly ACTUAL generation).

Statistical / baseline models: forecast(name, y, h, covid=None) -> np.ndarray(h)
  y      : pd.Series with monthly PeriodIndex (training data only, ends at the forecast origin)
  covid  : None (no intervention) or list of covid periods -> 0/1 regressor (models that accept regressors)
ML models (global, pooled across series): ml_forecast(...) in this module.

No capacity, consumption, population or GSDP enters any model here.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
from statsmodels.tsa.holtwinters import ExponentialSmoothing  # noqa: E402
from statsmodels.tsa.exponential_smoothing.ets import ETSModel  # noqa: E402
from statsmodels.tsa.statespace.sarimax import SARIMAX  # noqa: E402

M = 12
STAT_MODELS = ["naive", "snaive", "lintrend", "lintrend_season", "ses", "holt_damped", "hw_add", "hw_mul", "ets_auto", "arima", "sarima"]
BASELINES = ["naive", "snaive", "lintrend", "lintrend_season"]
REGRESSOR_MODELS = {"lintrend", "lintrend_season", "arima", "sarima"}  # accept the COVID intervention regressor
ML_MODELS = ["rf", "xgb"]
DESCRIPTION = {
    "naive": "Naive: last observed value",
    "snaive": "Seasonal naive: value 12 months earlier",
    "lintrend": "Linear trend (OLS on time)",
    "lintrend_season": "Linear trend + 11 month dummies (OLS)",
    "ses": "Simple exponential smoothing",
    "holt_damped": "Holt linear (damped) trend, no seasonality",
    "hw_add": "Holt-Winters damped trend, additive seasonality",
    "hw_mul": "Holt-Winters damped trend, multiplicative seasonality",
    "ets_auto": "ETS state-space, AICc selection over error{A,M} x trend{N,Ad} x season{A,M}",
    "arima": "ARIMA(p,1,q)+drift, (p,q) by AIC on first-origin window",
    "sarima": "SARIMA(p,d,q)(P,1,Q)12, order by AIC on first-origin window",
    "rf": "Random Forest, global pooled direct multi-horizon (seasonal log-ratio target)",
    "xgb": "XGBoost, global pooled direct multi-horizon (seasonal log-ratio target)",
}


def _dummy(index: pd.PeriodIndex, covid) -> np.ndarray | None:
    if not covid:
        return None
    s = {pd.Period(c, freq="M") for c in covid}
    return np.array([[1.0 if p in s else 0.0] for p in index])


def _future_index(y: pd.Series, h: int) -> pd.PeriodIndex:
    return pd.period_range(y.index[-1] + 1, periods=h, freq="M")


def _nonneg(f):
    f = np.asarray(f, dtype=float)
    return np.where(np.isfinite(f), np.maximum(f, 0.0), np.nan)


def _ols(y, h, covid, season):
    n = len(y)
    t = np.arange(n + h, dtype=float)
    idx = y.index.append(_future_index(y, h))
    X = [np.ones(n + h), t]
    if season:
        mo = np.array([p.month for p in idx])
        X += [(mo == k).astype(float) for k in range(2, 13)]
    d = _dummy(idx, covid)
    if d is not None and d[:n].sum() > 0:
        X.append(d[:, 0])
    X = np.column_stack(X)
    beta, *_ = np.linalg.lstsq(X[:n], y.values, rcond=None)
    return X[n:] @ beta


SARIMA_GRID = [((1, 0, 0), (0, 1, 1), "c"), ((1, 0, 0), (1, 1, 0), "c"), ((2, 0, 0), (0, 1, 1), "c"),
               ((0, 1, 1), (0, 1, 1), "n"), ((1, 1, 0), (0, 1, 1), "n"), ((1, 1, 1), (0, 1, 1), "n"),
               ((0, 1, 1), (1, 1, 0), "n"), ((1, 0, 1), (0, 1, 1), "c")]
ARIMA_GRID = [((p, 1, q), (0, 0, 0), "t") for p in (0, 1, 2) for q in (0, 1, 2)]


def select_order(y: pd.Series, kind: str, covid) -> tuple:
    """AIC selection on the given (first-origin) training window."""
    grid = SARIMA_GRID if kind == "sarima" else ARIMA_GRID
    best, best_aic = grid[0], np.inf
    ex = _dummy(y.index, covid)
    if ex is not None and ex.sum() == 0:
        ex = None
    for order, sorder, trend in grid:
        try:
            r = SARIMAX(y.values, exog=ex, order=order, seasonal_order=(*sorder, M if sorder != (0, 0, 0) else 0),
                        trend=trend, enforce_stationarity=False, enforce_invertibility=False).fit(disp=False)
            if np.isfinite(r.aic) and r.aic < best_aic:
                best, best_aic = (order, sorder, trend), r.aic
        except Exception:  # noqa: BLE001
            continue
    return best


def _sarimax(y, h, covid, spec):
    order, sorder, trend = spec
    ex = _dummy(y.index, covid)
    if ex is not None and ex.sum() == 0:
        ex = None
    exf = np.zeros((h, 1)) if ex is not None else None
    r = SARIMAX(y.values, exog=ex, order=order, seasonal_order=(*sorder, M if sorder != (0, 0, 0) else 0), trend=trend,
                enforce_stationarity=False, enforce_invertibility=False).fit(disp=False)
    return r.forecast(h, exog=exf)


def _ets_auto(y, h):
    pos = (y > 0).all()
    best, best_aicc = None, np.inf
    for err in (["add", "mul"] if pos else ["add"]):
        for trend, damped in [(None, False), ("add", True)]:
            for seas in (["add", "mul"] if pos else ["add"]):
                try:
                    r = ETSModel(y.astype(float).values, error=err, trend=trend, damped_trend=damped, seasonal=seas,
                                 seasonal_periods=M).fit(disp=False, maxiter=200)
                    if np.isfinite(r.aicc) and r.aicc < best_aicc:
                        best, best_aicc = r, r.aicc
                except Exception:  # noqa: BLE001
                    continue
    return best.forecast(h) if best is not None else np.full(h, np.nan)


def forecast(name: str, y: pd.Series, h: int, covid=None, spec=None) -> np.ndarray:
    y = y.astype(float)
    n = len(y)
    try:
        if name == "naive":
            f = np.repeat(y.iloc[-1], h)
        elif name == "snaive":
            f = np.array([y.iloc[n - M + (k % M)] for k in range(h)])
        elif name == "lintrend":
            f = _ols(y, h, covid, season=False)
        elif name == "lintrend_season":
            f = _ols(y, h, covid, season=True)
        elif name == "ses":
            f = ExponentialSmoothing(y.values, trend=None, seasonal=None).fit().forecast(h)
        elif name == "holt_damped":
            f = ExponentialSmoothing(y.values, trend="add", damped_trend=True, seasonal=None).fit().forecast(h)
        elif name == "hw_add":
            f = ExponentialSmoothing(y.values, trend="add", damped_trend=True, seasonal="add", seasonal_periods=M).fit().forecast(h)
        elif name == "hw_mul":
            if not (y > 0).all():
                return np.full(h, np.nan)
            f = ExponentialSmoothing(y.values, trend="add", damped_trend=True, seasonal="mul", seasonal_periods=M).fit().forecast(h)
        elif name == "ets_auto":
            f = _ets_auto(y, h)
        elif name in ("arima", "sarima"):
            f = _sarimax(y, h, covid, spec or select_order(y, name, covid))
        else:
            raise ValueError(name)
    except Exception:  # noqa: BLE001
        return np.full(h, np.nan)
    return _nonneg(f)


# ============================================================================ ML (global, pooled)
LEVEL_CODES = {"national": 0, "region": 1, "state": 2, "national_source": 3, "national_source_agg": 3, "state_source": 4, "import": 5}


def _features(v: np.ndarray, periods: pd.PeriodIndex, i: int, h: int, covid_set: set | None):
    """Features at origin index i (inclusive) for target i+h. Uses only v[:i+1]."""
    L = np.log1p(np.maximum(v, 0))
    ref = i + h - M  # seasonal reference index (<= i since h <= 12)
    yoy = lambda k: L[k] - L[k - M]  # noqa: E731
    f = {
        "h": h,
        "yoy_1": yoy(i),
        "yoy_mean3": np.mean([yoy(k) for k in range(i - 2, i + 1)]),
        "yoy_mean6": np.mean([yoy(k) for k in range(i - 5, i + 1)]),
        "yoy_std6": np.std([yoy(k) for k in range(i - 5, i + 1)]),
        "lag1_rel_ref": L[i] - L[ref],
        "rm3_rel_rm12": np.log1p(v[i - 2:i + 1].mean()) - np.log1p(v[i - 11:i + 1].mean()),
        "rs12_rel": np.log1p(v[i - 11:i + 1].std()) - np.log1p(v[i - 11:i + 1].mean() + 1e-9),
        "ref_rel_rm12": L[ref] - np.log1p(v[i - 11:i + 1].mean()),
        "zero_share12": float(np.mean(v[i - 11:i + 1] == 0)),
    }
    tp = periods[i] + h
    f["month_sin"], f["month_cos"] = np.sin(2 * np.pi * tp.month / 12), np.cos(2 * np.pi * tp.month / 12)
    f["target_month"] = tp.month
    f["year"] = tp.year
    if covid_set is not None:
        f["covid_ref"] = float(periods[ref] in covid_set)
        f["covid_window"] = float(any(periods[k] in covid_set for k in range(i - 17, i + 1)))
        f["covid_target"] = float(tp in covid_set)
    return f


MIN_HIST = 18  # observations needed before the first feature row (yoy over 6 months needs 17 lags)


def ml_forecast(series: dict, levels: dict, origin: str, model: str, covid, train_start: str, params: dict,
                h_max: int = 12, seed: int = 0):
    """Train one global model on all series truncated to [train_start, origin]; forecast h=1..h_max per series.
    Target = log1p(y[t+h]) - log1p(y[t+h-12]). Returns {node_id: np.ndarray(h_max)}."""
    from sklearn.ensemble import RandomForestRegressor
    from xgboost import XGBRegressor
    o = pd.Period(origin, freq="M")
    s0 = pd.Period(train_start, freq="M")
    cset = {pd.Period(c, freq="M") for c in covid} if covid else None
    Xr, yr, pred_rows, pred_keys = [], [], [], []
    for nid, s in series.items():
        s = s[(s.index >= s0) & (s.index <= o)]
        if len(s) < MIN_HIST + 1 or s.index[-1] != o:
            continue
        v, per = s.values.astype(float), s.index
        lc = LEVEL_CODES.get(levels.get(nid, ""), 9)
        n = len(v)
        for i in range(MIN_HIST - 1, n):
            for h in range(1, h_max + 1):
                if i + h < n:
                    f = _features(v, per, i, h, cset)
                    f["level"] = lc
                    Xr.append(f)
                    yr.append(np.log1p(max(v[i + h], 0)) - np.log1p(max(v[i + h - M], 0)))
                if i == n - 1:
                    f = _features(v, per, i, h, cset)
                    f["level"] = lc
                    pred_rows.append(f)
                    pred_keys.append((nid, h, v[i + h - M]))
    if not Xr or not pred_rows:
        return {}, None, []
    X = pd.DataFrame(Xr)
    Xp = pd.DataFrame(pred_rows)[X.columns]
    if model == "rf":
        m = RandomForestRegressor(random_state=seed, n_jobs=-1, **params)
    else:
        m = XGBRegressor(random_state=seed, n_jobs=8, tree_method="hist", **params)
    m.fit(X.values, np.array(yr))
    p = m.predict(Xp.values)
    out: dict[str, np.ndarray] = {}
    for (nid, h, refv), d in zip(pred_keys, p):
        out.setdefault(nid, np.full(h_max, np.nan))[h - 1] = max(np.expm1(np.log1p(max(refv, 0)) + d), 0.0)
    return out, m, list(X.columns)
