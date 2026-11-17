# Data Audit Report: India Energy Production Forecasting 2047 (INNOTHON)

**Stage:** data acquisition and audit only. No model has been trained and no forecast has been made.
**Audit date:** 2026-11-15
**Authorised sources:** National Power Portal (npp.gov.in) and the Renewable India GitHub dataset. No other data was used.
**Evidence files:** `data/metadata/download_manifest.csv`, `file_inventory.csv`, `sheet_inventory.csv`, `reports/download_summary.md`, `data_quality_report.md`, `data_dictionary.csv`, `data_availability.csv`, `reconciliation_results.csv`.

---

## 1. Executive summary

- **1,745 files were downloaded and verified, with 0 failures.** Each file was checked for presence, a matching file signature and successful opening.
  - 1,740 are NPP *Monthly Reports ACTUAL* XLS files: 20 report types × 87 months.
  - 1 is an NPP dashboard snapshot (JSON).
  - 4 are files from the GitHub repository (commit `89d5ef73e5`).
- **The NPP actual-generation archive covers 2019-07 to 2026-09 (87 consecutive months, no gaps).** The archive form was queried for every month back to 2010-01, and it returns nothing before 2019-07.
  - This gives 6 complete financial years (FY2020-21 to FY2025-26), plus Jul 2019–Mar 2020 and Apr–Sep 2026.
- **The NPP data is internally very consistent.** Every reconciliation where the period, unit and coverage match agrees within 0.001 GWh. The one exception is a single sector/hydro deviation of 2.26% in Feb-2020.
  - Monthly values sum exactly to the published April-to-date cumulative values.
  - No negative values were found.
- **Critical limitation: NPP publishes generation only for conventional sources.** These are thermal (coal, lignite, gas, diesel), nuclear, large hydro (>25 MW) and Bhutan imports.
  - **No solar, wind, small-hydro or biomass *generation* exists in either authorised source.** Only renewable *installed capacity* exists, and the rules forbid using it.
- **The GitHub dataset contains no generation data.**
  - Its usable supporting variables are Population and GSDP: annual, 34 states/UTs, 2006–2024.
  - Its README says some missing values were **predicted with XGBoost**, and the predicted cells are not flagged.
- **Geographic, climatic and urbanisation indicators are not available.**

Bottom line: national, regional and state-level forecasting of **conventional** generation, split by source (coal/thermal, gas, nuclear, hydro), is feasible from 87 months of verified data. Solar and wind generation cannot be forecast from authorised data. Total national production including renewables therefore cannot be measured from these sources. That gap needs a decision from you and/or the organisers (Section 15).

---

## 2. Data sources and download status

| Source | Method | Files | Status |
|---|---|---|---|
| NPP Monthly Reports ACTUAL (`/monthlyGenerationReportsAct`) | Official archive form (POST month + session CSRF token), links taken only from the portal's own response; XLS preferred | 1,740 | all verified |
| NPP dashboard `getAllZone?ID=IND` | single GET, saved as evidence | 1 | verified (current-day snapshot only) |
| GitHub `chrisjaimyantony/renewable-india-dataset` | `git clone --depth 1`, branch `main`, commit `89d5ef73e52a55251874c6e529374a9505c1059b` | 4 | verified, with sha256 recorded |

Access needed no login, OTP or CAPTCHA, and the downloader added a delay between requests.

These were **deliberately not downloaded**, with reasons:
- TENTATIVE monthly reports: not actual figures.
- Installed-capacity reports: capacity is prohibited.
- Coal and gas *supply* reports: fuel, not generation.
- Transmission reports.
- Daily generation reports: conventional sources only, and duplicate the monthly ACTUAL data. They were inspected and contain no renewable generation.

## 3. File inventory

All 1,745 files under `data/raw/` were inspected recursively, and 0 were unreadable (`data/metadata/file_inventory.csv`).

| Folder | Content | Files |
|---|---|---|
| `npp/all_india/YYYY/` | reports 01 (All India), 17 (Summary All India, gas-based) | 174 |
| `npp/region_wise/YYYY/` | report 02 | 87 |
| `npp/source_wise/YYYY/` | reports 03, 11, 12, 13, 14, 15 | 522 |
| `npp/station_wise/YYYY/` | report 16 (Region / State / Station detail) | 87 |
| `npp/other_reports/YYYY/` | reports 04–10, 18–20 (sector / utility detail) | 870 |
| `npp/other_reports/dashboard_snapshot/` | dashboard JSON | 1 |
| `npp/state_wise/` | **empty**: NPP publishes no separate state-wise generation file | 0 |
| `renewable_india/renewable-india-dataset/` | CSV, README, LICENSE, notebook | 4 |

