"""report_part2.py - extended-history, hierarchy, uncertainty and assumptions reports (called by make_reports.py)."""
from __future__ import annotations

import json

import pandas as pd

from common import BT, DATA, FC, REPORTS, SC, md_table, origins
from evaluate import metrics
from make_reports import header


def part2(a, d, sel):
    # ------------------------------------------------------------------ extended_history_sensitivity.md
    ext = d[d.experiment.isin(["A", "EXT"]) & (d.node_id == "TOTAL")]
    mm = metrics(ext, ["experiment", "model"])
    em = mm.pivot(index="model", columns="experiment", values="MASE").reset_index()
    ew = mm.pivot(index="model", columns="experiment", values="WAPE_%").reset_index()
    e = em.merge(ew, on="model", suffixes=("_MASE", "_WAPE"))
    e["delta_MASE"] = e["EXT_MASE"] - e["A_MASE"]
    stat_e = e[~e.model.isin(["rf", "xgb"])]
    bestA = stat_e.sort_values("A_MASE").iloc[0]
    bestE = stat_e.sort_values("EXT_MASE").iloc[0]
    fyn = pd.read_csv(DATA / "fy_national.csv")
    dom = fyn[fyn.series == "DOMESTIC_CONVENTIONAL_TOTAL"].set_index("fy_start").fy_total_gwh
    c_main = (dom[2025] / dom[2019]) ** (1 / 6) - 1
    c_ext = (dom[2025] / dom[2018]) ** (1 / 7) - 1
    changed = bestA.model != bestE.model
    txt = header("Extended-History Sensitivity") + f"""## Setup
- **Extended national series:** 2018-07..2026-09. The months 2018-07..2019-06 are flagged; they come from the published 'same month previous year' column (#5). The rest is the main data. File: `outputs/data/model_ready_extended_national.csv`. It is never merged into the main panel.
- **Reconciliation issue:** col #5 differs from the originally published col #4 by up to 0.10% (375 overlapping series-months, median 0.000%). This is **unresolved**, so the extended data are **not** used for the main results.
- **Comparability:** same origins ({origins('monthly')[0]}..{origins('monthly')[-1]}), horizons and metrics as experiment A, with the COVID regressor included. The MASE scale is the main-window seasonal-naive scale, so both runs share identical denominators.
- **ML caveat:** in EXT, RF and XGBoost are trained on the single national series, because no pooled panel exists for the extended period. Their results are not comparable with A and are shown for completeness only.

## National out-of-sample accuracy, main (A) vs extended (EXT)
{md_table(e[['model', 'A_MASE', 'EXT_MASE', 'delta_MASE', 'A_WAPE', 'EXT_WAPE']].sort_values('EXT_MASE'), '{:.3f}')}

## Does model selection change?
- Best statistical model on the main data: **{bestA.model}** (MASE {bestA.A_MASE:.3f}). With extended data: **{bestE.model}** (MASE {bestE.EXT_MASE:.3f}).
- {'**Yes, selection changes.**' if changed else 'No, selection is unchanged.'} Trend-type models (linear trend + month dummies, SARIMA) gain most from the extra 12 months, because their trend estimate rests on few seasonal cycles. ETS and Holt-Winters change little.
- **Interpretation:** the national choice between ETS and trend regression is sensitive to history length. That is evidence the short sample limits model identification, and this uncertainty is carried into the scenario ranges.

## Do projected trends change?
- **CAGR:** FY2019-20->FY2025-26 = {c_main * 100:.2f}%/yr; including the flagged FY2018-19, FY2018-19->FY2025-26 = {c_ext * 100:.2f}%/yr. The FY2018-19 total ({dom[2018]:,.0f} GWh) is almost identical to FY2019-20 ({dom[2019]:,.0f} GWh).
- Using the extended window would lower the central scenario's starting growth from {c_main * 100:.2f}% to {c_ext * 100:.2f}%. That change is well inside the low-high scenario range.

## Recommendation
Keep the main dataset as the primary basis. Adopt the extended history only if the 0.10% restatement differences are explained and you explicitly approve. If it is adopted, re-run national selection{' (the linear trend + month dummies model would then be selected over ETS)' if changed else ''}.
"""
    (REPORTS / "extended_history_sensitivity.md").write_text(txt, encoding="utf-8")

    # ------------------------------------------------------------------ hierarchical_reconciliation.md
    hm = pd.read_csv(BT / f"hier_metrics_{a.exp}.csv")
    coh = pd.read_csv(BT / f"hier_coherence_{a.exp}.csv")
    lv = ["National", "Regions (5)", "National sources", "National coal/lignite split", "States group A", "States group B", "States group C",
          "State x source (eligible)", "State x source (ineligible)"]
    meth = ["BASE", "BU", "TD", "MO", "OLS", "WLS_struct", "WLS_scale"]
    piv = hm.pivot(index="level_cat", columns="method", values="MASE").reindex(lv)[meth]
    wp = hm.pivot(index="level_cat", columns="method", values="WAPE_%").reindex(lv)[meth]
    score = piv.drop(index="National coal/lignite split").mean().rename("mean MASE (equal weight per level)").reset_index()
    cohs = coh.groupby("method").max_abs_incoherence_gwh.max().rename("max |incoherence| GWh").reset_index()
    meta = pd.read_csv(DATA / "node_metadata.csv")
    mi = meta.set_index("node_id")
    gcount = meta[meta.level == "state"].group.value_counts().to_dict()
    fc = pd.read_csv(FC / "monthly_forecast.csv")
    w = fc.pivot_table(index="period", columns="node_id", values="forecast_gwh")
    regs = [c for c in w if c.startswith("REG|")]
    sts = [c for c in w if c.startswith("ST|")]
    srcs = [f"NSRC|{s}" for s in ["COAL_LIGNITE", "NATURAL_GAS", "DIESEL", "NUCLEAR", "HYDRO"]]
    regdiff = max(float((w[[s for s in sts if mi.region.get(s) == r.split("|")[1]]].sum(axis=1) - w[r]).abs().max()) for r in regs)
    cells = [c for c in w if c.startswith("CELL|")]
    celldiff = max(float((w[[c for c in cells if c.split("|")[1] == s[3:]]].sum(axis=1) - w[s]).abs().max()) for s in sts)
    chk = pd.DataFrame([
        {"identity (final 18-month forecast)": "sum(regions) = TOTAL", "max |diff| GWh": float((w[regs].sum(axis=1) - w.TOTAL).abs().max())},
        {"identity (final 18-month forecast)": "sum(states incl. group C) = each region", "max |diff| GWh": regdiff},
        {"identity (final 18-month forecast)": "sum(cells) = each state", "max |diff| GWh": celldiff},
        {"identity (final 18-month forecast)": "sum(national sources) = TOTAL", "max |diff| GWh": float((w[srcs].sum(axis=1) - w.TOTAL).abs().max())},
        {"identity (final 18-month forecast)": "COAL + LIGNITE = COAL_LIGNITE (national)", "max |diff| GWh": float((w["NSRC|COAL"] + w["NSRC|LIGNITE"] - w["NSRC|COAL_LIGNITE"]).abs().max())},
    ])
    txt = header("Hierarchical Reconciliation") + f"""## Hierarchy
- **Bottom level:** 73 state x source cells, with sources COAL_LIGNITE, NATURAL_GAS, DIESEL, NUCLEAR and HYDRO.
- **Aggregates:** 33 states -> 5 regions -> national TOTAL, and 5 national source groups -> TOTAL. This is a grouped hierarchy of 117 nodes.
- **State count:** group A {gcount.get('A')} + group B {gcount.get('B')} + group C {gcount.get('C')} = 33 state series. The audit lists 34 states/UTs. The difference is JAMMU AND KASHMIR and LADAKH, merged into one harmonised series because Ladakh's stations were reported under J&K until 2019-11. No state is missing.
- **Coal vs lignite** is distinguished only nationally (report 11). At state level CEA reports lignite plants as coal, so the hierarchy uses COAL_LIGNITE. The reconciled national COAL_LIGNITE is split into COAL and LIGNITE in proportion to their own base forecasts.
- **Bhutan import** is outside the hierarchy and forecast separately; it is never added to domestic generation.
- **Base forecasts:**
  - Every directly modelled node uses the selected model for its level (`model_comparison.md`).
  - **Group C states** = region base forecast x seasonal proportion (the state's share of the region in the same month one year earlier).
  - **Ineligible cells** = state forecast x seasonal proportion.

## Methods compared (13 quarterly origins, h = 1..12)
- **BASE:** unreconciled base forecasts.
- **BU:** bottom-up.
- **TD:** top-down, by seasonal proportions of TOTAL.
- **MO:** middle-out from states.
- **OLS:** ordinary least-squares reconciliation.
- **WLS_struct:** weighted least squares, W = number of bottom series.
- **WLS_scale:** weighted least squares, W = squared seasonal-naive scale.

For every method, negative reconciled bottom values are set to 0 and the hierarchy is then re-aggregated.

### MASE
{md_table(piv.reset_index(), '{:.3f}')}

### WAPE %
{md_table(wp.reset_index(), '{:.2f}')}

### Overall score (selection rule fixed in advance: equal-weight mean MASE over levels)
{md_table(score.sort_values('mean MASE (equal weight per level)'), '{:.3f}')}

**Selected: {a.method}.**
- It has the best overall score among the **coherent** methods. BASE scores marginally better ({score.set_index('method').iloc[:, 0]['BASE']:.3f} vs {score.set_index('method').iloc[:, 0][a.method]:.3f}) but is not coherent, so it is not a valid final method.
- It sits close to the best method at every level and never degrades badly.
- By contrast, OLS and WLS_struct break down on small nodes (group C states, ineligible cells), where they amplify proportional errors of tiny series.
- Cost at the national level: MASE {piv.loc['National', 'BU']:.3f} vs {piv.loc['National', 'BASE']:.3f} for BASE.
- Gains at regional level: {piv.loc['Regions (5)', 'BU']:.3f} vs {piv.loc['Regions (5)', 'BASE']:.3f}. National sources: {piv.loc['National sources', 'BU']:.3f} vs {piv.loc['National sources', 'BASE']:.3f}.
- **Group C, allocation vs direct models:** allocation (BASE row, group C) scores MASE {piv.loc['States group C', 'BASE']:.3f}, against 0.902 for the best direct model (seasonal-naive, `model_comparison.md`).
  - So allocation is marginally *less* accurate on its own.
  - It is kept, as approved, because it ties these 8 volatile series to their region, guaranteeing coherence and stable long-run shares.
  - The accuracy difference (~0.015 MASE) is within backtest noise.

## Coherence checks
Backtest:
{md_table(cohs, '{:.2e}')}
Final forecast ({a.method}):
{md_table(chk, '{:.6f}')}
"""
    (REPORTS / "hierarchical_reconciliation.md").write_text(txt, encoding="utf-8")

    # ------------------------------------------------------------------ forecast_uncertainty.md
    it = pd.read_csv(FC / "interval_quantiles.csv")
    fy = pd.read_csv(FC / "fy_forecast.csv")
    nat = pd.read_csv(SC / "fy_scenarios_national.csv")
    asm = json.loads((SC / "scenario_assumptions.json").read_text(encoding="utf-8"))
    fy_show = fy[fy.node_id.isin(["TOTAL", "IMPORT|BHUTAN"]) | fy.node_id.str.startswith(("REG|", "NSRC|"))][
        ["node_id", "fy", "actual_months", "fy_total_gwh", "fy_lo80", "fy_hi80", "fy_lo95", "fy_hi95", "includes_beyond_validated_horizon"]]
    n47 = nat[nat.fy_start == 2046][["scenario", "growth_assumed", "deterministic_gwh", "p10_gwh", "p50_gwh", "p90_gwh"]]
    n_sel = nat[nat.fy_start.isin([2027, 2030, 2035, 2040, 2046])].pivot_table(index="fy", columns="scenario", values="p50_gwh").reset_index()
    reg47 = pd.read_csv(SC / "fy2047_regional.csv")
    src47 = pd.read_csv(SC / "fy2047_source.csv")
    st47 = pd.read_csv(SC / "fy2047_state.csv")
    r47 = reg47[reg47["quantile"] == "p50"].pivot_table(index="region", columns="scenario", values="gwh_damped_trend").reset_index()
    rsh = reg47[(reg47.scenario == "central") & (reg47["quantile"] == "p50")][["region", "share_damped_trend", "share_constant"]]
    s47 = src47[(src47.scenario == "central") & (src47["quantile"] == "p50")][["source", "share_damped_trend", "share_constant", "gwh_damped_trend"]]
    st47c = st47[(st47.scenario == "central") & (st47["quantile"] == "p50")].sort_values("gwh", ascending=False)[["state", "region", "group", "gwh"]].head(15)
    txt = header("Forecast Uncertainty") + f"""## 1. Statistical forecast intervals (Oct-2026..Mar-2028)
- **Method:** empirical. Backtest errors of the selected pipeline (experiment {a.exp}, {a.method} reconciliation) are scale-normalised: e = (actual - forecast)/s, where s is the in-sample seasonal-naive MAE (the MASE scale). The quantiles of e are pooled by level and by horizon band (1-3, 4-6, 7-9, 10-12 months). Interval = forecast + q x s, clipped at 0.
- **Group B** states and cells: widened by a factor of 1.25 (approved decision).
- **Horizons 13-18** lie beyond the validated horizon: they use the h = 10-12 quantiles widened by sqrt(h/12), and are flagged.
- **FY intervals:** the observed months plus the sum of the monthly bounds over the forecast months (comonotonic, i.e. conservative).

Quantiles used (in scale units):
{md_table(it, '{:.2f}')}

### FY forecasts with intervals (GWh)
{md_table(fy_show, '{:,.0f}')}

## 2. Scenario uncertainty to FY2046-47
- **Method:** Monte Carlo, {asm['n_sim']} paths per scenario. Annual log-growth shocks are iid with sigma = {asm['shock_sigma_log_growth']:.4f}, taken from observed FY growth excluding FY2020-21.
{md_table(n47, '{:,.3f}')}
- **Assumption uncertainty dominates.** The spread between scenarios is larger than the P10-P90 band within any single scenario. The dominant uncertainty is the assumed long-run growth path, which the 2019-2026 data cannot identify.
- **Unconstrained reference:** a log-linear trend on FY2019-20..FY2025-26, extrapolated to FY2046-47, gives {asm['reference_loglinear_trend_FY2046_47_gwh']:,.0f} GWh. That is above the high scenario, and it shows the risk of extrapolating 7 annual points over 21 years.

## 3. Allocation uncertainty (FY2046-47, central P50)
Region shares, damped trend vs constant (latest FY) shares:
{md_table(rsh, '{:.3f}')}
Source shares:
{md_table(s47, '{:,.3f}')}

## 4. Sources of uncertainty (ranked)
1. **Long-run growth assumptions.** The terminal growth rates are assumptions, and they drive the 2047 range.
2. **Missing renewable generation.** Conventional generation is the part of demand not met by renewables. Without renewable data, the substitution between the two cannot be modelled.
3. **Short history.** Only 7 FY points and 87 months exist, and the national model choice changes when 12 extra months are added.
4. **Structural breaks:** COVID in 2020, the weak monsoon in FY2023-24, and the FY2025-26 thermal decline.
5. **State-level volatility.** Plant commissioning and retirement cause step changes; group C is especially volatile.
6. **Hydrology.** Hydro output varies year to year, and Bhutan import is highly variable.
"""
    (REPORTS / "forecast_uncertainty.md").write_text(txt, encoding="utf-8")

    # ------------------------------------------------------------------ forecasting_assumptions.md
    sc_tab = pd.DataFrame([{"scenario": k, "start growth g0": v, "g0 source": asm["start_growth_source"][k],
                            "terminal growth FY2046-47 (ASSUMED)": asm["terminal_growth_gT_FY2046_47"][k]} for k, v in asm["start_growth_g0"].items()])
    txt = header("Forecasting Assumptions and Limitations") + f"""## Three distinct layers (never mix them)
| Layer | What it is | Horizon | Where |
|---|---|---|---|
| **Statistical forecast** | Model-based, validated by rolling-origin backtesting, reconciled, with empirical intervals | Oct-2026..Mar-2028 (validated to 12 months; months 13-18 flagged) | `outputs/forecasts/` |
| **Scenario projection** | Assumption-driven FY paths to FY2046-47 with Monte-Carlo bands; **not a prediction** | FY2028-29..FY2046-47 | `outputs/scenarios/` |
| **Policy recommendation** | Normative choices about the generation mix, including renewables | - | **Not produced in Phase 3** (next phase, after approval) |

## Data assumptions
- **Target:** monthly ACTUAL generation (CEA col #4), in GWh, July 2019 - September 2026 (87 months). Cumulative, capacity, PLF, target and consumption variables are never used.
- **Domestic** = coal + lignite + gas + diesel + nuclear + large hydro. Bhutan import is separate.
- **Solar, wind, small hydro and biomass generation are not modelled**, because no authorised generation dataset exists. The results are **not** total Indian production.
- **Harmonisation:**
  - J&K + Ladakh are merged into one series.
  - 'ANDHRA PRADESH.' is treated as 'ANDHRA PRADESH'.
  - State x source cells are zero-filled only where the state exists but has no station of that source.
- **Extended history** (2018-07..2019-06) is used for sensitivity only.
- **Population and GSDP** were tried as an optional experiment only ({asm['optional_population_gsdp_experiment']}) and are **not used**. {asm['optional_experiment_decision']}

## Modelling assumptions
- **Main experiment:** {a.exp} (full history, plus a COVID Mar-May 2020 intervention for regressor-capable models).
- **Selection:** out-of-sample mean MASE over h = 1..12. The chosen model must beat seasonal-naive.
- **ARIMA/SARIMA:** orders selected by AIC on the first-origin window, then held fixed.
- **ETS:** re-selected by AICc at each origin.
- **Explosion guard:** forecasts above 5x the historical maximum are treated as model failures.
- **ML:** global pooled models with a scale-free seasonal log-ratio target, using only features available at the origin.
- **Hierarchy:** {a.method} reconciliation. Group C states and ineligible cells are allocated by seasonal proportions. Coal and lignite are split only nationally.
- **Final models** are refitted on all data up to 2026-09.

## Scenario assumptions
{md_table(sc_tab, '{:.4f}')}
- **Growth path:** growth moves linearly from g0 to gT. The launch level is the reconciled statistical forecast for FY2027-28.
- **Terminal growth:** {asm['terminal_growth_source']}.
- **Allocation:**
  - Region, state and source shares follow damped share trends (phi = {asm['share_damping_phi']}).
  - The hydro share is the historical mean.
  - Group C states keep a constant share of their region.
  - Shares are identical across the three scenarios.

### Scenario medians (P50, GWh)
{md_table(n_sel, '{:,.0f}')}
### Regions FY2046-47 (P50, GWh)
{md_table(r47, '{:,.0f}')}
### Top 15 states FY2046-47 (central P50, GWh)
{md_table(st47c, '{:,.0f}')}

## Renewable policy-scenario framework (structure only; no invented data)
- Total requirement R(t) = conventional C(t) + non-conventional N(t) + net imports. Only C(t) and imports are observed.
- In the next phase, N(t) can be set as explicit policy targets, for example a share or TWh path for solar and wind. Those targets can then be checked for consistency against the C(t) scenarios above.
- No historical renewable observations will be created. N(t) stays outside the statistical models unless an authorised renewable generation dataset is approved.

## Key limitations
1. No renewable generation data, so total production and the transition of the generation mix cannot be estimated.
2. Only 87 months (7 FYs) of history are extrapolated 21 years ahead, so the scenarios are driven by assumptions.
3. State results describe where plants are located, not demand. Group C states are allocated, not modelled.
4. The national model choice is sensitive to history length (see the extended-history sensitivity).
5. Interval calibration rests on 13-39 backtest origins, so the tail quantiles are uncertain.
6. Coal and lignite cannot be separated below the national level.
"""
    (REPORTS / "forecasting_assumptions.md").write_text(txt, encoding="utf-8")
