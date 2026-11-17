"""
hier_backtest.py  (Phase 3H)
----------------------------
Backtests reconciliation methods at the common quarterly origins using the base forecasts of the
selected model per level (main experiment). Evaluates every method at every level and checks coherence.
Outputs: outputs/backtesting/hier_forecasts.csv, hier_metrics.csv, hier_coherence.csv
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from common import BT, CONFIG, MODELS, load_panel, origins, series_dict, summarise
from evaluate import level_cat, load, select
from hierarchy import AGG_SRC, METHODS, all_methods, build_base, split_coal_lignite, structure


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", default="A")
    a = ap.parse_args()
    d = load([a.exp])
    sel = select(d, a.exp)
    sel.to_csv(MODELS / f"selected_models_{a.exp}.csv", index=False)
    pick = dict(zip(sel.level_cat, sel.selected_model))
    rows, cells, S, meta = structure()
    m = meta.set_index("node_id")
    series = series_dict(load_panel())
    idx = {r: i for i, r in enumerate(rows)}
    d = d[d.forecast.notna() | d.model.isin(pick.values())]
    out, coh = [], []
    for o in origins("quarterly"):
        x = d[d.origin == o]
        fc, scl = {}, {}
        for nid, g in x.groupby("node_id"):
            lc = g.level_cat.iloc[0]
            mdl = pick.get(lc)
            gg = g[g.model == mdl].sort_values("h")
            if len(gg):
                fc[nid] = gg.forecast.values
                scl[nid] = gg.scale.iloc[0]
        hs = x[x.node_id == "TOTAL"].h.nunique()
        if hs == 0:
            continue
        fc = {k: v[:hs] for k, v in fc.items() if len(v) >= hs}
        need = ["TOTAL"] + [r for r in rows if r.startswith(("REG|", "NSRC|"))] + [s for s in m.index if s.startswith("ST|") and m.group[s] in ("A", "B")]
        if any(n not in fc for n in need):
            print("missing base forecasts at", o, [n for n in need if n not in fc][:5])
            continue
        Y = build_base(fc, series, rows, cells, meta, o, hs)
        scales = np.array([scl.get(r, np.nan) for r in rows])
        res = all_methods(Y, rows, cells, S, series, o, hs, scales)
        op = pd.Period(o, freq="M")
        for mth, R in res.items():
            # national coal / lignite split (national granularity only)
            cl = R[idx["NSRC|COAL_LIGNITE"]]
            coal, lig = split_coal_lignite(cl, fc.get("NSRC|COAL", cl * 0.97), fc.get("NSRC|LIGNITE", cl * 0.03))
            extra = {"NSRC|COAL": coal, "NSRC|LIGNITE": lig}
            if mth != "BASE":
                bot = R[[idx[c] for c in cells]]
                agg = S @ bot
                coh.append({"origin": o, "method": mth, "max_abs_incoherence_gwh": float(np.nanmax(np.abs(agg - R)))})
            for nid in rows + list(extra):
                f = R[idx[nid]] if nid in idx else extra[nid]
                s = series.get(nid)
                if s is None:
                    continue
                sc = scl.get(nid, np.nan)
                for k in range(hs):
                    tp = op + k + 1
                    if tp in s.index:
                        out.append((mth, nid, o, k + 1, s[tp], f[k], sc))
    df = pd.DataFrame(out, columns=["method", "node_id", "origin", "h", "actual", "forecast", "scale"])
    df["group"] = df.node_id.map(m.group).fillna("")
    df["level_cat"] = [level_cat("", n, g, m.eligible_direct.get(n) == True) for n, g in zip(df.node_id, df.group)]  # noqa: E712
    df.loc[df.node_id.isin(["NSRC|COAL", "NSRC|LIGNITE"]), "level_cat"] = "National coal/lignite split"
    df.to_csv(BT / f"hier_forecasts_{a.exp}.csv", index=False)
    met = summarise(df[df.forecast.notna()], ["level_cat", "method"])
    met.to_csv(BT / f"hier_metrics_{a.exp}.csv", index=False)
    pd.DataFrame(coh).to_csv(BT / f"hier_coherence_{a.exp}.csv", index=False)
    piv = met.pivot(index="level_cat", columns="method", values="MASE")[METHODS]
    print(piv.round(3).to_string())
    print(pd.DataFrame(coh).groupby("method").max_abs_incoherence_gwh.max())


if __name__ == "__main__":
    main()
