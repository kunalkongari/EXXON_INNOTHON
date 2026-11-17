"""
eda.py  (Phase 2B)
------------------
Exploratory analysis of the prepared datasets (outputs/data/). Writes figures to
outputs/eda/ and the report to outputs/reports/eda_report.md, plus supporting tables
in outputs/eda/tables/.

All figures show CONVENTIONAL generation only (no solar/wind/small hydro/biomass);
Bhutan import is shown separately and never stacked into domestic generation.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "outputs" / "data"
FIG = ROOT / "outputs" / "eda"
TAB = FIG / "tables"
REP = ROOT / "outputs" / "reports"

# reference palette (light), fixed slot order; text never wears series colour
SLOT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1"
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
CAT_COL = {"THERMAL": SLOT[0], "HYDRO": SLOT[1], "NUCLEAR": SLOT[2]}
SRC_ORDER = ["COAL", "LIGNITE", "NATURAL_GAS", "DIESEL", "NUCLEAR", "HYDRO"]
SRC_COL = {"COAL": SLOT[0], "HYDRO": SLOT[1], "NUCLEAR": SLOT[2], "NATURAL_GAS": SLOT[3], "LIGNITE": SLOT[4], "DIESEL": SLOT[6]}
REGIONS = ["Northern", "Western", "Southern", "Eastern", "North Eastern"]
REG_COL = dict(zip(REGIONS, SLOT))
FULL_FYS = [f"FY{y}-{str(y + 1)[2:]}" for y in range(2019, 2026)]  # FY2019-20 (from #9) .. FY2025-26

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "legend.frameon": False, "lines.linewidth": 2, "font.family": "DejaVu Sans",
})
SUB = "Conventional generation only (excludes solar, wind, small hydro, biomass). Source: NPP/CEA monthly ACTUAL reports."
FIGS: list[tuple[str, str]] = []


def save(fig, name, caption, note=None):
    fig.text(0.01, -0.01, SUB, fontsize=7.5, color=MUTED, ha="left", va="top")
    if note:
        fig.text(0.01, -0.045, note, fontsize=7.5, color=MUTED, ha="left", va="top")
    fig.savefig(FIG / name, dpi=150, bbox_inches="tight")
    plt.close(fig)
    FIGS.append((name, caption))


def twh(ax):
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"{v / 1000:,.0f}"))


def md(df, floatfmt="{:,.1f}"):
    cols = [str(c) for c in df.columns]
    s = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    for _, r in df.iterrows():
        s += "| " + " | ".join(floatfmt.format(v) if isinstance(v, (float, np.floating)) and not pd.isna(v) else ("" if pd.isna(v) else str(v)) for v in r.values) + " |\n"
    return s


def cagr(a, b, n):
    return (b / a) ** (1 / n) - 1 if a and a > 0 and b > 0 else np.nan


def main():
    for d in (FIG, TAB, REP):
        d.mkdir(parents=True, exist_ok=True)
    mn = pd.read_csv(DATA / "monthly_national.csv")
    ext = pd.read_csv(DATA / "monthly_national_extended.csv")
    mr = pd.read_csv(DATA / "monthly_regional.csv")
    ms = pd.read_csv(DATA / "monthly_state.csv")
    fn = pd.read_csv(DATA / "fy_national.csv")
    fr = pd.read_csv(DATA / "fy_regional.csv")
    fs = pd.read_csv(DATA / "fy_state.csv")
    for d in (mn, ext, mr, ms):
        d["date"] = pd.PeriodIndex(d.period, freq="M").to_timestamp()
    R = {}  # report fragments

    # ------------------------------------------------------------ 1 national monthly
    dom = mn[mn.series == "DOMESTIC_CONVENTIONAL_TOTAL"].set_index("date").value_gwh.sort_index()
    dom_ext = ext[ext.series == "DOMESTIC_CONVENTIONAL_TOTAL"].set_index("date").sort_index()
    bhu = mn[mn.series == "BHUTAN_IMPORT"].set_index("date").value_gwh.sort_index()
    fig, ax = plt.subplots(figsize=(11, 4.2))
    e = dom_ext[dom_ext.flag != "PRIMARY"].value_gwh
    if len(e):
        ax.plot(pd.concat([e, dom.iloc[:1]]), color=SLOT[0], lw=2, ls=(0, (3, 2)), alpha=0.7, label="Extended (from published prior-year column, flagged)")
    ax.plot(dom, color=SLOT[0], lw=2, label="Primary monthly actual (#4)")
    ax.plot(dom.rolling(12).mean(), color=INK2, lw=1.5, label="12-month rolling mean")
    ax.set_title("National domestic conventional generation, monthly (TWh)")
    twh(ax)
    ax.legend(loc="lower right", fontsize=8.5)
    for x, t in [("2020-04-01", "COVID lockdown"), ("2023-04-01", "FY23-24 weak monsoon (hydro)")]:
        ax.axvline(pd.Timestamp(x), color=MUTED, lw=1, ls=":")
        ax.text(pd.Timestamp(x), ax.get_ylim()[1] * 0.985, " " + t, fontsize=8, color=INK2, va="top")
    save(fig, "01_national_monthly.png", "Monthly domestic conventional generation with 12-month rolling mean; dashed = flagged extension 2018-07..2019-06.")

    fig, ax = plt.subplots(figsize=(11, 2.8))
    ax.bar(bhu.index, bhu.values, width=20, color=SLOT[2])
    ax.set_title("Bhutan import, monthly (GWh) - kept separate from domestic generation")
    save(fig, "02_bhutan_import_monthly.png", "Bhutan hydro import: strongly monsoonal, separate series.")

    # ------------------------------------------------------------ 2 FY totals and growth
    cats = ["THERMAL", "NUCLEAR", "HYDRO"]
    fyc = fn[fn.series.isin(cats + ["DOMESTIC_CONVENTIONAL_TOTAL", "BHUTAN_IMPORT"])].pivot(index="fy", columns="series", values="fy_total_gwh")
    fyc = fyc.loc[[f for f in ["FY2018-19"] + FULL_FYS if f in fyc.index]]
    fig, ax = plt.subplots(figsize=(10, 4.5))
    bottom = np.zeros(len(fyc))
    x = np.arange(len(fyc))
    for c in ["THERMAL", "HYDRO", "NUCLEAR"]:
        hatch = ["//" if f == "FY2018-19" else "" for f in fyc.index]
        bars = ax.bar(x, fyc[c], bottom=bottom, color=CAT_COL[c], width=0.62, edgecolor=SURFACE, linewidth=2, label=c.title())
        for b, h in zip(bars, hatch):
            b.set_hatch(h)
        bottom += fyc[c].values
    for i, v in enumerate(bottom):
        ax.text(i, v * 1.01, f"{v / 1000:,.0f}", ha="center", fontsize=8.5, color=INK)
    ax.set_xticks(x, fyc.index, fontsize=8.5)
    twh(ax)
    ax.set_title("Domestic conventional generation by financial year (TWh)")
    ax.legend(ncol=3, loc="upper left", fontsize=8.5)
    save(fig, "03_fy_national_by_category.png", "FY totals by category.",
         note="FY2018-19 (hatched) from published 'same period last year' column - flagged. FY2019-20 from published March cumulative. FY2026-27 partial, not shown.")

    g = fyc.pct_change() * 100
    gt = pd.DataFrame({"FY": fyc.index, "Domestic total (GWh)": fyc.DOMESTIC_CONVENTIONAL_TOTAL.values,
                       "YoY total %": g.DOMESTIC_CONVENTIONAL_TOTAL.values, "Thermal YoY %": g.THERMAL.values,
                       "Hydro YoY %": g.HYDRO.values, "Nuclear YoY %": g.NUCLEAR.values, "Bhutan import (GWh)": fyc.BHUTAN_IMPORT.values})
    gt.to_csv(TAB / "fy_national_growth.csv", index=False)
    R["fy"] = gt
    fig, axs = plt.subplots(1, 4, figsize=(13, 3.6), sharey=False)
    for ax, col, colr in zip(axs, ["YoY total %", "Thermal YoY %", "Hydro YoY %", "Nuclear YoY %"], [SLOT[0], SLOT[0], SLOT[1], SLOT[2]]):
        d = gt.dropna(subset=[col])
        ax.bar(d.FY.str.replace("FY", ""), d[col], color=colr, width=0.6)
        ax.axhline(0, color=INK2, lw=0.8)
        ax.set_title(col.replace(" YoY %", "").replace("YoY total %", "Domestic total"), fontsize=10)
        ax.tick_params(axis="x", rotation=60, labelsize=7.5)
        ax.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
    fig.suptitle("Financial-year growth, % YoY", x=0.01, ha="left", fontweight="bold")
    save(fig, "04_fy_yoy_growth.png", "FY YoY growth: total and by category (independent y-scales per panel).")
    n_y = 6
    c1 = cagr(fyc.DOMESTIC_CONVENTIONAL_TOTAL["FY2019-20"], fyc.DOMESTIC_CONVENTIONAL_TOTAL["FY2025-26"], n_y)
    c2 = cagr(fyc.DOMESTIC_CONVENTIONAL_TOTAL["FY2020-21"], fyc.DOMESTIC_CONVENTIONAL_TOTAL["FY2024-25"], 4)
    R["cagr"] = {"FY19-20->FY25-26": c1, "FY20-21->FY24-25": c2,
                 **{f"{c} FY19-20->FY25-26": cagr(fyc[c]["FY2019-20"], fyc[c]["FY2025-26"], n_y) for c in cats}}

    # monthly YoY
    yoy_m = (dom / dom.shift(12) - 1) * 100
    fig, ax = plt.subplots(figsize=(11, 3.4))
    ax.bar(yoy_m.index, yoy_m.values, width=20, color=[SLOT[0] if v >= 0 else SLOT[1] for v in yoy_m.fillna(0)])
    ax.axhline(0, color=INK2, lw=0.8)
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
    ax.set_title("Monthly YoY change, domestic conventional generation")
    save(fig, "05_monthly_yoy.png", "Monthly YoY; COVID base effects in 2020-21 dominate.")

    # ------------------------------------------------------------ 3 seasonality
    m = mn[mn.series.isin(cats + ["DOMESTIC_CONVENTIONAL_TOTAL"])].copy()
    m["fy_mean"] = m.groupby(["series", "fy"]).value_gwh.transform("mean")
    m["n_in_fy"] = m.groupby(["series", "fy"]).value_gwh.transform("size")
    full = m[m.n_in_fy == 12].copy()
    full["index"] = full.value_gwh / full.fy_mean
    si = full.groupby(["series", "month"])["index"].agg(["mean", "min", "max"]).reset_index()
    si.to_csv(TAB / "seasonal_indices.csv", index=False)
    mon_lbl = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]
    order = [4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3]
    fig, axs = plt.subplots(1, 4, figsize=(14, 3.6), sharey=True)
    for ax, s in zip(axs, ["DOMESTIC_CONVENTIONAL_TOTAL", "THERMAL", "HYDRO", "NUCLEAR"]):
        d = si[si.series == s].set_index("month").loc[order]
        colr = CAT_COL.get(s, SLOT[0])
        ax.fill_between(range(12), d["min"], d["max"], color=colr, alpha=0.18, lw=0)
        ax.plot(range(12), d["mean"], color=colr, marker="o", ms=4)
        ax.axhline(1, color=INK2, lw=0.8)
        ax.set_xticks(range(12), mon_lbl, fontsize=7.5, rotation=60)
        ax.set_title("Domestic total" if s.startswith("DOM") else s.title(), fontsize=10)
    axs[0].set_ylabel("month / FY monthly mean")
    fig.suptitle("Seasonal index by month of financial year (line = mean, band = min-max over complete FYs)", x=0.01, ha="left", fontweight="bold")
    save(fig, "06_seasonality.png", "Seasonal indices: hydro peaks Jul-Sep (monsoon), thermal peaks pre-monsoon/Mar-May and dips in monsoon.")
    R["season"] = si

    # STL decomposition (monthly, period 12)
    stl = STL(dom.asfreq("MS"), period=12, robust=True).fit()
    resid_z = (stl.resid - stl.resid.mean()) / stl.resid.std()
    outl = resid_z[resid_z.abs() > 2.5]
    fig, axs = plt.subplots(3, 1, figsize=(11, 6.5), sharex=True)
    axs[0].plot(stl.trend, color=SLOT[0]); axs[0].set_title("STL trend (TWh)", fontsize=10); twh(axs[0])
    axs[1].plot(stl.seasonal, color=SLOT[0]); axs[1].set_title("STL seasonal component (TWh)", fontsize=10); twh(axs[1])
    axs[2].bar(stl.resid.index, stl.resid.values, width=20, color=[SLOT[7] if abs(z) > 2.5 else MUTED for z in resid_z])
    axs[2].set_title("Remainder (red = |z| > 2.5, candidate outliers)", fontsize=10); twh(axs[2])
    fig.suptitle("Robust STL decomposition, national domestic conventional generation", x=0.01, ha="left", fontweight="bold")
    save(fig, "07_stl_decomposition.png", "STL trend/seasonal/remainder and outlier months.")
    R["outliers"] = pd.DataFrame({"month": outl.index.strftime("%Y-%m"), "remainder_z": outl.values,
                                  "remainder_gwh": stl.resid[outl.index].values})
    R["trend"] = stl.trend

    # ------------------------------------------------------------ 4 source shares
    src = fn[fn.series.isin(SRC_ORDER) & fn.fy.isin(FULL_FYS)].pivot(index="fy", columns="series", values="fy_total_gwh")[SRC_ORDER]
    share = src.div(src.sum(axis=1), axis=0) * 100
    share.round(2).to_csv(TAB / "fy_source_shares.csv")
    R["share"] = share.reset_index()
    R["src_abs"] = src.reset_index()
    fig, ax = plt.subplots(figsize=(10, 4.6))
    left = np.zeros(len(share))
    y = np.arange(len(share))
    for s in SRC_ORDER:
        ax.barh(y, share[s], left=left, color=SRC_COL[s], height=0.62, edgecolor=SURFACE, linewidth=2, label=s.replace("_", " ").title())
        for i, (l, v) in enumerate(zip(left, share[s])):
            if v > 4:
                ax.text(l + v / 2, i, f"{v:.1f}%", ha="center", va="center", fontsize=8, color="white" if s in ("COAL", "NUCLEAR") else INK)
        left += share[s].values
    ax.set_yticks(y, share.index)
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(mtick.PercentFormatter())
    ax.set_xlim(0, 100)
    ax.legend(ncol=6, loc="lower left", bbox_to_anchor=(0, 1.0), fontsize=8.5)
    ax.set_title("Source shares of domestic conventional generation, by FY", pad=26)
    save(fig, "08_source_shares.png", "Source shares within conventional generation.")

    fig, axs = plt.subplots(2, 3, figsize=(13, 6))
    for ax, s in zip(axs.ravel(), SRC_ORDER):
        d = mn[mn.series == s].set_index("date").value_gwh.sort_index()
        ax.plot(d, color=SRC_COL[s], lw=1.6)
        ax.plot(d.rolling(12).mean(), color=INK2, lw=1.2)
        ax.set_title(s.replace("_", " ").title() + " (GWh/month)", fontsize=10)
        ax.tick_params(labelsize=7.5)
    fig.suptitle("Monthly generation by source (independent scales; grey = 12-month mean)", x=0.01, ha="left", fontweight="bold")
    save(fig, "09_source_monthly.png", "Monthly series by source.")

    # ------------------------------------------------------------ 5 regional
    rt = fr[(fr.series == "DOMESTIC_CONVENTIONAL_TOTAL") & fr.fy.isin(FULL_FYS)].pivot(index="fy", columns="region", values="fy_total_gwh")[REGIONS]
    rt.to_csv(TAB / "fy_regional_totals.csv")
    reg_cagr = {r: cagr(rt[r].iloc[0], rt[r].iloc[-1], len(rt) - 1) * 100 for r in REGIONS}
    R["reg"] = rt.reset_index()
    R["reg_cagr"] = reg_cagr
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for r in REGIONS:
        ax.plot(rt.index, rt[r], color=REG_COL[r], marker="o", ms=5)
        ax.text(len(rt) - 1 + 0.08, rt[r].iloc[-1], f"{r} ({reg_cagr[r]:+.1f}%/yr)", va="center", fontsize=8.5, color=INK)
    ax.set_xlim(-0.3, len(rt) + 1.6)
    twh(ax)
    ax.set_title("Domestic conventional generation by region, FY (TWh)  - label: CAGR FY19-20->FY25-26")
    ax.tick_params(axis="x", labelsize=8.5)
    save(fig, "10_regional_fy.png", "Regional FY totals and CAGR.")

    rm = fr[fr.series.isin(cats) & (fr.fy == "FY2025-26")].pivot(index="region", columns="series", values="fy_total_gwh").loc[REGIONS]
    rshare = rm.div(rm.sum(axis=1), axis=0) * 100
    R["reg_mix"] = rshare.reset_index()
    fig, ax = plt.subplots(figsize=(10, 3.6))
    left = np.zeros(len(rshare))
    for c in ["THERMAL", "HYDRO", "NUCLEAR"]:
        ax.barh(range(len(rshare)), rshare[c], left=left, color=CAT_COL[c], height=0.6, edgecolor=SURFACE, linewidth=2, label=c.title())
        for i, (l, v) in enumerate(zip(left, rshare[c])):
            if v > 5:
                ax.text(l + v / 2, i, f"{v:.0f}%", ha="center", va="center", fontsize=8, color="white" if c == "THERMAL" else INK)
        left += rshare[c].values
    ax.set_yticks(range(len(rshare)), rshare.index)
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(mtick.PercentFormatter())
    ax.set_xlim(0, 100)
    ax.legend(ncol=3, loc="lower left", bbox_to_anchor=(0, 1.0), fontsize=8.5)
    ax.set_title("Regional generation mix, FY2025-26 (share of regional conventional generation)", pad=26)
    save(fig, "11_regional_mix.png", "Regional category mix FY2025-26.")

    fig, axs = plt.subplots(1, 5, figsize=(15, 3.2), sharey=False)
    for ax, r in zip(axs, REGIONS):
        d = mr[(mr.region == r) & (mr.series == "DOMESTIC_CONVENTIONAL_TOTAL")].set_index("date").value_gwh.sort_index()
        ax.plot(d, color=REG_COL[r], lw=1.4)
        ax.plot(d.rolling(12).mean(), color=INK2, lw=1.1)
        ax.set_title(r, fontsize=10)
        ax.tick_params(labelsize=7, axis="both")
        ax.tick_params(axis="x", rotation=45)
    fig.suptitle("Regional monthly generation (GWh; independent scales; grey = 12-month mean)", x=0.01, ha="left", fontweight="bold")
    save(fig, "12_regional_monthly.png", "Regional monthly series.")

    # ------------------------------------------------------------ 6 states
    st = ms[ms.series == "STATE_TOTAL"]
    sfy = fs[(fs.series == "STATE_TOTAL")].pivot_table(index="state_harmonised", columns="fy", values="fy_total_gwh", aggfunc="sum")
    region_of = fs.groupby("state_harmonised").region.first()
    stats = []
    for s, d in st.assign(state_harmonised=st.state_harmonised).groupby("state_harmonised"):
        v = d.groupby("period").value_gwh.sum().sort_index()
        yo = (v / v.shift(12) - 1).replace([np.inf, -np.inf], np.nan)
        a, b = sfy.loc[s].get("FY2019-20", np.nan), sfy.loc[s].get("FY2025-26", np.nan)
        stats.append({"state": s, "region": region_of.get(s, ""), "months": v.size, "first": v.index.min(),
                      "FY2025-26 GWh": b, "share_of_national_%": np.nan,
                      "CAGR FY19-20->25-26 %": cagr(a, b, 6) * 100 if pd.notna(a) else np.nan,
                      "monthly CV %": 100 * v.std() / v.mean() if v.mean() else np.nan,
                      "median |YoY| %": 100 * yo.abs().median(),
                      "zero months": int((v == 0).sum())})
    sd = pd.DataFrame(stats)
    tot26 = sd["FY2025-26 GWh"].sum()
    sd["share_of_national_%"] = 100 * sd["FY2025-26 GWh"] / tot26
    # modelling tier proposal (to be confirmed in Phase 2D)
    def tier(r):
        if r["months"] < 60 or r["FY2025-26 GWh"] < 1000 or r["zero months"] > 6:
            return "C - aggregate/share only"
        if r["share_of_national_%"] >= 2 and r["median |YoY| %"] < 15:
            return "A - direct model"
        return "B - direct model, wide bands"
    sd["proposed_tier"] = sd.apply(tier, axis=1)
    sd = sd.sort_values("FY2025-26 GWh", ascending=False)
    sd.to_csv(TAB / "state_statistics.csv", index=False)
    R["states"] = sd

    top = sd.head(15).iloc[::-1]
    fig, ax = plt.subplots(figsize=(10, 6))
    a19 = sfy.loc[top.state, "FY2019-20"]
    b26 = sfy.loc[top.state, "FY2025-26"]
    for i, s in enumerate(top.state):
        ax.plot([a19[s], b26[s]], [i, i], color=GRID, lw=3, zorder=1)
    ax.scatter(a19, range(len(top)), color=SLOT[6], s=50, zorder=2, label="FY2019-20", edgecolor=SURFACE, linewidth=1.5)
    ax.scatter(b26, range(len(top)), color=SLOT[0], s=60, zorder=3, label="FY2025-26", edgecolor=SURFACE, linewidth=1.5)
    ax.set_yticks(range(len(top)), [s.title() for s in top.state], fontsize=8.5)
    twh(ax)
    ax.set_xlabel("TWh")
    ax.legend(loc="lower right")
    ax.set_title("Top 15 states by conventional generation: FY2019-20 vs FY2025-26 (TWh)")
    save(fig, "13_state_top15.png", "Largest generating states, change over six years.")

    fig, ax = plt.subplots(figsize=(10, 5.5))
    tiers = {"A - direct model": SLOT[0], "B - direct model, wide bands": SLOT[3], "C - aggregate/share only": SLOT[7]}
    for t, colr in tiers.items():
        d = sd[sd.proposed_tier == t]
        ax.scatter(d["FY2025-26 GWh"].clip(lower=1), d["median |YoY| %"], s=55, color=colr, label=t, edgecolor=SURFACE, linewidth=1.5)
    big = sd.nlargest(4, "FY2025-26 GWh").state.tolist()
    for _, r in sd.iterrows():
        if r["median |YoY| %"] > 30:
            ax.annotate(r.state.title(), (max(r["FY2025-26 GWh"], 1), r["median |YoY| %"]), fontsize=7.5, color=INK2, xytext=(4, 3), textcoords="offset points")
    ax.annotate("4 largest: " + ", ".join(b.title() for b in big), xy=(0.99, 0.03), xycoords="axes fraction", ha="right", fontsize=7.5, color=INK2)
    ax.set_xscale("log")
    ax.set_xlabel("FY2025-26 generation (GWh, log scale)")
    ax.set_ylabel("median |monthly YoY change| (%)")
    ax.legend(fontsize=8.5)
    ax.set_title("State-level variability vs size (proposed modelling tiers)")
    save(fig, "14_state_variability.png", "Small states are far more volatile -> tiered modelling.")

    # state x source heatmap FY2025-26
    ss = fs[(fs.fy == "FY2025-26") & (fs.series != "STATE_TOTAL")].pivot_table(index="state_harmonised", columns="series", values="fy_total_gwh", aggfunc="sum").fillna(0)
    ss = ss.loc[sd.state, [c for c in ["COAL_LIGNITE", "NATURAL_GAS", "DIESEL", "NUCLEAR", "HYDRO"] if c in ss.columns]]
    ss.to_csv(TAB / "state_source_fy2025_26.csv")
    fig, ax = plt.subplots(figsize=(8, 10))
    vals = np.log10(ss.values + 1)
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("seq", ["#f4f3f0"] + SEQ)
    ax.imshow(vals, aspect="auto", cmap=cmap)
    ax.set_xticks(range(ss.shape[1]), [c.replace("_", " ").title() for c in ss.columns], fontsize=8.5)
    ax.set_yticks(range(ss.shape[0]), [s.title() for s in ss.index], fontsize=7.5)
    ax.grid(False)
    for i in range(ss.shape[0]):
        for j in range(ss.shape[1]):
            v = ss.values[i, j]
            if v > 0:
                ax.text(j, i, f"{v:,.0f}", ha="center", va="center", fontsize=6.5, color="white" if vals[i, j] > 3.8 else INK)
    ax.set_title("State x source generation, FY2025-26 (GWh; colour = log scale)")
    save(fig, "15_state_source_heatmap.png", "Which sources exist in which states (zero = blank).")

    # coverage of state x source cells
    sxs = ms[ms.series != "STATE_TOTAL"].groupby(["state_harmonised", "series"]).agg(months=("period", "nunique"), nonzero=("value_gwh", lambda x: int((x > 0).sum())), fy26=("value_gwh", "sum")).reset_index()
    sxs["eligible_direct_model"] = (sxs.months >= 84) & (sxs.nonzero >= 72)
    sxs.to_csv(TAB / "state_source_coverage.csv", index=False)
    R["sxs"] = sxs

    h = dom.copy(); h.index = h.index.to_period("M").astype(str)
    R["h1"] = (h[[f"2025-{m:02d}" for m in range(4, 10)]].sum(), h[[f"2026-{m:02d}" for m in range(4, 10)]].sum())
    write_report(R, mn, dom, bhu)


def write_report(R, mn, dom, bhu):
    fy, share, states, sxs = R["fy"], R["share"], R["states"], R["sxs"]
    si = R["season"]
    peak = si[si.series == "DOMESTIC_CONVENTIONAL_TOTAL"].sort_values("mean")
    hy = si[si.series == "HYDRO"].sort_values("mean")
    mon = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun", 7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}
    tiers = states.proposed_tier.value_counts()
    elig = sxs[sxs.eligible_direct_model]
    figs = "\n".join(f"![{c}](../eda/{n})\n*{n}: {c}*\n" for n, c in FIGS)
    st_cols = ["state", "region", "months", "FY2025-26 GWh", "share_of_national_%", "CAGR FY19-20->25-26 %", "monthly CV %", "median |YoY| %", "zero months", "proposed_tier"]
    txt = f"""# Exploratory Data Analysis (Phase 2B)

