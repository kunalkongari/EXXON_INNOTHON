# INNOTHON Final Presentation: Slide-to-Source Mapping

**Deck:** `INNOTHON_Final_Presentation.pptx`. 12 slides, 16:9 (10 × 5.625 in).
**Built by:** `presentation/build_deck.py`, on the Slidesgo template *Petroleum Industry Infographics* (`Petroleum Industry Infographics by Slidesgo.pptx`). The template file itself is unchanged.

**What was reused from the template:**
- theme colours: yellow FBCD0B, amber EA9600, red E51000, dark red C10500, grey-teal 9BB2AF / C1D3D0 / 6C7F7C, near-black 252626
- master, layouts and title placeholders
- infographic structures: the 3-card layout, icons in coloured circles, numbered process circles, the three-circle layout and the numbered-conclusion layout
- each final slide is built on one template slide (template numbers 1, 3, 31, 7, 11, 12, 29, 23, 25, 18, 30, 28)

**What was removed:** all petroleum artwork (pump jacks, rigs, tankers, barrels, US map), petroleum text and template animations.

**What was added:**
- energy-sector icons (react-icons, rendered to PNG): thermal plant, coal wagon, dam, nuclear plant, gas flame, generator, pylon, solar, wind
- native, editable PowerPoint charts on slides 5 and 11
- editable shapes for every other infographic
- a real dashboard screenshot on slide 12

## Slide-to-source mapping

| # | Slide | Numbers shown | Source file(s) | Layer |
|---|---|---|---|---|
| 1 | Title | Data window Jul-2019 – Sep-2026 | `reports/data_audit.md` | - |
| 2 | Challenge → Forecast → Strategy | (objectives, no figures) | project brief / `reports/final_methodology.md` | - |
| 3 | Data foundation | 1,745 files = 1,740 NPP XLS + 4 GitHub + 1 dashboard JSON; 87 months; 5 regions; 34 states/UTs; coal+lignite ≈84% (83.7%) | `data/metadata/download_manifest.csv`, `reports/download_summary.md`, `reports/data_audit.md`, `outputs/strategy/source_mix_scenarios.csv` (P0 = FY2025-26 shares) | Actual |
| 4 | Data engineering & validation | 2.26% (Feb-2020 hydro, sector vs national report); 13/14 preparation checks; 19/19 strategy checks | `reports/data_quality_report.md` §5; `outputs/data/validation_checks.csv`; `outputs/strategy/validation_checks.csv` | Actual / QA |
| 5 | Historical trends | FY totals 1,245 / 1,226 / 1,313 / 1,414 / 1,509 / 1,569 / 1,530 TWh; CAGR 3.49% (≈3.5%); −1.5% FY20-21; hydro −17.3% FY23-24; −2.5% FY25-26; mix: coal 81.75%, hydro 10.93%, nuclear 3.61%, lignite 1.98%, gas 1.70%, diesel 0.03% | `outputs/data/fy_national.csv`; `outputs/eda/tables/fy_national_growth.csv`; `outputs/eda/tables/fy_source_shares.csv` | Actual |
| 6 | Methodology | 87 months; 120 series; horizons 1/3/6/12; forecast Oct-2026 → Mar-2028 | `reports/backtesting_report.md`; `outputs/models/experiment_config.json`; `outputs/forecasts/monthly_forecast.csv` | Method |
| 7 | Model selection | MASE 0.710 / 0.710 / 0.799 / 0.771 / 0.976 / 0.902 / 0.961; national best baseline 0.769; XGBoost 0.990; RF 1.131 | `outputs/models/selected_models_A.csv`; `outputs/backtesting/metrics_by_level_model_A.csv` | Statistical forecast (validation) |
| 8 | Hierarchy | 1 / 5 / 33 / 73 series; cells by source: coal+lignite 18, hydro 25, gas 17, nuclear 6, diesel 7; overall MASE 0.827; national 0.710 → 0.741; regions 0.716 → 0.671 | `outputs/data/node_metadata.csv`; `reports/hierarchical_reconciliation.md`; `outputs/backtesting/hier_metrics_A.csv` | Statistical forecast |
| 9 | 2047 scenarios | Low 1,564 (1,248–1,970); Central 2,352 (1,863–2,968); High 3,690 (2,944–4,624) TWh; growth 0.7%→−1.5%, 3.5%→0%, 6.4%→+2%; 5,000 paths | `outputs/scenarios/fy_scenarios_national.csv`; `outputs/scenarios/scenario_assumptions.json` | Scenario projection |
| 10 | Regional strategy | Shares N 24.9 / W 36.0 / S 20.1 / E 17.7 / NE 1.3%; W coal+lignite 90.8%; E CAGR 5.5%, coal+lignite 95.2%; NE hydro 40.3%, gas 38.7%; S nuclear 7.0%, hydro 14.1%; N hydro 21.7% | `outputs/strategy/regional_summary.csv` | Actual (FY2025-26) |
| 11 | Energy-mix strategy | T1 gas 0.11%; T2 1.70%; T3 1.87%; coal+lignite P0 83.7%, P1 82.9%, P2 79.6%, P3 83.3% (central P50, 2,352 TWh) | `outputs/strategy/source_mix_scenarios.csv`; `outputs/strategy/source_trend_diagnostics.csv`; `reports/energy_mix_strategy.md` | Scenario projection / Policy scenario |
| 12 | Dashboard & conclusion | 9 pages; local URL http://localhost:8599 | `dashboard/app.py`; screenshot captured from the running app (Executive overview, light theme) | - |

