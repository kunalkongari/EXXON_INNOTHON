"""
final_forecast.py  (statistical forecast, Phase 3H/3I)
------------------------------------------------------
Refits the selected model per level on all main data up to 2026-09 and forecasts 18 months
(Oct-2026..Mar-2028 -> completes FY2026-27 and FY2027-28). Horizons 13-18 are BEYOND the
validated 12-month backtest horizon and are flagged.
Reconciles with the selected method, splits national coal/lignite, and attaches empirical
prediction intervals from the reconciled backtest errors (pooled by horizon band and level).
Group B intervals are widened by factor 1.25 (approved decision: wider intervals for group B).

Outputs: outputs/forecasts/monthly_forecast.csv, fy_forecast.csv, outputs/models/final_model_specs.json,
         outputs/models/ml_final_<model>.joblib (if an ML model is selected)
"""
from __future__ import annotations

import argparse
import json

import joblib
import numpy as np
import pandas as pd

from common import BT, CONFIG, FC, MODELS, load_panel, series_dict
from evaluate import level_cat
from hierarchy import all_methods, build_base, split_coal_lignite, structure
from models import ML_MODELS, REGRESSOR_MODELS, forecast, ml_forecast, select_order

H = 18
BANDS = [(1, 3), (4, 6), (7, 9), (10, 12)]
B_WIDEN = 1.25


