"""Shared paths, experiment configuration, data access and metrics for Phase 3."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "outputs" / "data"
MODELS = ROOT / "outputs" / "models"
BT = ROOT / "outputs" / "backtesting"
FC = ROOT / "outputs" / "forecasts"
SC = ROOT / "outputs" / "scenarios"
REPORTS = ROOT / "reports"
for _d in (MODELS, BT, FC, SC):
    _d.mkdir(parents=True, exist_ok=True)

# ----------------------------------------------------------------------------- configuration
CONFIG = {
    "main_data_start": "2019-07",
    "main_data_end": "2026-09",
    "extended_data_start": "2018-07",          # sensitivity only (Phase 3G)
    "experiment_B_start": "2021-04",           # FY2021-22
    "covid_months": ["2020-03", "2020-04", "2020-05"],
    "horizon_max": 12,
    "report_horizons": [1, 3, 6, 12],
    "origins_monthly": {"first": "2023-06", "last": "2026-08"},   # national, regional, national-source
    "origins_quarterly": {"first": "2023-06", "last": "2026-06", "step": 3},  # states, state x source
    "selection_metric": "mean MASE over horizons 1-12 (rolling-origin, out-of-sample); tie-break WAPE, then simplicity",
    "seed": 20470,
    "rf_params": {"n_estimators": 500, "min_samples_leaf": 3, "max_features": 0.6},
    "xgb_params": {"n_estimators": 400, "max_depth": 3, "learning_rate": 0.03, "subsample": 0.8,
                   "colsample_bytree": 0.8, "min_child_weight": 3, "reg_lambda": 1.0},
    "state_groups_rule": "C if <60 months or <1000 GWh FY2025-26 or >6 zero months; A if >=2% share and median|YoY|<15%; else B",
    "state_source_eligibility": {"min_months": 84, "min_nonzero": 72},
}


def save_config():
    (MODELS / "experiment_config.json").write_text(json.dumps(CONFIG, indent=2), encoding="utf-8")


def periods(first: str, last: str, step: int = 1) -> list[str]:
    return [str(p) for p in pd.period_range(first, last, freq="M")[::step]]


def origins(kind: str) -> list[str]:
    o = CONFIG["origins_monthly"] if kind == "monthly" else CONFIG["origins_quarterly"]
    return periods(o["first"], o["last"], o.get("step", 1))


def add_months(p: str, k: int) -> str:
    return str(pd.Period(p, freq="M") + k)


def load_panel(extended: bool = False) -> pd.DataFrame:
    """Model-ready long panel: node_id, level, period, value_gwh (+ metadata)."""
    f = DATA / ("model_ready_extended_national.csv" if extended else "model_ready_monthly.csv")
    return pd.read_csv(f)


def series_dict(panel: pd.DataFrame) -> dict[str, pd.Series]:
    out = {}
    for nid, d in panel.groupby("node_id"):
        s = d.set_index("period").value_gwh.sort_index()
        s.index = pd.PeriodIndex(s.index, freq="M")
        out[nid] = s
    return out


# ----------------------------------------------------------------------------- metrics
def seasonal_naive_scale(train: np.ndarray, m: int = 12) -> float:
    """In-sample MAE of the seasonal-naive forecast on the training window (MASE denominator)."""
    if len(train) <= m:
        d = np.abs(np.diff(train))
    else:
        d = np.abs(train[m:] - train[:-m])
    s = float(np.mean(d)) if len(d) else np.nan
    return s if s > 0 else np.nan


def summarise(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """df has columns: actual, forecast, scale (MASE denominator) + grouping columns.
    WAPE = sum|e|/sum|y| (pooled, robust to zeros unless all actuals are zero).
    MASE = mean(|e|/scale) over rows with a positive scale.
    Bias% = sum(f-y)/sum(y) (positive = over-forecast)."""
    d = df.copy()
    d["e"] = d.forecast - d.actual
    d["ae"] = d.e.abs()
    d["se"] = d.e ** 2
    d["sae"] = d.ae / d.scale
    g = d.groupby(by)
    out = pd.DataFrame({
        "n": g.size(),
        "MAE": g.ae.mean(),
        "RMSE": np.sqrt(g.se.mean()),
        "WAPE_%": 100 * g.ae.sum() / g.actual.apply(lambda x: np.abs(x).sum()).replace(0, np.nan),
        "MASE": g.sae.mean(),
        "bias_%": 100 * g.e.sum() / g.actual.sum().replace(0, np.nan),
    }).reset_index()
    return out


def md_table(df: pd.DataFrame, fmt: str = "{:,.2f}", maxrows: int = 200) -> str:
    if df is None or len(df) == 0:
        return "_none_\n"
    d = df.head(maxrows)
    cols = [str(c) for c in d.columns]
    s = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    for _, r in d.iterrows():
        cells = []
        for v in r.values:
            if isinstance(v, (float, np.floating)):
                cells.append("" if pd.isna(v) else fmt.format(v))
            else:
                cells.append(str(v))
        s += "| " + " | ".join(cells) + " |\n"
    if len(df) > maxrows:
        s += f"\n_{len(df) - maxrows} more rows in CSV_\n"
    return s
