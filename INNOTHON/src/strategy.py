"""
strategy.py  (Phase 4) - 2047 strategy tables, energy-mix framework, validation and strategy reports.

Inputs: Phase 2/3 outputs only (outputs/data, outputs/forecasts, outputs/scenarios, outputs/backtesting).
Nothing in data/raw or the Phase 3 reports is modified.

Three layers are kept separate in every output (column `layer`):
  actual                 published CEA monthly ACTUAL generation (FY totals)
  statistical forecast   Phase 3 reconciled ETS forecasts (FY2026-27, FY2027-28)
  scenario projection    Phase 3 approved low/central/high paths to FY2046-47 (assumption-driven)
  policy scenario        source-allocation RECOMMENDATIONS (this module) - not forecasts

Energy-mix framework (shares of DOMESTIC CONVENTIONAL generation only; solar, wind, small hydro and
biomass are NOT quantified anywhere):
  Trend reference T1  damped linear share trend (Phase 3 output, phi=0.8) - flagged artefacts
  Trend reference T2  constant FY2025-26 shares
  Trend reference T3  regime-adjusted: gas = mean share after its FY2022-23 structural step,
                      others as T1  (recommended trend reference)
  Policy P0..P3       documented allocation rules, each justified by observed data (see POLICY)
Every mix sums exactly to the scenario total (coal/lignite is the balancing item); lignite is split
from coal only nationally. Region x source matrices use iterative proportional fitting (IPF) seeded with
the FY2025-26 region x source pattern, matching regional totals and national source totals exactly.
"""
from __future__ import annotations

import datetime as dt
import json

import numpy as np
import pandas as pd

from common import BT, DATA, FC, MODELS, REPORTS, ROOT, SC, md_table

OUT = ROOT / "outputs" / "strategy"
OUT.mkdir(parents=True, exist_ok=True)
TODAY = dt.date.today().isoformat()
SRC = ["COAL", "LIGNITE", "NATURAL_GAS", "DIESEL", "NUCLEAR", "HYDRO"]
SRC5 = ["COAL_LIGNITE", "NATURAL_GAS", "DIESEL", "NUCLEAR", "HYDRO"]
REGIONS = ["Northern", "Western", "Southern", "Eastern", "North Eastern"]
SCEN = ["low", "central", "high"]
QS = ["p10", "p50", "p90"]
FULL_FYS = [f"FY{y}-{str(y + 1)[2:]}" for y in range(2019, 2026)]
SCOPE = ("> **Scope.** Domestic **conventional** generation monitored by CEA (coal, lignite, gas, diesel, nuclear, large hydro). "
         "Solar, wind, small hydro and biomass generation are **not quantified** (no authorised actual-generation data), so totals are "
         "**not** India's total electricity production or requirement. Generation location is not consumption. Bhutan import is separate.\n")
CONF = {"A": "Higher - direct ETS, stable series", "B": "Medium - direct ETS, intervals widened x1.25",
        "C": "Low - allocated from region (seasonal naive / share); indicative only"}
checks = []


def ck(name, diff, tol=1.0, detail=""):
    checks.append({"check": name, "max_abs_diff_gwh": float(diff), "tolerance_gwh": tol, "result": "PASS" if diff <= tol else "FAIL", "detail": detail})


def fy(y):
    return f"FY{y}-{str(y + 1)[2:]}"


def cagr(a, b, n):
    return (b / a) ** (1 / n) - 1 if a > 0 and b > 0 else np.nan