## 4. Dataset descriptions

**NPP / CEA "18-column" monthly ACTUAL reports.** Every sheet has a numbered header row (1…18) that fixes the meaning of each column. This was verified on every file, and all 1,740 parsed.

| Col | Meaning | Classification |
|---|---|---|
| #1 | Monitored capacity (MW) | Installed capacity: **not used** |
| #2, #3, #8 | Annual / monthly / April-to-date *programme* (target) | Other (target): not used |
| **#4** | **Actual generation in the month (GWh)** | **Actual generation: forecasting target** |
| #5 | Actual, same month last year | Actual generation (cross-check) |
| **#9** | **Actual generation, April to the reporting month (cumulative)** | **Actual generation, cumulative: never summed across months** |
| #10 | Actual, same period last year | Actual generation (cross-check) |
| #6, #7, #11, #12 | % ratios | Other |
| #13–#18 | Plant load factor (PLF) | Other operational (derived from capacity): not used |

Reports 17–20 use a 7-value layout: capacity, then target / generation / PLF for the month and for April-to-date. The parser maps these onto the same columns.

**Renewable India CSV**:
- 635 rows covering 34 states/UTs and years 2006–2024.
- Columns: State, Year, Installed Bio-Mass / Small Hydro / Solar / Wind / Waste-to-Energy (MW), Zone, Population, GSDP (crore INR, nominal).
- The README's column list and file name don't match the actual file.

## 5. Excel sheet inventory

Each XLS file has a single sheet. The sheet names are `summary-All_India_mgr_01` (report 01), `OPM_MON_16` (report 16) and `monWiseSummeryReport` (most others). The full list is in `data/metadata/sheet_inventory.csv`.
- **Units:** headers say GWH (reports 01–15) or MU (17–20). These are the same unit (1 MU = 1 GWh).
- Report 16 prints no energy unit. Its values reconcile exactly with report 02 (GWh), so GWh is **inferred**.
- The period declared inside each sheet matched the file name in **all** 1,740 files.

## 6. Historical coverage

- **Available:** 2019-07 to 2026-09, monthly, with no missing month and all 20 reports present every month.
- **Not available:** anything before 2019-07 (the archive returns no links), and 2026-10 onward, which exists only as TENTATIVE.

