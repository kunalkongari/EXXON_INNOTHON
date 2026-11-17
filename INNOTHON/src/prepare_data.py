"""
prepare_data.py  (Phase 2A)
---------------------------
Builds the forecasting datasets from the audited, parsed CEA tables in
data/processed/ (which are themselves read-only parses of data/raw/).

Rules enforced
  * Target variable = ACTUAL generation only (CEA col #4 monthly; #9 April-to-date
    cumulative used only for FY totals / validation). Capacity, PLF and targets dropped.
  * Cumulative values are never summed across months.
  * Bhutan import kept as a separate series; never part of domestic generation.
  * All values in GWh (1 GWh = 1 MU). No imputation, no synthetic history.
  * "Conventional" everywhere: these series exclude solar, wind, small hydro, biomass.

Outputs (outputs/data/)
  monthly_national.csv            national, by category and by source (primary, 2019-07..)
  monthly_national_extended.csv   adds 2018-07..2019-06 from published 'same month last year' (#5) - FLAGGED
  monthly_regional.csv            5 regions x THERMAL/NUCLEAR/HYDRO + domestic total
  monthly_state.csv               state x source (from station rows) + state total
  fy_national.csv, fy_regional.csv, fy_state.csv   financial-year totals with method flags
  validation_checks.csv           identity / reconciliation checks run during preparation
  data_preparation_log.md         decisions, exclusions, check results
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
OUT = ROOT / "outputs" / "data"
G, Y, G_LY, Y_LY = "gen_actual_month_gwh", "gen_actual_fytd_gwh", "gen_actual_same_month_prev_year_gwh", "gen_actual_fytd_prev_year_gwh"
TOL_GWH = 1.0  # rounding tolerance for identity checks

STATE_CANON = {  # recorded mapping decisions (raw labels untouched)
    "ANDHRA PRADESH.": "ANDHRA PRADESH",      # trailing-dot spelling variant 2019-07..2019-11
    "CHHATISGARH": "CHHATTISGARH",            # spelling variant (NPP spelling)
    "ANDAMAN & NICOBAR ISLANDS": "ANDAMAN AND NICOBAR ISLANDS",
}
# continuity group: Ladakh split from J&K (UT from 31-Oct-2019; separate in reports from 2019-12)
HARMONISED = {"JAMMU AND KASHMIR": "JAMMU AND KASHMIR + LADAKH", "LADAKH": "JAMMU AND KASHMIR + LADAKH"}
REGION_CANON = {"NORTHERN": "Northern", "WESTERN": "Western", "SOUTHERN": "Southern", "EASTERN": "Eastern", "NORTH EASTERN": "North Eastern"}
STATION_SOURCE = {"COAL": "COAL_LIGNITE", "LIGNITE": "COAL_LIGNITE", "NATURAL GAS": "NATURAL_GAS",
                  "DIESEL": "DIESEL", "NUCLEAR": "NUCLEAR", "HYDRO": "HYDRO"}

checks: list[dict] = []


def check(name, left, right, detail=""):
    d = (left - right).abs()
    checks.append({"check": name, "n": int(d.notna().sum()), "max_abs_diff_gwh": float(d.max()) if len(d) else np.nan,
                   "pass": bool((d.dropna() <= TOL_GWH).all()), "detail": detail})


def fy_cols(df: pd.DataFrame) -> pd.DataFrame:
    p = pd.PeriodIndex(df["period"], freq="M")
    start = np.where(p.month >= 4, p.year, p.year - 1)
    df = df.copy()
    df["year"], df["month"] = p.year, p.month
    df["fy_start"] = start
    df["fy"] = [f"FY{s}-{str(s + 1)[2:]}" for s in start]
    df["fy_month_no"] = ((p.month - 4) % 12) + 1  # Apr=1 .. Mar=12
    return df


def region_key(s: pd.Series) -> pd.Series:
    k = s.str.upper().str.extract(r"^(NORTH\s*EASTERN|NORTHERN|WESTERN|SOUTHERN|EASTERN)")[0].str.replace(r"\s+", " ", regex=True)
    return k.map(REGION_CANON)


def national(long: pd.DataFrame, nat: pd.DataFrame, stn: pd.DataFrame):
    rows = []
    cat_map = {"THERMAL": "THERMAL", "NUCLEAR": "NUCLEAR", "HYDRO": "HYDRO", "BHUTAN IMP": "BHUTAN_IMPORT", "TOTAL": "PUBLISHED_TOTAL_INCL_IMPORT"}
    n = nat[nat.category.isin(cat_map)].copy()
    n["series"] = n.category.map(cat_map)
    for _, r in n.iterrows():
        rows.append({"period": r.period, "series": r.series, "value_gwh": r[G], "fytd_gwh": r[Y],
                     "source_report": "R01", "source_column": "#4 (#9 for fytd)"})
    w = n.pivot(index="period", columns="series", values=G)
    wy = n.pivot(index="period", columns="series", values=Y)
    dom = w[["THERMAL", "NUCLEAR", "HYDRO"]].sum(axis=1)
    domy = wy[["THERMAL", "NUCLEAR", "HYDRO"]].sum(axis=1)
    check("R01 TOTAL - BHUTAN = THERMAL+NUCLEAR+HYDRO", w.PUBLISHED_TOTAL_INCL_IMPORT - w.BHUTAN_IMPORT, dom)
    for p in w.index:
        rows.append({"period": p, "series": "DOMESTIC_CONVENTIONAL_TOTAL", "value_gwh": dom[p], "fytd_gwh": domy[p],
                     "source_report": "R01 (derived sum)", "source_column": "#4 THERMAL+NUCLEAR+HYDRO"})

    # sources within THERMAL
    def pick(no, pat):
        d = long[(long.report_no == no) & long.lab1.str.contains(pat, case=False, regex=True, na=False)]
        d = d.drop_duplicates(["period"], keep="first")  # labels such as 'TOTAL STATE SEC.' repeat; these patterns are unique
        return d.set_index("period")[["c4", "c9"]]
    coal, lig = pick(11, r"^TOTAL COAL BASED"), pick(11, r"^TOTAL LIGNITE BASED")
    st = stn.copy()
    st["source"] = st.fuel.map(STATION_SOURCE)
    gas = st[st.source == "NATURAL_GAS"].groupby("period")[[G, Y]].sum()
    dsl = st[st.source == "DIESEL"].groupby("period")[[G, Y]].sum()
    excl = pick(15, r"^TOTAL EXCL")
    check("R11 coal + R11 lignite + R16 gas + R16 diesel = R01 THERMAL",
          coal.c4 + lig.c4 + gas[G] + dsl[G], w.THERMAL)
    check("R16 gas + R16 diesel = R15 'TOTAL EXCL. COAL/LIGNITE'", gas[G] + dsl[G], excl.c4)
    for name, src, rep, col in [("COAL", coal.rename(columns={"c4": G, "c9": Y}), "R11", "TOTAL COAL BASED"),
                                ("LIGNITE", lig.rename(columns={"c4": G, "c9": Y}), "R11", "TOTAL LIGNITE BASED"),
                                ("NATURAL_GAS", gas, "R16", "sum of gas station rows"),
                                ("DIESEL", dsl, "R16", "sum of diesel station rows")]:
        for p, r in src.iterrows():
            rows.append({"period": p, "series": name, "value_gwh": r[G], "fytd_gwh": r[Y], "source_report": rep, "source_column": f"#4 ({col})"})
    out = fy_cols(pd.DataFrame(rows))
    out["scope"] = np.select([out.series == "BHUTAN_IMPORT", out.series == "PUBLISHED_TOTAL_INCL_IMPORT"],
                             ["import", "domestic+import (published total)"], "domestic")
    out["level"] = np.where(out.series.isin(["COAL", "LIGNITE", "NATURAL_GAS", "DIESEL"]), "source", "category")
    out = out.sort_values(["series", "period"])
    return out, n


def national_extended(n: pd.DataFrame):
    """Monthly 2018-07..2019-06 from '#5 same month last year' in files 2019-07..2020-06.
    Validated where it overlaps original #4 (files 2020-07 onward)."""
    keep = ["THERMAL", "NUCLEAR", "HYDRO", "BHUTAN_IMPORT", "PUBLISHED_TOTAL_INCL_IMPORT"]
    a = n[n.series.isin(keep)][["period", "series", G, G_LY]].copy()
    a["ref_period"] = (pd.PeriodIndex(a.period, freq="M") - 12).astype(str)
    prior = a[["ref_period", "series", G_LY]].rename(columns={"ref_period": "period", G_LY: "value_from_c5"})
    orig = a[["period", "series", G]]
    ov = orig.merge(prior, on=["period", "series"])
    pct = (100 * (ov.value_from_c5 - ov[G]) / ov[G].replace(0, np.nan)).abs()
    check("Overlap: #5 (published next year) vs original #4", ov[G], ov.value_from_c5,
          f"{len(ov)} overlapping series-months; max |diff| {pct.max():.2f}%, median {pct.median():.3f}%, "
          f"{(pct > 0.1).sum()} pairs >0.1% -> small restatements; extended rows therefore FLAGGED, not merged")
    first = orig.period.min()
    back = prior[prior.period < first].copy()
    back["value_gwh"] = back.value_from_c5
    back["source_column"] = "#5 same month previous year (from file 12 months later)"
    back["flag"] = "EXTENDED_FROM_PRIOR_YEAR_COLUMN"
    orig2 = orig.rename(columns={G: "value_gwh"})
    orig2["source_column"], orig2["flag"] = "#4", "PRIMARY"
    ext = pd.concat([back[["period", "series", "value_gwh", "source_column", "flag"]], orig2])
    w = ext.pivot(index="period", columns="series", values="value_gwh")
    dom = w[["THERMAL", "NUCLEAR", "HYDRO"]].sum(axis=1).rename("value_gwh").reset_index()
    dom["series"], dom["source_column"] = "DOMESTIC_CONVENTIONAL_TOTAL", "derived sum"
    dom["flag"] = np.where(dom.period < first, "EXTENDED_FROM_PRIOR_YEAR_COLUMN", "PRIMARY")
    ext = fy_cols(pd.concat([ext, dom])).sort_values(["series", "period"])
    return ext, len(ov), float((ov[G] - ov.value_from_c5).abs().max())


