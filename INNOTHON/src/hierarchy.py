"""
hierarchy.py  (Phase 3H)
------------------------
Grouped hierarchy with 73 bottom series (state x source cells):
    TOTAL = sum(REG) = sum(ST) = sum(NSRC agg) = sum(CELL)
    REG   = sum of its states;  ST = sum of its cells;  NSRC|<src> = sum of CELL|*|<src>
Coal vs lignite is distinguished ONLY nationally: NSRC|COAL_LIGNITE (reconciled) is split into
NSRC|COAL and NSRC|LIGNITE in proportion to their own base forecasts.
Bhutan import is not part of the hierarchy.

Base forecasts (from the backtest of the main experiment, selected model per level):
  TOTAL, REG, NSRC, ST groups A/B, eligible CELLs -> direct model forecasts
  ST group C            -> allocation of the region's base forecast by seasonal proportion (same month last year)
  ineligible CELLs      -> allocation of the state's base forecast by seasonal proportion
Methods: BASE (incoherent), BU, TD (seasonal proportions from TOTAL), MO (middle-out from states),
         OLS, WLS_struct (W = diag(#bottom series)), WLS_scale (W = diag(seasonal-naive scale^2)).
Negative reconciled bottom values are set to 0 and the hierarchy re-aggregated bottom-up.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import DATA, add_months, load_panel, series_dict

AGG_SRC = ["COAL_LIGNITE", "NATURAL_GAS", "DIESEL", "NUCLEAR", "HYDRO"]
METHODS = ["BASE", "BU", "TD", "MO", "OLS", "WLS_struct", "WLS_scale"]


def structure():
    meta = pd.read_csv(DATA / "node_metadata.csv")
    cells = sorted(meta[meta.level == "state_source"].node_id)
    states = sorted(meta[meta.level == "state"].node_id)
    regions = sorted(meta[meta.level == "region"].node_id)
    rows = ["TOTAL"] + regions + states + [f"NSRC|{s}" for s in AGG_SRC] + cells
    S = np.zeros((len(rows), len(cells)))
    st_reg = meta.set_index("node_id").region
    for j, c in enumerate(cells):
        _, st, src = c.split("|")
        for i, r in enumerate(rows):
            if r == "TOTAL" or r == c or r == f"ST|{st}" or r == f"NSRC|{src}" or (r.startswith("REG|") and r == f"REG|{st_reg[c]}"):
                S[i, j] = 1
    return rows, cells, S, meta


def seasonal_share(child: pd.Series, parent: pd.Series, target: pd.Period) -> float:
    """Share of child in parent in the same month one year earlier (fallback: trailing 12 months)."""
    ref = target - 12
    if len(parent):
        while ref > parent.index[-1]:
            ref -= 12  # horizons > 12: use the most recent observed same calendar month
    pv, cv = parent.get(ref, np.nan), child.get(ref, np.nan)
    if pd.notna(pv) and pv > 0 and pd.notna(cv):
        return float(cv / pv)
    o = parent.index[parent.index <= ref]
    if len(o) == 0:
        return 0.0
    last = o[-12:]
    p12 = parent.reindex(last).sum()
    return float(child.reindex(last).fillna(0).sum() / p12) if p12 > 0 else 0.0


def reconcile(yhat: np.ndarray, S: np.ndarray, method: str, scale: np.ndarray | None = None) -> np.ndarray:
    nb = S.shape[1]
    if method == "OLS":
        P = np.linalg.solve(S.T @ S, S.T)
    elif method in ("WLS_struct", "WLS_scale"):
        w = S.sum(axis=1) if method == "WLS_struct" else np.where(np.isfinite(scale) & (scale > 0), scale ** 2, np.nanmedian(scale) ** 2)
        Wi = np.diag(1.0 / w)
        P = np.linalg.solve(S.T @ Wi @ S, S.T @ Wi)
    else:
        raise ValueError(method)
    b = P @ yhat
    b = np.maximum(b, 0.0)
    return S @ b


def coherent_from_bottom(b: np.ndarray, S: np.ndarray) -> np.ndarray:
    return S @ np.maximum(b, 0.0)


def build_base(fc: dict[str, np.ndarray], series: dict, rows, cells, meta, origin: str, h: int):
    """fc: node -> base forecasts (len h) for directly modelled nodes. Fills allocated nodes.
    Returns array (len(rows), h) of base forecasts."""
    o = pd.Period(origin, freq="M")
    m = meta.set_index("node_id")
    out = {k: np.asarray(v, dtype=float) for k, v in fc.items()}
    tps = [o + k for k in range(1, h + 1)]
    # group C states: allocate region base
    for st in m[(m.level == "state") & (m.group == "C")].index:
        reg = "REG|" + m.region[st]
        out[st] = np.array([out[reg][k] * seasonal_share(series[st][:o], series[reg][:o], tps[k]) if st in series and len(series[st][:o]) else 0.0 for k in range(h)])
    # ineligible cells: allocate state base
    for c in cells:
        if c in out and not np.all(np.isnan(out[c])) and m.eligible_direct.get(c) == True:  # noqa: E712
            continue
        st = "ST|" + c.split("|")[1]
        cs = series[c][:o] if c in series else pd.Series(dtype=float)
        out[c] = np.array([out[st][k] * seasonal_share(cs, series[st][:o], tps[k]) if len(cs) else 0.0 for k in range(h)])
    return np.vstack([out[r] for r in rows])


def all_methods(Y: np.ndarray, rows, cells, S, series, origin, h, scales):
    """Y: base forecasts (len(rows), h). Returns {method: coherent array}."""
    o = pd.Period(origin, freq="M")
    idx = {r: i for i, r in enumerate(rows)}
    res = {"BASE": Y.copy()}
    nb = len(cells)
    bot = Y[[idx[c] for c in cells], :]
    res["BU"] = coherent_from_bottom(np.nan_to_num(bot), S)
    tps = [o + k for k in range(1, h + 1)]
    td = np.zeros((nb, h))
    mo = np.zeros((nb, h))
    for j, c in enumerate(cells):
        st = "ST|" + c.split("|")[1]
        cs = series[c][:o]
        for k in range(h):
            td[j, k] = Y[idx["TOTAL"], k] * seasonal_share(cs, series["TOTAL"][:o], tps[k]) if len(cs) else 0.0
            mo[j, k] = Y[idx[st], k] * seasonal_share(cs, series[st][:o], tps[k]) if len(cs) else 0.0
    res["TD"] = coherent_from_bottom(td, S)
    res["MO"] = coherent_from_bottom(mo, S)
    Yf = np.nan_to_num(Y)
    for mth in ("OLS", "WLS_struct", "WLS_scale"):
        res[mth] = np.column_stack([reconcile(Yf[:, k], S, mth, scales) for k in range(h)])
    return res


def split_coal_lignite(cl: np.ndarray, coal_base: np.ndarray, lig_base: np.ndarray):
    tot = coal_base + lig_base
    share = np.where(tot > 0, coal_base / np.where(tot > 0, tot, 1), 0.97)
    return cl * share, cl * (1 - share)