_Generated by `src/eda.py` on {dt.date.today()}. Data: `outputs/data/` (Phase 2A). Figures: `outputs/eda/`; tables: `outputs/eda/tables/`._

> **Scope.** Every number below is **conventional generation monitored by CEA** (coal, lignite, gas, diesel, nuclear, large hydro).
> It excludes solar, wind, small hydro and biomass, so it is **not total Indian electricity production**. Bhutan import is reported separately.

## 1. Key findings
1. **Level and growth.** Domestic conventional generation was {fy.iloc[-1]['Domestic total (GWh)']/1000:,.0f} TWh in FY2025-26. CAGR FY2019-20->FY2025-26 = **{R['cagr']['FY19-20->FY25-26']*100:.2f}%/yr**; FY2020-21->FY2024-25 = {R['cagr']['FY20-21->FY24-25']*100:.2f}%/yr.
2. **Trend break in FY2025-26.** After four years of strong growth (FY21-22 to FY24-25), conventional generation **fell {abs(fy.iloc[-1]['YoY total %']):.1f}%** in FY2025-26, driven by thermal ({fy.iloc[-1]['Thermal YoY %']:+.1f}%) while hydro recovered ({fy.iloc[-1]['Hydro YoY %']:+.1f}%). With no RE generation data, we cannot attribute this, but it is consistent with displacement by non-conventional sources; it is the single most important uncertainty for trend extrapolation.
3. **Thermal dominance.** Coal is ~{share.iloc[-1]['COAL']:.0f}% of conventional generation; hydro {share.iloc[-1]['HYDRO']:.0f}%; nuclear {share.iloc[-1]['NUCLEAR']:.1f}%; gas {share.iloc[-1]['NATURAL_GAS']:.1f}%; lignite {share.iloc[-1]['LIGNITE']:.1f}%; diesel ~0%.
4. **Seasonality is strong and stable.** Domestic total peaks in {mon[int(peak.iloc[-1].month)]} (index {peak.iloc[-1]['mean']:.2f}) and troughs in {mon[int(peak.iloc[0].month)]} ({peak.iloc[0]['mean']:.2f}). Hydro is monsoonal: peak {mon[int(hy.iloc[-1].month)]} ({hy.iloc[-1]['mean']:.2f}), trough {mon[int(hy.iloc[0].month)]} ({hy.iloc[0]['mean']:.2f}). Thermal partially offsets hydro.
5. **Structural events.** COVID lockdown (Mar-May 2020; creates +42% YoY base effect in Apr-2021), weak-monsoon FY2023-24 (hydro {fy[fy.FY=='FY2023-24']['Hydro YoY %'].iloc[0]:+.1f}%), FY2025-26 thermal decline. STL outlier months (|z|>2.5): {', '.join(R['outliers'].month) or 'none'} (2025-10 = unusually low month within the FY2025-26 dip).
6. **Regions.** Western and Northern are the largest; CAGR FY19-20->FY25-26: {', '.join(f'{k} {v:+.1f}%' for k, v in R['reg_cagr'].items())}. North Eastern is hydro-dominated; other regions are thermal-dominated.
7. **States.** {len(states)} state series (J&K + Ladakh harmonised). Generation is concentrated: top 5 states = {states.head(5)['share_of_national_%'].sum():.0f}% of FY2025-26. Small/NE states and UTs are highly volatile (median |YoY| up to {states['median |YoY| %'].max():.0f}%). Proposed tiers: {', '.join(f'{k}: {v}' for k, v in tiers.items())}.
8. **State x source.** {len(elig)} of {len(sxs)} state x source cells have >=84 months and >=72 non-zero months (eligible for direct models); the rest are sparse, intermittent or new.
9. **Latest half-year.** Apr-Sep 2026 = {R['h1'][1]/1000:,.1f} TWh vs Apr-Sep 2025 = {R['h1'][0]/1000:,.1f} TWh ({100*(R['h1'][1]/R['h1'][0]-1):+.1f}%), so the FY2025-26 dip is not (yet) a sustained decline - another reason to model with scenario bands.
10. **Bhutan import** is small ({bhu.groupby(bhu.index.year).sum().mean()/1000:.1f} TWh/yr average), monsoonal and volatile; kept separate.

