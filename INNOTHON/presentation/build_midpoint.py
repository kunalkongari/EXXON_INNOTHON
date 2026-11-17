"""
build_midpoint.py - single-slide InnoThon 2026 mid-point review on the Slidesgo template.
Focus: problem, data foundation, approach and work done so far. Deliberately shows NO forecast
results, model scores or 2047 numbers (only descriptive data facts).
Run from INNOTHON/:  python presentation/build_midpoint.py <icons_dir> <screenshots_dir>
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_deck as B  # noqa: E402  (reads icons/screenshots dirs from sys.argv)
from build_deck import (AMB, CARD, DRED, G1, G3, HEAD, K, MUTED, RED, TINT_R, WHITE, Y, circle, icon, icon_circle,  # noqa: E402
                        keep_slides, label_in, line, notes, rrect, set_title, strip, text)
from pptx import Presentation  # noqa: E402
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN  # noqa: E402
from pptx.util import Inches  # noqa: E402

OUT = B.ROOT / "INNOTHON_MidPoint_Review_Approach.pptx"
GREEN = "1E8A4C"   # status colour for "Done" only (status, not a data series)


def header(s, x, y, n, txt, col):
    b = circle(s, x, y, 0.3, col)
    label_in(b, str(n), size=11, color=K if col == Y else WHITE)
    text(s, x + 0.38, y - 0.01, 3.0, 0.32, txt, size=12.5, font=HEAD, bold=True, color=K, anchor=MSO_ANCHOR.MIDDLE)


def build():
    prs = Presentation(str(B.TEMPLATE))
    keep_slides(prs, [3])  # template slide 3 as the base frame (title placeholder + theme)
    s = prs.slides[0]
    strip(s)
    set_title(s, "Forecasting India's Energy Production & Strategizing Its Fulfilment by 2047", size=20)
    t = [sh for sh in s.shapes if sh.is_placeholder][0]
    t.top, t.height = Inches(0.12), Inches(0.5)
    text(s, 0.3, 0.6, 9.4, 0.26, "INNOTHON 2026  ·  MID-POINT REVIEW  ·  APPROACH & PROGRESS", size=10, font=HEAD, bold=True, color=RED,
         align=PP_ALIGN.CENTER)
    for x, w in [(0.3, 2.75), (3.15, 3.8), (7.05, 2.65)]:
        rrect(s, x, 0.95, w, 4.1, CARD, radius=0.04)

    # ---------------- A: problem + data foundation
    header(s, 0.42, 1.05, 1, "PROBLEM", RED)
    text(s, 0.45, 1.42, 2.5, 0.8, "Forecast India's electricity production up to 2047, nationally, for the 5 grid regions and by state, and propose a region-specific generation strategy.",
         size=9.5)
    c = rrect(s, 0.45, 2.22, 2.5, 0.32, TINT_R, radius=0.25)
    label_in(c, "Authorised data · actual generation only", size=8.5, color=RED, font=B.BODY)
    header(s, 0.42, 2.66, 2, "DATA FOUNDATION", AMB)
    srcs = [("filecheck", RED, "National Power Portal", "CEA monthly ACTUAL generation reports"),
            ("folder", AMB, "Organiser GitHub dataset", "state population & GSDP (supporting)")]
    for i, (ic, col, hd, sub) in enumerate(srcs):
        yy = 3.06 + i * 0.5
        icon_circle(s, ic, 0.45, yy, 0.36, col, pad=0.2)
        text(s, 0.9, yy - 0.02, 2.1, 0.45, [[(hd, {"bold": True, "size": 9.5})], [(sub, {"size": 7.5, "color": MUTED})]])
    facts = [("1,745", "files"), ("87", "months"), ("5", "regions"), ("34", "states/UTs")]
    for i, (v, lab) in enumerate(facts):
        x = 0.45 + i * 0.63
        rrect(s, x, 4.08, 0.58, 0.48, WHITE, radius=0.12)
        text(s, x, 4.1, 0.58, 0.26, v, size=12, font=HEAD, bold=True, color=K, align=PP_ALIGN.CENTER)
        text(s, x, 4.34, 0.58, 0.2, lab, size=7, color=MUTED, align=PP_ALIGN.CENTER)
    text(s, 0.45, 4.66, 2.5, 0.3, "Jul-2019 – Sep-2026 · coal, lignite, gas, diesel, nuclear, large hydro", size=7.5, color=MUTED)

    # ---------------- B: approach (methodology pipeline)
    header(s, 3.27, 1.05, 3, "OUR APPROACH", Y)
    steps = [("filecheck", Y, "Data acquisition & audit", "automated download of the NPP archive; every file verified"),
             ("calendar", AMB, "Data engineering", "monthly actuals (not cumulative) in GWh; station → state → region → national checks"),
             ("search", AMB, "Exploratory analysis", "growth, seasonality, source mix, regional patterns, structural breaks"),
             ("brain", RED, "Forecasting models", "baselines → exponential smoothing / ARIMA → Random Forest / XGBoost"),
             ("target", RED, "Rolling-origin validation", "chronological backtests at 1, 3, 6, 12 months; select on out-of-sample error"),
             ("sitemap", DRED, "Hierarchical forecasts", "national → 5 regions → states → state × source, kept consistent"),
             ("route", K, "2047 scenarios & strategy", "low / central / high pathways → regional & source-mix strategy")]
    for i, (ic, col, hd, sub) in enumerate(steps):
        yy = 1.45 + i * 0.5
        if i < len(steps) - 1:
            line(s, 3.47, yy + 0.4, 3.47, yy + 0.5, color=G1, w=1.25)
        icon_circle(s, ic, 3.27, yy, 0.4, col, variant="d" if col == Y else "w", pad=0.2)
        text(s, 3.78, yy - 0.01, 3.1, 0.48, [[(hd, {"bold": True, "size": 10})], [(sub, {"size": 7.5, "color": MUTED})]])

    # ---------------- C: progress + challenges
    header(s, 7.17, 1.05, 4, "WORK DONE SO FAR", DRED)
    prog = [("Data acquisition & audit", "Done"), ("Cleaning & validation", "Done"), ("Exploratory analysis", "Done"),
            ("Model backtesting framework", "Done"), ("Hierarchical forecasts", "In progress"), ("2047 scenarios & strategy", "In progress"),
            ("Dashboard & final deck", "Next")]
    stc = {"Done": GREEN, "In progress": AMB, "Next": G3}
    for i, (it, stt) in enumerate(prog):
        yy = 1.45 + i * 0.29
        text(s, 7.2, yy, 1.62, 0.25, it, size=8.5, anchor=MSO_ANCHOR.MIDDLE)
        p = rrect(s, 8.86, yy + 0.02, 0.74, 0.21, stc[stt], radius=0.5)
        label_in(p, ("✓ " if stt == "Done" else "") + stt, size=7.5, font=B.BODY)
    header(s, 7.17, 3.55, 5, "CHALLENGES", RED)
    chal = [("warn", RED, "No solar/wind generation data", "capacity only - not allowed as a proxy"),
            ("calendar", AMB, "Short history, long horizon", "data from Jul-2019; 2047 is 21 years out"),
            ("layers", G3, "Inconsistent report formats", "cumulative vs monthly; lignite labelled as coal")]
    for i, (ic, col, hd, sub) in enumerate(chal):
        yy = 3.93 + i * 0.37
        icon_circle(s, ic, 7.2, yy, 0.3, col, pad=0.2)
        text(s, 7.58, yy - 0.04, 2.08, 0.38, [[(hd, {"bold": True, "size": 8.5})], [(sub, {"size": 7, "color": MUTED})]])

    st = rrect(s, 0.3, 5.12, 9.4, 0.36, K, radius=0.25)
    text(s, 0.45, 5.12, 9.1, 0.36, [[("Scope: ", {"bold": True, "color": Y}),
                                     ("domestic conventional generation from authorised NPP/CEA actuals · no installed capacity or consumption used · solar & wind flagged as a data gap",
                                      {"color": WHITE})]], size=8, anchor=MSO_ANCHOR.MIDDLE)

    notes(s, """
