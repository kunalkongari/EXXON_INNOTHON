"""
scenarios.py  (Phase 3I) - FY2047 scenario PROJECTIONS of domestic conventional generation.

These are NOT statistical forecasts. Monthly models are validated only to 12 months; beyond the
statistical forecast (to FY2027-28) the long-run path is a scenario defined by explicit assumptions:

  annual growth g(t) moves linearly from a data-derived starting rate g0 (FY2027-28) to an ASSUMED
  terminal rate gT (FY2046-47). Starting rates are CAGRs computed from the observed FY totals; terminal
  rates are scenario assumptions (stated, not estimated).
  Uncertainty: Monte-Carlo (5,000 paths) with iid annual log-growth shocks, sigma = std of observed FY
  log-growth excluding the COVID year FY2020-21. Reported as P10/P50/P90 per scenario.

Allocation to regions, states and national sources uses FY shares with a damped linear share trend
(phi = 0.8, i.e. the observed share trend fades over ~4-5 years); hydro share = mean of observed FYs
(weather-driven, no trend); group C states keep a constant share of their region. Shares are identical
across scenarios. A constant-share alternative is reported to show allocation uncertainty.
Solar, wind, small hydro and biomass are outside these projections (no authorised generation data).
"""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd

from common import CONFIG, DATA, FC, ROOT, SC

PHI = 0.8
N_SIM = 5000
TERMINAL = {"low": -0.015, "central": 0.0, "high": 0.02}
FY_END = 2046  # FY2046-47
SLOT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1"


def fy_label(y):
    return f"FY{y}-{str(y + 1)[2:]}"


def damped_share(hist: pd.Series, horizon_years: int, trend=True) -> float:
    """hist indexed by fy_start. Returns share after `horizon_years` years beyond the last observation."""
    if not trend or hist.size < 3:
        return float(hist.mean() if not trend else hist.iloc[-1])
    x = hist.index.values.astype(float)
    slope = np.polyfit(x, hist.values, 1)[0]
    cum = sum(PHI ** k for k in range(1, horizon_years + 1))
    return float(hist.iloc[-1] + slope * cum)


def normalise(d: dict) -> dict:
    d = {k: max(v, 0.0) for k, v in d.items()}
    s = sum(d.values())
    return {k: v / s for k, v in d.items()}