## 2. National financial-year generation and growth
{md(fy)}
CAGR by category FY19-20->FY25-26: {', '.join(f"{k.split()[0].title()} {v*100:+.2f}%" for k, v in R['cagr'].items() if ' FY' in k)}.

## 3. Source shares (% of domestic conventional generation)
{md(share, '{:.2f}')}

## 4. Seasonal indices (month / FY monthly mean, complete FYs)
{md(si.pivot(index='month', columns='series', values='mean').reset_index(), '{:.3f}')}

## 5. Regions
FY totals (GWh):
{md(R['reg'], '{:,.0f}')}
Regional mix FY2025-26 (%):
{md(R['reg_mix'], '{:.1f}')}

## 6. States (sorted by FY2025-26 generation)
{md(states[st_cols], '{:,.1f}')}
Tier rule (proposal, to be confirmed before Phase 2D): **C** if <60 months, <1,000 GWh in FY2025-26 or >6 zero months; **A** if >=2% national share and median |YoY| <15%; otherwise **B**.

## 7. Structural changes, outliers, data caveats for modelling
- STL remainder outliers: {md(R['outliers'], '{:.2f}') if len(R['outliers']) else 'none'}
- **COVID 2020-21** depresses the early level and inflates FY2021-22 growth: trend models should not treat it as normal variation (candidate intervention dummy, or start fits from FY2021-22 as a sensitivity).
- **FY2025-26 decline** breaks the linear trend; models fitted on FY2021-25 alone will over-project.
- **Short history**: 7 full FY points (8 with flagged FY2018-19) for an annual model; 87 monthly points (99 with flagged extension).
- **State series** reflect plant locations (new plants such as Lakshadweep 2022-12, Ladakh split 2019-12, plant retirements) -> step changes, not demand.

## 8. Figures
{figs}
"""
    (REP / "eda_report.md").write_text(txt, encoding="utf-8")
    print("EDA report written;", len(FIGS), "figures")


if __name__ == "__main__":
    main()