Published national conventional generation (financial-year totals from the March cumulative #9 figures, in GWh):

| FY | Thermal | Nuclear | Hydro | Bhutan imp. | **Total** |
|---|---|---|---|---|---|
| 2019-20 | 1,042,748 | 46,472 | 155,769 | 5,794 | 1,250,784 |
| 2020-21 | 1,032,514 | 43,029 | 150,300 | 8,766 | 1,234,608 |
| 2021-22 | 1,114,714 | 47,112 | 151,627 | 7,493 | 1,320,947 |
| 2022-23 | 1,206,211 | 45,861 | 162,099 | 6,742 | 1,420,913 |
| 2023-24 | 1,326,549 | 47,937 | 134,054 | 4,716 | 1,513,256 |
| 2024-25 | 1,363,890 | 56,681 | 148,634 | 5,484 | 1,574,689 |
| 2025-26 | 1,307,131 | 55,191 | 167,204 | 7,831 | 1,537,356 |

FY2019-20 is a published cumulative figure for the full year, but the archive holds individual monthly files only from July 2019.

## 7. Geographical coverage

**Regions (report 02):** Northern, Western, Southern, Eastern, North Eastern, plus Bhutan import and All India.

**States/UTs (report 16, `TOTAL <STATE>` rows):** 35 labels covering **34 distinct states/UTs**.
- `ANDHRA PRADESH.` (with a trailing dot, 2019-07 to 2019-11) and `ANDHRA PRADESH` (2019-12 onward) look like a spelling variant. Treating them as one state is a **proposed** mapping, and it has **not** been applied to the raw data or the processed tables.
- **LADAKH** appears separately from 2019-12, after the J&K reorganisation. Its stations (e.g. CHUTAK HPS) were previously under J&K. This is one reason 31 station names appear under two states.
- **LAKSHADWEEP** is present only from 2022-12, which reflects when its stations were monitored.
- Goa is present but has had 0 generation recently.
- **Absent:** Chandigarh (no monitored conventional station).

**State meaning:** this is the *location of monitored conventional stations*. States with little conventional generation look small even when they have large renewable generation. Shared projects (e.g. BBMB) are reported under one state.

**GitHub vs NPP names:**
- 33 states match after case, punctuation and "&"→"and" normalisation. CHHATISGARH and CHHATTISGARH are treated as a known variant. Only in GitHub: Chandigarh. Only in NPP: Ladakh, which GitHub folds into J&K. See `data/metadata/state_name_mapping.csv`.
- GitHub "Zone" labels **disagree with CEA regions**. Rajasthan is "West" (CEA: Northern), Chhattisgarh and MP are "Central" (CEA: Western), and A&N is "South" (CEA: Eastern). CEA regions should be used.

## 8. Energy source coverage

| Source | Generation available? | Where | Level |
|---|---|---|---|
| Coal | Yes | report 11 "TOTAL COAL BASED"; report 16 THERMAL group | national / sector / station; **state only as "THERMAL" (coal + lignite)** |
| Lignite | Yes | report 11 "TOTAL LIGNITE BASED" | national / station only. Report 16 labels lignite plants COAL |
| Natural gas | Yes | reports 12–14, 17–20; report 16 "NATURAL GAS" group | station / state / national |
| Diesel / liquid fuel | Yes (small) | report 15 | station / national |
| Nuclear | Yes | reports 01, 02, 10, 16 | national / region / state / station |
| Hydro (large, >25 MW) | Yes | reports 01, 02, 08–10, 16 | national / region / state / station |
| Bhutan import | Yes | reports 01, 02 | national |
| **Solar** | **No** | none | n/a |
| **Wind** | **No** | none | n/a |
| Small hydro, biomass, waste-to-energy | **No** | none | n/a |

FY2025-26 state fuel-group sums from report 16:
- THERMAL 1,281,104 GWh
- HYDRO 167,204 GWh
- NUCLEAR 55,191 GWh
- NATURAL GAS 26,026 GWh

Together with Bhutan's 7,831 GWh, these equal the national total exactly.

## 9. Generation versus capacity classification

- **Used as the target:** only CEA columns #4 (monthly actual) and #9 (April-to-date actual). Columns #5 and #10 serve as cross-checks.
- **Classified as installed capacity and excluded:** CEA #1, the NPP dashboard `res_*` fields, and all five `Installed - *` columns in the GitHub CSV.
- **Excluded for other reasons:** targets, PLF (derived from capacity) and the % ratios.
- No consumption variable exists in any downloaded file, and none was used.
- The full classification of all 304 dictionary entries is in `reports/data_dictionary.csv`.

## 10. Demographic and economic data availability

| Variable | Status | Caveats |
|---|---|---|
| Population | PARTIALLY AVAILABLE (annual 2006–2024, 34 states/UTs) | Partly XGBoost-predicted (not flagged); year basis (calendar vs financial) undocumented. AP and Telangana are back-cast to post-2014 boundaries; Telangana is missing 2013 (causing a dip in the national sum); Chandigarh starts 2013 and Delhi 2009; no Ladakh row. |
| GSDP | PARTIALLY AVAILABLE | Nominal (not inflation-adjusted); partly predicted; identical values repeated in consecutive years for A&N (5), Lakshadweep (5), J&K (4), Telangana (4) and Nagaland (1). |
| Urbanisation | NOT AVAILABLE | n/a |
| Geographic / land availability | NOT AVAILABLE | Only categorical region and zone labels exist. |
| Climatic (irradiance, wind, rainfall) | NOT AVAILABLE | n/a |

## 11. Data quality findings

Full detail is in `reports/data_quality_report.md`.

- **Completeness:** 87 of 87 months; 20 of 20 reports each month; 0% missing in national #4 and #9; 0.01% missing in station #4.
- **Consistency:**
  - Label variants: `ANDHRA PRADESH.` and `CHHATISGARH`.
  - Report 16 labels lignite plants COAL (16 report-11 lignite stations: 1,187 station-months labelled COAL).
  - GHATAMPUR TPP and PANKI TPS EXT are labelled LIGNITE for 14 station-months but COAL otherwise.
  - 5 duplicate station rows (same period, state, station and owner).
  - 31 station names appear under two states (the Ladakh split and the AP spelling variant).
- **Temporal:**
  - April monthly value equals the cumulative value in 100% of cases (financial year April–March confirmed).
  - The sum of monthly #4 values matches cumulative #9 with a maximum deviation of 0.000%.
  - "Same month last year" (#5) matches the figure originally published 12 months earlier in all 375 pairs (none differ by >1%), so there are no silent restatements.
  - There are no duplicate periods.
- **Numerical:**
  - 0 negative values; 0 zero national values.
  - 20.3% of station-months are zero, consistent with plants that are shut down or retired.
  - National YoY changes above 15% occur in 2021-03/04 (base effect from the COVID lockdown), 2021-08, 2022-05/06 and 2023-10.
  - 96 state-months show YoY changes above 100%, all in small-base states (NE states, A&N) or Haryana and Punjab around 2021.
- **GitHub:**
  - 95 year-on-year *decreases* in installed capacity (implausible for cumulative capacity).
  - Unbalanced panel: Chandigarh starts 2013, Delhi starts 2009, Telangana is missing 2013.
  - Zone labels are inconsistent with CEA regions.

## 12. Missing data

- Renewable generation is missing entirely: solar, wind, small hydro, biomass and waste-to-energy.
- Monthly ACTUAL reports before 2019-07 are missing.
- State-level coal and lignite can't be separated; only the combined THERMAL group exists.
- Urbanisation, climate, land and geography indicators are missing.
- There is no population or GSDP for 2025 or 2026.
- Some population and GSDP values are model-generated but not flagged.

No missing value was filled in, imputed or estimated.

## 13. Reconciliation findings

These checks were run only where period, unit, coverage and classification match. Tolerance is ±0.5%.

| Check | Pairs | Within tolerance | Max abs. diff |
|---|---|---|---|
| R01 TOTAL = THERMAL + NUCLEAR + HYDRO + BHUTAN | 87 | 100% | 0.000% |
| Σ regions (R02) = national (R01), by category | 348 | 100% | 0.001% |
| Σ state totals (R16) = region total (R02) | 435 | 100% | 0.001% |
| Σ stations (R16) = state total (R16) | 2,912 | 100% | 0.000% |
| Σ state fuel groups (R16) = state total (R16) | 2,912 | 100% | 0.000% |
| Σ sectors (R03) = national (R01), by category | 261 | 99.6% | 2.26% (Feb-2020 hydro: 8,626.47 vs 8,435.84 GWh) |
| R11 coal + lignite + R15 "TOTAL EXCL. COAL/LIGNITE" = R01 THERMAL | 87 | 100% | 0.000% |
| Σ state HYDRO / NUCLEAR / THERMAL+GAS groups (R16) = national (R01) | 87 each | 100% | 0.001% |

No comparison was made against capacity, consumption or renewables. No source value was altered.

## 14. Major limitations

1. **No renewable generation data.** India's generation includes a substantial and growing renewable share, so the conventional series in NPP *understates* total national production. Its trend also reflects renewables displacing thermal generation: thermal fell in FY2025-26 while hydro rose.
2. **Short history: 87 months (about 7.25 years).** Projecting to 2047 means extrapolating about 21 years beyond the data, roughly 3 times the observed span. The series also includes COVID-19 (2020–21) and a low-hydro year (FY2023-24).
3. **State-level coverage depends on where conventional stations are.** It shows where conventional power is generated, not what each state needs. States with no monitored plant are absent.
4. **The supporting variables are weak.** Population and GSDP are partly model-predicted, GSDP is nominal, and the year basis is unknown. There are no urbanisation, climate or land indicators, although the problem statement asks for them.
5. Coal and lignite can't be separated at state level.

## 15. Recommendations for the next phase

1. **Decide how to handle renewables. This is your decision, possibly with the organisers.** Options:
   - (a) Ask the organisers whether a renewable *generation* source is permitted. This is the preferred option.
   - (b) Scope the forecast explicitly as conventional generation, plus a scenario-based renewable *strategy* that isn't a data forecast.
   - Do **not** convert capacity into generation using capacity factors; the rules prohibit it.
2. Use **monthly #4** as the target. Use **#9 only to validate** financial-year totals, and use FY totals (Apr–Mar) for annual modelling.
3. Build tidy modelling tables from `data/processed/` at three levels: national × category, region × category, and state × fuel group. Apply and document the proposed `ANDHRA PRADESH.` → `ANDHRA PRADESH` mapping, and treat Ladakh's split from J&K explicitly.
4. Use population and GSDP only as optional, clearly caveated supporting regressors. If you use them, check sensitivity with and without them.
5. Make uncertainty explicit, e.g. scenario bands, because the forecast horizon is long relative to the history.

---

## Explicit answers

**A. Is national actual-generation forecasting feasible?**
**Yes, for conventional generation.** There are 87 consecutive verified months (2019-07 to 2026-09) of national actual generation (report 01, #4), which reconcile exactly with region, state, sector and fuel reports. *Total* national production including renewables is **not** measurable from authorised data (Answer D, Limitation 1).

**B. Is state-wise generation forecasting feasible?**
**Partially.** Report 16 gives monthly actual generation for 34 states/UTs over 87 months, and it reconciles to region totals within 0.001%. But it covers only conventional stations by location. Ladakh begins in 2019-12 and Lakshadweep in 2022-12, Chandigarh is absent, and several NE states and UTs have very small, volatile bases (YoY changes above 100%).

**C. Is energy-source-wise forecasting feasible?**
**Yes, for conventional sources.**
- Nationally: coal, lignite, gas plus liquid fuel, diesel, nuclear and hydro (reports 01 and 11–15, which reconcile 100% with national THERMAL).
- At state level: THERMAL (coal plus lignite), NATURAL GAS, NUCLEAR and HYDRO (report 16 fuel groups).

**D. Can all six requested sources (coal, hydro, solar, wind, nuclear, gas) be forecast separately?**
**No. Four of the six can.** Coal, hydro (large hydro only), nuclear and natural gas have actual-generation series. **Solar and wind generation are NOT AVAILABLE** in either authorised source; only installed capacity exists (NPP installed-capacity reports, dashboard `res_solar_power`/`res_wind_power`, GitHub `Installed - Solar/Wind`), and the rules prohibit using capacity.

**E. Is there enough historical data for a 2047 forecast?**
**There is enough for a trend- or scenario-based projection, but not for a high-confidence statistical extrapolation.**
- The data has 6 complete financial years plus partial years.
- The horizon is about 21 years, roughly 3 times the observed span, and the history includes COVID-19 and a drought year.
- Seasonality is well identified (87 months), but the long-run trend rests on very few annual points.
- The forecast must therefore carry wide, explicit uncertainty.

**F. Which supporting variables are available?**
Population and GSDP (nominal), annual, 34 states/UTs, 2006–2024 (GitHub). Both are flagged UNVERIFIED because the README discloses XGBoost-predicted values that aren't flagged. CEA region and state labels are also available as geography keys. Installed-capacity variables exist but are not eligible.

**G. Which requirements can't be satisfied with the permitted datasets?**
- Solar generation and wind generation.
- Small-hydro and biomass generation.
- Urbanisation trends.
- Climatic indicators.
- Geographic and land-availability indicators.
- Region-wise demographic statistics beyond total population.
- Generation history before 2019-07.
- Coal vs lignite separation at state level.

**H. Which data gaps need addressing?**
1. Renewable *generation* data (highest priority, since the problem statement explicitly asks for solar and wind).
2. Pre-2019 actual generation history.
3. Urbanisation, climate and land indicators.
4. Verified, non-imputed population and GSDP, or at least flags marking which values were imputed.

Following the rules, none of these were sourced elsewhere. All are reported here as gaps for the organisers or for you to decide on.

**I. What modelling strategy is recommended, given the data actually available?**
1. **Target:** monthly actual generation (#4), aggregated to financial-year totals for the long-horizon model.
2. **Hierarchy:** national → region → state × fuel group, reconciled top-down or bottom-up. The data already reconciles exactly, so hierarchical reconciliation is well supported.
3. **Models:** simple, transparent long-horizon models (log-linear or saturating growth trends, optionally with population and GSDP drivers), with seasonal decomposition for the monthly signal. Validate by back-testing on held-out financial years (e.g. train FY19-20 to FY23-24, test FY24-25 and FY25-26).
4. **Scenarios:** low, central and high bands instead of a single point for 2047.
5. **Renewables:** only once a permitted renewable generation source is confirmed. Otherwise state clearly that the forecast covers conventional generation, and treat any renewable mix as a policy scenario, not a data-driven forecast.
6. **Before modelling:** apply the documented state-name mapping and handle the Ladakh/J&K split.

*Forecasting will start only after you explicitly approve this audit.*
