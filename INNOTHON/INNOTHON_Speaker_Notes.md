# INNOTHON - Speaker Notes

Talk length: about 13 minutes of speaking plus 2 minutes for questions (12 slides). The same notes are embedded in each slide of `INNOTHON_Final_Presentation.pptx`.

Each slide's notes cover four things: **what to say**, the **technical context**, **what the visual means**, and the **transition**, followed by **likely judge questions** with short answers. Do not read the question sections aloud.

## Slide 1 - Forecasting India's Energy Production and Strategizing Its Fulfilment by 2047
_Target time: 0:45_

- **WHAT TO SAY (≈45 s):** Good morning. Our project is "Forecasting India's Energy Production and Strategizing Its Fulfilment by 2047". We built a data-driven framework that forecasts India's domestic conventional electricity generation - nationally, by grid region and by state - and turns those forecasts into region-specific strategies towards 2047.
- **CONTEXT:** Everything comes only from the two authorised sources - the National Power Portal (CEA monthly ACTUAL generation reports) and the organiser's GitHub dataset. Our results cover conventional generation: coal, lignite, gas, diesel, nuclear and large hydro.
- **THE VISUAL:** The hub shows the conventional sources we model. Solar and wind are drawn as outlines on purpose - there was no authorised actual-generation data for them, so they are not forecast.
- **TRANSITION:** Let me start with why a national number alone is not enough.
- **LIKELY QUESTION:** "Why not total generation?" - Because the authorised data contains actual generation only for conventional sources; using renewable installed capacity as a proxy is explicitly prohibited.

## Slide 2 - India's Energy Future: From Historical Generation to 2047
_Target time: 1:00_

- **WHAT TO SAY (≈60 s):** India needs a long-term view of electricity generation, but a single national projection hides an important fact: India's five grid regions generate electricity in very different ways - one is almost all coal, another is hydro and gas-led. So our framework moves from Challenge, to Forecast, to Strategy.
- **OBJECTIVES:** (1) forecast generation at national, regional and state level; (2) understand how much each conventional source contributes; (3) build evidence-based regional strategies towards 2047.
- **THE VISUAL:** Read left to right - the problem, the forecasting layer, and the strategy layer that uses the forecasts.
- **TRANSITION:** Before any forecast, we had to build a trustworthy data foundation.
- **LIKELY QUESTION:** "Is this a demand forecast?" - No. We forecast generation (production) from actual generation reports; demand and consumption data were not used, as required by the rules.

## Slide 3 - Building the Foundation: 1,745 Verified Source Files
_Target time: 1:00_

- **WHAT TO SAY (≈60 s):** Our foundation is 1,745 verified files: 1,740 monthly CEA "Actual" generation reports from the National Power Portal, the 4 files of the organiser's GitHub repository, and one dashboard snapshot kept as evidence. Every file was checked - it exists, it is genuinely an Excel or PDF file and it opens.
- **COVERAGE:** 87 continuous months, July 2019 to September 2026 - the portal's archive has nothing earlier - across 5 grid regions and 34 states and UTs.
- **THE GRID:** These are the sources with actual generation data: coal and lignite, large hydro, nuclear and natural gas. Diesel is tracked as its own series but is part of domestic generation; Bhutan imports are kept completely separate.
- LIMITATION (be explicit): Solar and wind actual generation was not available in the authorised sources, and installed capacity cannot be used as a substitute - so renewables are not forecast.
- **TRANSITION:** Next, how we turned these reports into a reliable dataset.
- **LIKELY QUESTIONS:** "Why only from 2019?" - The NPP archive returns no monthly ACTUAL reports before July 2019; we queried back to 2010. "What did you use from GitHub?" - Only population/GSDP for an optional test; it was not adopted because values are partly model-imputed.

## Slide 4 - Turning Raw Reports into a Reliable Forecasting Dataset
_Target time: 1:10_