TIMING: about 10 minutes - Problem 1 min, Data foundation 2 min, Approach 4 min, Work done so far 1.5 min, Challenges 1.5 min. Then 3 minutes of Q&A. Results are intentionally not shown at this stage.

[1 - PROBLEM, ~1 min] We are forecasting India's electricity production up to 2047 - for the country, for each of the five grid regions and for states - and turning that into a region-specific generation strategy. Two rules frame the work: only the authorised data sources may be used, and the forecast must be built on actual generation - not installed capacity and not consumption.

[2 - DATA FOUNDATION, ~2 min] Our main source is the National Power Portal: the CEA monthly 'Actual' generation reports. We automated the download of the full archive and verified every file - 1,745 files in total, including the organiser's GitHub dataset, which provides state population and GSDP as possible supporting variables. The data covers 87 continuous months, July 2019 to September 2026, across 5 grid regions and 34 states and UTs, for coal, lignite, gas, diesel, nuclear and large hydro.

[3 - APPROACH, ~4 min] Our approach has seven steps.
(1) Acquisition and audit - every report is downloaded and checked so we know exactly what the data can and cannot support.
(2) Data engineering - CEA reports contain both monthly and cumulative April-to-date figures; we use only monthly actuals, convert everything to GWh, and check that stations add up to states, states to regions and regions to the national total. Bhutan imports are kept separate from domestic generation.
(3) Exploratory analysis - growth, strong seasonality (hydro peaks in the monsoon), source mix, regional differences, and structural breaks such as COVID and a dry hydro year.
(4) Forecasting models - we compare simple baselines (naive, seasonal naive, linear trend) with statistical models (exponential smoothing, ARIMA/SARIMA) and machine learning (Random Forest, XGBoost).
(5) Rolling-origin validation - we repeatedly train only on past data and forecast 1, 3, 6 and 12 months ahead; a model is chosen only on its out-of-sample error, never on training fit.
(6) Hierarchical forecasting - national, regional, state and state-by-source forecasts are reconciled so they add up consistently.
(7) 2047 - because 21 years is far beyond any validated horizon, we will present low, central and high pathways with explicit assumptions, and derive regional and source-mix strategy from them.