def interval_table(exp: str, method: str) -> pd.DataFrame:
    d = pd.read_csv(BT / f"hier_forecasts_{exp}.csv")
    d = d[(d.method == method) & d.forecast.notna() & (d.scale > 0)].copy()
    d["lr"] = (d.actual - d.forecast) / d.scale  # scale-normalised error (same scaling as MASE; robust to zeros)
    rows = []
    for lc, g in d.groupby("level_cat"):
        for lo, hi in BANDS:
            x = g[(g.h >= lo) & (g.h <= hi)].lr
            if len(x) < 8:
                continue
            rows.append({"level_cat": lc, "h_lo": lo, "h_hi": hi, "n": len(x),
                         "q025": x.quantile(0.025), "q10": x.quantile(0.10), "q50": x.quantile(0.5),
                         "q90": x.quantile(0.90), "q975": x.quantile(0.975)})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", default="A")
    ap.add_argument("--method", required=True, help="selected reconciliation method")
    a = ap.parse_args()
    start = CONFIG["experiment_B_start"] if a.exp == "B" else CONFIG["main_data_start"]
    covid = CONFIG["covid_months"] if a.exp == "A" else None
    sel = pd.read_csv(MODELS / f"selected_models_{a.exp}.csv")
    pick = dict(zip(sel.level_cat, sel.selected_model))
    runner = dict(zip(sel.level_cat, sel.runner_up))
    rows, cells, S, meta = structure()
    m = meta.set_index("node_id")
    panel = load_panel()
    series = series_dict(panel)
    levels = panel.groupby("node_id")["level"].first().to_dict()
    origin = CONFIG["main_data_end"]
    op = pd.Period(origin, freq="M")
    s0 = pd.Period(start, freq="M")
    direct = ["TOTAL"] + [r for r in rows if r.startswith(("REG|", "NSRC|"))] + ["NSRC|COAL", "NSRC|LIGNITE"] + \
             [s for s in m.index if s.startswith("ST|") and m.group[s] in ("A", "B")] + \
             [c for c in cells if m.eligible_direct.get(c) == True] + ["IMPORT|BHUTAN"]  # noqa: E712
    specs, fc = {}, {}
    ml_cache = {}
    for nid in direct:
        lc = level_cat("", nid, m.group.get(nid, ""), m.eligible_direct.get(nid) == True)  # noqa: E712
        mdl = pick[lc]
        y = series[nid][(series[nid].index >= s0) & (series[nid].index <= op)]
        if mdl in ML_MODELS:
            if mdl not in ml_cache:
                params = CONFIG["rf_params"] if mdl == "rf" else CONFIG["xgb_params"]
                preds, model_obj, cols = ml_forecast(series, levels, origin, mdl, covid, start, params, 12, CONFIG["seed"])
                joblib.dump({"model": model_obj, "features": cols, "origin": origin}, MODELS / f"ml_final_{mdl}.joblib")
                ml_cache[mdl] = preds
            f12 = ml_cache[mdl][nid]
            alt = runner[lc] if runner[lc] not in ML_MODELS else "ets_auto"
            spec = select_order(y, alt, covid if alt in REGRESSOR_MODELS else None) if alt in ("arima", "sarima") else None
            f_alt = forecast(alt, y, H, covid=covid if alt in REGRESSOR_MODELS else None, spec=spec)
            f = np.concatenate([f12, f_alt[12:]])
            specs[nid] = {"level_cat": lc, "model": mdl, "h13_18_model": alt, "spec": str(spec)}
        else:
            spec = select_order(y, mdl, covid if mdl in REGRESSOR_MODELS else None) if mdl in ("arima", "sarima") else None
            f = forecast(mdl, y, H, covid=covid if mdl in REGRESSOR_MODELS else None, spec=spec)
            specs[nid] = {"level_cat": lc, "model": mdl, "spec": str(spec), "train": f"{y.index.min()}..{y.index.max()}"}
        fc[nid] = f
    Y = build_base({k: v for k, v in fc.items() if k in rows}, series, rows, cells, meta, origin, H)
    from common import seasonal_naive_scale
    scales = np.array([seasonal_naive_scale(series[r].values) if r in series else np.nan for r in rows])
    R = all_methods(Y, rows, cells, S, series, origin, H, scales)[a.method]
    # unreconciled base forecasts (comparison only; the official hierarchy is the reconciled one)
    tps0 = [str(op + k) for k in range(1, H + 1)]
    base_rows = []
    for i, r in enumerate(rows):
        for k in range(H):
            base_rows.append({"node_id": r, "period": tps0[k], "h": k + 1, "base_forecast_gwh": Y[i, k],
                              "base_source": "direct model" if r in fc else "allocation (seasonal proportion)"})
    for nid in ("NSRC|COAL", "NSRC|LIGNITE", "IMPORT|BHUTAN"):
        for k in range(H):
            base_rows.append({"node_id": nid, "period": tps0[k], "h": k + 1, "base_forecast_gwh": fc[nid][k], "base_source": "direct model"})
    pd.DataFrame(base_rows).to_csv(FC / "base_forecast_unreconciled.csv", index=False)
    idx = {r: i for i, r in enumerate(rows)}
    coal, lig = split_coal_lignite(R[idx["NSRC|COAL_LIGNITE"]], fc["NSRC|COAL"], fc["NSRC|LIGNITE"])
    final = {r: R[idx[r]] for r in rows}
    final["NSRC|COAL"], final["NSRC|LIGNITE"] = coal, lig
    final["IMPORT|BHUTAN"] = fc["IMPORT|BHUTAN"]  # separate, not reconciled into domestic
    it = interval_table(a.exp, a.method)
    node_scale = {nid: seasonal_naive_scale(series[nid].values) for nid in final if nid in series}
    # Bhutan import is outside the hierarchy: intervals from its own backtest errors (selected model)
    bi = pd.read_csv(BT / f"forecasts_{a.exp}.csv")
    bi = bi[(bi.node_id == "IMPORT|BHUTAN") & (bi.model == pick["Bhutan import (separate)"]) & bi.forecast.notna() & (bi.scale > 0)]
    bi = bi.assign(lr=(bi.actual - bi.forecast) / bi.scale)
    extra = []
    for lo, hi in BANDS:
        x = bi[(bi.h >= lo) & (bi.h <= hi)].lr
        if len(x) >= 8:
            extra.append({"level_cat": "Bhutan import (separate)", "h_lo": lo, "h_hi": hi, "n": len(x), "q025": x.quantile(0.025),
                          "q10": x.quantile(0.1), "q50": x.quantile(0.5), "q90": x.quantile(0.9), "q975": x.quantile(0.975)})
    it = pd.concat([it, pd.DataFrame(extra)], ignore_index=True)
    out = []
    tps = [op + k for k in range(1, H + 1)]
    for nid, f in final.items():
        g = m.group.get(nid, "")
        lc = level_cat("", nid, g, m.eligible_direct.get(nid) == True)  # noqa: E712
        if nid in ("NSRC|COAL", "NSRC|LIGNITE"):
            lc = "National coal/lignite split"
        if nid == "IMPORT|BHUTAN":
            lc = "Bhutan import (separate)"
        q = it[it.level_cat == lc]
        if q.empty:
            q = it[it.level_cat == "State x source (ineligible)"] if nid.startswith("CELL|") else it[it.level_cat == "National"]
        for k in range(H):
            h = k + 1
            hb = min(h, 12)
            row = q[(q.h_lo <= hb) & (q.h_hi >= hb)]
            widen = np.sqrt(h / 12) if h > 12 else 1.0
            widen *= B_WIDEN if g == "B" and nid.startswith(("ST|", "CELL|")) else 1.0
            rec = {"node_id": nid, "level_cat": lc, "group": g, "period": str(tps[k]), "h": h, "forecast_gwh": f[k],
                   "beyond_validated_horizon": h > 12}
            if len(row):
                r = row.iloc[0]
                sc = node_scale.get(nid, np.nan)
                for nm, col in [("lo95", "q025"), ("lo80", "q10"), ("hi80", "q90"), ("hi95", "q975")]:
                    rec[nm] = max(f[k] + r[col] * widen * sc, 0.0)
            out.append(rec)
    mf = pd.DataFrame(out)
    mf["model"] = mf.node_id.map(lambda n: specs.get(n, {}).get("model", "allocation (seasonal proportion)"))
    mf["series_type"] = "statistical forecast"
    mf.to_csv(FC / "monthly_forecast.csv", index=False)
    it.to_csv(FC / "interval_quantiles.csv", index=False)
    # FY totals: FY2026-27 = actual Apr-Sep 2026 + forecast Oct-Mar; FY2027-28 = forecast
    fy = []
    for nid, g in mf.groupby("node_id"):
        s = series.get(nid)
        for fy_start in (2026, 2027):
            months = [pd.Period(f"{fy_start}-04", freq="M") + k for k in range(12)]
            act = sum(s.get(p, 0) for p in months if s is not None and p <= op)
            gg = g[g.period.isin([str(p) for p in months])]
            row = {"node_id": nid, "level_cat": g.level_cat.iloc[0], "fy": f"FY{fy_start}-{str(fy_start + 1)[2:]}",
                   "actual_months": sum(p <= op for p in months), "actual_part_gwh": act,
                   "forecast_part_gwh": gg.forecast_gwh.sum(), "fy_total_gwh": act + gg.forecast_gwh.sum()}
            for b in ("lo80", "hi80", "lo95", "hi95"):
                if b in gg:
                    row[f"fy_{b}"] = act + gg[b].sum()  # comonotonic (conservative) aggregation
            row["includes_beyond_validated_horizon"] = bool(gg.beyond_validated_horizon.any())
            fy.append(row)
    pd.DataFrame(fy).to_csv(FC / "fy_forecast.csv", index=False)
    (MODELS / "final_model_specs.json").write_text(json.dumps({"experiment": a.exp, "reconciliation": a.method, "origin": origin,
                                                               "horizon": H, "nodes": specs}, indent=1), encoding="utf-8")
    t = pd.DataFrame(fy)
    print(t[t.node_id.isin(["TOTAL", "IMPORT|BHUTAN"]) | t.node_id.str.startswith("REG|")].round(0).to_string())


if __name__ == "__main__":
    main()
