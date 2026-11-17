"""
evaluate.py - out-of-sample metrics and model selection (Phases 3B-3G).

Selection rule (fixed before looking at results, see CONFIG["selection_metric"]):
  per reporting level, the model with the lowest mean MASE over horizons 1-12 on the rolling-origin
  backtest, among models with >= 95% forecast coverage; it must beat seasonal-naive (else seasonal-naive
  is selected). Ties within 0.01 MASE -> lower WAPE, then the simpler model.
Training-sample fit is never used for selection.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import BT, DATA, MODELS, summarise
from models import BASELINES, DESCRIPTION

SIMPLICITY = ["snaive", "naive", "lintrend", "lintrend_season", "ses", "holt_damped", "hw_add", "hw_mul", "ets_auto", "arima", "sarima", "rf", "xgb"]


def level_cat(row_level, nid, group, eligible):
    if nid == "TOTAL":
        return "National"
    if nid.startswith("REG|"):
        return "Regions (5)"
    if nid.startswith("NSRC|"):
        return "National sources"
    if nid.startswith("IMPORT|"):
        return "Bhutan import (separate)"
    if nid.startswith("ST|"):
        return f"States group {group}"
    if nid.startswith("CELL|"):
        return "State x source (eligible)" if eligible else "State x source (ineligible)"
    return row_level


def load(exps=("A", "B", "C", "EXT")) -> pd.DataFrame:
    meta = pd.read_csv(DATA / "node_metadata.csv")
    g = meta.set_index("node_id")
    fr = []
    for e in exps:
        f = BT / f"forecasts_{e}.csv"
        if f.exists():
            fr.append(pd.read_csv(f))
    d = pd.concat(fr, ignore_index=True)
    # explosion guard (uniform across experiments): forecasts > 5x the series maximum observed up to the
    # origin are numerical failures (seen for SARIMA on a few series) -> treated as missing (lowers coverage)
    from common import load_panel
    pan = load_panel()
    cm = pan.sort_values("period").assign(cmax=lambda x: x.groupby("node_id").value_gwh.cummax())
    key = dict(zip(zip(cm.node_id, cm.period), cm.cmax))
    lim = np.array([key.get((n, o), np.nan) for n, o in zip(d.node_id, d.origin)])
    bad = (d.forecast > 5 * lim) & np.isfinite(lim) & (lim > 0)
    d["guard_flag"] = bad
    d.loc[bad, "forecast"] = np.nan
    d["group"] = d.node_id.map(g.group).fillna("")
    d["eligible"] = d.node_id.map(g.eligible_direct)
    d["level_cat"] = [level_cat(lv, n, gr, el) for lv, n, gr, el in zip(d.level, d.node_id, d.group, d.eligible == True)]  # noqa: E712
    return d


def coverage(d: pd.DataFrame, by):
    return d.groupby(by).forecast.apply(lambda x: x.notna().mean()).rename("coverage").reset_index()


def metrics(d: pd.DataFrame, by):
    ok = d[d.forecast.notna()]
    m = summarise(ok, by)
    c = coverage(d, by)
    return m.merge(c, on=by)


def select(d: pd.DataFrame, exp: str) -> pd.DataFrame:
    """Per level_cat selection on experiment `exp`."""
    x = d[d.experiment == exp]
    m = metrics(x, ["level_cat", "model"])
    rows = []
    for lc, g in m.groupby("level_cat"):
        g = g[g.coverage >= 0.95].copy()
        g["simp"] = g.model.map({k: i for i, k in enumerate(SIMPLICITY)})
        g = g.sort_values(["MASE", "WAPE_%", "simp"])
        best = g.iloc[0]
        close = g[(g.MASE - best.MASE).abs() <= 0.01].sort_values(["WAPE_%", "simp"])
        best = close.iloc[0]
        sn = g[g.model == "snaive"].iloc[0] if (g.model == "snaive").any() else None
        bb = g[g.model.isin(BASELINES)].sort_values("MASE").iloc[0]
        chosen = best.model if sn is None or best.MASE < sn.MASE else "snaive"
        rows.append({"level_cat": lc, "selected_model": chosen, "description": DESCRIPTION[chosen],
                     "MASE": best.MASE if chosen == best.model else sn.MASE, "WAPE_%": best["WAPE_%"] if chosen == best.model else sn["WAPE_%"],
                     "best_baseline": bb.model, "baseline_MASE": bb.MASE, "baseline_WAPE_%": bb["WAPE_%"],
                     "snaive_MASE": sn.MASE if sn is not None else np.nan,
                     "improvement_vs_best_baseline_%": 100 * (1 - (best.MASE / bb.MASE)) if chosen == best.model else 0.0,
                     "runner_up": g[g.model != chosen].iloc[0].model if len(g) > 1 else ""})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    d = load()
    for e in sorted(d.experiment.unique()):
        print(e)
        print(select(d, e).round(3).to_string())
