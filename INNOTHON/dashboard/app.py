"""
INNOTHON - India Conventional Generation: Forecasts and 2047 Strategy dashboard.

Run:  streamlit run dashboard/app.py     (from the INNOTHON folder)

Reads ONLY saved outputs (outputs/data, outputs/forecasts, outputs/scenarios, outputs/strategy,
outputs/backtesting, outputs/models). No model is re-fitted and no figure is computed from anything
other than those files. Domestic conventional generation only - solar, wind, small hydro and biomass
generation are not quantified (no authorised actual-generation data). Bhutan import is separate.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs"
st.set_page_config(page_title="India Conventional Generation 2047", page_icon="⚡", layout="wide")

# ----------------------------------------------------------------------------- style
SLOT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SRC_COL = {"COAL": SLOT[0], "COAL_LIGNITE": SLOT[0], "HYDRO": SLOT[1], "NUCLEAR": SLOT[2], "NATURAL_GAS": SLOT[3], "LIGNITE": SLOT[4], "DIESEL": SLOT[6],
           "THERMAL": SLOT[0]}
SRC_LABEL = {"COAL": "Coal", "LIGNITE": "Lignite", "COAL_LIGNITE": "Coal + lignite", "NATURAL_GAS": "Natural gas", "DIESEL": "Diesel",
             "NUCLEAR": "Nuclear", "HYDRO": "Large hydro", "THERMAL": "Thermal"}
REGIONS = ["Northern", "Western", "Southern", "Eastern", "North Eastern"]
REG_COL = dict(zip(REGIONS, SLOT))
SC_COL = {"low": SLOT[2], "central": SLOT[0], "high": SLOT[1]}
try:
    DARK = (st.context.theme.type == "dark")
except Exception:  # noqa: BLE001 - older Streamlit / test harness
    DARK = False
INK = "#f0efec" if DARK else "#0b0b0b"          # primary series ink (actuals) - follows the active theme
INK2 = "#c3c2b7" if DARK else "#52514e"
GRID = "rgba(128,128,128,0.25)"                    # neutral grid, readable on light and dark
SHADE = "rgba(128,128,128,0.14)"
FULL_FYS = [f"FY{y}-{str(y + 1)[2:]}" for y in range(2019, 2026)]
SCOPE = ("**Scope:** domestic **conventional** generation monitored by CEA (coal, lignite, gas, diesel, nuclear, large hydro). "
         "Solar, wind, small hydro and biomass generation are **not quantified** (no authorised actual-generation data), so these figures are "
         "**not** India's total electricity production or requirement. Generation location ≠ consumption. Bhutan import is shown separately.")

st.markdown("""<style>
.block-container {padding-top: 1.6rem; padding-bottom: 2rem;}
div[data-testid="stMetricValue"] {font-size: 1.55rem;}
.layer {display:inline-block;color:#0b0b0b;padding:2px 9px;border-radius:10px;font-size:0.78rem;font-weight:600;margin-right:6px;border:1px solid #c9c8c2}
.l-act {background:#eef3fb} .l-stat {background:#eaf7f1} .l-scen {background:#fdf3e6} .l-pol {background:#f6eefa}
</style>""", unsafe_allow_html=True)


def layer_badges(*names):
    cls = {"Actual": "l-act", "Statistical forecast": "l-stat", "Scenario projection": "l-scen", "Policy scenario": "l-pol"}
    st.markdown(" ".join(f'<span class="layer {cls[n]}">{n}</span>' for n in names), unsafe_allow_html=True)


def fig_base(fig, title="", ytitle="", height=420, legend=True):
    fig.update_layout(title=dict(text=title, x=0, xref="paper", font=dict(size=15)), height=height,
                      margin=dict(l=70, r=20, t=80 if title else 40, b=60),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", hovermode="x unified", showlegend=legend,
                      legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, font=dict(size=11)),
                      font=dict(color=INK, size=12))
    fig.update_xaxes(showgrid=False, linecolor=GRID, automargin=True)
    fig.update_yaxes(title=ytitle, gridcolor=GRID, zeroline=False, automargin=True)
    return fig


def download(df: pd.DataFrame, name: str, label="Download CSV"):
    st.download_button(label, df.to_csv(index=False).encode("utf-8"), file_name=name, mime="text/csv", key=f"dl_{name}")


def band(fig, x, lo, hi, color, name, opacity=0.18):
    opacity = min(opacity * (1.8 if DARK else 1.0), 0.6)  # bands need more weight on a dark surface
    fig.add_trace(go.Scatter(x=list(x) + list(x)[::-1], y=list(hi) + list(lo)[::-1], fill="toself", fillcolor=color, opacity=opacity,
                             line=dict(width=0), name=name, hoverinfo="skip"))


def twh(v):
    return f"{v / 1000:,.0f} TWh"


# ----------------------------------------------------------------------------- data
@st.cache_data
def load():
    d = {}
    d["mn"] = pd.read_csv(O / "data/monthly_national.csv")
    d["mr"] = pd.read_csv(O / "data/monthly_regional.csv")
    d["ms"] = pd.read_csv(O / "data/monthly_state.csv")
    d["fn"] = pd.read_csv(O / "data/fy_national.csv")
    d["fr"] = pd.read_csv(O / "data/fy_regional.csv")
    d["fs"] = pd.read_csv(O / "data/fy_state.csv")
    d["meta"] = pd.read_csv(O / "data/node_metadata.csv")
    d["mf"] = pd.read_csv(O / "forecasts/monthly_forecast.csv")
    d["ff"] = pd.read_csv(O / "forecasts/fy_forecast.csv")
    d["base"] = pd.read_csv(O / "forecasts/base_forecast_unreconciled.csv")
    d["iq"] = pd.read_csv(O / "forecasts/interval_quantiles.csv")
    d["scn"] = pd.read_csv(O / "scenarios/fy_scenarios_national.csv")
    d["asm"] = json.loads((O / "scenarios/scenario_assumptions.json").read_text(encoding="utf-8"))
    for k in ["national_strategy", "regional_strategy", "regional_summary", "state_strategy", "state_summary", "source_mix_scenarios",
              "source_trend_diagnostics", "regional_source_mix_2047", "validation_checks", "dash_covid_comparison", "dash_extended_comparison"]:
        d[k] = pd.read_csv(O / f"strategy/{k}.csv")
    d["met"] = pd.read_csv(O / "backtesting/metrics_by_level_model_A.csv")
    d["meth"] = pd.read_csv(O / "backtesting/metrics_by_level_model_horizon_A.csv")
    d["hier"] = pd.read_csv(O / "backtesting/hier_metrics_A.csv")
    d["sel"] = pd.read_csv(O / "models/selected_models_A.csv")
    d["ver"] = (O / "data/model_data_verification.md").read_text(encoding="utf-8")
    for k in ("mn", "mr", "ms"):
        d[k]["date"] = pd.PeriodIndex(d[k].period, freq="M").to_timestamp()
    for k in ("mf", "base"):
        d[k]["date"] = pd.PeriodIndex(d[k].period, freq="M").to_timestamp()
    return d


D = load()
mn, mr, ms, mf, ff = D["mn"], D["mr"], D["ms"], D["mf"], D["ff"]
dom_fy = D["fn"][(D["fn"].series == "DOMESTIC_CONVENTIONAL_TOTAL") & D["fn"].fy.isin(FULL_FYS)].set_index("fy").fy_total_gwh
n47 = D["scn"][D["scn"].fy_start == 2046].set_index("scenario")
f26 = ff[(ff.node_id == "TOTAL") & (ff.fy == "FY2026-27")].iloc[0]
f27 = ff[(ff.node_id == "TOTAL") & (ff.fy == "FY2027-28")].iloc[0]


def hist_series(series):
    return mn[mn.series == series].sort_values("date")


def fc_node(node):
    return mf[mf.node_id == node].sort_values("date")


def forecast_chart(hist_df, fc_df, title, color=SLOT[0], base_df=None, height=430, show_from=None):
    fig = go.Figure()
    h = hist_df if show_from is None else hist_df[hist_df.date >= show_from]
    fig.add_trace(go.Scatter(x=h.date, y=h.value_gwh, name="Actual", line=dict(color=INK, width=2),
                             hovertemplate="%{x|%b %Y}: %{y:,.0f} GWh"))
    if fc_df is not None and len(fc_df):
        if "lo95" in fc_df and fc_df.lo95.notna().any():
            band(fig, fc_df.date, fc_df.lo95, fc_df.hi95, color, "95% interval", 0.12)
            band(fig, fc_df.date, fc_df.lo80, fc_df.hi80, color, "80% interval", 0.22)
        fig.add_trace(go.Scatter(x=fc_df.date, y=fc_df.forecast_gwh, name="Forecast (reconciled)", line=dict(color=color, width=2.5),
                                 customdata=np.stack([fc_df.h, fc_df.beyond_validated_horizon], axis=-1),
                                 hovertemplate="%{x|%b %Y}: %{y:,.0f} GWh (h=%{customdata[0]}, beyond validated: %{customdata[1]})"))
        last = fc_df[fc_df.beyond_validated_horizon == False]  # noqa: E712
        if len(last) < len(fc_df):
            fig.add_vrect(x0=last.date.max(), x1=fc_df.date.max(), fillcolor=SHADE, opacity=1, line_width=0,
                          annotation_text="beyond validated 12-month horizon", annotation_position="top left", annotation_font_size=10)
    if base_df is not None and len(base_df):
        fig.add_trace(go.Scatter(x=base_df.date, y=base_df.base_forecast_gwh, name="Unreconciled national ETS (comparison)",
                                 line=dict(color=SLOT[7], width=1.8, dash="dot"), hovertemplate="%{x|%b %Y}: %{y:,.0f} GWh"))
    return fig_base(fig, title, "GWh / month", height)


def scenario_fan(selected=("low", "central", "high"), height=430):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=list(dom_fy.index), y=dom_fy.values / 1000, name="Actual FY", mode="lines+markers", line=dict(color=INK, width=2)))
    fig.add_trace(go.Scatter(x=["FY2025-26", "FY2026-27", "FY2027-28"], y=[dom_fy["FY2025-26"] / 1000, f26.fy_total_gwh / 1000, f27.fy_total_gwh / 1000],
                             name="Statistical forecast", mode="lines+markers", line=dict(color=INK, dash="dash")))
    for s in selected:
        x = D["scn"][(D["scn"].scenario == s) & (D["scn"].fy_start >= 2027)].sort_values("fy_start")
        band(fig, x.fy, x.p10_gwh.fillna(x.p50_gwh) / 1000, x.p90_gwh.fillna(x.p50_gwh) / 1000, SC_COL[s], f"{s} P10-P90", 0.15)
        fig.add_trace(go.Scatter(x=x.fy, y=x.p50_gwh / 1000, name=f"{s.title()} (P50)", line=dict(color=SC_COL[s], width=2.5),
                                 hovertemplate="%{x}: %{y:,.0f} TWh"))
    fig.update_xaxes(tickangle=-40, nticks=12)
    return fig_base(fig, "", "TWh / year", height)


# ----------------------------------------------------------------------------- navigation
PAGES = ["1 · Executive overview", "2 · Historical generation", "3 · National forecast", "4 · Regional analysis", "5 · State explorer",
         "6 · Energy sources", "7 · 2047 energy strategy", "8 · Model performance", "9 · Assumptions & limitations"]
with st.sidebar:
    st.markdown("### ⚡ India conventional generation\n**Forecasts & 2047 strategy**")
    page = st.radio("Page", PAGES, label_visibility="collapsed", key="page")
    st.divider()
    st.caption("Data: NPP / CEA Monthly Reports ACTUAL, Jul-2019 to Sep-2026 (87 months). Units: GWh (monthly), TWh (annual); 1 GWh = 1 MU.")
    st.caption("Layers: Actual · Statistical forecast (validated ETS, to Mar-2028) · Scenario projection (assumption-driven, to FY2046-47) · Policy scenario (recommendation).")

st.title(page.split(" · ")[1])
st.info(SCOPE, icon="ℹ️")

# ============================================================================= 1 EXECUTIVE
if page == PAGES[0]:
    layer_badges("Actual", "Statistical forecast", "Scenario projection")
    c = st.columns(5)
    c[0].metric("FY2025-26 actual", twh(dom_fy["FY2025-26"]), f"{100 * (dom_fy['FY2025-26'] / dom_fy['FY2024-25'] - 1):+.1f}% YoY")
    c[1].metric("FY2026-27 forecast", twh(f26.fy_total_gwh), f"{100 * (f26.fy_total_gwh / dom_fy['FY2025-26'] - 1):+.1f}% vs FY25-26",
                help=f"Reconciled ETS; 6 actual + 6 forecast months. 95% interval {f26.fy_lo95 / 1000:,.0f}-{f26.fy_hi95 / 1000:,.0f} TWh")
    for i, s in enumerate(["low", "central", "high"]):
        c[2 + i].metric(f"FY2046-47 {s} (P50)", twh(n47.loc[s, "p50_gwh"]),
                        help=f"P10-P90 {n47.loc[s, 'p10_gwh'] / 1000:,.0f}-{n47.loc[s, 'p90_gwh'] / 1000:,.0f} TWh. Assumption-driven projection, not a prediction.")
    st.plotly_chart(scenario_fan(), width="stretch")
    col1, col2 = st.columns([3, 2])
    with col1:
        st.subheader("Key findings")
        sh = D["fn"][D["fn"].series.isin(["COAL", "LIGNITE", "NATURAL_GAS", "DIESEL", "NUCLEAR", "HYDRO"]) & (D["fn"].fy == "FY2025-26")].set_index("series").fy_total_gwh
        cagr = 100 * ((dom_fy["FY2025-26"] / dom_fy["FY2019-20"]) ** (1 / 6) - 1)
        rs = D["regional_summary"].set_index("region")
        st.markdown(f"""
- Conventional generation grew **{cagr:.1f}%/yr** (FY2019-20→FY2025-26) but **fell {abs(100 * (dom_fy['FY2025-26'] / dom_fy['FY2024-25'] - 1)):.1f}%** in FY2025-26 (thermal decline, hydro recovery).
- The reconciled forecast for FY2026-27 is **{twh(f26.fy_total_gwh)}** (95%: {f26.fy_lo95 / 1000:,.0f}–{f26.fy_hi95 / 1000:,.0f}); Apr–Sep 2026 is already +7.5% on Apr–Sep 2025.
- Coal + lignite = **{100 * (sh['COAL'] + sh['LIGNITE']) / sh.sum():.0f}%** of conventional output; large hydro {100 * sh['HYDRO'] / sh.sum():.0f}%, nuclear {100 * sh['NUCLEAR'] / sh.sum():.1f}%, gas {100 * sh['NATURAL_GAS'] / sh.sum():.1f}%.
- **Western** region produces {rs.loc['Western', 'share_of_national_FY2025-26_%']:.0f}% of conventional generation; **Eastern** grew fastest ({rs.loc['Eastern', 'CAGR_FY19-20_to_FY25-26_%']:.1f}%/yr); **North Eastern** is hydro/gas-led.
- 2047 scenarios span **{n47.loc['low', 'p50_gwh'] / 1000:,.0f}–{n47.loc['high', 'p50_gwh'] / 1000:,.0f} TWh** (P50): the range is driven by assumed long-run growth, not by model precision.
- ETS beats every benchmark out-of-sample at national level (MASE 0.71 vs 0.77 for the best baseline).
""")
    with col2:
        st.subheader("Headline table")
        t = D["national_strategy"]
        t = t[t.series.str.startswith("DOMESTIC") & ~t.series.str.contains("unreconciled") & t.fy.isin(["FY2024-25", "FY2025-26", "FY2026-27", "FY2027-28", "FY2035-36", "FY2046-47"])]
        show = t[["fy", "layer", "scenario", "p10_gwh", "p50_gwh", "p90_gwh"]].copy()
        for cc in ["p10_gwh", "p50_gwh", "p90_gwh"]:
            show[cc] = (show[cc] / 1000).round(0)
        st.dataframe(show.rename(columns={"p10_gwh": "low bound TWh", "p50_gwh": "central TWh", "p90_gwh": "high bound TWh"}), hide_index=True, width="stretch")
        st.caption("Forecast rows: bounds = 80% interval. Scenario rows: P10/P90.")
        download(D["national_strategy"], "national_strategy.csv")

# ============================================================================= 2 HISTORICAL
elif page == PAGES[1]:
    layer_badges("Actual")
    opts = {"Domestic conventional total": "DOMESTIC_CONVENTIONAL_TOTAL", "Thermal": "THERMAL", "Nuclear": "NUCLEAR", "Large hydro": "HYDRO",
            "Coal": "COAL", "Lignite": "LIGNITE", "Natural gas": "NATURAL_GAS", "Diesel": "DIESEL", "Bhutan import (separate)": "BHUTAN_IMPORT"}
    c1, c2 = st.columns([2, 3])
    sel = c1.multiselect("Series", list(opts), default=["Domestic conventional total"], key="h_series")
    dmin, dmax = mn.date.min().to_pydatetime(), mn.date.max().to_pydatetime()
    rng = c2.slider("Period", min_value=dmin, max_value=dmax, value=(dmin, dmax), format="MMM YYYY", key="h_range")
    fig = go.Figure()
    for i, s in enumerate(sel):
        x = hist_series(opts[s])
        x = x[(x.date >= rng[0]) & (x.date <= rng[1])]
        fig.add_trace(go.Scatter(x=x.date, y=x.value_gwh, name=s, line=dict(color=SRC_COL.get(opts[s], SLOT[i % 8]), width=2),
                                 hovertemplate="%{x|%b %Y}: %{y:,.0f} GWh"))
    st.plotly_chart(fig_base(fig, "Monthly actual generation", "GWh / month"), width="stretch")
    t1, t2, t3, t4 = st.tabs(["Financial years", "Year-on-year growth", "Seasonality", "Source trends"])
    with t1:
        cats = D["fn"][D["fn"].series.isin(["THERMAL", "HYDRO", "NUCLEAR"]) & D["fn"].fy.isin(FULL_FYS)]
        fig = go.Figure()
        for cname in ["THERMAL", "HYDRO", "NUCLEAR"]:
            x = cats[cats.series == cname]
            fig.add_trace(go.Bar(x=x.fy, y=x.fy_total_gwh / 1000, name=SRC_LABEL[cname], marker_color=SRC_COL[cname], hovertemplate="%{x}: %{y:,.1f} TWh"))
        fig.update_layout(barmode="stack")
        st.plotly_chart(fig_base(fig, "Domestic conventional generation by FY (FY2019-20 from published March cumulative)", "TWh"), width="stretch")
        tab = cats.pivot(index="fy", columns="series", values="fy_total_gwh").assign(DOMESTIC_TOTAL=dom_fy).reset_index()
        tab["BHUTAN_IMPORT_separate"] = tab.fy.map(D["fn"][D["fn"].series == "BHUTAN_IMPORT"].set_index("fy").fy_total_gwh)
        st.dataframe(tab.round(1), hide_index=True, width="stretch")
        download(tab, "fy_national_actual.csv")
    with t2:
        fyy = dom_fy.pct_change() * 100
        x = hist_series("DOMESTIC_CONVENTIONAL_TOTAL").set_index("date").value_gwh
        yoy = (x / x.shift(12) - 1) * 100
        c1, c2 = st.columns(2)
        f1 = go.Figure(go.Bar(x=fyy.index[1:], y=fyy.values[1:], marker_color=[SLOT[0] if v >= 0 else SLOT[1] for v in fyy.values[1:]], hovertemplate="%{x}: %{y:.1f}%"))
        c1.plotly_chart(fig_base(f1, "FY growth, domestic total", "% YoY", 360, False), width="stretch")
        f2 = go.Figure(go.Bar(x=yoy.index, y=yoy.values, marker_color=[SLOT[0] if v >= 0 else SLOT[1] for v in yoy.fillna(0)], hovertemplate="%{x|%b %Y}: %{y:.1f}%"))
        c2.plotly_chart(fig_base(f2, "Monthly YoY (COVID base effects in 2020-21)", "% YoY", 360, False), width="stretch")
    with t3:
        s = st.selectbox("Series", ["DOMESTIC_CONVENTIONAL_TOTAL", "THERMAL", "HYDRO", "NUCLEAR", "NATURAL_GAS", "BHUTAN_IMPORT"], key="h_seas",
                         format_func=lambda v: SRC_LABEL.get(v, v.replace("_", " ").title()))
        x = hist_series(s).copy()
        x["n"] = x.groupby("fy").value_gwh.transform("size")
        x = x[x.n == 12]
        fig = go.Figure()
        order = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]
        for i, (f_, g) in enumerate(x.groupby("fy")):
            g = g.sort_values("fy_month_no")
            fig.add_trace(go.Scatter(x=order, y=g.value_gwh, name=f_, line=dict(width=1.6, color=SLOT[i % 8]), hovertemplate=f"{f_} %{{x}}: %{{y:,.0f}} GWh"))
        st.plotly_chart(fig_base(fig, "Monthly profile by financial year (complete FYs)", "GWh / month"), width="stretch")
    with t4:
        srcs = ["COAL", "LIGNITE", "NATURAL_GAS", "DIESEL", "NUCLEAR", "HYDRO"]
        x = D["fn"][D["fn"].series.isin(srcs) & D["fn"].fy.isin(FULL_FYS)].pivot(index="fy", columns="series", values="fy_total_gwh")[srcs]
        shr = 100 * x.div(x.sum(axis=1), axis=0)
        fig = go.Figure()
        for s in srcs:
            fig.add_trace(go.Bar(x=shr.index, y=shr[s], name=SRC_LABEL[s], marker_color=SRC_COL[s], hovertemplate="%{x}: %{y:.2f}%"))
        fig.update_layout(barmode="stack")
        st.plotly_chart(fig_base(fig, "Source shares of domestic conventional generation", "% of total"), width="stretch")
        download((x / 1000).round(2).reset_index(), "fy_source_generation_twh.csv")

# ============================================================================= 3 NATIONAL FORECAST
elif page == PAGES[2]:
    layer_badges("Actual", "Statistical forecast", "Scenario projection")
    c1, c2 = st.columns([1, 3])
    show_un = c1.checkbox("Show unreconciled national ETS", value=True, key="nf_un")
    start = c2.select_slider("Show history from", options=[f"{y}-01" for y in range(2020, 2027)], value="2022-01", key="nf_start")
    fig = forecast_chart(hist_series("DOMESTIC_CONVENTIONAL_TOTAL"), fc_node("TOTAL"), "National domestic conventional generation - actual vs forecast",
                         base_df=D["base"][D["base"].node_id == "TOTAL"].sort_values("date") if show_un else None, show_from=pd.Timestamp(start))
    st.plotly_chart(fig, width="stretch")
    t = ff[ff.node_id == "TOTAL"][["fy", "actual_months", "actual_part_gwh", "forecast_part_gwh", "fy_total_gwh", "fy_lo80", "fy_hi80", "fy_lo95", "fy_hi95", "includes_beyond_validated_horizon"]]
    ub = D["national_strategy"][D["national_strategy"].series.str.contains("unreconciled")][["fy", "p50_gwh"]].rename(columns={"p50_gwh": "unreconciled_ETS_fy_gwh"})
    t = t.merge(ub, on="fy", how="left")
    st.dataframe(t.round(0), hide_index=True, width="stretch")
    st.caption("Official values = bottom-up reconciled ETS. Unreconciled national ETS is shown for comparison only (backtest MASE 0.710 unreconciled vs 0.741 reconciled; reconciliation guarantees coherence with regions, states and sources).")
    download(fc_node("TOTAL").drop(columns=["date"]), "national_monthly_forecast.csv")
    st.subheader("2047 scenario comparison")
    sel = st.multiselect("Scenarios", ["low", "central", "high"], default=["low", "central", "high"], key="nf_scen")
    st.plotly_chart(scenario_fan(sel), width="stretch")
    a = D["asm"]
    st.dataframe(pd.DataFrame([{"scenario": k, "start growth g0": f"{100 * v:.2f}%", "g0 source": a["start_growth_source"][k],
                                "terminal growth FY2046-47 (assumed)": f"{100 * a['terminal_growth_gT_FY2046_47'][k]:+.1f}%",
                                "P50 FY2046-47 TWh": round(n47.loc[k, 'p50_gwh'] / 1000), "P10 TWh": round(n47.loc[k, 'p10_gwh'] / 1000),
                                "P90 TWh": round(n47.loc[k, 'p90_gwh'] / 1000)} for k, v in a["start_growth_g0"].items()]), hide_index=True, width="stretch")
    st.caption(f"Growth moves linearly from g0 (FY2028-29) to the terminal rate (FY2046-47); {a['n_sim']:,} Monte-Carlo paths, annual log-growth shock σ = {a['shock_sigma_log_growth']:.3f}.")
    download(D["scn"], "national_scenarios.csv")
    with st.expander("Bhutan import (separate, not domestic)"):
        st.plotly_chart(forecast_chart(hist_series("BHUTAN_IMPORT"), fc_node("IMPORT|BHUTAN"), "Bhutan import - Holt-Winters forecast", color=SLOT[2], height=360), width="stretch")

# ============================================================================= 4 REGIONAL
elif page == PAGES[3]:
    layer_badges("Actual", "Statistical forecast", "Scenario projection")
    regs = st.multiselect("Regions", REGIONS, default=REGIONS, key="r_sel")
    rt = D["fr"][(D["fr"].series == "DOMESTIC_CONVENTIONAL_TOTAL") & D["fr"].fy.isin(FULL_FYS)]
    c1, c2 = st.columns(2)
    fig = go.Figure()
    for r in regs:
        x = rt[rt.region == r]
        fc = ff[(ff.node_id == f"REG|{r}")]
        fig.add_trace(go.Scatter(x=list(x.fy) + list(fc.fy), y=list(x.fy_total_gwh / 1000) + list(fc.fy_total_gwh / 1000), name=r,
                                 line=dict(color=REG_COL[r], width=2), mode="lines+markers", hovertemplate=f"{r} %{{x}}: %{{y:,.1f}} TWh"))
    fig.add_vline(x=6.5, line_dash="dot", line_color=INK2)
    c1.plotly_chart(fig_base(fig, "Regional FY generation (right of line: reconciled forecast)", "TWh", 400), width="stretch")
    sh = rt.pivot(index="fy", columns="region", values="fy_total_gwh")[REGIONS]
    sh = 100 * sh.div(sh.sum(axis=1), axis=0)
    fig = go.Figure()
    for r in REGIONS:
        fig.add_trace(go.Bar(x=sh.index, y=sh[r], name=r, marker_color=REG_COL[r], hovertemplate=f"{r} %{{x}}: %{{y:.1f}}%"))
    fig.update_layout(barmode="stack")
    c2.plotly_chart(fig_base(fig, "Contribution to national conventional generation", "% of national", 400), width="stretch")
    r1 = st.selectbox("Forecast trajectory for region", REGIONS, key="r_one")
    h = mr[(mr.region == r1) & (mr.series == "DOMESTIC_CONVENTIONAL_TOTAL")].sort_values("date")
    st.plotly_chart(forecast_chart(h, fc_node(f"REG|{r1}"), f"{r1} - monthly actual and reconciled forecast", color=REG_COL[r1], show_from=pd.Timestamp("2022-01")), width="stretch")
    c1, c2 = st.columns(2)
    rs = D["regional_strategy"]
    x = rs[(rs.fy == "FY2046-47") & rs.source.isna()]
    fig = go.Figure()
    for s in ["low", "central", "high"]:
        p = x[x.scenario == s].set_index(["region", "quantile"]).gwh
        fig.add_trace(go.Bar(x=REGIONS, y=[p[(r, "p50")] / 1000 for r in REGIONS], name=s.title(), marker_color=SC_COL[s],
                             error_y=dict(type="data", symmetric=False, array=[(p[(r, "p90")] - p[(r, "p50")]) / 1000 for r in REGIONS],
                                          arrayminus=[(p[(r, "p50")] - p[(r, "p10")]) / 1000 for r in REGIONS], thickness=1),
                             hovertemplate="%{x}: %{y:,.0f} TWh (P50)"))
    fig.update_layout(barmode="group")
    c1.plotly_chart(fig_base(fig, "FY2046-47 regional allocation (P50, whiskers P10-P90)", "TWh", 420), width="stretch")
    mix = rs[(rs.fy == "FY2025-26") & rs.source.notna()].pivot_table(index="region", columns="source", values="gwh").reindex(REGIONS)
    mix = 100 * mix.div(mix.sum(axis=1), axis=0)
    fig = go.Figure()
    for s in ["COAL_LIGNITE", "HYDRO", "NUCLEAR", "NATURAL_GAS", "DIESEL"]:
        fig.add_trace(go.Bar(y=mix.index, x=mix[s], name=SRC_LABEL[s], orientation="h", marker_color=SRC_COL[s], hovertemplate="%{y}: %{x:.1f}%"))
    fig.update_layout(barmode="stack", hovermode="y unified")
    c2.plotly_chart(fig_base(fig, "Regional source mix FY2025-26 (actual)", "", 420), width="stretch")
    st.subheader("Regional summary")
    st.dataframe(D["regional_summary"].round(2), hide_index=True, width="stretch")
    download(D["regional_summary"], "regional_summary.csv")
    download(D["regional_strategy"], "regional_strategy.csv", "Download full regional strategy CSV")

# ============================================================================= 5 STATE EXPLORER
elif page == PAGES[4]:
    layer_badges("Actual", "Statistical forecast", "Scenario projection")
    ss = D["state_summary"]
    c1, c2, c3 = st.columns([1, 1, 2])
    rf = c1.selectbox("Region", ["All"] + REGIONS, key="s_reg")
    gf = c2.selectbox("Group", ["All", "A", "B", "C"], key="s_grp")
    cand = ss[((ss.region == rf) | (rf == "All")) & ((ss.group == gf) | (gf == "All"))].sort_values("FY2025-26_gwh", ascending=False)
    if cand.empty:
        st.warning("No state matches the filters.")
        st.stop()
    state = c3.selectbox("State / UT series", cand.state.tolist(), key="s_state", format_func=lambda v: v.title())
    row = ss[ss.state == state].iloc[0]
    grp = row.group
    m = st.columns(5)
    m[0].metric("Group", grp, help={"A": "Direct ETS", "B": "Direct ETS, intervals widened x1.25", "C": "Allocated from regional forecast"}[grp])
    m[1].metric("Region", row.region)
    m[2].metric("FY2025-26 actual", f"{row['FY2025-26_gwh']:,.0f} GWh")
    m[3].metric("FY2026-27 forecast", f"{row['FY2026-27_forecast_gwh']:,.0f} GWh", help=f"95%: {row['FY2026-27_lo95']:,.0f}-{row['FY2026-27_hi95']:,.0f} GWh")
    m[4].metric("Share of region FY25-26", f"{row['share_of_region_FY2025-26_%']:.1f}%")
    st.caption(f"Confidence: **{row.confidence}**. Model: {row.model}." + (" J&K + Ladakh is one harmonised series (Ladakh separate in CEA reports only from 2019-12); 33 series cover 34 states/UTs." if "LADAKH" in state else ""))
    if grp == "C":
        st.warning("Group C: small or volatile series - values are indicative only; the series is allocated from its region's forecast (seasonal proportion).")
    h = ms[(ms.state_harmonised == state) & (ms.series == "STATE_TOTAL")].groupby("date").value_gwh.sum().reset_index().sort_values("date")
    st.plotly_chart(forecast_chart(h, fc_node(f"ST|{state}"), f"{state.title()} - monthly generation and forecast", color=REG_COL.get(row.region, SLOT[0])), width="stretch")
    c1, c2 = st.columns(2)
    cells = ms[(ms.state_harmonised == state) & (ms.series != "STATE_TOTAL")].groupby(["date", "series"]).value_gwh.sum().reset_index()
    fig = go.Figure()
    for s in ["COAL_LIGNITE", "HYDRO", "NUCLEAR", "NATURAL_GAS", "DIESEL"]:
        x = cells[cells.series == s]
        if len(x) and x.value_gwh.sum() > 0:
            fc = mf[mf.node_id == f"CELL|{state}|{s}"].sort_values("date")
            fig.add_trace(go.Scatter(x=list(x.date) + list(fc.date), y=list(x.value_gwh) + list(fc.forecast_gwh), name=SRC_LABEL[s], stackgroup="one",
                                     line=dict(color=SRC_COL[s], width=0.5), hovertemplate="%{x|%b %Y}: %{y:,.0f} GWh"))
    fig.add_vline(x=pd.Timestamp("2026-09-15"), line_dash="dot", line_color=INK2)
    c1.plotly_chart(fig_base(fig, "Source breakdown (actual, then reconciled forecast after dotted line)", "GWh / month", 400), width="stretch")
    sr = D["state_strategy"]
    shr = sr[(sr.state == state) & sr.source.isna() & sr.share_of_region.notna() & (sr.layer != "scenario projection")]
    fig = go.Figure(go.Bar(x=shr.fy, y=100 * shr.share_of_region, marker_color=[SLOT[0] if l == "actual" else SLOT[2] for l in shr.layer],
                           hovertemplate="%{x}: %{y:.2f}% of region"))
    c2.plotly_chart(fig_base(fig, "Share of regional generation (blue actual, green forecast)", "% of region", 400, False), width="stretch")
    st.subheader("FY2046-47 allocations")
    a = sr[(sr.state == state) & (sr.fy == "FY2046-47")].pivot_table(index="scenario", columns="quantile", values="gwh").reindex(["low", "central", "high"])
    disp = a.copy()
    if grp == "B":
        disp = disp.round(-1)
    elif grp == "C":
        disp = disp.map(lambda v: float(f"{v:.2g}"))
    else:
        disp = disp.round(0)
    st.dataframe(disp.rename(columns=lambda c: f"{c.upper()} GWh").reset_index(), hide_index=True, width="stretch")
    st.caption(f"Display rounding: {row.display_rounding}. 2047 state value = regional allocation x state share in region (damped trend for groups A/B, constant for C). Full precision in the CSV.")
    download(sr[sr.state == state], f"state_{state.replace(' ', '_')}.csv")
    download(ss, "state_summary_all.csv", "Download all-state summary CSV")

# ============================================================================= 6 SOURCES
elif page == PAGES[5]:
    layer_badges("Actual", "Statistical forecast", "Scenario projection")
    srcs = ["COAL", "LIGNITE", "NATURAL_GAS", "DIESEL", "NUCLEAR", "HYDRO"]
    sel = st.multiselect("Sources", srcs, default=srcs, format_func=lambda v: SRC_LABEL[v], key="src_sel")
    fyh = D["fn"][D["fn"].series.isin(srcs) & D["fn"].fy.isin(FULL_FYS)][["fy", "series", "fy_total_gwh"]]
    fyf = ff[ff.node_id.isin([f"NSRC|{s}" for s in srcs])].assign(series=lambda x: x.node_id.str[5:])[["fy", "series", "fy_total_gwh", "fy_lo95", "fy_hi95"]]
    allfy = pd.concat([fyh.assign(layer="actual"), fyf.assign(layer="forecast")])
    c1, c2 = st.columns(2)
    fig = go.Figure()
    for s in sel:
        x = allfy[allfy.series == s]
        fig.add_trace(go.Scatter(x=x.fy, y=x.fy_total_gwh / 1000, name=SRC_LABEL[s], mode="lines+markers", line=dict(color=SRC_COL[s], width=2),
                                 hovertemplate=f"{SRC_LABEL[s]} %{{x}}: %{{y:,.1f}} TWh"))
    fig.add_vline(x=6.5, line_dash="dot", line_color=INK2)
    fig.update_yaxes(type="log")
    c1.plotly_chart(fig_base(fig, "FY generation by source (log scale; right of line = forecast)", "TWh (log)", 420), width="stretch")
    tot = allfy.groupby("fy").fy_total_gwh.sum()
    allfy["share_%"] = 100 * allfy.fy_total_gwh / allfy.fy.map(tot)
    fig = go.Figure()
    for s in sel:
        x = allfy[allfy.series == s]
        fig.add_trace(go.Bar(x=x.fy, y=x["share_%"], name=SRC_LABEL[s], marker_color=SRC_COL[s], hovertemplate="%{x}: %{y:.2f}%"))
    fig.update_layout(barmode="stack")
    c2.plotly_chart(fig_base(fig, "Share of domestic conventional generation", "%", 420), width="stretch")
    one = st.selectbox("Monthly detail", srcs, index=2, format_func=lambda v: SRC_LABEL[v], key="src_one")
    st.plotly_chart(forecast_chart(hist_series(one), fc_node(f"NSRC|{one}"), f"{SRC_LABEL[one]} - monthly actual and reconciled forecast",
                                   color=SRC_COL[one], show_from=pd.Timestamp("2021-01")), width="stretch")
    st.caption("Coal and lignite are separated only nationally (state-level CEA data report lignite plants as coal). Source forecasts are reconciled: they sum exactly to the national total.")
    st.dataframe(allfy.pivot_table(index="fy", columns="series", values="fy_total_gwh").round(0).reset_index(), hide_index=True, width="stretch")
    download(allfy, "source_fy_actual_forecast.csv")

# ============================================================================= 7 STRATEGY
elif page == PAGES[6]:
    tabs = st.tabs(["Trend-based reference", "Policy scenarios", "Regional strategy", "State allocations", "Scenario assumptions", "Limitations"])
    mix = D["source_mix_scenarios"]
    with tabs[0]:
        layer_badges("Scenario projection")
        st.markdown("Statistical extrapolation of source **shares** applied to the approved scenario totals. **T3 is the recommended reference**; T1 is kept for transparency but contains a flagged artefact.")
        c1, c2 = st.columns(2)
        scn = c1.selectbox("Scenario", ["central", "low", "high"], key="t_scn")
        q = c2.selectbox("Quantile", ["p50", "p10", "p90"], key="t_q")
        x = mix[(mix.framework == "trend reference") & (mix.scenario == scn) & (mix["quantile"] == q)]
        fig = go.Figure()
        for s in ["COAL", "LIGNITE", "NATURAL_GAS", "DIESEL", "NUCLEAR", "HYDRO"]:
            y = x[x.source == s]
            fig.add_trace(go.Bar(y=y.variant, x=y.gwh / 1000, name=SRC_LABEL[s], orientation="h", marker_color=SRC_COL[s],
                                 customdata=100 * y.share, hovertemplate="%{y}: %{x:,.1f} TWh (%{customdata:.2f}%)"))
        fig.update_layout(barmode="stack", hovermode="y unified")
        st.plotly_chart(fig_base(fig, f"FY2046-47 mix - {scn} {q.upper()}", "", 330), width="stretch")
        dg = D["source_trend_diagnostics"]
        st.dataframe(dg.round(2), hide_index=True, width="stretch")
        st.warning("**Gas artefact:** the damped linear trend (T1) drives the gas share to ~0.1% because it extends a one-off step (4.16% in FY2020-21 → 1.69% in FY2022-23); "
                   "the share has been flat at 1.7–2.1% since, and the reconciled forecast rises in FY2027-28. T3 uses the post-step mean.")
        download(x, f"trend_reference_{scn}_{q}.csv")
    with tabs[1]:
        layer_badges("Policy scenario")
        st.markdown("**Recommendations, not statistical forecasts.** Each rule uses only shares or levels already observed in FY2019-20..FY2025-26; coal/lignite is the balancing item, so every mix sums exactly to the conventional total. **Solar, wind, small hydro and biomass are not quantified.**")
        c1, c2 = st.columns(2)
        scn = c1.selectbox("Scenario", ["central", "low", "high"], key="p_scn")
        q = c2.selectbox("Quantile", ["p50", "p10", "p90"], key="p_q")
        x = mix[(mix.framework == "policy") & (mix.scenario == scn) & (mix["quantile"] == q)]
        fig = go.Figure()
        for s in ["COAL", "LIGNITE", "NATURAL_GAS", "DIESEL", "NUCLEAR", "HYDRO"]:
            y = x[x.source == s]
            fig.add_trace(go.Bar(y=y.variant, x=y.gwh / 1000, name=SRC_LABEL[s], orientation="h", marker_color=SRC_COL[s],
                                 customdata=100 * y.share, hovertemplate="%{y}: %{x:,.1f} TWh (%{customdata:.2f}%)"))
        fig.update_layout(barmode="stack", hovermode="y unified")
        st.plotly_chart(fig_base(fig, f"FY2046-47 policy mixes - {scn} {q.upper()} (total {x.total_conventional_gwh.iloc[0] / 1000:,.0f} TWh)", "", 330), width="stretch")
        st.dataframe(x.drop_duplicates("variant")[["variant", "rule", "justification"]], hide_index=True, width="stretch")
        st.dataframe(x.pivot_table(index="variant", columns="source", values="share").mul(100).round(2).reset_index(), hide_index=True, width="stretch")
        st.success("Recommended: **T3 × central** as planning reference; **P2 (demonstrated maximum shares)** as the preferred direction (lowest coal share already achieved by the existing system); **P3** as a safeguard in the low scenario.")
        download(mix, "source_mix_scenarios.csv")
    with tabs[2]:
        layer_badges("Scenario projection", "Policy scenario")
        rx = D["regional_source_mix_2047"]
        c1, c2, c3 = st.columns(3)
        var = c1.selectbox("Mix variant", sorted(rx.variant.unique()), index=sorted(rx.variant.unique()).index([v for v in rx.variant.unique() if v.startswith("T3")][0]), key="rs_var")
        scn = c2.selectbox("Scenario", ["central", "low", "high"], key="rs_scn")
        q = c3.selectbox("Quantile", ["p50", "p10", "p90"], key="rs_q")
        y = rx[(rx.variant == var) & (rx.scenario == scn) & (rx["quantile"] == q)].pivot(index="region", columns="source", values="gwh").reindex(REGIONS)
        fig = go.Figure()
        for s in ["COAL_LIGNITE", "HYDRO", "NUCLEAR", "NATURAL_GAS", "DIESEL"]:
            fig.add_trace(go.Bar(x=REGIONS, y=y[s] / 1000, name=SRC_LABEL[s], marker_color=SRC_COL[s], hovertemplate="%{x}: %{y:,.1f} TWh"))
        fig.update_layout(barmode="stack")
        st.plotly_chart(fig_base(fig, "FY2046-47 region x source (IPF-balanced: rows = regional totals, columns = national source totals)", "TWh", 420), width="stretch")
        st.dataframe(D["regional_summary"][["region", "share_of_national_FY2025-26_%", "CAGR_FY19-20_to_FY25-26_%", "data_supported_characteristics",
                                             "2047_low_p50_gwh", "2047_central_p50_gwh", "2047_high_p50_gwh"]].round(1), hide_index=True, width="stretch")
        st.caption("Full narrative per region: reports/regional_2047_strategy.md. Generation location is not consumption.")
        download(rx, "regional_source_mix_2047.csv")
    with tabs[3]:
        layer_badges("Scenario projection")
        sr = D["state_strategy"]
        c1, c2 = st.columns(2)
        rf = c1.selectbox("Region", ["All"] + REGIONS, key="sa_reg")
        scn = c2.selectbox("Scenario", ["central", "low", "high"], key="sa_scn")
        x = sr[(sr.fy == "FY2046-47") & (sr.scenario == scn) & ((sr.region == rf) | (rf == "All"))].pivot_table(index=["region", "state", "group"], columns="quantile", values="gwh").reset_index()
        x = x.sort_values(["region", "p50"], ascending=[True, False])
        st.dataframe(x.round(0), hide_index=True, width="stretch")
        st.caption("States sum exactly to their region in every scenario/quantile (validation table, page 9). Group C values are indicative.")
        download(x, f"state_allocations_2047_{scn}.csv")
    with tabs[4]:
        a = D["asm"]
        st.json({k: a[k] for k in ["base_year", "start_growth_g0", "start_growth_source", "terminal_growth_gT_FY2046_47", "terminal_growth_source",
                                   "growth_path", "shock_sigma_log_growth", "shock_sigma_source", "n_sim", "share_damping_phi", "excluded"]})
    with tabs[5]:
        st.markdown("""
- Policy scenarios allocate **conventional** generation only; they are not a full energy plan because renewable generation is unquantified.
- Shares in 2047 rest on 7 observed FYs; P2/P3 use only demonstrated values, never capacity or consumption.
- Region x source and state allocations are balancing allocations (IPF / shares), not forecasts.
- Scenario totals are assumption-driven; see page 9.
""")

# ============================================================================= 8 MODEL PERFORMANCE
elif page == PAGES[7]:
    layer_badges("Statistical forecast")
    met = D["met"]
    levels = ["National", "Regions (5)", "National sources", "States group A", "States group B", "States group C", "State x source (eligible)",
              "State x source (ineligible)", "Bhutan import (separate)"]
    c1, c2 = st.columns([1, 2])
    lvl = c1.selectbox("Forecasting level", levels, key="mp_lvl")
    metric = c2.radio("Metric", ["MASE", "WAPE_%", "MAE", "RMSE", "bias_%"], horizontal=True, key="mp_met")
    x = met[met.level_cat == lvl].sort_values("MASE")
    selm = D["sel"].set_index("level_cat").selected_model.get(lvl)
    base_models = {"naive", "snaive", "lintrend", "lintrend_season"}
    fig = go.Figure(go.Bar(x=x.model, y=x[metric], marker_color=[SLOT[1] if m == selm else (SLOT[6] if m in base_models else SLOT[0]) for m in x.model],
                           hovertemplate="%{x}: %{y:,.3f}"))
    st.plotly_chart(fig_base(fig, f"{lvl}: out-of-sample {metric} (orange = selected, violet = baseline)", metric, 380, False), width="stretch")
    st.dataframe(x.round(3), hide_index=True, width="stretch")
    download(met, "metrics_by_level_model.csv")
    t1, t2, t3, t4 = st.tabs(["Forecast horizons", "COVID sensitivity", "Extended-history sensitivity", "Reconciliation trade-offs"])
    with t1:
        mods = st.multiselect("Models", sorted(D["meth"].model.unique()), default=["ets_auto", "snaive", "lintrend_season", "xgb"], key="mp_mods")
        y = D["meth"][(D["meth"].level_cat == lvl) & D["meth"].model.isin(mods)]
        fig = go.Figure()
        for i, mname in enumerate(mods):
            z = y[y.model == mname].sort_values("h")
            fig.add_trace(go.Scatter(x=z.h, y=z[metric], name=mname, mode="lines+markers", line=dict(color=SLOT[i % 8])))
        fig.update_xaxes(tickvals=[1, 3, 6, 12], title="horizon (months)")
        st.plotly_chart(fig_base(fig, f"{metric} by horizon - {lvl}", metric, 380), width="stretch")
    with t2:
        cv = D["dash_covid_comparison"]
        z = cv[cv.level_cat == lvl].pivot_table(index="model", columns="experiment", values="MASE").round(3).reset_index()
        st.markdown("A = full history + COVID indicator (**main**); B = training from FY2021-22; C = no indicator. Common 13 quarterly origins. Smoothing/naive models cannot use a regressor (A = C).")
        st.dataframe(z, hide_index=True, width="stretch")
        download(cv, "covid_sensitivity.csv")
    with t3:
        ex = D["dash_extended_comparison"].pivot_table(index="model", columns="experiment", values="MASE").round(3).reset_index()
        st.markdown("National TOTAL only. EXT adds the flagged Jul-2018–Jun-2019 months (sensitivity only; not used for main results). **Model selection would change** (linear trend + month dummies 0.644 < ETS 0.701).")
        st.dataframe(ex.sort_values("EXT"), hide_index=True, width="stretch")
    with t4:
        h = D["hier"].pivot_table(index="level_cat", columns="method", values="MASE").round(3)
        fig = go.Figure(go.Heatmap(z=h.values, x=h.columns, y=h.index, colorscale=[[0, "#cde2fb"], [0.5, "#3987e5"], [1, "#0d366b"]],
                                   zmin=0.6, zmax=1.3, text=h.values, texttemplate="%{text:.2f}", hovertemplate="%{y} / %{x}: MASE %{z:.3f}"))
        st.plotly_chart(fig_base(fig, "Reconciliation methods - MASE by level (BU selected; values >1.3 shown at max colour)", "", 440, False), width="stretch")
        st.caption("BASE = unreconciled (incoherent). BU = bottom-up (official). OLS/WLS_struct break down on small nodes.")

# ============================================================================= 9 ASSUMPTIONS
elif page == PAGES[8]:
    st.markdown(f"""
### Data sources
- **National Power Portal / CEA Monthly Reports ACTUAL** - 1,740 XLS files, monthly ACTUAL generation (col #4), Jul-2019 to Sep-2026, 87 continuous months. Cumulative, capacity, PLF, target and consumption fields are never used.
- **Renewable India dataset (GitHub)** - installed capacity (not used: prohibited as a generation proxy) and partly model-imputed population/GSDP (optional experiment only, not adopted).

### Historical coverage
FY2019-20 (from published March cumulative) to FY2025-26 complete; FY2026-27 partly observed (Apr-Sep 2026). Extended Jul-2018–Jun-2019 data used only as a sensitivity test.

### Missing renewable generation
No authorised actual-generation series exists for solar, wind, small hydro or biomass. **They are not quantified anywhere in this dashboard.** Conventional generation is therefore **not** total Indian electricity production; total requirement = conventional + non-conventional + net imports.

### Forecasting assumptions
Experiment A (full history + Mar–May 2020 COVID regressor where supported); ETS selected by out-of-sample MASE; bottom-up reconciliation over 73 state x source cells; empirical intervals (group B widened x1.25; months 13–18 beyond the validated horizon are flagged).

### Long-term uncertainty
2047 values are **scenario projections**: growth moves from observed CAGRs to **assumed** terminal rates; Monte-Carlo bands. 87 months of data are extrapolated 21 years - the range, not the median, is the message.

### State-level limitations
State values describe where conventional plants are located, not demand. 33 series cover 34 states/UTs (J&K + Ladakh combined). Group C (8 small/volatile series) is allocated from regional forecasts and shown with reduced precision.

### Bhutan import treatment
Bhutan hydro import is forecast separately (Holt-Winters) and **never** added to domestic generation.
""")
    st.subheader("Validation checks (strategy outputs)")
    v = D["validation_checks"]
    st.dataframe(v, hide_index=True, width="stretch")
    st.success(f"{(v.result == 'PASS').sum()} of {len(v)} checks pass.") if (v.result == "PASS").all() else st.error("Some checks fail - see table.")
    download(v, "validation_checks.csv")
    with st.expander("Model-ready data verification (Phase 3A)"):
        st.markdown(D["ver"])
    with st.expander("Interval quantiles used (scale units)"):
        st.dataframe(D["iq"].round(3), hide_index=True, width="stretch")

st.divider()
st.caption("INNOTHON · Forecasting India's Energy Production and Strategizing its Fulfillment by 2047 · All figures from saved project outputs (outputs/). "
           "Statistical forecasts ≠ scenario projections ≠ policy recommendations.")