def main():
    fyn = pd.read_csv(DATA / "fy_national.csv")
    fyr = pd.read_csv(DATA / "fy_regional.csv")
    fys = pd.read_csv(DATA / "fy_state.csv")
    meta = pd.read_csv(DATA / "node_metadata.csv").set_index("node_id")
    fcast = pd.read_csv(FC / "fy_forecast.csv")
    hist = fyn[(fyn.series == "DOMESTIC_CONVENTIONAL_TOTAL") & fyn.fy_total_gwh.notna() & (fyn.fy_start >= 2019)].set_index("fy_start").fy_total_gwh
    t26 = fcast[(fcast.node_id == "TOTAL") & (fcast.fy == "FY2026-27")].iloc[0]
    t27 = fcast[(fcast.node_id == "TOTAL") & (fcast.fy == "FY2027-28")].iloc[0]
    level = hist.copy()
    level[2026] = t26.fy_total_gwh  # statistical estimate (6 actual + 6 forecast months)
    level[2027] = t27.fy_total_gwh  # statistical forecast (includes months beyond validated horizon)
    lg = np.log(level).diff().dropna()
    g_obs = lg.loc[:2025]
    sigma = float(g_obs.drop(index=2020, errors="ignore").std(ddof=1))
    cagr = lambda a, b: (level[b] / level[a]) ** (1 / (b - a)) - 1  # noqa: E731
    g0 = {"central": cagr(2019, 2025), "high": cagr(2020, 2024), "low": cagr(2023, 2025)}  # observed complete FYs only
    assumptions = {
        "base_year": "FY2027-28 = statistical forecast (reconciled national TOTAL)",
        "start_growth_g0": {k: round(v, 5) for k, v in g0.items()},
        "start_growth_source": {"central": "CAGR FY2019-20 -> FY2025-26 (all observed complete FYs)", "high": "CAGR FY2020-21 -> FY2024-25 (post-COVID expansion)",
                                "low": "CAGR FY2023-24 -> FY2025-26 (most recent observed slowdown)"},
        "terminal_growth_gT_FY2046_47": TERMINAL,
        "terminal_growth_source": "ASSUMPTION (not estimated): central = conventional generation plateaus by 2047; high = continued expansion; low = gradual decline",
        "growth_path": "linear interpolation g0 -> gT between FY2028-29 and FY2046-47",
        "shock_sigma_log_growth": round(sigma, 5),
        "shock_sigma_source": "std of observed FY log growth FY2020-21..FY2025-26 excluding FY2020-21 (COVID)",
        "n_sim": N_SIM, "share_damping_phi": PHI, "seed": CONFIG["seed"],
        "excluded": "solar, wind, small hydro, biomass, waste-to-energy (no authorised generation data); Bhutan import (separate)",
    }
    years = list(range(2028, FY_END + 1))
    rng = np.random.default_rng(CONFIG["seed"])
    rows = []
    for sc in ["low", "central", "high"]:
        g = np.interp(years, [years[0], years[-1]], [g0[sc], TERMINAL[sc]])
        det = [level[2027]]
        for gi in g:
            det.append(det[-1] * np.exp(np.log1p(gi)))
        shocks = rng.normal(0, sigma, size=(N_SIM, len(years)))
        paths = level[2027] * np.exp(np.cumsum(np.log1p(g) + shocks, axis=1))
        for i, y in enumerate(years):
            rows.append({"scenario": sc, "fy_start": y, "fy": fy_label(y), "growth_assumed": g[i], "deterministic_gwh": det[i + 1],
                         "p10_gwh": np.percentile(paths[:, i], 10), "p50_gwh": np.percentile(paths[:, i], 50), "p90_gwh": np.percentile(paths[:, i], 90)})
        for y in (2026, 2027):
            rows.append({"scenario": sc, "fy_start": y, "fy": fy_label(y), "growth_assumed": np.nan, "deterministic_gwh": level[y],
                         "p10_gwh": np.nan, "p50_gwh": level[y], "p90_gwh": np.nan, "note": "statistical forecast"})
    nat = pd.DataFrame(rows).sort_values(["scenario", "fy_start"])
    nat["series_type"] = np.where(nat.fy_start <= 2027, "statistical forecast", "scenario projection")
    nat.to_csv(SC / "fy_scenarios_national.csv", index=False)

    # reference: unconstrained log-linear trend on observed FY totals (not a scenario, shows extrapolation risk)
    x = np.array(hist.index, float)
    b = np.polyfit(x, np.log(hist.values), 1)
    ref2047 = float(np.exp(np.polyval(b, FY_END)))

    # ---------------- allocation shares for FY2046-47
    yrs_ahead = FY_END - 2025
    reg = fyr[(fyr.series == "DOMESTIC_CONVENTIONAL_TOTAL") & fyr.fy_total_gwh.notna()].pivot(index="fy_start", columns="region", values="fy_total_gwh")
    reg_sh = reg.div(reg.sum(axis=1), axis=0)
    rs_trend = normalise({r: damped_share(reg_sh[r], yrs_ahead) for r in reg_sh})
    rs_const = normalise({r: reg_sh[r].iloc[-1] for r in reg_sh})
    st = fys[(fys.series == "STATE_TOTAL") & fys.fy_total_gwh.notna()].groupby(["state_harmonised", "region", "fy_start"]).fy_total_gwh.sum().reset_index()
    st_sh = {}
    for r, g in st.groupby("region"):
        p = g.pivot(index="fy_start", columns="state_harmonised", values="fy_total_gwh").fillna(0)
        p = p.div(p.sum(axis=1), axis=0)
        sh = {}
        for s in p:
            grp = meta.group.get("ST|" + s, "C")
            sh[s] = damped_share(p[s], yrs_ahead, trend=(grp in ("A", "B")))
            if grp == "C":
                sh[s] = float(p[s].iloc[-1])
        st_sh[r] = normalise(sh)
    srcs = ["COAL", "LIGNITE", "NATURAL_GAS", "DIESEL", "NUCLEAR", "HYDRO"]
    src = fyn[fyn.series.isin(srcs) & fyn.method.str.startswith("sum of 12")].pivot(index="fy_start", columns="series", values="fy_total_gwh")
    src_sh = src.div(src.sum(axis=1), axis=0)
    ss = normalise({s: damped_share(src_sh[s], yrs_ahead, trend=(s != "HYDRO")) for s in srcs})
    ss_const = normalise({s: src_sh[s].iloc[-1] for s in srcs})

    n47 = nat[nat.fy_start == FY_END].set_index("scenario")
    reg_rows, st_rows, src_rows = [], [], []
    for sc in ["low", "central", "high"]:
        for q in ["p10_gwh", "p50_gwh", "p90_gwh"]:
            tot = n47.loc[sc, q]
            for r, sh in rs_trend.items():
                reg_rows.append({"scenario": sc, "quantile": q[:3], "region": r, "share_damped_trend": sh, "share_constant": rs_const[r],
                                 "gwh_damped_trend": tot * sh, "gwh_constant_share": tot * rs_const[r]})
                for s, ssh in st_sh[r].items():
                    st_rows.append({"scenario": sc, "quantile": q[:3], "region": r, "state": s, "group": meta.group.get("ST|" + s, ""),
                                    "share_in_region": ssh, "gwh": tot * sh * ssh})
            for s, sh in ss.items():
                src_rows.append({"scenario": sc, "quantile": q[:3], "source": s, "share_damped_trend": sh, "share_constant": ss_const[s],
                                 "gwh_damped_trend": tot * sh, "gwh_constant_share": tot * ss_const[s]})
    pd.DataFrame(reg_rows).to_csv(SC / "fy2047_regional.csv", index=False)
    pd.DataFrame(st_rows).to_csv(SC / "fy2047_state.csv", index=False)
    pd.DataFrame(src_rows).to_csv(SC / "fy2047_source.csv", index=False)

    # ---------------- optional experiment: population / GSDP association (NOT used in projections)
    gh = pd.read_csv(ROOT / "data" / "raw" / "renewable_india" / "renewable-india-dataset" / "data" / "renewable_energy_dataset.csv")
    ann = gh.groupby("Year")[["Population", "GSDP (crore INR)"]].sum()
    common = [y for y in hist.index if y in ann.index]
    opt = {}
    if len(common) >= 4:
        lg_ = np.log(hist.loc[common].values)
        for v in ["Population", "GSDP (crore INR)"]:
            lx = np.log(ann.loc[common, v].values)
            e, c0 = np.polyfit(lx, lg_, 1)
            r2 = np.corrcoef(lx, lg_)[0, 1] ** 2
            opt[v] = {"elasticity": round(float(e), 3), "r2": round(float(r2), 3), "n_years": len(common),
                      "years": f"{common[0]}..{common[-1]} (GitHub 'Year' mapped to FY start; year basis undocumented)"}
    assumptions["optional_population_gsdp_experiment"] = opt
    assumptions["optional_experiment_decision"] = ("NOT used: <= 6 overlapping years, values partly XGBoost-imputed (unflagged), GSDP nominal, "
                                                   "and no authorised projections of population/GSDP to 2047 exist.")
    assumptions["reference_loglinear_trend_FY2046_47_gwh"] = ref2047
    (SC / "scenario_assumptions.json").write_text(json.dumps(assumptions, indent=2, default=float), encoding="utf-8")

    # ---------------- figure
    plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "axes.edgecolor": GRID, "axes.grid": True,
                         "grid.color": GRID, "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
                         "xtick.color": INK2, "ytick.color": INK2, "font.size": 10, "legend.frameon": False})
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(hist.index, hist.values / 1000, color=INK, lw=2, marker="o", ms=4, label="Observed FY total")
    ax.plot([2025, 2026, 2027], [hist[2025] / 1000, level[2026] / 1000, level[2027] / 1000], color=INK, lw=2, ls=(0, (3, 2)), label="Statistical forecast")
    for sc, col in [("high", SLOT[1]), ("central", SLOT[0]), ("low", SLOT[2])]:
        d = nat[(nat.scenario == sc) & (nat.fy_start >= 2027)].sort_values("fy_start")
        ax.fill_between(d.fy_start, d.p10_gwh / 1000, d.p90_gwh / 1000, color=col, alpha=0.15, lw=0)
        ax.plot(d.fy_start, d.p50_gwh / 1000, color=col, lw=2, label=f"{sc.title()} scenario (P50, band P10-P90)")
        v = d.iloc[-1]
        ax.text(FY_END + 0.3, v.p50_gwh / 1000, f"{sc.title()}: {v.p50_gwh / 1000:,.0f} TWh", va="center", fontsize=8.5, color=INK)
    ax.set_xlim(2018.5, FY_END + 4.5)
    ax.set_xticks(list(range(2019, FY_END + 1, 3)), [fy_label(y) for y in range(2019, FY_END + 1, 3)], fontsize=8, rotation=30)
    ax.set_ylabel("TWh", color=INK2)
    ax.set_title("Domestic conventional generation: observed, statistical forecast and FY2046-47 scenario projections", loc="left", fontweight="bold", fontsize=11)
    ax.legend(loc="upper left", fontsize=8.5)
    fig.text(0.01, -0.02, "Scenarios are assumption-driven projections, not predictions. Conventional generation only - excludes solar, wind, small hydro, biomass; Bhutan import excluded.",
             fontsize=7.5, color=MUTED)
    fig.savefig(SC / "national_scenarios.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(nat[nat.fy_start.isin([2027, 2030, 2035, 2040, FY_END])].round(0).to_string())
    print(json.dumps({k: assumptions[k] for k in ["start_growth_g0", "shock_sigma_log_growth"]}, indent=1), ref2047)


if __name__ == "__main__":
    main()