def ipf(seed: pd.DataFrame, row_t: pd.Series, col_t: pd.Series, iters=500) -> pd.DataFrame:
    """Scale seed (rows=regions, cols=sources) to match row and column totals exactly (zeros stay zero)."""
    m = seed.astype(float).copy()
    col_t = col_t * row_t.sum() / col_t.sum()
    for _ in range(iters):
        m = m.mul(row_t / m.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
        m = m.mul(col_t / m.sum(axis=0).replace(0, np.nan), axis=1).fillna(0)
        if (m.sum(axis=1) - row_t).abs().max() < 1e-6:
            break
    return m


def main():
    # ------------------------------------------------------------------ load
    fyn = pd.read_csv(DATA / "fy_national.csv")
    fyr = pd.read_csv(DATA / "fy_regional.csv")
    fys = pd.read_csv(DATA / "fy_state.csv")
    meta = pd.read_csv(DATA / "node_metadata.csv").set_index("node_id")
    fcf = pd.read_csv(FC / "fy_forecast.csv")
    mf = pd.read_csv(FC / "monthly_forecast.csv")
    base = pd.read_csv(FC / "base_forecast_unreconciled.csv")
    nat = pd.read_csv(SC / "fy_scenarios_national.csv")
    r47 = pd.read_csv(SC / "fy2047_regional.csv")
    s47 = pd.read_csv(SC / "fy2047_state.csv")
    src47 = pd.read_csv(SC / "fy2047_source.csv")
    asm = json.loads((SC / "scenario_assumptions.json").read_text(encoding="utf-8"))
    sel = pd.read_csv(MODELS / "selected_models_A.csv")

    dom = fyn[(fyn.series == "DOMESTIC_CONVENTIONAL_TOTAL") & fyn.fy.isin(FULL_FYS)].set_index("fy").fy_total_gwh
    bhu = fyn[(fyn.series == "BHUTAN_IMPORT") & fyn.fy.isin(FULL_FYS)].set_index("fy").fy_total_gwh
    srcfy = fyn[fyn.series.isin(SRC) & fyn.fy.isin(FULL_FYS)].pivot(index="fy", columns="series", values="fy_total_gwh")[SRC]
    sh = srcfy.div(srcfy.sum(axis=1), axis=0)
    ck("Historical: national sources sum to domestic total (FY)", (srcfy.sum(axis=1) - dom).abs().max())

    # ------------------------------------------------------------------ national strategy table
    rows = []
    for f_, v in dom.items():
        rows.append({"fy": f_, "layer": "actual", "scenario": "all", "series": "DOMESTIC_CONVENTIONAL_TOTAL", "p10_gwh": np.nan, "p50_gwh": v, "p90_gwh": np.nan,
                     "lo95_gwh": np.nan, "hi95_gwh": np.nan, "note": "published CEA ACTUAL (FY2019-20 from March cumulative)"})
        rows.append({"fy": f_, "layer": "actual", "scenario": "all", "series": "BHUTAN_IMPORT (separate)", "p50_gwh": bhu[f_], "note": "not domestic"})
    for f_ in ["FY2026-27", "FY2027-28"]:
        t = fcf[(fcf.node_id == "TOTAL") & (fcf.fy == f_)].iloc[0]
        rows.append({"fy": f_, "layer": "statistical forecast", "scenario": "all", "series": "DOMESTIC_CONVENTIONAL_TOTAL (reconciled BU)",
                     "p10_gwh": t.fy_lo80, "p50_gwh": t.fy_total_gwh, "p90_gwh": t.fy_hi80, "lo95_gwh": t.fy_lo95, "hi95_gwh": t.fy_hi95,
                     "note": f"{int(t.actual_months)} actual + {12 - int(t.actual_months)} forecast months; p10/p90 columns hold the 80% interval"
                             + ("; includes months beyond validated 12-month horizon" if t.includes_beyond_validated_horizon else "")})
        months = [str(pd.Period(f"{2026 if f_ == 'FY2026-27' else 2027}-04", freq="M") + k) for k in range(12)]
        act = float(t.actual_part_gwh)
        ub = base[(base.node_id == "TOTAL") & base.period.isin(months)].base_forecast_gwh.sum()
        rows.append({"fy": f_, "layer": "statistical forecast", "scenario": "all", "series": "DOMESTIC_CONVENTIONAL_TOTAL (unreconciled national ETS, comparison)",
                     "p50_gwh": act + ub, "note": "comparison only - not the official hierarchy"})
        b = fcf[(fcf.node_id == "IMPORT|BHUTAN") & (fcf.fy == f_)].iloc[0]
        rows.append({"fy": f_, "layer": "statistical forecast", "scenario": "all", "series": "BHUTAN_IMPORT (separate)", "p10_gwh": b.fy_lo80,
                     "p50_gwh": b.fy_total_gwh, "p90_gwh": b.fy_hi80, "lo95_gwh": b.fy_lo95, "hi95_gwh": b.fy_hi95, "note": "Holt-Winters; not domestic"})
    for _, r in nat[nat.fy_start >= 2028].iterrows():
        rows.append({"fy": r.fy, "layer": "scenario projection", "scenario": r.scenario, "series": "DOMESTIC_CONVENTIONAL_TOTAL",
                     "p10_gwh": r.p10_gwh, "p50_gwh": r.p50_gwh, "p90_gwh": r.p90_gwh, "growth_assumed": r.growth_assumed,
                     "deterministic_gwh": r.deterministic_gwh, "note": "assumption-driven projection, not a prediction"})
    ns = pd.DataFrame(rows)
    ns.to_csv(OUT / "national_strategy.csv", index=False)
    approved = {"low": (1564, 1248, 1970), "central": (2352, 1863, 2968), "high": (3690, 2944, 4624)}
    n47 = nat[nat.fy_start == 2046].set_index("scenario")
    for s, (m, lo, hi) in approved.items():
        d = max(abs(n47.loc[s, "p50_gwh"] / 1000 - m), abs(n47.loc[s, "p10_gwh"] / 1000 - lo), abs(n47.loc[s, "p90_gwh"] / 1000 - hi))
        ck(f"Approved 2047 {s} scenario reproduced (TWh, rounding)", d, 0.5, "median, P10, P90 vs approved values")

    # ------------------------------------------------------------------ energy mix: trend references
    yrs = 21  # FY2025-26 -> FY2046-47
    t1 = src47[(src47.scenario == "central") & (src47["quantile"] == "p50")].set_index("source").share_damped_trend.reindex(SRC)
    t2 = sh.loc["FY2025-26"]
    gas_post = sh.loc[["FY2022-23", "FY2023-24", "FY2024-25", "FY2025-26"], "NATURAL_GAS"].mean()
    t3 = t1.copy()
    t3["NATURAL_GAS"] = gas_post
    t3["COAL"] = 1 - t3.drop("COAL").sum()
    # diagnostics of each source trend
    diag = []
    for s in SRC:
        x = np.arange(len(sh))
        slope = np.polyfit(x, sh[s].values, 1)[0]
        resid = sh[s].values - np.polyval(np.polyfit(x, sh[s].values, 1), x)
        post = sh[s].iloc[3:]
        diag.append({"source": s, "share_FY2019_20_%": 100 * sh[s].iloc[0], "share_FY2025_26_%": 100 * sh[s].iloc[-1],
                     "min_%": 100 * sh[s].min(), "max_%": 100 * sh[s].max(), "linear_slope_pp_per_yr": 100 * slope,
                     "post_FY2022_23_slope_pp_per_yr": 100 * np.polyfit(np.arange(len(post)), post.values, 1)[0],
                     "T1_damped_2047_%": 100 * t1[s], "T2_constant_%": 100 * t2[s], "T3_regime_adjusted_%": 100 * t3[s]})
    diag = pd.DataFrame(diag)
    artefacts = {
        "NATURAL_GAS": f"ARTEFACT: share fell 4.16% -> 1.69% between FY2020-21 and FY2022-23 (a one-off step), then stayed flat (1.69-2.07%) for 4 years; "
                       f"the 7-point linear trend extends the step and drives the share to {100 * t1['NATURAL_GAS']:.2f}%. The reconciled statistical forecast "
                       f"rises to {100 * fcf[(fcf.node_id == 'NSRC|NATURAL_GAS') & (fcf.fy == 'FY2027-28')].fy_total_gwh.iloc[0] / fcf[(fcf.node_id == 'TOTAL') & (fcf.fy == 'FY2027-28')].fy_total_gwh.iloc[0]:.2f}% in FY2027-28, contradicting the trend. Use T3 (post-step mean {100 * gas_post:.2f}%).",
        "LIGNITE": "Steady decline 2.65% -> 1.98% (consistent direction all 7 FYs); damped trend is plausible but rests on 7 points - QUALIFIED.",
        "DIESEL": "Negligible (<0.05%); trend from very small numbers - not meaningful.",
        "HYDRO": "Weather-driven (8.9%-12.5%); Phase 3 uses the 7-FY mean, no trend - appropriate.",
        "NUCLEAR": "3.2-3.7%, no clear trend; damped trend keeps it near 3.6% - plausible.",
        "COAL": "Balancing item; inherits every other assumption.",
    }
    diag["assessment"] = diag.source.map(artefacts)
    diag.to_csv(OUT / "source_trend_diagnostics.csv", index=False)

    # ------------------------------------------------------------------ energy mix: policy scenarios
    lig_in_cl = srcfy.loc["FY2025-26", "LIGNITE"] / (srcfy.loc["FY2025-26", "COAL"] + srcfy.loc["FY2025-26", "LIGNITE"])
    mx_share = sh.max()
    mx_abs = srcfy.max()
    POLICY = {
        "P0_status_quo_FY2025_26": ("Hold the latest observed mix (FY2025-26).", "Latest complete year; no change in relative roles of sources."),
        "P1_historical_average": ("Mean shares FY2019-20..FY2025-26.", "Smooths hydrology (wet/dry years) and gas-price episodes across 7 observed years."),
        "P2_demonstrated_max_share": ("Each non-coal source at its highest observed FY share (hydro, nuclear, gas); lignite and diesel at FY2025-26 share; coal = balance.",
                                      "Every share has already been achieved by the existing system within FY2019-20..FY2025-26; lowest coal dependence demonstrated in the data."),
        "P3_no_decline_floor": ("Each non-coal source at least its highest observed annual generation (TWh) - never below demonstrated output; otherwise FY2025-26 share; coal/lignite = balance.",
                                "Protects demonstrated hydro, nuclear and gas output from being crowded out; effect largest in the low scenario."),
    }
    mixes = []

    def add_mix(framework, variant, scen, q, total, shares_or_gwh, justification, rule):
        g = pd.Series(shares_or_gwh, dtype=float)
        if g.sum() <= 1.0 + 1e-9:  # shares
            g = g * total
        cl = total - g.drop(["COAL", "LIGNITE"], errors="ignore").sum()
        if "COAL" in g.index and framework == "trend reference":
            pass
        else:
            g["COAL"], g["LIGNITE"] = cl * (1 - lig_in_cl), cl * lig_in_cl
        g = g.reindex(SRC).fillna(0)
        g["COAL"] += total - g.sum()  # exact closure
        for s in SRC:
            mixes.append({"framework": framework, "variant": variant, "scenario": scen, "quantile": q, "fy": "FY2046-47", "source": s,
                          "gwh": g[s], "share": g[s] / total, "total_conventional_gwh": total, "rule": rule, "justification": justification,
                          "layer": "scenario projection" if framework == "trend reference" else "policy scenario",
                          "flag": artefacts.get(s, "") if (framework == "trend reference" and variant.startswith("T1") and s in ("NATURAL_GAS", "LIGNITE")) else ""})

    for scn in SCEN:
        for q in QS:
            total = n47.loc[scn, f"{q}_gwh"]
            add_mix("trend reference", "T1_damped_trend (Phase 3)", scn, q, total, t1.to_dict(), "Phase 3 damped share trend (phi=0.8); hydro = 7-FY mean", "statistical extrapolation of shares")
            add_mix("trend reference", "T2_constant_FY2025_26", scn, q, total, t2.to_dict(), "Shares frozen at latest observed FY", "no trend")
            add_mix("trend reference", "T3_regime_adjusted (recommended reference)", scn, q, total, t3.to_dict(),
                    f"T1 with gas at its post-FY2022-23 mean ({100 * gas_post:.2f}%) - removes the gas artefact", "trend with structural-break correction")
            p0 = {s: t2[s] for s in ["NATURAL_GAS", "DIESEL", "NUCLEAR", "HYDRO"]}
            add_mix("policy", "P0_status_quo_FY2025_26", scn, q, total, p0, POLICY["P0_status_quo_FY2025_26"][1], POLICY["P0_status_quo_FY2025_26"][0])
            p1 = {s: sh[s].mean() for s in ["NATURAL_GAS", "DIESEL", "NUCLEAR", "HYDRO"]}
            add_mix("policy", "P1_historical_average", scn, q, total, p1, POLICY["P1_historical_average"][1], POLICY["P1_historical_average"][0])
            p2 = {"NATURAL_GAS": mx_share["NATURAL_GAS"], "NUCLEAR": mx_share["NUCLEAR"], "HYDRO": mx_share["HYDRO"], "DIESEL": t2["DIESEL"]}
            add_mix("policy", "P2_demonstrated_max_share", scn, q, total, p2, POLICY["P2_demonstrated_max_share"][1], POLICY["P2_demonstrated_max_share"][0])
            p3 = {s: max(t2[s] * total, mx_abs[s]) for s in ["NATURAL_GAS", "NUCLEAR", "HYDRO"]}
            p3["DIESEL"] = t2["DIESEL"] * total
            add_mix("policy", "P3_no_decline_floor", scn, q, total, p3, POLICY["P3_no_decline_floor"][1], POLICY["P3_no_decline_floor"][0])
    mix = pd.DataFrame(mixes)
    # T1/T2/T3 COAL handling: shares already include coal & lignite -> closure via exact sum
    clos = mix.groupby(["framework", "variant", "scenario", "quantile"]).apply(lambda g: abs(g.gwh.sum() - g.total_conventional_gwh.iloc[0])).max()
    ck("Every source mix sums exactly to its conventional total", clos, 1e-6)
    ck("No negative source allocation", float(max(0, -mix.gwh.min())), 1e-9)
    mix.to_csv(OUT / "source_mix_scenarios.csv", index=False)

    # ------------------------------------------------------------------ regional strategy
    rt = fyr[(fyr.series == "DOMESTIC_CONVENTIONAL_TOTAL") & fyr.fy.isin(FULL_FYS)].pivot(index="fy", columns="region", values="fy_total_gwh")[REGIONS]
    ck("Historical: sum of regions = national (FY)", (rt.sum(axis=1) - dom).abs().max())
    cells = fys[(fys.series != "STATE_TOTAL") & fys.fy.isin(FULL_FYS)].groupby(["fy", "region", "series"]).fy_total_gwh.sum().unstack().reindex(columns=SRC5).fillna(0)
    rmix26 = cells.loc["FY2025-26"].reindex(REGIONS)
    rrows, rsum = [], []
    for r in REGIONS:
        for f_ in FULL_FYS:
            rrows.append({"region": r, "fy": f_, "layer": "actual", "scenario": "all", "quantile": "actual", "gwh": rt.loc[f_, r],
                          "share_of_national": rt.loc[f_, r] / dom[f_]})
            for s in SRC5:
                rrows.append({"region": r, "fy": f_, "layer": "actual", "scenario": "all", "quantile": "actual", "source": s,
                              "gwh": cells.loc[(f_, r), s] if (f_, r) in cells.index else 0.0})
        for f_ in ["FY2026-27", "FY2027-28"]:
            t = fcf[(fcf.node_id == f"REG|{r}") & (fcf.fy == f_)].iloc[0]
            tn = fcf[(fcf.node_id == "TOTAL") & (fcf.fy == f_)].iloc[0]
            rrows.append({"region": r, "fy": f_, "layer": "statistical forecast", "scenario": "all", "quantile": "p50", "gwh": t.fy_total_gwh,
                          "lo80": t.fy_lo80, "hi80": t.fy_hi80, "lo95": t.fy_lo95, "hi95": t.fy_hi95, "share_of_national": t.fy_total_gwh / tn.fy_total_gwh})
        for scn in SCEN:
            for q in QS:
                x = r47[(r47.scenario == scn) & (r47["quantile"] == q) & (r47.region == r)].iloc[0]
                rrows.append({"region": r, "fy": "FY2046-47", "layer": "scenario projection", "scenario": scn, "quantile": q,
                              "gwh": x.gwh_damped_trend, "gwh_constant_share_alt": x.gwh_constant_share, "share_of_national": x.share_damped_trend})
        a, b = rt.loc["FY2019-20", r], rt.loc["FY2025-26", r]
        m26 = rmix26.loc[r] / rmix26.loc[r].sum()
        f27 = fcf[(fcf.node_id == f"REG|{r}") & (fcf.fy == "FY2026-27")].iloc[0]
        c47 = r47[(r47.scenario == "central") & (r47["quantile"] == "p50") & (r47.region == r)].iloc[0]
        rsum.append({"region": r, "FY2019-20_gwh": a, "FY2025-26_gwh": b, "CAGR_FY19-20_to_FY25-26_%": 100 * cagr(a, b, 6),
                     "share_of_national_FY2025-26_%": 100 * b / dom["FY2025-26"],
                     **{f"mix_{s}_%": 100 * m26[s] for s in SRC5},
                     "FY2026-27_forecast_gwh": f27.fy_total_gwh, "FY2026-27_lo95": f27.fy_lo95, "FY2026-27_hi95": f27.fy_hi95,
                     "forecast_growth_FY26-27_vs_FY25-26_%": 100 * (f27.fy_total_gwh / b - 1),
                     "share_2047_damped_%": 100 * c47.share_damped_trend, "share_2047_constant_%": 100 * c47.share_constant,
                     **{f"2047_{scn}_p50_gwh": r47[(r47.scenario == scn) & (r47["quantile"] == "p50") & (r47.region == r)].gwh_damped_trend.iloc[0] for scn in SCEN},
                     "2047_central_p10_gwh": r47[(r47.scenario == "central") & (r47["quantile"] == "p10") & (r47.region == r)].gwh_damped_trend.iloc[0],
                     "2047_central_p90_gwh": r47[(r47.scenario == "central") & (r47["quantile"] == "p90") & (r47.region == r)].gwh_damped_trend.iloc[0]})
    rsum = pd.DataFrame(rsum)
    # evidence-based strengths (rules on observed data only)
    strengths = {}
    for _, r in rsum.iterrows():
        s = []
        if r["share_of_national_FY2025-26_%"] == rsum["share_of_national_FY2025-26_%"].max():
            s.append(f"largest conventional generator ({r['share_of_national_FY2025-26_%']:.1f}% of national FY2025-26)")
        if r["CAGR_FY19-20_to_FY25-26_%"] == rsum["CAGR_FY19-20_to_FY25-26_%"].max():
            s.append(f"fastest growth FY19-20->FY25-26 ({r['CAGR_FY19-20_to_FY25-26_%']:.1f}%/yr)")
        if r["mix_HYDRO_%"] >= 15:
            s.append(f"high large-hydro share ({r['mix_HYDRO_%']:.1f}%)")
        if r["mix_NUCLEAR_%"] == rsum["mix_NUCLEAR_%"].max():
            s.append(f"highest nuclear share ({r['mix_NUCLEAR_%']:.1f}%)")
        if r["mix_NATURAL_GAS_%"] >= 10:
            s.append(f"substantial gas generation ({r['mix_NATURAL_GAS_%']:.1f}%)")
        if r["mix_COAL_LIGNITE_%"] >= 90:
            s.append(f"coal/lignite-dominant ({r['mix_COAL_LIGNITE_%']:.1f}%) - concentration risk")
        strengths[r.region] = "; ".join(s) or "no distinctive feature beyond its share"
    rsum["data_supported_characteristics"] = rsum.region.map(strengths)
    rsum.to_csv(OUT / "regional_summary.csv", index=False)
    rs = pd.DataFrame(rrows)
    # region x source 2047 via IPF (trend reference T3 and policy variants) - exact margins
    rx = []
    for (fw, var, scn, q), g in mix.groupby(["framework", "variant", "scenario", "quantile"]):
        nat_src = g.set_index("source").gwh
        col_t = pd.Series({"COAL_LIGNITE": nat_src["COAL"] + nat_src["LIGNITE"], "NATURAL_GAS": nat_src["NATURAL_GAS"],
                           "DIESEL": nat_src["DIESEL"], "NUCLEAR": nat_src["NUCLEAR"], "HYDRO": nat_src["HYDRO"]})
        row_t = r47[(r47.scenario == scn) & (r47["quantile"] == q)].set_index("region").gwh_damped_trend.reindex(REGIONS)
        m = ipf(rmix26[SRC5], row_t, col_t)
        for reg in REGIONS:
            for s in SRC5:
                rx.append({"framework": fw, "variant": var, "scenario": scn, "quantile": q, "region": reg, "source": s, "gwh": m.loc[reg, s]})
        ck_r = float((m.sum(axis=1) - row_t).abs().max())
        ck_c = float((m.sum(axis=0) - col_t).abs().max())
        if (ck_r > 1 or ck_c > 1):
            checks.append({"check": f"IPF margins {var} {scn} {q}", "max_abs_diff_gwh": max(ck_r, ck_c), "tolerance_gwh": 1, "result": "FAIL", "detail": ""})
    rx = pd.DataFrame(rx)
    worst = rx.groupby(["variant", "scenario", "quantile", "region"]).gwh.sum().reset_index().merge(
        r47.rename(columns={"gwh_damped_trend": "t"})[["scenario", "quantile", "region", "t"]], on=["scenario", "quantile", "region"])
    ck("Region x source 2047 (IPF): rows = regional totals", (worst.gwh - worst.t).abs().max())
    cs = rx.groupby(["framework", "variant", "scenario", "quantile", "source"]).gwh.sum().reset_index()
    mm = mix.assign(source5=mix.source.replace({"COAL": "COAL_LIGNITE", "LIGNITE": "COAL_LIGNITE"})).groupby(["framework", "variant", "scenario", "quantile", "source5"]).gwh.sum().reset_index()
    cc = cs.merge(mm, left_on=["framework", "variant", "scenario", "quantile", "source"], right_on=["framework", "variant", "scenario", "quantile", "source5"])
    ck("Region x source 2047 (IPF): columns = national source totals", (cc.gwh_x - cc.gwh_y).abs().max())
    rx.to_csv(OUT / "regional_source_mix_2047.csv", index=False)
    rs.to_csv(OUT / "regional_strategy.csv", index=False)

    # ------------------------------------------------------------------ state strategy
    stt = fys[(fys.series == "STATE_TOTAL") & fys.fy.isin(FULL_FYS)].groupby(["state_harmonised", "region", "fy"]).fy_total_gwh.sum().unstack()
    stc = fys[(fys.series != "STATE_TOTAL") & (fys.fy == "FY2025-26")].groupby(["state_harmonised", "series"]).fy_total_gwh.sum().unstack().reindex(columns=SRC5).fillna(0)
    srows, ssum = [], []
    for (s, r), v in stt.iterrows():
        nid = f"ST|{s}"
        grp = meta.group.get(nid, "")
        reg_tot = rt[r]
        for f_ in FULL_FYS:
            if pd.notna(v.get(f_)):
                srows.append({"state": s, "region": r, "group": grp, "fy": f_, "layer": "actual", "scenario": "all", "quantile": "actual",
                              "gwh": v[f_], "share_of_region": v[f_] / reg_tot[f_]})
        for src in SRC5:
            srows.append({"state": s, "region": r, "group": grp, "fy": "FY2025-26", "layer": "actual", "scenario": "all", "quantile": "actual",
                          "source": src, "gwh": stc.loc[s, src] if s in stc.index else 0.0})
        for f_ in ["FY2026-27", "FY2027-28"]:
            t = fcf[(fcf.node_id == nid) & (fcf.fy == f_)].iloc[0]
            rr = fcf[(fcf.node_id == f"REG|{r}") & (fcf.fy == f_)].iloc[0]
            srows.append({"state": s, "region": r, "group": grp, "fy": f_, "layer": "statistical forecast", "scenario": "all", "quantile": "p50",
                          "gwh": t.fy_total_gwh, "lo80": t.fy_lo80, "hi80": t.fy_hi80, "lo95": t.fy_lo95, "hi95": t.fy_hi95,
                          "share_of_region": t.fy_total_gwh / rr.fy_total_gwh})
            for src in SRC5:
                c = fcf[(fcf.node_id == f"CELL|{s}|{src}") & (fcf.fy == f_)]
                if len(c):
                    srows.append({"state": s, "region": r, "group": grp, "fy": f_, "layer": "statistical forecast", "scenario": "all", "quantile": "p50",
                                  "source": src, "gwh": c.fy_total_gwh.iloc[0]})
        for scn in SCEN:
            for q in QS:
                x = s47[(s47.scenario == scn) & (s47["quantile"] == q) & (s47.state == s)].iloc[0]
                srows.append({"state": s, "region": r, "group": grp, "fy": "FY2046-47", "layer": "scenario projection", "scenario": scn, "quantile": q,
                              "gwh": x.gwh, "share_of_region": x.share_in_region})
        a, b = v.get("FY2019-20"), v.get("FY2025-26")
        t27 = fcf[(fcf.node_id == nid) & (fcf.fy == "FY2026-27")].iloc[0]
        g47 = {scn: s47[(s47.scenario == scn) & (s47["quantile"] == "p50") & (s47.state == s)].gwh.iloc[0] for scn in SCEN}
        mixs = stc.loc[s] / stc.loc[s].sum() if s in stc.index and stc.loc[s].sum() > 0 else pd.Series(0, index=SRC5)
        ssum.append({"state": s, "region": r, "group": grp, "confidence": CONF.get(grp, ""), "first_month": meta.loc[nid, "first"],
                     "FY2019-20_gwh": a, "FY2025-26_gwh": b, "CAGR_FY19-20_to_FY25-26_%": 100 * cagr(a, b, 6) if pd.notna(a) and pd.notna(b) else np.nan,
                     "share_of_region_FY2025-26_%": 100 * b / reg_tot["FY2025-26"] if pd.notna(b) else np.nan,
                     "main_source_FY2025-26": mixs.idxmax() if mixs.sum() > 0 else "none",
                     **{f"mix_{x}_%": 100 * mixs[x] for x in SRC5},
                     "FY2026-27_forecast_gwh": t27.fy_total_gwh, "FY2026-27_lo95": t27.fy_lo95, "FY2026-27_hi95": t27.fy_hi95,
                     "model": "ETS (direct)" if grp in ("A", "B") else "allocation of regional forecast (seasonal proportion); seasonal-naive benchmark",
                     **{f"2047_{scn}_p50_gwh": g47[scn] for scn in SCEN},
                     "display_rounding": "nearest 1 GWh" if grp == "A" else ("nearest 10 GWh" if grp == "B" else "2 significant figures (indicative)")})
    ssum = pd.DataFrame(ssum).sort_values(["region", "FY2025-26_gwh"], ascending=[True, False])
    ssum.to_csv(OUT / "state_summary.csv", index=False)
    ss = pd.DataFrame(srows)
    ss.to_csv(OUT / "state_strategy.csv", index=False)
    # reconciliation: states -> regions (historic, forecast, 2047)
    h = ss[(ss.layer == "actual") & ss.source.isna()].groupby(["fy", "region"]).gwh.sum()
    ck("States sum to regions (actual FY)", float((h - rt.stack().swaplevel().rename_axis(["fy", "region"]).reindex(h.index)).abs().max()) if False else
       float(max(abs(h.loc[(f_, r)] - rt.loc[f_, r]) for f_ in FULL_FYS for r in REGIONS)))
    fh = ss[(ss.layer == "statistical forecast") & ss.source.isna()].groupby(["fy", "region"]).gwh.sum()
    ck("States sum to regions (forecast FY, reconciled BU)", float(max(abs(fh.loc[(f_, r)] - fcf[(fcf.node_id == f'REG|{r}') & (fcf.fy == f_)].fy_total_gwh.iloc[0]) for f_ in ["FY2026-27", "FY2027-28"] for r in REGIONS)))
    sh47 = ss[(ss.layer == "scenario projection")].groupby(["scenario", "quantile", "region"]).gwh.sum().reset_index().merge(
        r47[["scenario", "quantile", "region", "gwh_damped_trend"]], on=["scenario", "quantile", "region"])
    ck("States sum to regions (2047 all scenarios/quantiles)", float((sh47.gwh - sh47.gwh_damped_trend).abs().max()))
    rn = r47.groupby(["scenario", "quantile"]).gwh_damped_trend.sum().reset_index()
    rn["nat"] = [n47.loc[s, f"{q}_gwh"] for s, q in zip(rn.scenario, rn["quantile"])]
    ck("Regions sum to national (2047 all scenarios/quantiles)", float((rn.gwh_damped_trend - rn.nat).abs().max()))
    fr = sum(fcf[(fcf.node_id == f"REG|{r}") & (fcf.fy == "FY2026-27")].fy_total_gwh.iloc[0] for r in REGIONS)
    ck("Regions sum to national (forecast FY2026-27)", abs(fr - fcf[(fcf.node_id == "TOTAL") & (fcf.fy == "FY2026-27")].fy_total_gwh.iloc[0]))
    fsrc = sum(fcf[(fcf.node_id == f"NSRC|{s}") & (fcf.fy == "FY2026-27")].fy_total_gwh.iloc[0] for s in SRC)
    ck("National sources sum to national (forecast FY2026-27)", abs(fsrc - fcf[(fcf.node_id == "TOTAL") & (fcf.fy == "FY2026-27")].fy_total_gwh.iloc[0]))
    w = mf.pivot_table(index="period", columns="node_id", values="forecast_gwh")
    ck("Monthly forecast: Bhutan import not in TOTAL (TOTAL = sum of regions)", float((w[[f"REG|{r}" for r in REGIONS]].sum(axis=1) - w.TOTAL).abs().max()))
    ck("Intervals ordered lo95<=lo80<=forecast<=hi80<=hi95 (monthly)", float(((mf.lo95 > mf.lo80 + 1e-6) | (mf.lo80 > mf.forecast_gwh + 1e-6) | (mf.forecast_gwh > mf.hi80 + 1e-6) | (mf.hi80 > mf.hi95 + 1e-6)).sum()), 0)
    ck("No renewable series in any strategy output", float(sum(x.astype(str).str.contains("SOLAR|WIND", case=False).sum() for x in [mix.source, rx.source])), 0)
    ck("State series count = 33 (34 states/UTs, J&K+Ladakh harmonised)", abs(ssum.shape[0] - 33), 0)
    pd.DataFrame(checks).to_csv(OUT / "validation_checks.csv", index=False)

    export_dashboard_tables()
    write_reports(ns, mix, diag, rsum, rx, ssum, asm, sel, POLICY, gas_post, dom, sh, srcfy, n47, fcf)
    print(pd.DataFrame(checks)[["check", "max_abs_diff_gwh", "result"]].to_string())


def write_reports(ns, mix, diag, rsum, rx, ssum, asm, sel, POLICY, gas_post, dom, sh, srcfy, n47, fcf):
    hdr = lambda t: f"# {t}\n\n_Generated by `src/strategy.py` on {TODAY} from Phase 2-3 outputs._\n\n{SCOPE}\n"  # noqa: E731
    t26 = fcf[(fcf.node_id == "TOTAL") & (fcf.fy == "FY2026-27")].iloc[0]
    t27 = fcf[(fcf.node_id == "TOTAL") & (fcf.fy == "FY2027-28")].iloc[0]
    u = ns[ns.series.str.contains("unreconciled")].set_index("fy").p50_gwh
    nat_tab = ns[(ns.series.str.startswith("DOMESTIC")) & ns.fy.isin(["FY2025-26", "FY2026-27", "FY2027-28", "FY2030-31", "FY2035-36", "FY2040-41", "FY2046-47"])][
        ["fy", "layer", "scenario", "series", "p10_gwh", "p50_gwh", "p90_gwh", "lo95_gwh", "hi95_gwh"]]
    sc_tab = pd.DataFrame([{"scenario": k, "start growth g0": v, "source of g0": asm["start_growth_source"][k],
                            "terminal growth FY2046-47 (assumed)": asm["terminal_growth_gT_FY2046_47"][k],
                            "FY2046-47 P50 TWh": n47.loc[k, "p50_gwh"] / 1000, "P10 TWh": n47.loc[k, "p10_gwh"] / 1000, "P90 TWh": n47.loc[k, "p90_gwh"] / 1000}
                           for k, v in asm["start_growth_g0"].items()])
    txt = hdr("National 2047 Strategy") + f"""## 1. Where conventional generation stands
- **FY2025-26 actual:** {dom['FY2025-26'] / 1000:,.0f} TWh ({100 * (dom['FY2025-26'] / dom['FY2024-25'] - 1):+.1f}% YoY, the first decline since FY2020-21).
- **Growth:** CAGR FY2019-20->FY2025-26 was {100 * cagr(dom['FY2019-20'], dom['FY2025-26'], 6):.2f}%/yr.
- **FY2026-27 statistical forecast (reconciled bottom-up ETS):** {t26.fy_total_gwh / 1000:,.0f} TWh (95% range {t26.fy_lo95 / 1000:,.0f}-{t26.fy_hi95 / 1000:,.0f}), of which 6 months are actual. The unreconciled national ETS gives {u['FY2026-27'] / 1000:,.0f} TWh (comparison only).
- **FY2027-28:** {t27.fy_total_gwh / 1000:,.0f} TWh (95% range {t27.fy_lo95 / 1000:,.0f}-{t27.fy_hi95 / 1000:,.0f}); it includes months beyond the validated 12-month horizon.

## 2. 2047 scenarios (approved; unchanged from Phase 3)
{md_table(sc_tab, '{:,.3f}')}
**Growth transition:**
- Annual growth moves linearly from g0 in FY2028-29 to the assumed terminal rate in FY2046-47. The launch level is the reconciled FY2027-28 forecast.
- Uncertainty comes from {asm['n_sim']} Monte-Carlo paths with iid annual log-growth shocks (sigma = {asm['shock_sigma_log_growth']:.4f}), giving P10/P50/P90.
- These are **projections of domestic conventional generation**, not national energy requirements.

{md_table(nat_tab, '{:,.0f}')}

## 3. Strategic reading (evidence-based)
1. **Plan around a range, not a point.** The low-high spread in 2047 ({n47.loc['low', 'p50_gwh'] / 1000:,.0f}-{n47.loc['high', 'p50_gwh'] / 1000:,.0f} TWh) exceeds the entire FY2025-26 output. Investment in conventional plants should be staged and reversible.
2. **The FY2025-26 dip and the +7.5% April-September 2026 rebound** show that annual direction is not yet settled. Re-estimate the scenario starting rates each year as new FY actuals arrive.
3. **Coal/lignite is ~84% of conventional output.** Every scenario's growth falls mainly on coal unless a policy mix (`energy_mix_strategy.md`) is adopted.
4. **Renewable generation is the missing half of the strategy.** The total requirement cannot be stated until an authorised actual-generation series for solar and wind is available. The framework is in `final_methodology.md`.

## 4. Limitations
The history is short (87 months, 7 FYs), the extrapolation runs 21 years, the terminal growth rates are assumptions, and there is no renewable or consumption data (by rule). Details: `forecast_uncertainty.md`, `forecasting_assumptions.md` (Phase 3).
"""
    (REPORTS / "national_2047_strategy.md").write_text(txt, encoding="utf-8")

    # ---------------- energy mix
    c = mix[(mix.scenario == "central") & (mix["quantile"] == "p50")]
    piv = c.pivot_table(index="variant", columns="source", values="share").reindex(columns=SRC) * 100
    pivg = c.pivot_table(index="variant", columns="source", values="gwh").reindex(columns=SRC) / 1000
    allsc = mix[mix["quantile"] == "p50"].pivot_table(index=["variant", "scenario"], columns="source", values="gwh").reindex(columns=SRC) / 1000
    hist = (100 * sh).round(2).reset_index()
    pol = pd.DataFrame([{"policy scenario": k, "rule": v[0], "justification (data)": v[1]} for k, v in POLICY.items()])
    txt = hdr("Energy-Mix Strategy (conventional sources)") + f"""**Two separate analyses.** (1) A *trend-based reference*, which is a statistical extrapolation of shares with its artefacts flagged. (2) *Policy scenarios*: **recommendations, not forecasts**. Both allocate the approved domestic conventional totals. In every case the sources sum exactly to that total, with coal/lignite as the balancing item. Lignite is separated from coal only nationally (FY2025-26 lignite share of coal+lignite = {100 * srcfy.loc['FY2025-26', 'LIGNITE'] / (srcfy.loc['FY2025-26', 'COAL'] + srcfy.loc['FY2025-26', 'LIGNITE']):.2f}%).
**Solar, wind, small hydro and biomass are not quantified.**

## 1. Observed shares (% of domestic conventional generation)
{md_table(hist, '{:.2f}')}

## 2. Trend-based reference: diagnostics and artefacts
{md_table(diag.drop(columns=['assessment']), '{:.2f}')}

**Assessment per source:**
""" + "\n".join(f"- **{r.source}**: {r.assessment}" for r in diag.itertuples()) + f"""

**Gas investigation.** The Phase 3 damped trend drives gas to {diag.set_index('source').loc['NATURAL_GAS', 'T1_damped_2047_%']:.2f}% by 2047. The data contradict a continuing decline:
- the post-FY2022-23 slope is {diag.set_index('source').loc['NATURAL_GAS', 'post_FY2022_23_slope_pp_per_yr']:+.2f} pp/yr;
- the reconciled forecast for FY2027-28 is higher;
- September 2026 was the highest gas month in two years.

**T3 (regime-adjusted, gas = {100 * gas_post:.2f}%) is the recommended trend reference.** T1 is kept for transparency and flagged.

## 3. Policy scenarios (recommendations)
{md_table(pol)}
Not used: any source percentage without an observed basis; any capacity, consumption or renewable input; new-build assumptions (installed capacity is prohibited as a basis).

## 4. FY2046-47 mixes - central scenario, P50
Shares (%):
{md_table(piv.reset_index(), '{:.2f}')}
Generation (TWh):
{md_table(pivg.reset_index(), '{:,.1f}')}

## 5. All scenarios (P50, TWh)
{md_table(allsc.reset_index(), '{:,.1f}')}

## 6. Recommendation
- **Reference case for planning:** T3 x central scenario.
- **Preferred policy direction: P2 (demonstrated maximum shares).** It lowers coal dependence to the lowest level already achieved by the existing system, without assuming any untested capability.
- **Use P3 (no-decline floor) as a safeguard** in the low scenario, so demonstrated hydro, nuclear and gas output is not crowded out.
- Regional allocations of every mix (region x source, IPF-balanced to both regional and national totals) are in `outputs/strategy/regional_source_mix_2047.csv`.
"""
    (REPORTS / "energy_mix_strategy.md").write_text(txt, encoding="utf-8")

    # ---------------- regional
    rx_c = rx[(rx.variant.str.startswith("T3")) & (rx.scenario == "central") & (rx["quantile"] == "p50")].pivot(index="region", columns="source", values="gwh").reindex(columns=SRC5) / 1000
    rx_p2 = rx[(rx.variant.str.startswith("P2")) & (rx.scenario == "central") & (rx["quantile"] == "p50")].pivot(index="region", columns="source", values="gwh").reindex(columns=SRC5) / 1000
    cols = ["region", "FY2019-20_gwh", "FY2025-26_gwh", "CAGR_FY19-20_to_FY25-26_%", "share_of_national_FY2025-26_%", "FY2026-27_forecast_gwh",
            "forecast_growth_FY26-27_vs_FY25-26_%", "share_2047_damped_%", "share_2047_constant_%", "2047_low_p50_gwh", "2047_central_p50_gwh", "2047_high_p50_gwh",
            "2047_central_p10_gwh", "2047_central_p90_gwh"]
    sel_r = sel.set_index("level_cat").loc["Regions (5)"]
    per = []
    for _, d in rsum.iterrows():
        per.append(f"""### {d['region']}
- **Historical:** {d['FY2019-20_gwh'] / 1000:,.0f} TWh (FY2019-20) -> {d['FY2025-26_gwh'] / 1000:,.0f} TWh (FY2025-26); CAGR {d['CAGR_FY19-20_to_FY25-26_%']:.2f}%/yr; {d['share_of_national_FY2025-26_%']:.1f}% of national conventional generation.
- **Source mix FY2025-26:** coal/lignite {d['mix_COAL_LIGNITE_%']:.1f}%, hydro {d['mix_HYDRO_%']:.1f}%, nuclear {d['mix_NUCLEAR_%']:.1f}%, gas {d['mix_NATURAL_GAS_%']:.1f}%, diesel {d['mix_DIESEL_%']:.2f}%.
- **Forecast FY2026-27:** {d['FY2026-27_forecast_gwh'] / 1000:,.0f} TWh (95% {d['FY2026-27_lo95'] / 1000:,.0f}-{d['FY2026-27_hi95'] / 1000:,.0f}); {d['forecast_growth_FY26-27_vs_FY25-26_%']:+.1f}% vs FY2025-26.
- **2047 allocation (P50):** low {d['2047_low_p50_gwh'] / 1000:,.0f} / central {d['2047_central_p50_gwh'] / 1000:,.0f} / high {d['2047_high_p50_gwh'] / 1000:,.0f} TWh. Central P10-P90: {d['2047_central_p10_gwh'] / 1000:,.0f}-{d['2047_central_p90_gwh'] / 1000:,.0f} TWh. Share {d['share_2047_damped_%']:.1f}% (damped trend) vs {d['share_2047_constant_%']:.1f}% (constant).
- **Data-supported characteristics:** {d['data_supported_characteristics']}.
- **Strategy:** {strategy_text(d)}
- **Limitations:** generation location is not consumption; the regional share trend rests on 7 FYs; the regional source mix in 2047 is an allocation (IPF), not a forecast.
""")
    txt = hdr("Regional 2047 Strategy") + f"""Regional forecasts: ETS (out-of-sample MASE {sel_r.MASE:.3f} vs best baseline {sel_r.baseline_MASE:.3f}), reconciled bottom-up from the states. 2047 regional totals use the Phase 3 damped-trend shares; a constant-share alternative is shown to indicate allocation uncertainty.

## Summary
{md_table(rsum[cols], '{:,.1f}')}

## Region profiles
""" + "\n".join(per) + f"""
## 2047 region x source, central P50 (TWh)
T3 regime-adjusted trend reference:
{md_table(rx_c.reset_index(), '{:,.1f}')}
P2 demonstrated-maximum policy:
{md_table(rx_p2.reset_index(), '{:,.1f}')}
Region rows equal the regional totals and source columns equal the national source totals (iterative proportional fitting seeded with the FY2025-26 pattern; regions without a source in FY2025-26, e.g. Eastern nuclear, stay at zero).
"""
    (REPORTS / "regional_2047_strategy.md").write_text(txt, encoding="utf-8")

    # ---------------- state
    sc = ["state", "region", "group", "FY2025-26_gwh", "CAGR_FY19-20_to_FY25-26_%", "share_of_region_FY2025-26_%", "main_source_FY2025-26",
          "FY2026-27_forecast_gwh", "FY2026-27_lo95", "FY2026-27_hi95", "2047_low_p50_gwh", "2047_central_p50_gwh", "2047_high_p50_gwh", "confidence"]
    view = ssum[sc].copy()
    for cname in ["FY2026-27_forecast_gwh", "FY2026-27_lo95", "FY2026-27_hi95", "2047_low_p50_gwh", "2047_central_p50_gwh", "2047_high_p50_gwh", "FY2025-26_gwh"]:
        view[cname] = [round_disp(v, g) for v, g in zip(view[cname], view.group)]
    gc = ssum.group.value_counts().to_dict()
    txt = hdr("State 2047 Strategy") + f"""## State groups and counting
- **33 state series cover 34 states/UTs.** JAMMU AND KASHMIR and LADAKH are one harmonised series (Ladakh's stations were reported under J&K until 2019-11). Groups: A {gc.get('A')}, B {gc.get('B')}, C {gc.get('C')}.
- **Group A** - direct ETS. **Group B** - direct ETS, intervals widened x1.25. **Group C** - allocated from the regional forecast by seasonal proportion; seasonal-naive is the benchmark.
- **State reconciliation:** states sum exactly to regions (actual, forecast and every 2047 scenario/quantile; see `outputs/strategy/validation_checks.csv`).
- **Precision:** group B figures are shown to 10 GWh and group C to 2 significant figures, to avoid false precision; full values are in the CSV.
- **2047 state allocations:** region total x state share within region. The share is a damped trend for groups A/B and constant for group C.

## State table (GWh)
{md_table(view, '{:,.1f}')}

## Reading the results
- **States are where plants are, not where electricity is needed.** A state's "share" is its share of regional *generation*.
- **Group C** (Meghalaya, Manipur, A&N, Mizoram, Nagaland, Puducherry, Lakshadweep, Goa) is indicative only. Values are small and volatile, and Lakshadweep is observed only since 2022-12.
- Source contribution per state (FY2025-26 actual and FY2026-27/27-28 forecasts by source) is in `outputs/strategy/state_strategy.csv` and in the dashboard State Explorer.
- No 2047 state x source split is published: state totals are reconciled, but a state-level source allocation 21 years ahead would add precision the data cannot support.
"""
    (REPORTS / "state_2047_strategy.md").write_text(txt, encoding="utf-8")

    # ---------------- final methodology
    txt = hdr("Final Methodology") + f"""## 1. Data (Phases 1-2)
- **Authorised sources only.** NPP / CEA *Monthly Reports ACTUAL* (1,740 XLS files, 2019-07..2026-09) and the Renewable India GitHub dataset (used only for an optional population/GSDP experiment, which was not adopted).
- **Target:** monthly ACTUAL generation (CEA col #4), in GWh. Excluded: cumulative (#9), capacity, PLF, targets and consumption.
- **Domestic conventional** = coal + lignite + gas + diesel + nuclear + large hydro. Bhutan import is separate.
- **Harmonisation:** J&K + Ladakh (33 series = 34 states/UTs); 'ANDHRA PRADESH.' = 'ANDHRA PRADESH'.
- **Extended July 2018 - June 2019 data:** sensitivity only.

## 2. Forecasting (Phase 3, approved)
- **Experiment A:** full history, with a March-May 2020 COVID regressor where the model supports one.
- **Validation:** rolling-origin expanding-window backtests; h = 1, 3, 6, 12; metrics MAE, RMSE, WAPE, MASE and bias.
- **Selected models:** ETS (national, regions, national sources, group A/B states, eligible state x source cells); seasonal-naive (group C, ineligible cells); Holt-Winters (Bhutan import).
- **Hierarchy:** bottom-up reconciliation over 73 state x source cells. Coal and lignite are split only nationally.
- **Intervals:** empirical, scale-normalised backtest errors by horizon band; group B widened x1.25; months 13-18 flagged.

## 3. Scenarios (Phase 3, approved)
- **Growth path:** g0 (observed CAGRs) moving linearly to an assumed terminal rate. Low 0.7% -> -1.5%; central 3.5% -> 0%; high 6.4% -> +2%.
- **Uncertainty:** {asm['n_sim']} Monte-Carlo paths (sigma {asm['shock_sigma_log_growth']:.4f}).
- **Allocation:** regions and states by damped share trends (group C constant); hydro share = historical mean.

## 4. Strategy (Phase 4)
- **Energy mix:** trend references T1 (Phase 3 damped trend, flagged), T2 (constant FY2025-26) and T3 (regime-adjusted gas, recommended), plus policy scenarios P0-P3, each with a data justification. Every mix sums exactly to the conventional total.
- **Region x source:** IPF balancing to regional totals and national source totals.
- **States:** totals reconcile exactly to regions; precision is reduced for groups B and C.

## 5. Layers - never mixed
| Layer | Basis | Use |
|---|---|---|
| Actual | CEA published | history |
| Statistical forecast | validated models | FY2026-27, FY2027-28 |
| Scenario projection | stated assumptions + Monte-Carlo | FY2028-29..FY2046-47 |
| Policy scenario | documented allocation rules | recommendations |

## 6. Renewable framework (unquantified)
- Total requirement R(t) = conventional C(t) + non-conventional N(t) + net imports. Only C(t) and imports are observed.
- N(t) (solar, wind, small hydro, biomass) is **not quantified**: no authorised actual-generation series exists.
- If an authorised series is approved, N(t) can be (a) forecast with the same pipeline and (b) combined with C(t) to state total production, and the policy mixes can be extended. Until then, no renewable figure appears in any output.

## 7. Reproduce
```
python src/build_model_data.py
python src/backtest.py --exp A          # B, C, EXT for sensitivities
python src/hier_backtest.py --exp A
python src/final_forecast.py --exp A --method BU
python src/scenarios.py
python src/make_reports.py --exp A --method BU
python src/strategy.py
streamlit run dashboard/app.py
```
"""
    (REPORTS / "final_methodology.md").write_text(txt, encoding="utf-8")


def export_dashboard_tables():
    """Small comparison tables for the dashboard (avoids loading the full backtest files there)."""
    from common import origins
    from evaluate import load, metrics
    d = load(["A", "B", "C", "EXT"])
    q = set(origins("quarterly"))
    cv = d[d.experiment.isin(["A", "B", "C"]) & d.origin.isin(q)]
    metrics(cv, ["experiment", "level_cat", "model"]).to_csv(OUT / "dash_covid_comparison.csv", index=False)
    ext = d[d.experiment.isin(["A", "EXT"]) & (d.node_id == "TOTAL")]
    metrics(ext, ["experiment", "model"]).to_csv(OUT / "dash_extended_comparison.csv", index=False)


def strategy_text(d) -> str:
    parts = []
    if d["mix_COAL_LIGNITE_%"] >= 90:
        parts.append("concentration risk: almost all output is coal/lignite and the region has little hydro, gas or nuclear to scale up, so its coal share stays high even under the diversified policy mixes (P2/P3); diversification here cannot be shown with conventional data alone")
    if d["mix_HYDRO_%"] >= 15:
        parts.append("protect and plan around hydrological variability (monsoon seasonality, dry-year risk seen in FY2023-24)")
    if d["mix_NUCLEAR_%"] >= 3:
        parts.append("retain nuclear contribution (stable baseload seen in the data)")
    if d["mix_NATURAL_GAS_%"] >= 10:
        parts.append("gas is a material share here, so regional gas availability matters more than nationally")
    if d["CAGR_FY19-20_to_FY25-26_%"] >= 5:
        parts.append("fastest-growing region - largest absolute additions in all scenarios")
    return "; ".join(parts) or "track national scenarios; no distinctive data-driven lever"


def round_disp(v, g):
    if pd.isna(v):
        return v
    if g == "A":
        return round(v)
    if g == "B":
        return round(v, -1)
    if v == 0:
        return 0
    from math import floor, log10
    return round(v, -int(floor(log10(abs(v)))) + 1)


if __name__ == "__main__":
    main()
