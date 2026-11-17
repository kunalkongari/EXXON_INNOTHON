# INNOTHON: India Energy Production Forecasting and 2047 Strategy

**Problem:** forecast India's energy production to 2047 and propose a region-specific generation strategy.

**What this project delivers:** an evidence-based forecast and strategy for India's **domestic conventional generation**: coal, lignite, natural gas, diesel, nuclear and large hydro. It is built only from the two authorised sources.

> **Scope.** Solar, wind, small-hydro and biomass generation are **not quantified**. No authorised actual-generation data exists for them, and installed capacity is prohibited as a substitute. The figures are therefore **not** India's total electricity production. Generation location is not consumption. Bhutan import is kept separate.

## Quick start: dashboard
From inside the `INNOTHON/` folder:
```bash
pip install -r requirements.txt
streamlit run dashboard/app.py
```
Then open the URL Streamlit prints (default http://localhost:8501).

The dashboard reads only the saved files in `outputs/`, so nothing needs to be re-run first.

To smoke-test all 9 pages and their filters without a browser:
```bash
python dashboard/test_app.py
```

**Dashboard pages:**
1. Executive overview
2. Historical generation
3. National forecast
4. Regional analysis
5. State explorer
6. Energy sources
7. 2047 energy strategy
8. Model performance
9. Assumptions & limitations

Every table has a CSV download.

## Authorised data sources
1. **National Power Portal:** CEA *Monthly Reports ACTUAL* (https://npp.gov.in/publishedReports). 1,740 XLS files, July 2019 - September 2026.
2. **Renewable India dataset:** https://github.com/chrisjaimyantony/renewable-india-dataset. Used only for an optional population/GSDP experiment, which was not adopted.

## Pipeline (reproduce everything)
| Phase | Command | Output |
|---|---|---|
| 1. Acquisition & audit | `python scripts/download_npp.py`, `scripts/download_github.py`, `scripts/inspect_files.py`, `scripts/audit_data.py`, `scripts/validate_data.py` | `data/`, audit reports |
| 2. Preparation & EDA | `python src/prepare_data.py`, `python src/eda.py` | `outputs/data/`, `outputs/eda/`, `outputs/reports/eda_report.md` |
| 3. Forecasting | `python src/build_model_data.py`; `python src/backtest.py --exp A` (also `B`, `C`, `EXT`); `python src/hier_backtest.py --exp A`; `python src/final_forecast.py --exp A --method BU`; `python src/scenarios.py`; `python src/make_reports.py --exp A --method BU` | `outputs/models`, `outputs/backtesting`, `outputs/forecasts`, `outputs/scenarios` |
| 4. Strategy | `python src/strategy.py` | `outputs/strategy/`, strategy reports |

Run the `src/` scripts from inside `src/`, or with `src` on the Python path. The Phase 3 backtests take about 1-1.5 hours on 8 cores.

## Folder layout
```
data/raw/        original downloads (never modified)
data/processed/  parsed CEA tables
data/metadata/   manifests, inventories, mappings
outputs/data/    forecasting datasets (monthly, FY, model-ready)
outputs/eda/     EDA figures and tables
outputs/models/  experiment config, selected models, ARIMA orders, final model specs
outputs/backtesting/  rolling-origin forecasts and metrics
outputs/forecasts/    reconciled 18-month forecast and intervals (+ unreconciled base)
outputs/scenarios/    FY2046-47 scenario projections and allocations
outputs/strategy/     national/regional/state strategy tables, source-mix scenarios, validation
reports/         audit, Phase 3 and Phase 4 reports (see final_methodology.md)
src/  scripts/  dashboard/
```

## Key reports
- **Audit:** `reports/data_audit.md`
- **Methodology:** `reports/final_methodology.md`
- **Phase 3 (forecasting):** `model_comparison.md`, `backtesting_report.md`, `covid_sensitivity.md`, `extended_history_sensitivity.md`, `hierarchical_reconciliation.md`, `forecasting_assumptions.md`, `forecast_uncertainty.md`
- **Phase 4 (strategy):** `national_2047_strategy.md`, `regional_2047_strategy.md`, `state_2047_strategy.md`, `energy_mix_strategy.md`