def regional(reg: pd.DataFrame):
    r = reg.copy()
    r["region"] = region_key(r.region)
    r = r.dropna(subset=["region"])
    r["category"] = r.category.str.upper()
    tot = r[r.category == "TOTAL"].set_index(["period", "region"])[G]
    r = r[r.category.isin(["THERMAL", "NUCLEAR", "HYDRO"])]
    s = r.groupby(["period", "region"])[G].sum()
    check("R02 regional TOTAL = THERMAL+NUCLEAR+HYDRO", tot, s)
    rows = r[["period", "region", "category", G, Y]].rename(columns={"category": "series", G: "value_gwh", Y: "fytd_gwh"})
    d = r.groupby(["period", "region"])[[G, Y]].sum().reset_index().rename(columns={G: "value_gwh", Y: "fytd_gwh"})
    d["series"] = "DOMESTIC_CONVENTIONAL_TOTAL"
    out = fy_cols(pd.concat([rows, d]))
    out["source_report"] = "R02"
    return out.sort_values(["region", "series", "period"])


def state(stn: pd.DataFrame, stt: pd.DataFrame, stf: pd.DataFrame):
    s = stn.copy()
    s["state"] = s.state.replace(STATE_CANON)
    s["source"] = s.fuel.map(STATION_SOURCE)
    unmapped = s[s.source.isna()]
    s["region"] = region_key(s.region)
    agg = s.groupby(["period", "region", "state", "source"])[[G, Y]].sum().reset_index()
    tt = stt.copy()
    tt["state"] = tt.state.replace(STATE_CANON)
    tt = tt[tt.get("note", pd.Series("", index=tt.index)).fillna("") == ""]
    tt_s = tt.groupby(["period", "state"])[[G, Y]].sum()
    st_s = agg.groupby(["period", "state"])[[G, Y]].sum()
    check("Sum of station rows by state = published state total (#4)", st_s[G], tt_s[G].reindex(st_s.index))
    check("Sum of station rows by state = published state total (#9 fytd)", st_s[Y], tt_s[Y].reindex(st_s.index),
          "differences mean stations listed during the year but dropped later, or vice versa")
    ff = stf.copy()
    ff["state"] = ff.state.replace(STATE_CANON)
    fg = ff.groupby(["period", "state", "fuel_group"])[G].sum().unstack()
    srcw = agg.pivot_table(index=["period", "state"], columns="source", values=G, aggfunc="sum").fillna(0)
    th_groups = srcw.get("COAL_LIGNITE", 0) + srcw.get("DIESEL", 0)
    check("State COAL_LIGNITE + DIESEL (stations) = R16 'THERMAL' group", th_groups, fg["THERMAL"].reindex(srcw.index).fillna(0))
    check("State NATURAL_GAS (stations) = R16 'NATURAL GAS' group", srcw.get("NATURAL_GAS", 0), fg["NATURAL GAS"].reindex(srcw.index).fillna(0))
    rows = agg.rename(columns={"source": "series", G: "value_gwh", Y: "fytd_gwh"})
    tot = tt.reset_index()[["period", "state", G, Y]] if False else tt[["period", "state", G, Y]].groupby(["period", "state"]).sum().reset_index()
    reg_of = agg.groupby("state").region.agg(lambda x: x.mode().iat[0])
    tot["region"] = tot.state.map(reg_of)
    tot = tot.rename(columns={G: "value_gwh", Y: "fytd_gwh"})
    tot["series"] = "STATE_TOTAL"
    out = fy_cols(pd.concat([rows, tot]))
    out["state_harmonised"] = out.state.replace(HARMONISED)
    out["source_report"] = np.where(out.series == "STATE_TOTAL", "R16 'TOTAL <STATE>' row", "R16 station rows")
    out = out.sort_values(["state", "series", "period"])
    return out, unmapped