- **WHAT TO SAY (≈70 s):** The CEA reports are formatted spreadsheets, not tables, so we built a six-step pipeline: raw reports, extraction, monthly actual generation, state and regional aggregation, validation, and a forecast-ready dataset.
- **KEY RULES:** Raw files are never modified. Each report has both a monthly figure and a cumulative April-to-date figure - we use only the monthly actual as the forecasting target, so nothing is double-counted. Everything is in GWh. Station, state, regional and national totals are reconciled, and Bhutan imports are kept out of domestic generation.
- VALIDATION - three different stages (keep them separate):
- (1) Audit reconciliation: all cross-report checks agree within 0.001%; the single exception is February 2020 hydro, where the sector report and the national report differ by 2.26%.
- (2) Data preparation: 13 of 14 identity checks within 1 GWh; the one exception is the extended 2018-19 history, which differs by at most 0.10% from originally published figures - so it is used only as a sensitivity test.
- (3) Strategy and dashboard: 19 of 19 checks passed.
- **TRANSITION:** With clean data, what does history tell us?
- **LIKELY QUESTION:** "Did you fix the 2.26% difference?" - No; we never alter source data. It is documented, and it does not affect the national series we model.

## Slide 5 - What Does India's Historical Generation Tell Us?
_Target time: 1:10_

- **WHAT TO SAY (≈70 s):** This is seven years of actual domestic conventional generation. It grew from 1,245 TWh in FY2019-20 to a peak of 1,569 TWh in FY2024-25 - about 3.5% a year overall.
- THREE EVENTS (the coloured bars): FY2020-21 dipped 1.5% because of COVID. FY2023-24 still grew, but hydro fell by about 17% in a weak monsoon year, and thermal filled the gap. FY2025-26 fell 2.5%: thermal declined while hydro recovered.
- **THE MIX:** Coal alone is about 82% of conventional generation, large hydro 11%, nuclear 3.6%, lignite 2% and gas 1.7%.
- **WHY IT MATTERS:** The series is short and has structural breaks, so the forecasting method must be validated carefully - which is the next slide.
- **LIKELY QUESTIONS:** "Why did FY2025-26 fall?" - Our data shows thermal fell and hydro rose; we cannot attribute the cause because renewable generation is not in the authorised data. "Is FY2019-20 complete?" - Monthly files start in July 2019; the full-year value is CEA's own published April-to-March cumulative figure.

## Slide 6 - How Do We Forecast India's Energy Generation?
_Target time: 1:05_

- **WHAT TO SAY (≈65 s):** Our workflow has seven steps, shown on the right: historical data, exploratory analysis, model training, rolling-origin backtesting, model selection, forecast generation and hierarchical reconciliation.
- **MODELS:** We compared simple baselines - naive, seasonal naive and linear trend - with statistical models - exponential smoothing (ETS), Holt-Winters and ARIMA/SARIMA - and machine learning - Random Forest and XGBoost, trained as global models across all series.
- **BACKTESTING:** Rolling-origin means we repeatedly pretend to be at a past month, train only on data up to that point, and forecast 1, 3, 6 and 12 months ahead, then compare with what actually happened. Selection is based only on these out-of-sample errors, never on training fit.
- **COVID:** A March-May 2020 intervention indicator was used for models that accept regressors.
- **TRANSITION:** So which model won?
- **LIKELY QUESTIONS:** "Why not deep learning (LSTM)?" - With 87 monthly points, deep models would overfit; our ML results already show that more complex models did not beat ETS. "How many forecast origins?" - 39 monthly origins for national, regional and source series; 13 quarterly origins for states.

## Slide 7 - Why Exponential Smoothing Was Selected
_Target time: 1:10_

