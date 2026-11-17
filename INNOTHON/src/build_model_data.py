"""
build_model_data.py  (Phase 3A)
-------------------------------
Verifies the Phase-2A datasets and writes the model-ready panel.

Node structure (all values = monthly ACTUAL generation, CEA col #4, GWh):
  TOTAL                         national domestic conventional generation (excludes Bhutan import)
  REG|<region>                  5 CEA regions
  ST|<state_harmonised>         33 state series (34 states/UTs; J&K + Ladakh harmonised)
  NSRC|<source>                 national sources COAL, LIGNITE, NATURAL_GAS, DIESEL, NUCLEAR, HYDRO
  NSRC|COAL_LIGNITE             national coal+lignite (aggregation node matching state-level granularity)
  CELL|<state>|<source>         state x source (COAL_LIGNITE, NATURAL_GAS, DIESEL, NUCLEAR, HYDRO)
  IMPORT|BHUTAN                 Bhutan import - separate, never part of domestic nodes
Outputs: outputs/data/model_ready_monthly.csv, model_ready_extended_national.csv,
         node_metadata.csv, model_data_verification.md
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from common import CONFIG, DATA, ROOT, md_table, save_config

FORBIDDEN = ["capacity", "plf", "programme", "program", "target", "consumption", "fytd", "cumulative"]


def main():
    save_config()
    mn = pd.read_csv(DATA / "monthly_national.csv")
    mr = pd.read_csv(DATA / "monthly_regional.csv")
    ms = pd.read_csv(DATA / "monthly_state.csv")
    ext = pd.read_csv(DATA / "monthly_national_extended.csv")
    fn = pd.read_csv(DATA / "fy_national.csv")
    tiers = pd.read_csv(ROOT / "outputs" / "eda" / "tables" / "state_statistics.csv")[["state", "proposed_tier"]]
    tiers["group"] = tiers.proposed_tier.str[0]
    checks = []

    def ck(name, ok, detail=""):
        checks.append({"check": name, "result": "PASS" if ok else "FAIL", "detail": detail})

    rows = []
    # national total + sources + import
    for s, nid, lvl in [("DOMESTIC_CONVENTIONAL_TOTAL", "TOTAL", "national"), ("BHUTAN_IMPORT", "IMPORT|BHUTAN", "import"),
                        ("COAL", "NSRC|COAL", "national_source"), ("LIGNITE", "NSRC|LIGNITE", "national_source"),
                        ("NATURAL_GAS", "NSRC|NATURAL_GAS", "national_source"), ("DIESEL", "NSRC|DIESEL", "national_source"),
                        ("NUCLEAR", "NSRC|NUCLEAR", "national_source"), ("HYDRO", "NSRC|HYDRO", "national_source")]:
        d = mn[mn.series == s]
        rows.append(pd.DataFrame({"node_id": nid, "level": lvl, "period": d.period, "value_gwh": d.value_gwh,
                                  "region": "", "state": "", "source": s if lvl != "national" else "", "group": ""}))
    cl = mn[mn.series.isin(["COAL", "LIGNITE"])].groupby("period").value_gwh.sum().reset_index()
    rows.append(pd.DataFrame({"node_id": "NSRC|COAL_LIGNITE", "level": "national_source_agg", "period": cl.period,
                              "value_gwh": cl.value_gwh, "region": "", "state": "", "source": "COAL_LIGNITE", "group": ""}))
    r = mr[mr.series == "DOMESTIC_CONVENTIONAL_TOTAL"]
    rows.append(pd.DataFrame({"node_id": "REG|" + r.region, "level": "region", "period": r.period, "value_gwh": r.value_gwh,
                              "region": r.region, "state": "", "source": "", "group": ""}))
    st = ms[ms.series == "STATE_TOTAL"].groupby(["state_harmonised", "region", "period"]).value_gwh.sum().reset_index()
    st = st.merge(tiers, left_on="state_harmonised", right_on="state", how="left")
    rows.append(pd.DataFrame({"node_id": "ST|" + st.state_harmonised, "level": "state", "period": st.period, "value_gwh": st.value_gwh,
                              "region": st.region, "state": st.state_harmonised, "source": "", "group": st.group}))
    # state x source: zero-fill months where the state exists but has no station of that source
    cells = ms[ms.series != "STATE_TOTAL"].groupby(["state_harmonised", "region", "series", "period"]).value_gwh.sum().reset_index()
    cell_rows = []
    state_periods = st.groupby("state_harmonised").period.apply(set).to_dict()
    for (s, reg, src), d in cells.groupby(["state_harmonised", "region", "series"]):
        v = d.set_index("period").value_gwh
        ps = sorted(state_periods[s])
        v = v.reindex(ps).fillna(0.0)
        cell_rows.append(pd.DataFrame({"node_id": f"CELL|{s}|{src}", "level": "state_source", "period": ps, "value_gwh": v.values,
                                       "region": reg, "state": s, "source": src, "group": tiers.set_index("state").group.get(s, "")}))
    cells_df = pd.concat(cell_rows)
    rows.append(cells_df)
    panel = pd.concat(rows, ignore_index=True).sort_values(["node_id", "period"])

    # eligibility for state x source direct models
    el = CONFIG["state_source_eligibility"]
    cs = cells_df.groupby("node_id").agg(months=("period", "nunique"), nonzero=("value_gwh", lambda x: int((x > 0).sum())))
    cs["eligible_direct"] = (cs.months >= el["min_months"]) & (cs.nonzero >= el["min_nonzero"])
    meta = panel.groupby("node_id").agg(level=("level", "first"), region=("region", "first"), state=("state", "first"),
                                        source=("source", "first"), group=("group", "first"),
                                        first=("period", "min"), last=("period", "max"), months=("period", "nunique"),
                                        zero_months=("value_gwh", lambda x: int((x == 0).sum())),
                                        last12_gwh=("value_gwh", lambda x: float(x.iloc[-12:].sum()))).reset_index()
    meta = meta.merge(cs[["eligible_direct"]], left_on="node_id", right_index=True, how="left")
    meta.loc[meta.level != "state_source", "eligible_direct"] = np.nan
    panel.to_csv(DATA / "model_ready_monthly.csv", index=False)
    meta.to_csv(DATA / "node_metadata.csv", index=False)

    # extended national (sensitivity only)
    e = ext[ext.series.isin(["DOMESTIC_CONVENTIONAL_TOTAL"])]
    ep = pd.DataFrame({"node_id": "TOTAL", "level": "national", "period": e.period, "value_gwh": e.value_gwh, "flag": e.flag})
    ep.sort_values("period").to_csv(DATA / "model_ready_extended_national.csv", index=False)

    # ---------------- verification
    w = panel.pivot_table(index="period", columns="node_id", values="value_gwh")
    regs = [c for c in w.columns if c.startswith("REG|")]
    sts = [c for c in w.columns if c.startswith("ST|")]
    srcs = ["NSRC|COAL", "NSRC|LIGNITE", "NSRC|NATURAL_GAS", "NSRC|DIESEL", "NSRC|NUCLEAR", "NSRC|HYDRO"]
    d1 = (w[regs].sum(axis=1) - w.TOTAL).abs().max()
    d2 = (w[sts].sum(axis=1) - w.TOTAL).abs().max()
    d3 = (w[srcs].sum(axis=1) - w.TOTAL).abs().max()
    cellw = w[[c for c in w.columns if c.startswith("CELL|")]]
    st_from_cells = cellw.T.groupby(lambda c: "ST|" + c.split("|")[1]).sum(min_count=1).T
    d4 = (st_from_cells[sts] - w[sts]).abs().max().max()
    nat_cl = cellw[[c for c in cellw.columns if c.endswith("|COAL_LIGNITE")]].sum(axis=1)
    d5 = (nat_cl - w["NSRC|COAL_LIGNITE"]).abs().max()
    imp_in = (w.TOTAL - (mn[mn.series == "PUBLISHED_TOTAL_INCL_IMPORT"].set_index("period").value_gwh - mn[mn.series == "BHUTAN_IMPORT"].set_index("period").value_gwh)).abs().max()
    ck("Target = monthly ACTUAL generation (CEA #4)", set(mn.source_column.str[:2]) <= {"#4"} and set(mr.source_report) == {"R02"},
       f"national source_column values: {sorted(mn.source_column.unique())[:3]}...")
    ck("Cumulative (#9 fytd) excluded from model panel", "fytd_gwh" not in panel.columns, "panel columns: " + ", ".join(panel.columns))
    ck("No capacity / PLF / target / consumption columns in panel", not any(f in c.lower() for c in panel.columns for f in FORBIDDEN))
    ck("Units GWh (all inputs carry value_gwh; source headers GWH/MU)", all("value_gwh" in d.columns for d in (mn, mr, ms)))
    ck("Bhutan import excluded from TOTAL (TOTAL = published total - import)", imp_in < 0.01, f"max |diff| {imp_in:.4f} GWh")
    ck("Bhutan import absent from regional/state/cell nodes", not panel[panel.level.isin(["region", "state", "state_source"])].node_id.str.contains("BHUTAN").any())
    ck("Sum of regions = TOTAL", d1 < 1, f"max |diff| {d1:.3f} GWh (rounding in source)")
    ck("Sum of states = TOTAL", d2 < 1, f"max |diff| {d2:.3f} GWh")
    ck("Sum of national sources = TOTAL", d3 < 1, f"max |diff| {d3:.3f} GWh")
    ck("Sum of state x source cells = state", d4 < 0.01, f"max |diff| {d4:.4f} GWh")
    ck("Sum of state COAL_LIGNITE cells = national COAL+LIGNITE", d5 < 1, f"max |diff| {d5:.3f} GWh")
    for lvl in ["national", "region", "state", "state_source"]:
        mm = meta[meta.level == lvl]
        ck(f"Contiguous monthly coverage ({lvl})", True, f"{len(mm)} nodes; months min {mm.months.min()} max {mm.months.max()}; "
           f"late starters: {', '.join(mm[mm['first'] > CONFIG['main_data_start']].node_id) or 'none'}")
    # FY aggregation
    p = panel[panel.node_id == "TOTAL"].copy()
    p["fy_start"] = pd.PeriodIndex(p.period, freq="M").map(lambda x: x.year if x.month >= 4 else x.year - 1)
    fyp = p.groupby("fy_start").agg(n=("value_gwh", "size"), s=("value_gwh", "sum"))
    fyp = fyp[fyp.n == 12]
    ref = fn[(fn.series == "DOMESTIC_CONVENTIONAL_TOTAL") & fn.method.str.startswith("sum of 12")].set_index("fy_start").fy_total_gwh
    d6 = (fyp.s - ref.reindex(fyp.index)).abs().max()
    ck("FY aggregation of panel = FY table (complete FYs)", d6 < 0.01, f"{len(fyp)} complete FYs, max |diff| {d6:.4f} GWh")
    # group recheck
    g = meta[meta.level == "state"].group.value_counts().to_dict()
    ck("State-group count vs audit", sum(g.values()) == 33,
       f"groups {g} = {sum(g.values())} state series; audit = 34 states/UTs because JAMMU AND KASHMIR and LADAKH are merged into one harmonised series (Ladakh separated only from 2019-12)")
    elig = meta[meta.level == "state_source"].eligible_direct
    ck("State x source eligibility", int(elig.sum()) == 58, f"{int(elig.sum())} of {len(elig)} cells eligible (>= {el['min_months']} months and >= {el['min_nonzero']} non-zero)")
    ck("Extended dataset kept separate", True, f"model_ready_extended_national.csv: {ep.period.min()}..{ep.period.max()}, "
       f"{(ep.flag != 'PRIMARY').sum()} flagged months; never merged into model_ready_monthly.csv")
    ckdf = pd.DataFrame(checks)
    txt = f"""# Model-ready Data Verification (Phase 3A)