def fy_tables(mon: pd.DataFrame, keys: list[str], label: str):
    """FY totals. Complete FYs (12 monthly files): sum of monthly #4, cross-checked with March #9.
    FY with missing months but a March file: published March #9 (full-year actual, flagged).
    FY without March (in progress): reported as partial (sum of available months), flagged."""
    g = mon.groupby(keys + ["fy", "fy_start"])
    out = g.agg(n_months=("value_gwh", "size"), sum_monthly_gwh=("value_gwh", "sum")).reset_index()
    mar = mon[mon.fy_month_no == 12][keys + ["fy", "fytd_gwh"]].rename(columns={"fytd_gwh": "march_cumulative_gwh"})
    out = out.merge(mar, on=keys + ["fy"], how="left")
    out["fy_total_gwh"] = np.where(out.n_months == 12, out.sum_monthly_gwh,
                                   np.where(out.march_cumulative_gwh.notna(), out.march_cumulative_gwh, np.nan))
    out["method"] = np.select(
        [out.n_months == 12, out.march_cumulative_gwh.notna()],
        ["sum of 12 monthly actuals (#4)", "published March April-to-date actual (#9); monthly files incomplete"],
        "PARTIAL FY - not a full-year total")
    out["partial_fy_sum_gwh"] = np.where(out.method.str.startswith("PARTIAL"), out.sum_monthly_gwh, np.nan)
    full = out[out.n_months == 12].dropna(subset=["march_cumulative_gwh"])
    if len(full):
        check(f"{label}: sum of 12 monthly = March cumulative (#9)", full.sum_monthly_gwh, full.march_cumulative_gwh,
              "difference = in-year revisions folded into cumulative")
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    long = pd.read_csv(PROC / "cea_rows_long.csv", low_memory=False)
    nat = pd.read_csv(PROC / "national_monthly.csv")
    reg = pd.read_csv(PROC / "region_monthly.csv")
    stn = pd.read_csv(PROC / "station_monthly.csv")
    stt = pd.read_csv(PROC / "state_total_monthly.csv")
    stf = pd.read_csv(PROC / "state_fuel_monthly.csv")

    mn, n_raw = national(long, nat, stn)
    mn.to_csv(OUT / "monthly_national.csv", index=False)
    n_raw2 = n_raw.rename(columns={})  # keep G/G_LY
    ext, n_ov, max_ov = national_extended(n_raw2.assign(series=n_raw2.series))
    ext.to_csv(OUT / "monthly_national_extended.csv", index=False)
    mr = regional(reg)
    mr.to_csv(OUT / "monthly_regional.csv", index=False)
    ms, unmapped = state(stn, stt, stf)
    ms.to_csv(OUT / "monthly_state.csv", index=False)
    # check regional = sum of states
    rs = ms[ms.series == "STATE_TOTAL"].groupby(["period", "region"]).value_gwh.sum()
    rr = mr[mr.series == "DOMESTIC_CONVENTIONAL_TOTAL"].set_index(["period", "region"]).value_gwh
    check("Sum of state totals = regional domestic total", rs, rr.reindex(rs.index))
    nn = mn[mn.series == "DOMESTIC_CONVENTIONAL_TOTAL"].set_index("period").value_gwh
    check("Sum of regions = national domestic total", mr[mr.series == "DOMESTIC_CONVENTIONAL_TOTAL"].groupby("period").value_gwh.sum(), nn)

    fn = fy_tables(mn, ["series", "scope", "level"], "national")
    # FY2018-19 from published 'same period last year' (#10) in the 2020-03 file - flagged
    m20 = n_raw[n_raw.period == "2020-03"]
    add = []
    for _, r in m20.iterrows():
        add.append({"series": r.series, "scope": "import" if r.series == "BHUTAN_IMPORT" else ("domestic+import (published total)" if r.series.startswith("PUBLISHED") else "domestic"),
                    "level": "category", "fy": "FY2018-19", "fy_start": 2018, "n_months": 0, "sum_monthly_gwh": np.nan,
                    "march_cumulative_gwh": r[Y_LY], "fy_total_gwh": r[Y_LY],
                    "method": "published 'same period last year' (#10) in 2020-03 file - EXTENDED, flagged", "partial_fy_sum_gwh": np.nan})
    d18 = sum(r[Y_LY] for _, r in m20.iterrows() if r.series in ("THERMAL", "NUCLEAR", "HYDRO"))
    add.append({**add[0], "series": "DOMESTIC_CONVENTIONAL_TOTAL", "scope": "domestic", "march_cumulative_gwh": d18, "fy_total_gwh": d18})
    fn = pd.concat([pd.DataFrame(add), fn]).sort_values(["series", "fy_start"])
    fn.to_csv(OUT / "fy_national.csv", index=False)
    fr = fy_tables(mr, ["region", "series"], "regional")
    fr.to_csv(OUT / "fy_regional.csv", index=False)
    fs = fy_tables(ms, ["state", "state_harmonised", "region", "series"], "state")
    fs.to_csv(OUT / "fy_state.csv", index=False)

    ck = pd.DataFrame(checks)
    ck.to_csv(OUT / "validation_checks.csv", index=False)
    write_log(mn, ext, mr, ms, fn, ck, unmapped, n_ov, max_ov)
    print(ck.to_string())