[4 - WORK DONE SO FAR, ~1.5 min] Completed: data acquisition and audit, cleaning and validation, exploratory analysis, and the model backtesting framework. In progress: the hierarchical forecasts and the 2047 scenarios and strategy. Next: the dashboard and the final presentation.

[5 - CHALLENGES, ~1.5 min] First, the authorised sources contain no actual solar or wind generation - only installed capacity, which we are not allowed to use as a proxy - so we model conventional generation and state renewables as a data gap. Second, the archive starts in July 2019, which is a short history for a 2047 horizon. Third, the reports are inconsistent: monthly and cumulative figures sit side by side, and at state level lignite plants are labelled as coal.

FEEDBACK WE WOULD LIKE: Is modelling conventional generation, with renewables flagged as a data gap, an acceptable scope? Is scenario-based 2047 reporting the expected format?

LIKELY QUESTIONS:
- 'Why not use capacity for solar and wind?' It is not generation, and the rules prohibit it as a substitute.
- 'Why so many models?' To make the choice evidence-based: simple baselines set the bar, and complex models must beat them out of sample.
- 'What will you show at the final?' National, regional and state forecasts with uncertainty, 2047 scenarios, and a regional generation strategy.
""")
    prs.save(str(OUT))
    print("saved", OUT)


if __name__ == "__main__":
    build()
