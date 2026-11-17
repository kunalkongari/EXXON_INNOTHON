"""
audit_data.py
-------------
Parses every downloaded CEA monthly ACTUAL generation report (read-only) into tidy
tables under data/processed/, then builds the data dictionary and the data
availability matrix.

CEA "18-column" layout (verified by inspection of the raw sheets): a header row
contains the column numbers 1..18. Their meaning is:
   #1  Monitored capacity (MW)                       -> INSTALLED/MONITORED CAPACITY (not usable)
   #2  Annual generation target / programme (GWh)    -> OTHER (target, not actual)
   #3  Programme for the month (GWh)                 -> OTHER (target)
   #4  ACTUAL generation in the month (GWh = MU)     -> ACTUAL GENERATION, monthly
   #5  Actual generation same month last year (GWh)  -> ACTUAL GENERATION, monthly (prior year, as restated)
   #6  % of programme (4/3)                          -> OTHER (ratio)
   #7  % of last year (4/5)                          -> OTHER (ratio)
   #8  Programme April..month (GWh)                  -> OTHER (target, cumulative)
   #9  ACTUAL generation April..month (GWh)          -> ACTUAL GENERATION, cumulative FY-to-date
   #10 Actual same period last year (GWh)            -> ACTUAL GENERATION, cumulative FY-to-date (prior year)
   #11 % of programme (9/8), #12 % of last year (9/10) -> OTHER (ratio)
   #13-#18 Plant load factor (%)                     -> OTHER OPERATIONAL (PLF; derived from capacity)

Outputs
  data/processed/cea_rows_long.csv       every numeric row of reports 1-15,17-20 with section context
  data/processed/national_monthly.csv    report 1  (category x month)
  data/processed/region_monthly.csv      report 2  (region x category x month)
  data/processed/sector_monthly.csv      report 3  (sector x category x month)
  data/processed/station_monthly.csv     report 16 station rows (region/state/sector/owner/fuel)
  data/processed/state_fuel_monthly.csv  report 16 "TOTAL <fuel>" rows per state
  data/processed/state_total_monthly.csv report 16 "TOTAL <STATE>" rows
  data/processed/parse_log.csv           per-file parse status
  reports/data_dictionary.csv
  reports/data_availability.csv
No value is imputed, rescaled or altered; values are copied as published.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
NPP = RAW / "npp"
GH_CSV = RAW / "renewable_india" / "renewable-india-dataset" / "data" / "renewable_energy_dataset.csv"
PROC = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"
LOGS = ROOT / "logs"

MON = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}
FNAME_RE = re.compile(r"18_col_act-(\d+)_(\d{4})-([A-Z]{3})\.xls$", re.I)
COLS = [f"c{i}" for i in range(1, 19)]
COL_MEANING = {
    "c1": ("Monitored capacity", "MW", "Installed capacity", "snapshot at month end", "NOT ELIGIBLE (capacity)"),
    "c2": ("Annual generation target/programme", "GWh", "Other operational variable (target)", "annual", "NOT ELIGIBLE (target, not actual)"),
    "c3": ("Generation programme for the month", "GWh", "Other operational variable (target)", "monthly", "NOT ELIGIBLE (target)"),
    "c4": ("ACTUAL generation during the month", "GWh (=MU)", "Actual energy generation", "monthly", "ELIGIBLE - forecasting target"),
    "c5": ("Actual generation in same month of previous year", "GWh (=MU)", "Actual energy generation", "monthly (prior-year, as reported)", "ELIGIBLE - cross-check only"),
    "c6": ("% of programme for the month (c4/c3)", "%", "Other operational variable (ratio)", "monthly", "NOT ELIGIBLE"),
    "c7": ("% of same month last year (c4/c5)", "%", "Other operational variable (ratio)", "monthly", "NOT ELIGIBLE"),
    "c8": ("Generation programme April..reporting month", "GWh", "Other operational variable (target)", "cumulative FY-to-date", "NOT ELIGIBLE (target)"),
    "c9": ("ACTUAL generation April..reporting month", "GWh (=MU)", "Actual energy generation", "cumulative FY-to-date", "ELIGIBLE - do NOT sum across months"),
    "c10": ("Actual generation same period previous year", "GWh (=MU)", "Actual energy generation", "cumulative FY-to-date (prior year)", "ELIGIBLE - cross-check only"),
    "c11": ("% of programme FY-to-date (c9/c8)", "%", "Other operational variable (ratio)", "cumulative", "NOT ELIGIBLE"),
    "c12": ("% of last year FY-to-date (c9/c10)", "%", "Other operational variable (ratio)", "cumulative", "NOT ELIGIBLE"),
    "c13": ("PLF programme, month", "%", "Other operational variable (PLF)", "monthly", "NOT ELIGIBLE (capacity-derived)"),
    "c14": ("PLF actual, month", "%", "Other operational variable (PLF)", "monthly", "NOT ELIGIBLE (capacity-derived)"),
    "c15": ("PLF actual same month last year", "%", "Other operational variable (PLF)", "monthly", "NOT ELIGIBLE (capacity-derived)"),
    "c16": ("PLF programme FY-to-date", "%", "Other operational variable (PLF)", "cumulative", "NOT ELIGIBLE (capacity-derived)"),
    "c17": ("PLF actual FY-to-date", "%", "Other operational variable (PLF)", "cumulative", "NOT ELIGIBLE (capacity-derived)"),
    "c18": ("PLF actual same period last year", "%", "Other operational variable (PLF)", "cumulative", "NOT ELIGIBLE (capacity-derived)"),
}
REPORT_TITLES = {
    1: "All India", 2: "Region Wise", 3: "Thermal, Hydro and Nuclear Consolidated (by sector)", 4: "Sector Wise",
    5: "Central Sector Thermal", 6: "State Sector Thermal", 7: "Pvt. Sector Utilities & IPP Thermal",
    8: "Central Sector Hydro", 9: "State Sector Hydro", 10: "Pvt. & IPP Hydro and Central Sector Nuclear",
    11: "Coal/Lignite/Multi Fuel", 12: "Gas and Liquid Fuel (Central)", 13: "Gas and Liquid Fuel (State)",
    14: "Gas and Liquid Fuel (Pvt.)", 15: "Diesel", 16: "Region wise State wise and Station wise Detail",
    17: "Summary All India (gas-based stations)", 18: "Gas Based Stations (Central)", 19: "Gas Based Stations (State)",
    20: "Gas Based Stations (Private)",
}
GEO_LEVEL = {1: "National", 2: "Region", 3: "National by sector", 4: "National by sector/utility", 16: "Region/State/Station",
             17: "Region (gas-based)", 11: "Station / national fuel totals", 12: "Station", 13: "Station", 14: "Station", 15: "Station"}
SECTOR_RE = re.compile(r"^(STATE|PVT|PRIVATE|CENTRAL|IPP)(\s|\.|$)", re.I)
REGION_RE = re.compile(r"^(NORTHERN|WESTERN|SOUTHERN|EASTERN|NORTH\s*EASTERN)\s*REGION", re.I)


def setup_logging():
    LOGS.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("audit")
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for h in (logging.FileHandler(LOGS / "audit_data.log", encoding="utf-8", mode="w"), logging.StreamHandler(sys.stdout)):
        h.setFormatter(fmt)
        log.addHandler(h)
    return log


def norm(s) -> str:
    return re.sub(r"\s+", " ", str(s)).strip()


def is_num(v) -> bool:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return False
    if isinstance(v, (int, float, np.integer, np.floating)):
        return True
    try:
        float(str(v).replace(",", ""))
        return True
    except ValueError:
        return False


def to_num(v):
    if not is_num(v):
        return np.nan
    return float(str(v).replace(",", "")) if not isinstance(v, (int, float, np.integer, np.floating)) else float(v)


def parse_cea(path: Path):
    """Return (period_in_sheet, colmap, rows DataFrame). Raises on structural failure."""
    df = pd.read_excel(path, header=None, dtype=object)
    # locate the header row holding 1..18
    hdr_idx, colmap = None, {}
    for i in range(min(len(df), 40)):
        cand = {}
        for j, v in enumerate(df.iloc[i].values):
            if is_num(v) and float(to_num(v)).is_integer() and 1 <= to_num(v) <= 18:
                cand.setdefault(int(to_num(v)), j)
        if len(cand) >= 17 and all(k in cand for k in (1, 4, 9)):
            hdr_idx, colmap = i, cand
            break
    if hdr_idx is None:
        return parse_gas7(df)
    head = " ".join(norm(v) for v in df.head(hdr_idx).values.ravel() if pd.notna(v))
    m = re.search(r"PERIOD\s*:?\s*([A-Za-z]{3})[- ]?(\d{4})", head, re.I)
    period = f"{m.group(2)}-{MON[m.group(1).upper()]:02d}" if m and m.group(1).upper() in MON else ""
    first_num_col = colmap[1]
    out = []
    for i in range(hdr_idx + 1, len(df)):
        row = df.iloc[i].values
        labels = [norm(v) for v in row[:first_num_col] if pd.notna(v) and norm(v) and not is_num(v)]
        vals = {f"c{k}": to_num(row[j]) for k, j in colmap.items() if j < len(row)}
        n_num = sum(not np.isnan(v) for v in vals.values())
        if not labels and n_num == 0:
            continue
        if labels and re.match(r"(?i)^(report version|note\b|remarks|https?://|page\b)", labels[0]):
            continue  # report footer, not data
        lab1 = labels[0] if labels else ""
        lab2 = " ".join(labels[1:]) if len(labels) > 1 else ""
        # some sheets pack "TOTAL <many spaces> FUEL" into a single cell
        if not lab2 and re.match(r"^TOTAL\s{2,}\S", str(row[0]) if pd.notna(row[0]) else ""):
            pass
        out.append({"row": i, "lab1": lab1, "lab2": lab2, "n_num": n_num, **vals})
    rows = pd.DataFrame(out)
    for c in COLS:
        if c not in rows:
            rows[c] = np.nan
    return period, colmap, rows


def parse_gas7(df: pd.DataFrame):
    """Reports 17-20 (gas-based station summaries) use a 7-value layout:
    Monitored capacity | TARGET(month) | GENERATION(month) | PLF(month) | TARGET(FY) | GENERATION(FY) | PLF(FY).
    Values are mapped onto the 18-column equivalents c1,c3,c4,c14,c8,c9,c17."""
    hdr_idx = None
    for i in range(min(len(df), 30)):
        txt = [norm(v).upper() for v in df.iloc[i].values if pd.notna(v)]
        if sum(t.startswith("TARGET") for t in txt) >= 2 and sum(t.startswith("GENERATION") for t in txt) >= 2:
            hdr_idx = i
            break
    if hdr_idx is None:
        raise ValueError("neither 18-column header nor 7-value gas layout found")
    hrow = [norm(v).upper() if pd.notna(v) else "" for v in df.iloc[hdr_idx].values]
    first_tgt = next(j for j, t in enumerate(hrow) if t.startswith("TARGET"))
    cap_col = first_tgt - 1
    mapping = ["c1", "c3", "c4", "c14", "c8", "c9", "c17"]
    colmap = {mapping[k]: cap_col + k for k in range(7)}
    head = " ".join(norm(v) for v in df.head(hdr_idx).values.ravel() if pd.notna(v))
    m = re.search(r"\b([A-Za-z]{3})-(\d{4})\b", head)
    period = f"{m.group(2)}-{MON[m.group(1).upper()]:02d}" if m and m.group(1).upper() in MON else ""
    out = []
    for i in range(hdr_idx + 1, len(df)):
        row = df.iloc[i].values
        labels = [norm(v) for v in row[:cap_col] if pd.notna(v) and norm(v) and not is_num(v)]
        vals = {c: to_num(row[j]) if j < len(row) else np.nan for c, j in colmap.items()}
        n_num = sum(not np.isnan(v) for v in vals.values())
        if not labels and n_num == 0:
            continue
        out.append({"row": i, "lab1": labels[0] if labels else "", "lab2": " ".join(labels[1:]), "n_num": n_num, **vals})
    rows = pd.DataFrame(out)
    for c in COLS:
        if c not in rows:
            rows[c] = np.nan
    return period, {"layout": "gas7", **colmap}, rows


def add_section(rows: pd.DataFrame) -> pd.DataFrame:
    """Attach the most recent non-numeric header label(s) as section context."""
    sec, sec2 = "", ""
    s1, s2 = [], []
    for _, r in rows.iterrows():
        if r["n_num"] == 0 and r["lab1"]:
            sec2, sec = sec, r["lab1"]
        s1.append(sec)
        s2.append(sec2)
    rows = rows.copy()
    rows["section"], rows["parent_section"] = s1, s2
    return rows


def parse_r16(rows: pd.DataFrame):
    """Walk report-16 hierarchy: REGION > STATE > SECTOR > stations > owner/fuel subtotal."""
    region = state = sector = ""
    pending = []
    stations, fuel_tot, state_tot = [], [], []
    for _, r in rows.iterrows():
        l1, l2 = r["lab1"], r["lab2"]
        u1 = l1.upper()
        if r["n_num"] == 0:
            if REGION_RE.match(u1):
                region, state, sector = norm(u1), "", ""
            elif SECTOR_RE.match(u1):
                sector = norm(u1)
            elif u1:
                state, sector = norm(u1), ""
            continue
        vals = {c: r[c] for c in COLS}
        m_tot = re.match(r"^TOTAL\s+(.*)$", u1)
        if u1 == "TOTAL" or (m_tot and l2 and not SECTOR_RE.match(m_tot.group(1))):
            # state fuel-group total e.g. 'TOTAL' + 'NATURAL GAS' or packed 'TOTAL      HYDRO'
            fuel = norm(l2) if l2 else ""
            fuel_tot.append({"region": region, "state": state, "fuel_group": fuel or "(blank)", "row": r["row"], **vals})
            continue
        if m_tot and not l2:
            name = norm(m_tot.group(1))
            if state and name.replace(" ", "") == state.replace(" ", ""):
                state_tot.append({"region": region, "state": state, "label": l1, "row": r["row"], **vals})
            elif name in {"THERMAL", "HYDRO", "NUCLEAR", "NATURAL GAS", "DIESEL", "LIGNITE", "COAL"} or re.match(r"^(THERMAL|HYDRO|NUCLEAR|NATURAL GAS|DIESEL|LIGNITE|COAL)$", name):
                fuel_tot.append({"region": region, "state": state, "fuel_group": name, "row": r["row"], **vals})
            else:
                state_tot.append({"region": region, "state": state, "label": l1, "row": r["row"], "note": "unmatched TOTAL row", **vals})
            continue
        if l2:
            # owner/fuel subtotal (assign fuel to pending stations) or sector/fuel-group subtotal
            if SECTOR_RE.match(u1):
                pending = []
                continue
            for st in pending:
                st["owner"], st["fuel"] = l1, norm(l2)
            stations.extend(pending)
            pending = []
            continue
        pending.append({"region": region, "state": state, "sector": sector, "station": l1, "owner": "", "fuel": "", "row": r["row"], **vals})
    for st in pending:
        st["fuel"] = "(unassigned)"
    stations.extend(pending)
    return pd.DataFrame(stations), pd.DataFrame(fuel_tot), pd.DataFrame(state_tot)


def main():
    log = setup_logging()
    PROC.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in NPP.rglob("*.xls") if FNAME_RE.search(p.name))
    log.info("parsing %d CEA monthly ACTUAL xls files", len(files))
    long_rows, st_all, ft_all, tt_all, plog = [], [], [], [], []
    for k, p in enumerate(files, 1):
        m = FNAME_RE.search(p.name)
        no, fy, fm = int(m.group(1)), int(m.group(2)), MON[m.group(3).upper()]
        fperiod = f"{fy}-{fm:02d}"
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        try:
            period, colmap, rows = parse_cea(p)
            status = "OK"
            note = "" if period == fperiod else f"period in sheet '{period}' differs from filename '{fperiod}'"
            base = {"period": fperiod, "period_in_sheet": period, "report_no": no, "source_file": rel}
            if no == 16:
                st, ft, tt = parse_r16(rows)
                for d, acc in ((st, st_all), (ft, ft_all), (tt, tt_all)):
                    if len(d):
                        for kk, vv in base.items():
                            d[kk] = vv
                        acc.append(d)
            else:
                rows = add_section(rows)
                rows = rows[rows["n_num"] > 0]
                for kk, vv in base.items():
                    rows[kk] = vv
                long_rows.append(rows)
            plog.append({**base, "status": status, "n_rows": len(rows), "colmap": json.dumps(colmap), "note": note})
        except Exception as e:  # noqa: BLE001
            log.error("PARSE FAILED %s: %s", rel, e)
            plog.append({"period": fperiod, "period_in_sheet": "", "report_no": no, "source_file": rel,
                         "status": "FAILED", "n_rows": 0, "colmap": "", "note": f"{type(e).__name__}: {e}"})
        if k % 200 == 0:
            log.info("  parsed %d/%d", k, len(files))

    pd.DataFrame(plog).to_csv(PROC / "parse_log.csv", index=False)
    long = pd.concat(long_rows, ignore_index=True)
    lead = ["period", "period_in_sheet", "report_no", "source_file", "row", "parent_section", "section", "lab1", "lab2", "n_num"]
    long = long[lead + COLS]
    long.to_csv(PROC / "cea_rows_long.csv", index=False)

    keep = {"c1": "monitored_capacity_mw__not_for_forecasting", "c4": "gen_actual_month_gwh", "c5": "gen_actual_same_month_prev_year_gwh",
            "c9": "gen_actual_fytd_gwh", "c10": "gen_actual_fytd_prev_year_gwh", "c3": "programme_month_gwh"}

    def tidy(df, extra):
        d = df[["period", "report_no", "source_file", *extra, *keep]].rename(columns=keep)
        return d

    # report 1: national
    r1 = long[long.report_no == 1].copy()
    r1["category"] = r1["lab1"].str.upper().str.replace(r"\.$", "", regex=True)
    tidy(r1, ["category"]).to_csv(PROC / "national_monthly.csv", index=False)
    # report 2: region
    r2 = long[long.report_no == 2].copy()
    r2["region"] = r2["section"].str.upper().str.replace(r"\s+", " ", regex=True)
    r2["category"] = r2["lab1"].replace("", "(blank)").str.upper()
    tidy(r2, ["region", "category"]).to_csv(PROC / "region_monthly.csv", index=False)
    # report 3: sector
    r3 = long[long.report_no == 3].copy()
    r3["sector"] = r3["section"].str.upper()
    r3["category"] = r3["lab1"].str.upper()
    tidy(r3, ["sector", "category"]).to_csv(PROC / "sector_monthly.csv", index=False)
    # report 16
    if st_all:
        st = pd.concat(st_all, ignore_index=True)
        tidy(st, ["region", "state", "sector", "station", "owner", "fuel"]).to_csv(PROC / "station_monthly.csv", index=False)
    if ft_all:
        ft = pd.concat(ft_all, ignore_index=True)
        tidy(ft, ["region", "state", "fuel_group"]).to_csv(PROC / "state_fuel_monthly.csv", index=False)
    if tt_all:
        tt = pd.concat(tt_all, ignore_index=True)
        if "note" not in tt:
            tt["note"] = ""
        tidy(tt, ["region", "state", "label", "note"]).to_csv(PROC / "state_total_monthly.csv", index=False)
    log.info("processed tables written")

    build_dictionary(long, log)
    build_availability(log)


def ex(series, n=3):
    s = series.dropna()
    return "; ".join(str(round(x, 2)) if isinstance(x, float) else str(x) for x in s.drop_duplicates().head(n))


def build_dictionary(long: pd.DataFrame, log):
    recs = []
    # CEA monthly reports: one block per report number
    r16 = pd.read_csv(PROC / "station_monthly.csv") if (PROC / "station_monthly.csv").exists() else None
    for no in sorted(REPORT_TITLES):
        sub = long[long.report_no == no] if no != 16 else (r16.rename(columns={
            "monitored_capacity_mw__not_for_forecasting": "c1", "gen_actual_month_gwh": "c4",
            "gen_actual_same_month_prev_year_gwh": "c5", "gen_actual_fytd_gwh": "c9",
            "gen_actual_fytd_prev_year_gwh": "c10", "programme_month_gwh": "c3"}) if r16 is not None else pd.DataFrame())
        if sub.empty:
            continue
        ds = f"NPP CEA monthly ACTUAL report {no:02d} - {REPORT_TITLES[no]}"
        geo = GEO_LEVEL.get(no, "Station / utility")
        sheet = "single sheet (name varies: summary-All_India_mgr_01 / monWiseSummeryReport / OPM_MON_16)"
        label_desc = ("Row label: category / region / sector / station name (with section context)" if no != 16
                      else "Hierarchy: region, state, sector, station, owner, fuel (derived from row structure)")
        recs.append({"dataset": ds, "sheet": sheet, "column": "row labels (lab1/lab2/section)", "data_type": "string",
                     "description": label_desc, "unit": "", "classification": "Identifier / geography",
                     "geographical_level": geo, "temporal_granularity": "monthly file", "missing_pct": 0.0,
                     "example_values": ex(sub["lab1"] if "lab1" in sub else sub["station"]),
                     "usage_eligibility": "ELIGIBLE (keys)", "remarks": "labels copied verbatim; spelling variants recorded in quality report"})
        for c in COLS:
            if c not in sub or sub[c].isna().all():
                continue  # column not present in this report's layout
            desc, unit, cls, gran, elig = COL_MEANING[c]
            recs.append({"dataset": ds, "sheet": sheet, "column": f"{c} (CEA col #{c[1:]})", "data_type": "float",
                         "description": desc, "unit": unit, "classification": cls, "geographical_level": geo,
                         "temporal_granularity": gran,
                         "missing_pct": round(100 * sub[c].isna().mean(), 2),
                         "example_values": ex(sub[c]), "usage_eligibility": elig,
                         "remarks": ("Values are ACTUAL (from 'Monthly Reports ACTUAL'); hydro/Bhutan rows have no PLF"
                                     if c in ("c4", "c9") else "")})
    # Renewable India CSV
    if GH_CSV.exists():
        g = pd.read_csv(GH_CSV)
        meta = {
            "State": ("State / UT name", "", "Identifier / geography", "ELIGIBLE (key; needs mapping to NPP spellings)"),
            "Year": ("Year of observation (README does not state calendar vs financial year)", "year", "Identifier / time", "ELIGIBLE (key) - year basis UNVERIFIED"),
            "Installed - Bio-Mass Power": ("Installed biomass capacity", "MW", "Installed capacity", "NOT ELIGIBLE (capacity)"),
            "Installed - Small Hydro Power": ("Installed small-hydro capacity", "MW", "Installed capacity", "NOT ELIGIBLE (capacity)"),
            "Installed - Solar Power": ("Installed solar capacity", "MW", "Installed capacity", "NOT ELIGIBLE (capacity)"),
            "Installed - Wind Power": ("Installed wind capacity", "MW", "Installed capacity", "NOT ELIGIBLE (capacity)"),
            "Zone": ("Zone label assigned by dataset author", "", "Identifier / geography", "USE WITH CAUTION (does not match CEA regions)"),
            "Installed - Waste to Energy": ("Installed waste-to-energy capacity", "MW", "Installed capacity", "NOT ELIGIBLE (capacity)"),
            "Population": ("Estimated population", "persons", "Demographic variable", "ELIGIBLE (supporting) - partly model-predicted, UNVERIFIED"),
            "GSDP (crore INR)": ("Gross State Domestic Product, nominal", "INR crore (nominal)", "Economic variable", "ELIGIBLE (supporting) - partly model-predicted, nominal, UNVERIFIED"),
        }
        for c in g.columns:
            d, u, cls, el = meta.get(c, ("UNVERIFIED", "", "Unknown / unverified", "UNVERIFIED"))
            recs.append({"dataset": "Renewable India dataset (renewable_energy_dataset.csv)", "sheet": "(csv)", "column": c,
                         "data_type": str(g[c].dtype), "description": d, "unit": u, "classification": cls,
                         "geographical_level": "State/UT", "temporal_granularity": "annual",
                         "missing_pct": round(100 * g[c].isna().mean(), 2), "example_values": ex(g[c]),
                         "usage_eligibility": el,
                         "remarks": "README: some missing values were predicted with XGBoost regression; imputed cells are NOT flagged"})
    # dashboard snapshot
    for p in (NPP / "other_reports" / "dashboard_snapshot").glob("*.json"):
        recs.append({"dataset": "NPP dashboard getAllZone snapshot", "sheet": p.name, "column": "installed_Capacity.res_solar_power / res_wind_power / ...",
                     "data_type": "float", "description": "Current installed capacity by type incl. RE", "unit": "MW",
                     "classification": "Installed capacity", "geographical_level": "National", "temporal_granularity": "single current snapshot",
                     "missing_pct": 0, "example_values": "", "usage_eligibility": "NOT ELIGIBLE (capacity)", "remarks": "no historical series"})
        recs.append({"dataset": "NPP dashboard getAllZone snapshot", "sheet": p.name, "column": "headerMap.GN_OBJ.actual_generation",
                     "data_type": "float", "description": "Actual conventional generation for latest day / FY-to-date", "unit": "MU",
                     "classification": "Actual energy generation", "geographical_level": "National", "temporal_granularity": "single current snapshot",
                     "missing_pct": 0, "example_values": "", "usage_eligibility": "NOT USED (snapshot only; monthly reports supersede)", "remarks": ""})
    pd.DataFrame(recs).to_csv(REPORTS / "data_dictionary.csv", index=False)
    log.info("data dictionary: %d entries", len(recs))


def cov(df: pd.DataFrame, col="period"):
    if df is None or df.empty:
        return "", 0
    ps = sorted(df[col].dropna().unique())
    return f"{ps[0]} to {ps[-1]}", len(ps)


def build_availability(log):
    nat = pd.read_csv(PROC / "national_monthly.csv")
    reg = pd.read_csv(PROC / "region_monthly.csv")
    stf = pd.read_csv(PROC / "state_fuel_monthly.csv") if (PROC / "state_fuel_monthly.csv").exists() else pd.DataFrame()
    stn = pd.read_csv(PROC / "station_monthly.csv") if (PROC / "station_monthly.csv").exists() else pd.DataFrame()
    stt = pd.read_csv(PROC / "state_total_monthly.csv") if (PROC / "state_total_monthly.csv").exists() else pd.DataFrame()
    long = pd.read_csv(PROC / "cea_rows_long.csv", low_memory=False)
    g = pd.read_csv(GH_CSV) if GH_CSV.exists() else pd.DataFrame()

    def nat_cat(pat):
        return nat[nat.category.str.contains(pat, case=False, na=False)]

    def fuel_rows(pat, reports):
        return long[long.report_no.isin(reports) & long.lab1.str.contains(pat, case=False, na=False)]

    n_c, n_n = cov(nat)
    rows = []

    def add(req, status, ds, c, gran, unit, ev):
        rows.append({"data_requirement": req, "status": status, "dataset": ds, "historical_coverage": c,
                     "granularity": gran, "unit": unit, "evidence_notes": ev})

    add("National generation", "AVAILABLE" if n_n else "NOT AVAILABLE", "NPP report 01 (All India), also 02/04/17",
        f"{n_c} ({n_n} months)", "monthly (c4) + FY-to-date cumulative (c9)", "GWh (=MU)",
        "Conventional generation only: THERMAL, NUCLEAR, HYDRO (>25 MW), BHUTAN IMPORT. Excludes RE (solar, wind, small hydro, biomass).")
    add("Region-wise generation", "AVAILABLE" if len(reg) else "NOT AVAILABLE", "NPP report 02 (Region Wise)",
        "{} ({} months)".format(*cov(reg)), "monthly; 5 regions x THERMAL/NUCLEAR/HYDRO + Bhutan import", "GWh",
        "Conventional only. Regions: Northern, Western, Southern, Eastern, North Eastern.")
    ns = stt["state"].nunique() if len(stt) else 0
    add("State-wise generation", "PARTIALLY AVAILABLE" if len(stt) else "NOT AVAILABLE", "NPP report 16 'TOTAL <STATE>' rows",
        "{} ({} months)".format(*cov(stt)), f"monthly; {ns} states/UTs with conventional stations", "GWh",
        "Generation by LOCATION of monitored conventional stations (>25 MW). States with no monitored conventional plant are absent. No RE.")
    add("Station-wise generation", "AVAILABLE" if len(stn) else "NOT AVAILABLE", "NPP report 16 station rows (+ reports 5-15)",
        "{} ({} months)".format(*cov(stn)), f"monthly; ~{stn.groupby('period').station.nunique().median() if len(stn) else 0:.0f} stations/month", "GWh",
        "Monitored conventional stations only.")
    coal = fuel_rows(r"^TOTAL COAL BASED", [11])
    lig = fuel_rows(r"^TOTAL LIGNITE", [11])
    add("Coal generation", "AVAILABLE" if len(coal) else "UNVERIFIED", "NPP report 11 ('TOTAL COAL BASED'); state-level via report 16 THERMAL group",
        "{} ({} months)".format(*cov(coal)), "monthly, national (+ sector); state-level only as THERMAL group", "GWh",
        f"Lignite separately in report 11 ('TOTAL LIGNITE BASED', {cov(lig)[1]} months). At state level coal is reported inside 'THERMAL' group.")
    hyd = nat_cat("^HYDRO")
    add("Hydro generation", "PARTIALLY AVAILABLE" if len(hyd) else "NOT AVAILABLE", "NPP reports 01/02/16",
        "{} ({} months)".format(*cov(hyd)), "monthly; national, regional, state, station", "GWh",
        "Large hydro (>25 MW) only. Small hydro generation NOT available (only small-hydro capacity in GitHub dataset).")
    nuc = nat_cat("^NUCLEAR")
    add("Nuclear generation", "AVAILABLE" if len(nuc) else "NOT AVAILABLE", "NPP reports 01/02/10/16",
        "{} ({} months)".format(*cov(nuc)), "monthly; national, regional, state, station", "GWh", "")
    gas_state = stf[stf.fuel_group.str.contains("GAS", case=False, na=False)] if len(stf) else pd.DataFrame()
    add("Natural gas generation", "AVAILABLE" if len(gas_state) else "UNVERIFIED", "NPP reports 12-14 (gas & liquid fuel by sector), 16 ('NATURAL GAS' group), 17-20",
        "{} ({} months)".format(*cov(gas_state)), "monthly; station, state (report 16), national via sector totals", "GWh",
        "Reports 12-14 combine gas and liquid fuel stations; report 16 state 'NATURAL GAS' group gives gas at state level.")
    add("Solar generation", "NOT AVAILABLE", "none", "", "", "",
        "NPP monthly/daily generation reports cover conventional sources only. NPP dashboard and GitHub dataset contain only solar INSTALLED CAPACITY (prohibited as substitute).")
    add("Wind generation", "NOT AVAILABLE", "none", "", "", "",
        "Same as solar: only wind INSTALLED CAPACITY exists in authorised sources.")
    if len(g):
        yrs = f"{g.Year.min()} to {g.Year.max()}"
        add("Population", "PARTIALLY AVAILABLE", "Renewable India dataset", f"{yrs} ({g.Year.nunique()} years)",
            f"annual, {g.State.nunique()} states/UTs (unbalanced panel, {len(g)} rows)", "persons",
            "README states some values were predicted by XGBoost; imputed cells not flagged; year basis (CY/FY) not documented.")
        add("GSDP", "PARTIALLY AVAILABLE", "Renewable India dataset", f"{yrs} ({g.Year.nunique()} years)",
            "annual, state", "INR crore (nominal)", "Nominal (not inflation adjusted); partly model-predicted; not flagged.")
    else:
        add("Population", "NOT AVAILABLE", "", "", "", "", "GitHub dataset missing")
        add("GSDP", "NOT AVAILABLE", "", "", "", "", "GitHub dataset missing")
    add("Geographic indicators", "NOT AVAILABLE", "none", "", "", "",
        "Only categorical region/zone labels exist. No area, land availability, terrain or resource-potential data in authorised sources.")
    add("Climatic indicators", "NOT AVAILABLE", "none", "", "", "", "No irradiance, wind speed, rainfall or temperature data in authorised sources.")
    add("Urbanization indicators", "NOT AVAILABLE", "none", "", "", "", "No urban population share or urbanisation rate in authorised sources.")
    pd.DataFrame(rows).to_csv(REPORTS / "data_availability.csv", index=False)
    log.info("availability matrix written")


if __name__ == "__main__":
    main()