## Items flagged for review

1. **Slide 4: validation stages were separated, not merged.** The brief linked "13/14 preparation checks" with "one hydro discrepancy of 2.26% in February 2020". In the project files these are different stages:
   - **Preparation (13/14):** the one check outside the 1 GWh tolerance is the *extended-history overlap*, which differs by at most 0.10% (`outputs/data/validation_checks.csv`).
   - **Audit reconciliation (2.26%):** the February 2020 hydro gap is between the sector report and the national report (`reports/data_quality_report.md`).

   The slide shows them as separate tiles.
2. **"Diesel, retained separately" (slide 3).** Diesel is its own source series, but it is *part of* domestic conventional generation (≈0.03%). Only Bhutan imports are kept outside the domestic total. The slide says exactly this.
3. **Regional map (slide 10)** is a *schematic* grid-region layout, labelled "not to scale". A real India boundary map would mean bringing in an external geographic dataset, which the competition rules exclude. Swap in an official map only if the organisers allow it.
4. **MASE wording (slide 7).** MASE divides out-of-sample errors by the *in-sample* seasonal-naive error. "MASE < 1" therefore means errors are smaller than the seasonal-naive error scale. The out-of-sample seasonal-naive forecast itself scores 0.89 nationally. The speaker notes explain this nuance.
5. **Fonts.** The template uses *Fira Sans Extra Condensed* and *Roboto*, which are not installed on this machine and may be missing on the presentation PC. The deck uses **Arial Narrow** (headings) and **Arial** (body), which ship with Office, so it renders identically everywhere.
6. **Dashboard URL** `http://localhost:8599` works only on the machine running `streamlit run dashboard/app.py`. For a live demo, start it before presenting; the default Streamlit port is 8501 unless `--server.port 8599` is passed.

## Quality checks performed
- Every slide was rendered with Microsoft PowerPoint 16 (COM export) and inspected visually. Overlaps, clipping and spacing problems were fixed over 4 render passes.
- `validate.py` (OOXML schema, relationships, content types) was run against the template: **all validations passed**.
- No leftover template or petroleum text in any slide, note, layout or master. All 30 media files are referenced only by slides; none are template artwork.
- Speaker notes are present on all 12 slides (≈139–249 words each).
- Every number on the slides was checked against the source files in the table above.