- **WHAT TO SAY (≈70 s):** This chart shows the out-of-sample MASE of the model selected at each level. MASE compares forecast error with the error of a simple seasonal-naive forecast: below 1 means our model does better than that benchmark scale. The dashed line marks 1.0.
- **RESULT:** Exponential smoothing, ETS, was the most accurate model at six of seven levels - 0.710 nationally and for regions, 0.799 for national sources, 0.771 for the largest states, 0.976 for group B states and 0.961 for state-by-source series.
- **ML:** XGBoost and Random Forest did not outperform ETS - nationally they scored 0.990 and 1.131. With only 87 months, a well-specified smoothing model captures trend and seasonality more reliably than tree models.
- **GROUP C:** For the eight small, volatile states, no model beat seasonal naive, so we keep the benchmark - simplest adequate model.
- **TRANSITION:** Forecasting each level separately creates a new problem: the numbers do not add up. That is solved by reconciliation.
- **LIKELY QUESTIONS:** "Why MASE and not MAPE?" - Some state-by-source series contain zeros, which break MAPE; MASE is scale-free and robust. "Was selection biased?" - The rule was fixed before results were seen: lowest out-of-sample MASE, and it must beat seasonal naive.

## Slide 8 - One Consistent Forecast Across Every Geographic Level
_Target time: 1:05_

- **WHAT TO SAY (≈65 s):** We forecast at four linked levels: one national total, five grid regions, 33 state series and 73 state-by-source series. If each is forecast independently, states would not add up to their region, and regions would not add up to the nation.
- **RECONCILIATION:** We compared bottom-up, top-down, middle-out and least-squares reconciliation. Bottom-up was selected: forecasts are made at the state-by-source level and summed upwards, so every level is consistent by construction. Its overall hierarchical MASE is 0.827.
- **TRADE-OFF:** Nationally the error rises slightly - from 0.710 before reconciliation to 0.741 after - but regional accuracy improves from 0.716 to 0.671. We accept that small national cost for a fully consistent picture.
- **COUNTING NOTE:** 33 state series represent 34 states and UTs because Jammu & Kashmir and Ladakh are combined for continuity. Source splits at state level are limited because CEA reports lignite plants as coal.
- **TRANSITION:** Short-term forecasts are validated for 12 months. For 2047 we move to scenarios.
- **LIKELY QUESTIONS:** "Why not MinT/optimal reconciliation?" - Least-squares variants (OLS, WLS) broke down on very small series; bottom-up was most robust. "Which unreconciled forecast is better?" - The unreconciled national ETS is kept in the dashboard for comparison.

## Slide 9 - Three Possible Pathways for India's Conventional Energy Generation in 2047
_Target time: 1:20_

- **WHAT TO SAY (≈80 s - key slide):** Monthly models are validated only 12 months ahead, so 2047 is presented as three assumption-driven pathways, not as predictions.
- **HOW THEY ARE BUILT:** Each scenario starts from a growth rate we actually observed and moves linearly to an assumed growth rate by FY2046-47. Low starts at 0.7% (the recent FY2023-24 to FY2025-26 slowdown) and ends at minus 1.5%. Central starts at 3.5% (the full FY2019-20 to FY2025-26 trend) and ends at 0%, a plateau. High starts at 6.4% (the post-COVID expansion) and ends at plus 2%. The launch point is our reconciled statistical forecast for FY2027-28.
- **RESULTS:** Median 2047 conventional generation is 1,564 TWh (low), 2,352 TWh (central - our planning baseline) and 3,690 TWh (high). The P10-P90 bands come from 5,000 simulated paths with year-to-year shocks sized from history: 1,863 to 2,968 TWh for central.
- **READ THE BOTTOM CHART:** On one common scale, the gap between scenarios is larger than any single band - the long-run assumption matters more than model precision.
- **CAVEAT:** These are domestic conventional generation only - not total energy requirement, and not including renewables.
- **TRANSITION:** Nationally that is the range; regionally the picture is very different.
- **LIKELY QUESTIONS:** "Why should conventional growth go to zero?" - It is a stated assumption (plateau), not an estimate; the low and high cases bracket it. "Why not use population or GDP?" - Only six overlapping years, partly imputed values and no authorised projections to 2047.

## Slide 10 - India Is Not One Energy Region: Five Regions, Different Priorities
_Target time: 1:10_