def md(df):
    cols = list(df.columns)
    s = "| " + " | ".join(map(str, cols)) + " |\n|" + "---|" * len(cols) + "\n"
    for _, r in df.iterrows():
        s += "| " + " | ".join(f"{v:,.2f}" if isinstance(v, float) else str(v) for v in r.values) + " |\n"
    return s


def write_log(mn, ext, mr, ms, fn, ck, unmapped, n_ov, max_ov):
    st_months = ms[ms.series == "STATE_TOTAL"].groupby("state").period.agg(["min", "max", "nunique"]).reset_index()
    fy_show = fn[fn.series.isin(["DOMESTIC_CONVENTIONAL_TOTAL", "BHUTAN_IMPORT"])][["series", "fy", "n_months", "fy_total_gwh", "partial_fy_sum_gwh", "method"]]
    txt = f"""# Data Preparation Log (Phase 2A)

_Generated by `src/prepare_data.py` on {dt.date.today()}. Inputs: `data/processed/*.csv` (parsed read-only from `data/raw/`). Raw files untouched._

## Scope statement
All series are **conventional generation monitored by CEA** (thermal = coal + lignite + gas + diesel, nuclear, large hydro >25 MW).
They **exclude solar, wind, small hydro, biomass and waste-to-energy** and therefore **do not represent total Indian electricity production**.
Bhutan import is a separate series (`scope = import`) and is never included in domestic totals.

## Target variable and columns
| Kept | CEA column | Use |
|---|---|---|
| `value_gwh` | #4 actual generation in the month | forecasting target |
| `fytd_gwh` | #9 actual April-to-date (cumulative) | FY totals / validation only, never summed across months |
| extended series only | #5 actual same month previous year, #10 same period previous year | flagged back-extension |

Excluded: #1 monitored capacity (MW), #2/#3/#8 programme targets, #6/#7/#11/#12 ratios, #13-#18 PLF. No consumption variable exists.
Units: all GWh (= MU); report headers state GWH/MU; report 16 unit inferred from exact reconciliation with report 02.

## Financial-year mapping
FY = April-March, labelled `FY<start>-<end2>` (Apr-2020..Mar-2021 = FY2020-21). `fy_month_no` Apr=1..Mar=12.
FY totals: complete FY = sum of 12 monthly actuals (cross-checked with March #9); FY2019-20 (monthly files only from Jul-2019) uses the published March-2020 #9 full-year actual; FY2026-27 is PARTIAL (Apr-Sep) and is not a full-year value.

## Datasets
| File | Rows | Coverage | Series |
|---|---|---|---|
| monthly_national.csv | {len(mn)} | {mn.period.min()}..{mn.period.max()} | {', '.join(sorted(mn.series.unique()))} |
| monthly_national_extended.csv | {len(ext)} | {ext.period.min()}..{ext.period.max()} | categories + domestic total; rows before {mn.period.min()} flagged `EXTENDED_FROM_PRIOR_YEAR_COLUMN` |
| monthly_regional.csv | {len(mr)} | {mr.period.min()}..{mr.period.max()} | 5 regions x THERMAL/NUCLEAR/HYDRO/DOMESTIC_CONVENTIONAL_TOTAL |
| monthly_state.csv | {len(ms)} | {ms.period.min()}..{ms.period.max()} | {ms.state.nunique()} states/UTs x COAL_LIGNITE/NATURAL_GAS/DIESEL/NUCLEAR/HYDRO + STATE_TOTAL |
| fy_national/regional/state.csv | | FY2018-19 (national, flagged) / FY2019-20..FY2026-27 (partial) | |

## Classification and mapping decisions
1. **Source taxonomy.** National: COAL and LIGNITE from report 11 totals; NATURAL_GAS and DIESEL as sums of report-16 station rows (gas stations include liquid-fuel operation of gas plants, as CEA reports them). State: COAL_LIGNITE (report 16 labels lignite plants COAL; the two 'LIGNITE'-labelled UP stations are merged here too), NATURAL_GAS, DIESEL, NUCLEAR, HYDRO.
2. **State names** (raw untouched; applied in outputs only): {', '.join(f'`{k}` -> `{v}`' for k, v in STATE_CANON.items())}.
3. **Ladakh / J&K.** Ladakh appears separately from 2019-12. `state` keeps them separate; `state_harmonised` = `JAMMU AND KASHMIR + LADAKH` for a continuous series.
4. **Region** of a state = CEA region heading in report 16 (not the GitHub 'Zone').
5. **Bhutan import** retained only nationally (`BHUTAN_IMPORT`); regional/state data contain domestic generation only.
6. **Extended history** (separate file): national monthly 2018-07..2019-06 from #5 of files published 12 months later. Overlap test vs original #4: {n_ov} series-months, max |diff| {max_ov:.3f} GWh. FY2018-19 national total from #10 in the 2020-03 file. Both are published CEA actuals, not synthetic, but are flagged and kept out of the primary dataset.
7. Unmapped station fuel labels: {len(unmapped)} rows.

## Validation checks (tolerance {TOL_GWH} GWh)
{md(ck)}

## FY totals - national
{md(fy_show)}

## State coverage (STATE_TOTAL months present)
{md(st_months)}

## Exclusions
- Reports 04-10, 12-14, 17-20 are used only for validation (sector/utility views duplicate the hierarchy above).
- Installed-capacity, PLF, programme/target and percentage columns are dropped.
- No RE generation exists; nothing was estimated from capacity.
"""
    (OUT / "data_preparation_log.md").write_text(txt, encoding="utf-8")


if __name__ == "__main__":
    main()
