"""
validate_data.py
----------------
1. Re-verifies every downloaded file (exists, size, magic bytes, opens) and writes
   data/metadata/download_manifest.csv  (a file is SUCCESS only if verified here)
   reports/download_summary.md
2. Runs data-quality and reconciliation checks on the processed tables produced by
   audit_data.py and on the Renewable India CSV, writing
   reports/data_quality_report.md
   reports/reconciliation_results.csv
   data/metadata/state_name_mapping.csv   (NPP vs GitHub spellings; mapping decisions recorded, nothing renamed in raw)
Read-only with respect to data/raw/. No value is modified to force agreement.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
META = ROOT / "data" / "metadata"
PROC = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"
LOGS = ROOT / "logs"
GH_CSV = RAW / "renewable_india" / "renewable-india-dataset" / "data" / "renewable_energy_dataset.csv"
TOL = 0.5  # % tolerance for reconciliation (rounding)


def setup_logging():
    LOGS.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("validate")
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for h in (logging.FileHandler(LOGS / "validate_data.log", encoding="utf-8", mode="w"), logging.StreamHandler(sys.stdout)):
        h.setFormatter(fmt)
        log.addHandler(h)
    return log


def sniff(path: Path) -> str:
    head = path.open("rb").read(8)
    if head.startswith(b"\xD0\xCF\x11\xE0"):
        return "xls"
    if head.startswith(b"PK\x03\x04"):
        return "xlsx"
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.lstrip().startswith(b"<"):
        return "html"
    return "text"


def md_table(df: pd.DataFrame, maxrows: int = 60) -> str:
    if df is None or len(df) == 0:
        return "_none_\n"
    d = df.head(maxrows).copy()
    for c in d.columns:
        if d[c].dtype.kind == "f":
            d[c] = d[c].map(lambda x: "" if pd.isna(x) else f"{x:,.2f}")
    cols = [str(c) for c in d.columns]
    out = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    for _, r in d.iterrows():
        out += "| " + " | ".join(str(v).replace("|", "/") for v in r.values) + " |\n"
    if len(df) > maxrows:
        out += f"\n_... {len(df) - maxrows} more rows (see CSV outputs)_\n"
    return out


def month_range(a: str, b: str):
    p = pd.period_range(a, b, freq="M")
    return [str(x) for x in p]


# ---------------------------------------------------------------- manifest
def build_manifest(log):
    rows = []
    npp = pd.read_csv(META / "npp_download_log.csv", dtype=str).fillna("") if (META / "npp_download_log.csv").exists() else pd.DataFrame()
    latest = npp.loc[npp.report_category != "dashboard_snapshot", "reporting_period"].max() if len(npp) else ""
    for _, r in npp.iterrows():
        p = ROOT / r["local_path"]
        status, note = r["download_status"], r["notes"]
        if status == "SUCCESS":
            if not p.exists():
                status, note = "FAILED_VERIFICATION", "file missing on disk"
            else:
                real = sniff(p)
                ok = (r["file_format"] in ("xls", "xlsx") and real in ("xls", "xlsx")) or (r["file_format"] == real) or \
                     (r["file_format"] == "json" and real == "text")
                if not ok:
                    status, note = "FAILED_VERIFICATION", f"signature {real}"
                elif real in ("xls", "xlsx"):
                    try:
                        pd.ExcelFile(p).sheet_names
                    except Exception as e:  # noqa: BLE001
                        status, note = "FAILED_VERIFICATION", f"unreadable: {e}"
        rows.append({
            "file_name": r["file_name"], "source": "National Power Portal (npp.gov.in)",
            "report_name": (f"Monthly ACTUAL report {int(r['report_no']):02d} - " if r["report_no"] else "") + r["report_name"],
            "report_category": r["report_category"], "reporting_period": r["reporting_period"],
            "download_date": r["download_date"], "original_url": r["original_url"], "file_format": r["file_format"],
            "file_size_bytes": p.stat().st_size if p.exists() else r["file_size_bytes"], "download_status": status,
            "historical_or_current": ("current" if r["reporting_period"] == latest or r["report_category"] == "dashboard_snapshot" else "historical"),
            "notes": "; ".join(x for x in [note, f"local: {r['local_path']}"] if x),
        })
    gh = pd.read_csv(META / "github_download_log.csv", dtype=str).fillna("") if (META / "github_download_log.csv").exists() else pd.DataFrame()
    for _, r in gh.iterrows():
        p = ROOT / r["local_path"]
        rows.append({
            "file_name": r["file_name"], "source": "Renewable India dataset (GitHub chrisjaimyantony/renewable-india-dataset)",
            "report_name": "renewable-india-dataset repository file", "report_category": "github_" + r["file_format"],
            "reporting_period": "2006-2024 (annual)" if r["file_name"].endswith(".csv") else "n/a",
            "download_date": r["download_date"], "original_url": r["original_url"], "file_format": r["file_format"],
            "file_size_bytes": p.stat().st_size if p.exists() else "", "download_status": r["download_status"] if p.exists() else "FAILED_VERIFICATION",
            "historical_or_current": f"current snapshot (branch {r['branch']}, commit {r['commit'][:10]})",
            "notes": f"sha256={r['sha256'][:16]}...; local: {r['local_path']}",
        })
    man = pd.DataFrame(rows)
    man.to_csv(META / "download_manifest.csv", index=False)
    log.info("manifest: %d rows, %d verified", len(man), (man.download_status == "SUCCESS").sum())
    return man


def download_summary(man: pd.DataFrame, log):
    npp = man[man.source.str.startswith("National")]
    mon = npp[npp.report_category != "dashboard_snapshot"]
    ok = mon[mon.download_status == "SUCCESS"]
    cov = pd.read_csv(META / "npp_archive_coverage.csv") if (META / "npp_archive_coverage.csv").exists() else pd.DataFrame()
    have = sorted(cov.loc[cov.archive_has_links == "YES", "reporting_period"]) if len(cov) else sorted(ok.reporting_period.unique())
    first, last = (have[0], have[-1]) if have else ("", "")
    gaps = [m for m in month_range(first, last) if m not in set(have)] if have else []
    per_month = ok.groupby("reporting_period").file_name.nunique()
    incomplete = per_month[per_month < 20]
    ok_xls = ok[ok.file_format.isin(["xls", "xlsx"])]
    reports_per_no = ok_xls.assign(no=ok_xls.report_name.str.extract(r"report (\d+)")[0]).groupby("no").reporting_period.nunique()
    failed = man[man.download_status != "SUCCESS"]
    queried_no = cov.loc[cov.archive_has_links == "NO", "reporting_period"].tolist() if len(cov) else []
    lines = [
        "# Download Summary\n",
        f"_Generated by `scripts/validate_data.py` on {dt.date.today().isoformat()}. A file counts as downloaded only if it exists, its magic bytes match its format and it opens._\n",
        "## 1. Total downloaded (verified) files\n",
        f"- **{(man.download_status == 'SUCCESS').sum()}** verified files out of {len(man)} manifest rows.\n",
        "## 2. Files per authorised source\n",
        md_table(man.groupby(["source", "download_status"]).size().rename("files").reset_index()),
        "\n## 3. Report categories\n",
        md_table(man.groupby(["source", "report_category", "file_format"]).size().rename("files").reset_index()),
        "\n## 4. Historical year coverage (NPP Monthly Reports ACTUAL)\n",
        f"- Archive form `/monthlyGenerationReportsAct` queried for every month from {queried_no[0] if queried_no else '?'} to {dt.date.today():%Y-%m}.\n",
        f"- Months for which the portal publishes links: **{len(have)}** ({first} to {last}).\n",
        "- Months covered per report number (XLS):\n\n" + md_table(reports_per_no.rename("months").reset_index().rename(columns={"no": "report_no"})),
        "\n- Financial years with all 12 months: " + ", ".join(
            f"FY{y}-{str(y + 1)[2:]}" for y in range(2015, 2027)
            if all(m in set(have) for m in month_range(f"{y}-04", f"{y + 1}-03"))) + "\n",
        "\n## 5. Oldest and newest available reports\n",
        f"- Oldest: **{first}** (archive returns no links for any month before this; queried back to {queried_no[0] if queried_no else '?'}).\n",
        f"- Newest ACTUAL: **{last}**. (A TENTATIVE report exists for the following month but was deliberately not downloaded.)\n",
        "\n## 6. Missing reporting periods\n",
        f"- Gaps inside {first}..{last}: {', '.join(gaps) if gaps else 'none'}.\n",
        f"- Months with fewer than 20 verified report files: {', '.join(f'{k} ({v})' for k, v in incomplete.items()) if len(incomplete) else 'none'}.\n",
        "- Before " + first + ": no monthly ACTUAL reports are published in the portal archive. Coverage is therefore NOT complete for earlier history.\n",
        "\n## 7. Failed downloads\n",
        md_table(failed[["file_name", "reporting_period", "download_status", "notes"]]),
        "\n## 8. Unavailable report categories\n",
        "- **Solar generation, wind generation, small-hydro / biomass generation**: no generation report on NPP (monthly or daily). Only RE *installed capacity* is published (Installed Capacity reports, daily DGR-1 'R.E.S' row, dashboard JSON) - prohibited as a substitute.\n",
        "- **State-wise generation report as a separate file**: not published; state totals exist only inside report 16.\n",
        "- **Separate lignite / multi-fuel / liquid-fuel files**: not separate; included in reports 11-15.\n",
        "- **Pre-" + first + " monthly ACTUAL archive**: not available on the portal.\n",
        "\n## 9. Portal restrictions / access limitations\n",
        "- No login, OTP or CAPTCHA needed for published reports. Archive form requires a session CSRF token (obtained by loading the page normally).\n",
        "- `robots.txt` returned empty. Requests were rate-limited by the script (0.4 s delay).\n",
        "- Deliberately NOT downloaded: TENTATIVE monthly reports, installed-capacity reports, fuel-supply (coal/gas supply) reports, transmission reports, daily generation reports (daily granularity duplicates monthly ACTUAL; only conventional sources).\n",
        "- The dashboard (`/dashBoard/getAllZone`) exposes only a current-day snapshot (saved once as evidence).\n",
        "\n## 10. Remaining manual download requirements\n",
        "- None required for the authorised monthly ACTUAL archive.\n",
        "- If the organisers can supply pre-2019 CEA monthly ACTUAL reports or RE *generation* data through an authorised channel, that would close the main gaps (see data_audit.md).\n",
    ]
    (REPORTS / "download_summary.md").write_text("".join(lines), encoding="utf-8")
    log.info("download summary written")
    return {"first": first, "last": last, "n_months": len(have), "gaps": gaps}


# ---------------------------------------------------------------- quality
def fy_of(period: str) -> int:
    y, m = map(int, period.split("-"))
    return y if m >= 4 else y - 1


def quality(log, dl):
    sec = []
    rec = []
    nat = pd.read_csv(PROC / "national_monthly.csv")
    reg = pd.read_csv(PROC / "region_monthly.csv")
    sct = pd.read_csv(PROC / "sector_monthly.csv")
    stn = pd.read_csv(PROC / "station_monthly.csv")
    stf = pd.read_csv(PROC / "state_fuel_monthly.csv")
    stt = pd.read_csv(PROC / "state_total_monthly.csv")
    long = pd.read_csv(PROC / "cea_rows_long.csv", low_memory=False)
    plog = pd.read_csv(PROC / "parse_log.csv")
    G = "gen_actual_month_gwh"
    Y = "gen_actual_fytd_gwh"

    # ---------- parse status
    ps = plog.groupby(["report_no", "status"]).size().unstack(fill_value=0)
    sec.append("## 0. Parse status of downloaded XLS files\n" + md_table(ps.reset_index()) +
               f"\nPeriod declared inside the sheet differs from file name in **{plog.note.fillna('').str.contains('differs').sum()}** files.\n")

    # ---------- completeness
    periods = sorted(nat.period.unique())
    exp = month_range(periods[0], periods[-1])
    miss_nat = [m for m in exp if m not in set(periods)]
    cats = nat.groupby("period").category.apply(lambda s: ";".join(sorted(s)))
    cat_var = cats.value_counts().rename("months").reset_index().rename(columns={"category": "category set"})
    st_months = stt.groupby("state").period.nunique().sort_values()
    n_p16 = stt.period.nunique()
    st_incomplete = st_months[st_months < n_p16]
    fuel_sets = stf.groupby("fuel_group").period.nunique().rename("months").reset_index()
    sec.append(
        "## 1. Completeness\n"
        f"- National (report 01): {len(periods)} months, {periods[0]}..{periods[-1]}; missing months inside range: {', '.join(miss_nat) or 'none'}.\n"
        f"- Category sets per month (report 01):\n\n{md_table(cat_var)}\n"
        f"- Report 16 states/UTs with a 'TOTAL <STATE>' row: **{stt.state.nunique()}**. States not present in every month ({n_p16} months):\n\n"
        + md_table(st_incomplete.rename("months_present").reset_index()) +
        f"\n- State fuel-group labels in report 16 and months present:\n\n{md_table(fuel_sets)}\n"
        f"- Missing values in eligible columns: national c4 {nat[G].isna().mean()*100:.2f}%, c9 {nat[Y].isna().mean()*100:.2f}%; "
        f"station c4 {stn[G].isna().mean()*100:.2f}%; state totals c4 {stt[G].isna().mean()*100:.2f}%.\n"
        "- Energy sources missing entirely: **solar, wind, small hydro, biomass, waste-to-energy generation** (not published by NPP).\n")

    # ---------- consistency
    st_names = sorted(stt.state.unique())
    fuels = sorted(stn.fuel.dropna().unique())
    regions = sorted(reg.region.unique())
    unit_note = ""
    si = META / "sheet_inventory.csv"
    if si.exists():
        s = pd.read_csv(si)
        s = s[s.file_name.str.contains("18_col_act", na=False)]
        s["no"] = s.file_name.str.extract(r"act-(\d+)_")[0].astype(int)
        unit_note = md_table(s.groupby(["no", "units_in_header"]).size().rename("files").reset_index())
    stn_name_var = stn.groupby("station").state.nunique()
    multi_state = stn_name_var[stn_name_var > 1]
    dup_st = stn.duplicated(["period", "state", "station", "owner"]).sum()
    # lignite stations as listed in report 11 'LIGNITE BASED' section
    r11 = long[(long.report_no == 11) & long.section.str.contains("LIGNITE BASED", case=False, na=False)
               & ~long.lab1.str.match(r"(?i)^TOTAL", na=False)]
    lig_names = set(r11.lab1.str.upper().str.strip())
    lig_in16 = stn[stn.station.str.upper().str.strip().isin(lig_names)]
    lig_lab = lig_in16.groupby("fuel").size().to_dict()
    labelled_lig = stn[stn.fuel == "LIGNITE"].groupby(["state", "station"]).period.agg(["min", "max", "count"]).reset_index()
    other_lab = {s: sorted(stn.loc[(stn.station == s) & (stn.fuel != "LIGNITE"), "fuel"].unique()) for s in labelled_lig.station}
    labelled_lig["other_labels_same_station"] = labelled_lig.station.map(lambda s: "/".join(other_lab[s]) or "none")
    dup_nat = nat.duplicated(["period", "category"]).sum()
    sec.append(
        "## 2. Consistency\n"
        f"- Region labels (report 02): {', '.join(regions)}.\n"
        f"- State labels (report 16, verbatim): {', '.join(st_names)}.\n"
        f"- Station fuel labels (report 16): {', '.join(fuels)}.\n"
        f"- Stations listed as LIGNITE-based in report 11 ({len(lig_names)} names) carry these fuel labels in report 16 (station-months): {lig_lab}. "
        "**Report 16 labels lignite plants as COAL**, and state fuel-group totals have no LIGNITE group (lignite is inside THERMAL). "
        "Lignite is separable only nationally / by station via report 11.\n"
        f"- Stations that DO carry a 'LIGNITE' label in report 16 (the same station is labelled COAL in other months -> label inconsistency over time):\n\n{md_table(labelled_lig)}\n"
        f"- Units found in sheet headers (GWH and MU are identical units: 1 MU = 1 GWh):\n\n{unit_note}\n"
        "- Report 16 header does not print the energy unit; its values reconcile exactly with report 02 (GWh) - see section 5 - so GWh is inferred and marked as such.\n"
        f"- Duplicate records: national (period, category) {dup_nat}; station (period, state, station, owner) {dup_st}.\n"
        f"- Station names appearing under more than one state: {len(multi_state)} "
        + (f"({', '.join(multi_state.index[:15])})" if len(multi_state) else "") + "\n"
        "- Date formats: report headers use 'MAR-2020' / 'Mar-2020'; file names use 'YYYY-MON'. All normalised to YYYY-MM in processed tables (raw untouched).\n")

    # ---------- temporal integrity: monthly vs cumulative
    t = nat.copy()
    t["fy"] = t.period.map(fy_of)
    t = t.sort_values("period")
    t["cum_from_monthly"] = t.groupby(["fy", "category"])[G].cumsum()
    t["n_months_in_fy"] = t.groupby(["fy", "category"]).cumcount() + 1
    t["fy_start_month_ok"] = t.groupby(["fy", "category"]).period.transform("min").str.endswith("-04")
    tt = t[t.fy_start_month_ok]
    tt = tt.assign(diff_pct=100 * (tt[Y] - tt["cum_from_monthly"]) / tt[Y])
    worst = tt.loc[tt.diff_pct.abs().sort_values(ascending=False).index][["period", "category", G, Y, "cum_from_monthly", "diff_pct"]].head(12)
    april = t[t.period.str.endswith("-04")]
    april_ok = (abs(april[G] - april[Y]) < 0.01).mean() * 100
    # restatement: c5 (same month last year) vs c4 published a year earlier
    a = nat[["period", "category", G]].copy()
    a["period_next"] = (pd.PeriodIndex(a.period, freq="M") + 12).astype(str)
    b = nat[["period", "category", "gen_actual_same_month_prev_year_gwh"]]
    r = a.merge(b, left_on=["period_next", "category"], right_on=["period", "category"], suffixes=("", "_n"))
    r["restate_pct"] = 100 * (r["gen_actual_same_month_prev_year_gwh"] - r[G]) / r[G]
    big_restate = r[r.restate_pct.abs() > 1][["period", "category", G, "gen_actual_same_month_prev_year_gwh", "restate_pct"]]
    sec.append(
        "## 3. Temporal integrity\n"
        "- Every report gives BOTH a monthly value (c4) and an April-to-date cumulative value (c9). Financial year = April-March.\n"
        f"- April rows where monthly == cumulative (expected reset): **{april_ok:.1f}%**.\n"
        f"- Sum of monthly c4 vs published cumulative c9 (national, FYs with April present): median |diff| "
        f"{tt.diff_pct.abs().median():.3f}%, max |diff| {tt.diff_pct.abs().max():.3f}%. Largest deviations:\n\n{md_table(worst)}\n"
        "  Deviations indicate later revisions folded into the cumulative figure; cumulative values must not be summed across months.\n"
        f"- 'Same month last year' (c5) vs value originally published 12 months earlier: {len(r)} comparable pairs, "
        f"{len(big_restate)} differ by >1% (restatements / coverage changes):\n\n{md_table(big_restate.sort_values('restate_pct', key=abs, ascending=False), 15)}\n"
        f"- Duplicate reporting periods: {plog.duplicated(['period', 'report_no']).sum()}.\n")

    # ---------- numerical integrity
    num_cols = [c for c in long.columns if re.fullmatch(r"c(4|5|9|10)", c)]
    neg = long[(long[num_cols] < 0).any(axis=1)][["period", "report_no", "lab1", *num_cols]]
    neg_st = stn[(stn[[G, Y]] < 0).any(axis=1)][["period", "state", "station", G, Y]]
    zero_nat = nat[(nat[G] == 0) & (~nat.category.str.contains("BHUTAN"))][["period", "category", G]]
    tot = nat[nat.category == "TOTAL"].sort_values("period").set_index("period")[G]
    yoy = (tot / tot.shift(12) - 1) * 100
    mom = tot.pct_change() * 100
    out_yoy = yoy[yoy.abs() > 15].round(2)
    st_tot = stt.pivot_table(index="period", columns="state", values=G, aggfunc="sum")
    st_yoy = (st_tot / st_tot.shift(12) - 1) * 100
    st_jumps = st_yoy.stack().loc[lambda s: s.abs() > 100].round(1).rename("yoy_pct").reset_index()
    sec.append(
        "## 4. Numerical integrity\n"
        f"- Negative generation values (c4/c5/c9/c10) in reports 1-15,17-20: **{len(neg)}** rows; in report 16 stations: **{len(neg_st)}** rows.\n\n"
        + md_table(pd.concat([neg.head(10), neg_st.head(10)]), 20) +
        f"\n- Zero monthly generation for national THERMAL/NUCLEAR/HYDRO/TOTAL: {len(zero_nat)} rows.\n"
        f"- Station rows with zero monthly generation (retired/shut/outage): {(stn[G] == 0).mean()*100:.1f}% of station-months (expected for units under shutdown; not an error).\n"
        f"- National TOTAL monthly YoY change >15%: {len(out_yoy)} months:\n\n{md_table(out_yoy.rename('yoy_pct').reset_index())}\n"
        f"- National TOTAL month-on-month range: {mom.min():.1f}% to {mom.max():.1f}% (seasonality).\n"
        f"- State total YoY changes >100% (small bases / new or retired plants): {len(st_jumps)} state-months:\n\n{md_table(st_jumps, 20)}\n")

    # ---------- reconciliation
    def recon(name, left, right, keys, lname, rname, cond):
        m = left.merge(right, on=keys, how="outer", suffixes=("_l", "_r"))
        m.columns = [*keys, lname, rname]
        m["diff"] = m[lname] - m[rname]
        m["diff_pct"] = 100 * m["diff"] / m[rname].replace(0, np.nan)
        rec.append(pd.DataFrame({
            "check": name, "period": m["period"],
            "key": m[keys[1]] if len(keys) > 1 else "",
            "left_name": lname, "left_value_gwh": m[lname], "right_name": rname, "right_value_gwh": m[rname],
            "diff_gwh": m["diff"], "diff_pct": m["diff_pct"], "comparable_because": cond}))
        both = m.dropna(subset=[lname, rname])
        within = (both.diff_pct.abs().fillna(0) <= TOL).mean() * 100 if len(both) else np.nan
        return {"check": name, "pairs_compared": len(both), "unmatched_keys": len(m) - len(both),
                "within_tol_pct": round(within, 1),
                "median_abs_diff_pct": round(m.diff_pct.abs().median(), 3), "max_abs_diff_pct": round(m.diff_pct.abs().max(), 3)}

    res = []
    n = nat.pivot_table(index="period", columns="category", values=G, aggfunc="sum")
    comp = [c for c in n.columns if c != "TOTAL"]
    res.append(recon("R01 TOTAL = THERMAL+NUCLEAR+HYDRO+BHUTAN", n[["TOTAL"]].reset_index(),
                     n[comp].sum(axis=1).rename("sum").reset_index(), ["period"], "r01_total", "sum_components",
                     "same report, month, unit"))
    rg = reg[~reg.region.str.contains("ALL INDIA")].copy()
    rg["cat"] = rg.category.str.upper().str.replace("(BLANK)", "BHUTAN IMP", regex=False)
    rg.loc[rg.region.str.contains("BHUTAN"), "cat"] = "BHUTAN IMP"
    rgs = rg[rg.cat.isin(["THERMAL", "NUCLEAR", "HYDRO", "BHUTAN IMP"])].groupby(["period", "cat"])[G].sum().reset_index()
    nn = nat[nat.category.isin(["THERMAL", "NUCLEAR", "HYDRO"]) | nat.category.str.startswith("BHUTAN")].copy()
    nn["cat"] = nn.category.where(~nn.category.str.startswith("BHUTAN"), "BHUTAN IMP")
    res.append(recon("Sum of regions (R02) = national (R01) by category", rgs, nn[["period", "cat", G]], ["period", "cat"],
                     "sum_regions", "national", "same month, unit, category; Bhutan treated as its own 'region'"))
    # R16 state totals summed by region vs R02 regional totals (excl Bhutan)
    rtot = reg[reg.category.str.upper() == "TOTAL"][["period", "region", G]].copy()
    rtot["region_key"] = rtot.region.str.extract(r"^(NORTH EASTERN|NORTHERN|WESTERN|SOUTHERN|EASTERN)")[0]
    stt2 = stt.copy()
    stt2["region_key"] = stt2.region.str.extract(r"^(NORTH EASTERN|NORTHERN|WESTERN|SOUTHERN|EASTERN)")[0]
    ssum = stt2.groupby(["period", "region_key"])[G].sum().reset_index()
    res.append(recon("Sum of state totals (R16) = region total (R02)", ssum, rtot.dropna(subset=["region_key"])[["period", "region_key", G]],
                     ["period", "region_key"], "sum_states_r16", "region_r02", "same month, unit; conventional stations only in both"))
    # station sum vs state total
    stsum = stn.groupby(["period", "state"])[G].sum().reset_index()
    res.append(recon("Sum of stations (R16) = state total (R16)", stsum, stt.groupby(["period", "state"])[G].sum().reset_index(),
                     ["period", "state"], "sum_stations", "state_total", "same report, month, unit"))
    fsum = stf.groupby(["period", "state"])[G].sum().reset_index()
    res.append(recon("Sum of state fuel-groups (R16) = state total (R16)", fsum, stt.groupby(["period", "state"])[G].sum().reset_index(),
                     ["period", "state"], "sum_fuel_groups", "state_total", "same report, month, unit"))
    # sector (R03) vs national
    s3 = sct[sct.category.isin(["THERMAL", "NUCLEAR", "HYDRO"]) & ~sct.sector.str.contains("TOTAL|ALL INDIA", na=False)]
    s3 = s3[~s3.sector.str.match(r"^TOTAL", na=False)]
    s3s = s3.groupby(["period", "category"])[G].sum().reset_index().rename(columns={"category": "cat"})
    res.append(recon("Sum of sectors (R03) = national (R01) by category", s3s,
                     nn[nn.cat.isin(["THERMAL", "NUCLEAR", "HYDRO"])][["period", "cat", G]], ["period", "cat"],
                     "sum_sectors", "national", "same month, unit; THERMAL/NUCLEAR/HYDRO (Bhutan import has no sector)"))
    # fuel: R11 coal + lignite + R15 'TOTAL EXCL. COAL/LIGNITE' vs R01 THERMAL
    def pick(no, pat):
        d = long[(long.report_no == no) & long.lab1.str.contains(pat, case=False, regex=True, na=False)]
        return d.groupby("period")["c4"].sum()  # c4 = actual monthly generation in the long table
    coal, lig = pick(11, r"^TOTAL COAL BASED"), pick(11, r"^TOTAL LIGNITE BASED")
    multi = pick(11, r"^TOTAL MULTI")
    excl = pick(15, r"^TOTAL EXCL")
    fs = pd.concat([coal.rename("coal"), lig.rename("lignite"), multi.rename("multi_fuel"), excl.rename("gas_liquid_diesel")], axis=1)
    fs["sum_fuels"] = fs.fillna(0).sum(axis=1)
    th = n["THERMAL"].rename("national_thermal")
    res.append(recon("R11 coal+lignite(+multi) + R15 'TOTAL EXCL. COAL/LIGNITE' = R01 THERMAL",
                     fs["sum_fuels"].reset_index(), th.reset_index(), ["period"], "sum_fuel_reports", "r01_thermal",
                     "same month, unit; label match on 'TOTAL ...' rows"))
    # R16 fuel groups nationally vs R01
    for fg, cat in [("HYDRO", "HYDRO"), ("NUCLEAR", "NUCLEAR")]:
        a1 = stf[stf.fuel_group == fg].groupby("period")[G].sum().reset_index()
        res.append(recon(f"Sum of state '{fg}' groups (R16) = national {cat} (R01)", a1, n[[cat]].reset_index(), ["period"],
                         f"r16_{fg.lower()}", f"r01_{cat.lower()}", "same month/unit"))
    a1 = stf[stf.fuel_group.isin(["THERMAL", "NATURAL GAS", "DIESEL"])].groupby("period")[G].sum().reset_index()
    res.append(recon("Sum of state THERMAL+NATURAL GAS(+DIESEL) groups (R16) = national THERMAL (R01)", a1, n[["THERMAL"]].reset_index(),
                     ["period"], "r16_thermal_groups", "r01_thermal", "same month/unit"))
    resdf = pd.DataFrame(res)
    allrec = pd.concat(rec, ignore_index=True)
    allrec.to_csv(REPORTS / "reconciliation_results.csv", index=False)
    worst_rec = allrec.dropna(subset=["diff_pct"])
    worst_rec = worst_rec[worst_rec.diff_pct.abs() > TOL]
    worst_rec = worst_rec.loc[worst_rec.diff_pct.abs().sort_values(ascending=False).index].groupby("check").head(4)
    worst_rec = worst_rec.drop(columns=["comparable_because"])
    unmatched = allrec[allrec.left_value_gwh.isna() | allrec.right_value_gwh.isna()]
    worst_rec = pd.concat([worst_rec, unmatched.drop(columns=["comparable_because"]).groupby("check").head(4)])
    sec.append(
        "## 5. Reconciliation (only where period, unit, coverage and classification match)\n"
        f"Tolerance: +/-{TOL}% (rounding). Source data are NOT modified to force agreement.\n\n{md_table(resdf)}\n"
        f"Largest deviations per check (full detail in `reports/reconciliation_results.csv`):\n\n{md_table(worst_rec, 40)}\n"
        "- Report 16 'state' = location of monitored conventional stations; inter-state shared projects (e.g. BBMB) appear under one state.\n"
        "- Comparisons against consumption, capacity or RE were NOT performed (prohibited / not comparable).\n")

    # ---------- GitHub dataset
    g = pd.read_csv(GH_CSV)
    yrs = g.groupby("State").Year.agg(["min", "max", "nunique"])
    full = set(range(g.Year.min(), g.Year.max() + 1))
    yrs["missing_years"] = g.groupby("State").Year.apply(lambda s: ",".join(map(str, sorted(full - set(s)))) or "none")
    dups = g.duplicated(["State", "Year"]).sum()
    cap_cols = [c for c in g.columns if c.startswith("Installed")]
    gs = g.sort_values(["State", "Year"])
    drops = []
    for c in cap_cols:
        d = gs.groupby("State")[c].diff()
        drops.append(gs.loc[d < 0, ["State", "Year"]].assign(column=c, change=d[d < 0]))
    drops = pd.concat(drops)
    repeated_gsdp = gs.groupby("State")["GSDP (crore INR)"].apply(lambda s: int((s.diff() == 0).sum())).loc[lambda s: s > 0]
    pop_jump = gs.groupby("State").Population.pct_change().mul(100)
    pj = gs.loc[pop_jump.abs() > 10, ["State", "Year"]].assign(pop_change_pct=pop_jump[pop_jump.abs() > 10].round(1))
    # state name mapping
    npp_states = set(stt.state.unique())
    gh_states = set(g.State.unique())
    def key(s):
        return re.sub(r"[^A-Z]", "", s.upper().replace("&", "AND"))
    alias = {"CHHATISGARH": "CHHATTISGARH", "ORISSA": "ODISHA"}
    nk = {alias.get(key(s), key(s)): s for s in npp_states}
    gk = {alias.get(key(s), key(s)): s for s in gh_states}
    maprows = []
    for k in sorted(set(nk) | set(gk)):
        maprows.append({"key": k, "npp_report16_name": nk.get(k, ""), "github_name": gk.get(k, ""),
                        "decision": "matched (case/punctuation/'&'->'and' normalisation" + (", known spelling variant" if k in alias.values() and (nk.get(k, "").upper() != gk.get(k, "").upper()) else "") + ")"
                        if k in nk and k in gk else ("only in NPP" if k in nk else "only in GitHub")})
    mp = pd.DataFrame(maprows)
    mp.to_csv(META / "state_name_mapping.csv", index=False)
    zones = g.groupby("Zone").State.apply(lambda s: ", ".join(sorted(s.unique())))
    npp_reg = stt.groupby("state").region.first()
    zone_vs = []
    for _, r in mp[(mp.npp_report16_name != "") & (mp.github_name != "")].iterrows():
        gz = g.loc[g.State == r.github_name, "Zone"].iloc[0]
        zone_vs.append({"state": r.github_name, "github_zone": gz, "npp_region": npp_reg.get(r.npp_report16_name, "")})
    zv = pd.DataFrame(zone_vs)
    sec.append(
        "## 6. Renewable India dataset (GitHub) checks\n"
        f"- Rows {len(g)}, states/UTs {g.State.nunique()}, years {g.Year.min()}-{g.Year.max()}; duplicate (State, Year): {dups}; missing cells: {int(g.isna().sum().sum())}.\n"
        "- **README discloses that some missing values were predicted with XGBoost regression; predicted cells are not flagged.** Population and GSDP therefore contain an unknown share of model-generated values -> treat as UNVERIFIED supporting variables.\n"
        "- README column list (Solar, Wind, GSDP...) does not match actual headers (e.g. 'Installed - Solar Power', 'GSDP (crore INR)', extra 'Zone' column); README file name 'renewable_energy_india.csv' differs from actual 'renewable_energy_dataset.csv'.\n"
        "- Year basis (calendar vs financial) is not documented.\n"
        f"- Unbalanced panel (years per state):\n\n{md_table(yrs.reset_index(), 40)}\n"
        f"- Installed-capacity decreases year-on-year (implausible for cumulative capacity; indicates data issues): {len(drops)} cases:\n\n{md_table(drops.head(20))}\n"
        f"- States with identical GSDP repeated in consecutive years (likely carried forward): {len(repeated_gsdp)}\n\n{md_table(repeated_gsdp.rename('repeats').reset_index())}\n"
        f"- Population changes >10% year-on-year: {len(pj)}\n\n{md_table(pj, 20)}\n"
        f"- 'Zone' labels: {', '.join(zones.index)}. Comparison with CEA regions of report 16:\n\n{md_table(zv, 40)}\n"
        f"- State name mapping NPP vs GitHub (saved to data/metadata/state_name_mapping.csv; nothing renamed in raw):\n\n{md_table(mp, 50)}\n")

    head = ["# Data Quality Report\n",
            f"_Generated by `scripts/validate_data.py` on {dt.date.today().isoformat()} from processed tables (raw files untouched)._\n\n",
            f"Scope: NPP Monthly Reports ACTUAL {dl['first']}..{dl['last']} ({dl['n_months']} months) and the Renewable India CSV.\n\n"]
    (REPORTS / "data_quality_report.md").write_text("".join(head) + "\n".join(sec), encoding="utf-8")
    log.info("quality report written")
    return resdf


def main():
    log = setup_logging()
    man = build_manifest(log)
    dl = download_summary(man, log)
    res = quality(log, dl)
    print(res.to_string())


if __name__ == "__main__":
    main()