- **WHAT TO SAY (≈70 s):** India's conventional generation is not one system. The schematic map shows each grid region's share of national conventional generation in FY2025-26.
- WESTERN is the largest contributor - about 36% - and about 91% of its conventional output is coal and lignite.
- EASTERN grew fastest, about 5.5% a year, but about 95% of its conventional mix is coal and lignite - a concentration risk.
- NORTH EASTERN is small (1.3%) but the most diversified: about 40% large hydro and 39% natural gas.
- SOUTHERN has the highest nuclear share, about 7%.
- NORTHERN gets about 22% of its conventional generation from large hydro.
- **STRATEGY IMPLICATION:** The same national target means different actions per region - protecting hydro against dry years in the North and North-East, retaining nuclear baseload in the South, and managing coal concentration in the East and West.
- **IMPORTANT CAVEAT:** These describe where generation happens and with which sources - not electricity demand and not resource potential.
- **TRANSITION:** How should the conventional mix evolve to 2047?
- **LIKELY QUESTIONS:** "Why a schematic, not a real map?" - We only use authorised data; the layout shows CEA regions without importing an external boundary dataset. "Do regions trade power?" - Yes; generation location is not consumption, which is why we never call these regional requirements.

## Slide 11 - From Forecasting to Strategic Planning
_Target time: 1:10_

- **WHAT TO SAY (≈70 s):** The strategy layer has two parts that we keep strictly separate.
- FIRST - the trend reference. Extrapolating source shares exposed an artefact: natural gas fell from 4.2% to 1.7% between FY2020-21 and FY2022-23 - a one-off step - and has been flat since. A straight trend (T1) keeps extending that step and drives gas to 0.11% by 2047. T2 simply holds today's shares. T3 stabilises gas at its post-2022 average of 1.87%; we recommend T3 as the planning baseline because it does not extrapolate an unusual decline forever.
- SECOND - policy scenarios, which are recommendations, not forecasts. They allocate the same conventional total differently. P0 keeps today's mix (83.7% coal and lignite), P1 uses the seven-year average (82.9%), P3 guarantees no source falls below its best historical output (83.3%). P2 sets hydro, nuclear and gas at the best shares the existing system has already achieved, which lowers coal-plus-lignite to 79.6%. We recommend P2 as the preferred direction.
- **BE CLEAR:** P2 is grounded in history, not optimised - no cost, grid or resource-potential modelling was done, and solar and wind are not quantified.
- **TRANSITION:** How can decision-makers use all of this?
- **LIKELY QUESTIONS:** "Is 79.6% achievable?" - Every share in P2 has already occurred in FY2019-20 to FY2025-26; feasibility in TWh terms needs capacity and cost studies outside our authorised data. "Where are renewables?" - They would come on top of, or substitute for, conventional generation; they can be added once authorised generation data exists.

## Slide 12 - A Decision-Support Framework for India's Energy Future
_Target time: 1:00_

- **WHAT TO SAY (≈60 s):** Everything we showed is packaged into an interactive Streamlit dashboard with nine pages: an executive overview, historical generation, national forecasts with uncertainty, regional analysis, a state explorer, energy sources, the 2047 strategy, model performance and an assumptions page. Every chart has filters and every table can be downloaded. It runs locally - "streamlit run dashboard/app.py" - and reads only our saved, validated outputs.
- **THREE MESSAGES:** First, historical generation data, handled carefully, can support a structured and validated forecasting framework. Second, India's regions are very different, so planning must be region-specific. Third, for a horizon as long as 2047, transparent assumptions and uncertainty ranges matter more than a single number.
- **CLOSE:** From historical generation data to evidence-based regional strategies - a transparent framework for India's conventional energy planning towards 2047. Thank you - we are happy to take questions.
- **LIKELY QUESTIONS:** "What would you add next?" - Authorised actual generation data for solar and wind, so total production can be forecast with the same pipeline; then cost and grid constraints for optimised mixes. "Can it be updated?" - Yes; the pipeline is scripted end to end and re-runs when new monthly CEA reports are published.
