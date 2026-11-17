"""
backtest.py  (Phases 3B-3G)
---------------------------
Rolling-origin, expanding-window backtest. For every origin the model sees only data
up to and including the origin month and forecasts h = 1..12 months ahead.

Experiments
  A    full history (2019-07..origin) + COVID intervention regressor (regressor-capable models / ML features)
  B    training from FY2021-22 (2021-04..origin), no COVID months in sample
  C    full history, no intervention (benchmark)
  EXT  national TOTAL only, extended history 2018-07..origin (+ COVID regressor) - sensitivity, Phase 3G

Usage: python backtest.py --exp A [--levels monthly quarterly] [--models ...] [--jobs 8]
Output: outputs/backtesting/forecasts_<exp>.csv, outputs/models/orders_<exp>.csv
"""
from __future__ import annotations

import argparse
import time

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

from common import BT, CONFIG, MODELS, add_months, load_panel, origins, seasonal_naive_scale, series_dict
from models import ML_MODELS, REGRESSOR_MODELS, STAT_MODELS, forecast, ml_forecast, select_order

H = CONFIG["horizon_max"]
MONTHLY_PREFIX = ("TOTAL", "REG|", "NSRC|", "IMPORT|")
QUARTERLY_PREFIX = ("ST|", "CELL|")


def exp_settings(exp: str):
    if exp == "A":
        return CONFIG["main_data_start"], CONFIG["covid_months"]
    if exp == "B":
        return CONFIG["experiment_B_start"], None
    if exp == "C":
        return CONFIG["main_data_start"], None
    if exp == "EXT":
        return CONFIG["extended_data_start"], CONFIG["covid_months"]
    raise ValueError(exp)