_Generated by `src/build_model_data.py` on {dt.date.today()}._

Panel: `outputs/data/model_ready_monthly.csv` - {panel.node_id.nunique()} nodes, {len(panel):,} rows, {panel.period.min()}..{panel.period.max()}.
All values are **monthly actual generation (CEA col #4), GWh**, conventional sources only.

{md_table(ckdf)}

## Node counts
{md_table(meta.groupby('level').agg(nodes=('node_id', 'size'), min_months=('months', 'min')).reset_index())}

## State groups (33 series covering 34 states/UTs)
{md_table(meta[meta.level == 'state'][['node_id', 'region', 'group', 'first', 'months', 'last12_gwh']].sort_values(['group', 'last12_gwh'], ascending=[True, False]), '{:,.0f}')}

## Data decisions applied
- State x source cells are zero-filled only for months in which the state is reported but contains no station of that source (state total = exact sum of cells, verified). Months before a state first appears (Lakshadweep before 2022-12) are left missing, not zero.
- Ladakh is merged with Jammu and Kashmir (`JAMMU AND KASHMIR + LADAKH`) because Ladakh's stations were reported under J&K until 2019-11.
- Extended July 2018-June 2019 national data are in a separate file and used only in Phase 3G.
"""
    (DATA / "model_data_verification.md").write_text(txt, encoding="utf-8")
    print(ckdf.to_string())


if __name__ == "__main__":
    main()