def run_node(nid, s, level, origin_list, models, exp, start, covid, main_s):
    rows, orders = [], []
    s0 = pd.Period(start, freq="M")
    first_o = pd.Period(origin_list[0], freq="M")
    specs = {}
    for name in ("arima", "sarima"):
        if name in models:
            tr = s[(s.index >= s0) & (s.index <= first_o)]
            specs[name] = select_order(tr, name, covid) if len(tr) >= 30 else None
            orders.append({"experiment": exp, "node_id": nid, "model": name, "spec": str(specs[name]), "selected_on": f"{tr.index.min()}..{first_o}"})
    for o in origin_list:
        op = pd.Period(o, freq="M")
        tr = s[(s.index >= s0) & (s.index <= op)]
        if len(tr) < 25 or tr.index[-1] != op:
            continue
        scale = seasonal_naive_scale(main_s[main_s.index <= op].values)
        fut = [op + k for k in range(1, H + 1)]
        act = [s.get(p, np.nan) for p in fut]
        if all(np.isnan(act)):
            continue
        for name in models:
            cv = covid if name in REGRESSOR_MODELS else None
            f = forecast(name, tr, H, covid=cv, spec=specs.get(name))
            for k in range(H):
                if not np.isnan(act[k]):
                    rows.append((exp, name, nid, level, o, k + 1, str(fut[k]), act[k], f[k], scale))
    return rows, orders


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", required=True, choices=["A", "B", "C", "EXT"])
    ap.add_argument("--levels", nargs="+", default=["monthly", "quarterly"])
    ap.add_argument("--models", nargs="+", default=STAT_MODELS + ML_MODELS)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--nodes", nargs="*", default=None, help="restrict to node ids (testing)")
    ap.add_argument("--ml-origins", choices=["all", "quarterly"], default="all",
                    help="quarterly = ML refit only at the quarterly origins (compute saving for sensitivity runs)")
    ap.add_argument("--copy-nonregressor-from", default=None,
                    help="for exp C: models without regressors give identical results to exp A (same data, no exogenous input); "
                         "copy their rows from this experiment instead of recomputing")
    a = ap.parse_args()
    if a.copy_nonregressor_from:
        a.models = [m for m in a.models if m in REGRESSOR_MODELS or m in ML_MODELS]
    t0 = time.time()
    start, covid = exp_settings(a.exp)
    panel = load_panel(extended=(a.exp == "EXT"))
    if a.exp == "EXT":
        panel["level"] = "national"
        a.levels = ["monthly"]
    S = series_dict(panel)
    main_S = series_dict(load_panel()) if a.exp == "EXT" else S
    levels = panel.groupby("node_id")["level"].first().to_dict()
    om, oq = origins("monthly"), origins("quarterly")
    plan = []
    for nid in S:
        if a.nodes and nid not in a.nodes:
            continue
        if "monthly" in a.levels and nid.startswith(MONTHLY_PREFIX):
            plan.append((nid, om))
        elif "quarterly" in a.levels and nid.startswith(QUARTERLY_PREFIX):
            plan.append((nid, oq))
    stat = [m for m in a.models if m in STAT_MODELS]
    res = Parallel(n_jobs=a.jobs, verbose=0)(
        delayed(run_node)(nid, S[nid], levels[nid], ol, stat, a.exp, start, covid, main_S[nid]) for nid, ol in plan)
    rows = [r for rr, _ in res for r in rr]
    orders = [o for _, oo in res for o in oo]
    print(f"[{a.exp}] statistical models done: {len(plan)} nodes, {len(rows):,} rows, {time.time() - t0:.0f}s", flush=True)

    # ML: one global model per origin covering every node in the plan
    node_orig = {nid: set(ol) for nid, ol in plan}
    imp = []
    for name in [m for m in a.models if m in ML_MODELS]:
        params = CONFIG["rf_params"] if name == "rf" else CONFIG["xgb_params"]
        all_o = sorted(set().union(*node_orig.values())) if node_orig else []
        if a.ml_origins == "quarterly":
            all_o = [o for o in all_o if o in set(oq)]
        for o in all_o:
            sub = {nid: S[nid] for nid in node_orig}
            preds, mdl, cols = ml_forecast(sub, levels, o, name, covid, start, params, H, CONFIG["seed"])
            op = pd.Period(o, freq="M")
            for nid, f in preds.items():
                if o not in node_orig[nid]:
                    continue
                s = S[nid]
                scale = seasonal_naive_scale(main_S[nid][main_S[nid].index <= op].values)
                for k in range(H):
                    tp = op + k + 1
                    if tp in s.index:
                        rows.append((a.exp, name, nid, levels[nid], o, k + 1, str(tp), s[tp], f[k], scale))
            if mdl is not None and o == all_o[-1]:
                fi = getattr(mdl, "feature_importances_", None)
                if fi is not None:
                    imp += [{"experiment": a.exp, "model": name, "origin": o, "feature": c, "importance": float(v)} for c, v in zip(cols, fi)]
        print(f"[{a.exp}] {name} done, {time.time() - t0:.0f}s", flush=True)

    df = pd.DataFrame(rows, columns=["experiment", "model", "node_id", "level", "origin", "h", "target", "actual", "forecast", "scale"])
    if a.copy_nonregressor_from:
        src = pd.read_csv(BT / f"forecasts_{a.copy_nonregressor_from}.csv")
        src = src[~src.model.isin(list(REGRESSOR_MODELS) + ML_MODELS)].assign(experiment=a.exp)
        df = pd.concat([df, src], ignore_index=True)
        print(f"[{a.exp}] copied {len(src):,} non-regressor rows from {a.copy_nonregressor_from}")
    tag = a.exp + ("" if a.nodes is None else "_test")
    df.to_csv(BT / f"forecasts_{tag}.csv", index=False)
    if orders:
        pd.DataFrame(orders).to_csv(MODELS / f"orders_{tag}.csv", index=False)
    if imp:
        pd.DataFrame(imp).to_csv(MODELS / f"ml_feature_importance_{tag}.csv", index=False)
    print(f"[{a.exp}] wrote {len(df):,} rows in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
