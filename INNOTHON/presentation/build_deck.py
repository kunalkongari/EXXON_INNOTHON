"""
build_deck.py - builds INNOTHON_Final_Presentation.pptx on the Slidesgo "Petroleum Industry Infographics"
template (theme, master, layouts, colour system and selected infographic slides are reused; petroleum
artwork is removed and replaced by energy-sector content).

All numbers come from project outputs (see INNOTHON_Slide_Source_Mapping.md). Run from INNOTHON/:
    python presentation/build_deck.py <icons_dir> <screenshots_dir>
"""
from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import pandas as pd
from PIL import Image
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "Petroleum Industry Infographics by Slidesgo.pptx"
OUT = ROOT / "INNOTHON_Final_Presentation.pptx"
ICONS = Path(sys.argv[1])
SHOTS = Path(sys.argv[2])
TMP = Path(sys.argv[2]).parent

# ---------------------------------------------------------------- template palette (theme1.xml)
Y, AMB, RED, DRED = "FBCD0B", "EA9600", "E51000", "C10500"
G1, G2, G3, K = "9BB2AF", "C1D3D0", "6C7F7C", "252626"
CARD, TINT_R, MUTED, WHITE = "F1F1F1", "FDECEA", "5F6B69", "FFFFFF"
HEAD, BODY = "Arial Narrow", "Arial"          # Office-safe stand-ins for Fira Sans Extra Condensed / Roboto
SRC_COL = {"COAL": RED, "LIGNITE": DRED, "HYDRO": G1, "NUCLEAR": Y, "NATURAL_GAS": AMB, "DIESEL": G3, "COAL_LIGNITE": RED}


def rgb(h):
    return RGBColor.from_string(h)


# ---------------------------------------------------------------- slide plumbing
def keep_slides(prs, order):
    lst = prs.slides._sldIdLst
    ids = list(lst)
    keep = [ids[i - 1] for i in order]
    for el in ids:
        lst.remove(el)
        if el not in keep:
            prs.part.drop_rel(el.rId)
    for el in keep:
        lst.append(el)


def strip(slide, keep_title=True, keep=()):
    """Remove every shape except the title placeholder (and shapes whose index is in keep)."""
    for i, sh in enumerate(list(slide.shapes)):
        if keep_title and sh.is_placeholder and sh.placeholder_format.type in (1, 3):  # TITLE / CENTER_TITLE
            continue
        if i in keep:
            continue
        sh._element.getparent().remove(sh._element)
    t = slide._element.find(qn("p:timing"))
    if t is not None:
        slide._element.remove(t)


def title_shape(slide):
    for sh in slide.shapes:
        if sh.is_placeholder and sh.placeholder_format.type in (1, 3):
            return sh
    return None


def set_title(slide, text, size=22):
    t = title_shape(slide)
    t.left, t.top, t.width, t.height = Inches(0.5), Inches(0.22), Inches(9.0), Inches(0.62)
    tf = t.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    for r in list(p.runs)[1:]:
        r._r.getparent().remove(r._r)
    for extra in tf.paragraphs[1:]:
        extra._p.getparent().remove(extra._p)
    r = p.runs[0] if p.runs else p.add_run()
    r.text = text
    f = r.font
    f.name, f.size, f.bold = HEAD, Pt(size), True
    f.color.rgb = rgb(K)
    p.alignment = PP_ALIGN.CENTER


def text(slide, x, y, w, h, paras, size=11, color=K, font=BODY, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
         italic=False, spacing=0, name=None):
    """paras: str | list of str | list of list of (text, overrides dict)."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    if isinstance(paras, str):
        paras = [paras]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if spacing:
            p.space_after = Pt(spacing)
        runs = para if isinstance(para, list) else [(para, {})]
        for t, o in runs:
            r = p.add_run()
            r.text = t
            f = r.font
            f.name = o.get("font", font)
            f.size = Pt(o.get("size", size))
            f.bold = o.get("bold", bold)
            f.italic = o.get("italic", italic)
            f.color.rgb = rgb(o.get("color", color))
    return tb


def shape(slide, kind, x, y, w, h, fill=None, line=None, lw=1.0, name=None):
    s = slide.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        s.name = name
    if fill:
        s.fill.solid()
        s.fill.fore_color.rgb = rgb(fill)
    else:
        s.fill.background()
    if line:
        s.line.color.rgb = rgb(line)
        s.line.width = Pt(lw)
    else:
        s.line.fill.background()
    s.shadow.inherit = False
    return s


def circle(slide, x, y, d, fill, **kw):
    return shape(slide, MSO_SHAPE.OVAL, x, y, d, d, fill, **kw)


def rrect(slide, x, y, w, h, fill, radius=0.12, **kw):
    s = shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h, fill, **kw)
    s.adjustments[0] = radius
    return s


def label_in(s, txt, size=11, color=WHITE, bold=True, font=HEAD, align=PP_ALIGN.CENTER):
    tf = s.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    lines = txt if isinstance(txt, list) else [txt]
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        runs = ln if isinstance(ln, list) else [(ln, {})]
        for t, o in runs:
            r = p.add_run()
            r.text = t
            r.font.name, r.font.size, r.font.bold = o.get("font", font), Pt(o.get("size", size)), o.get("bold", bold)
            r.font.color.rgb = rgb(o.get("color", color))


def icon(slide, name, x, y, size, variant="w"):
    return slide.shapes.add_picture(str(ICONS / f"{name}_{variant}.png"), Inches(x), Inches(y), Inches(size), Inches(size))


def icon_circle(slide, name, x, y, d, fill, variant="w", pad=0.24):
    circle(slide, x, y, d, fill)
    s = d * (1 - 2 * pad)
    icon(slide, name, x + (d - s) / 2, y + (d - s) / 2, s, variant)


def line(slide, x1, y1, x2, y2, color=G2, w=1.5, dash=False, arrow=False):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = rgb(color)
    c.line.width = Pt(w)
    ln = c.line._get_or_add_ln()
    if dash:
        d = ln.makeelement(qn("a:prstDash"), {"val": "dash"})
        ln.append(d)
    if arrow:
        t = ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"})
        ln.append(t)
    return c


def source(slide, txt):
    text(slide, 0.5, 5.33, 9.0, 0.2, txt, size=8, color=MUTED, name="Source note")


def notes(slide, txt):
    slide.notes_slide.notes_text_frame.text = txt.strip()


def style_chart(chart, size=9):
    chart.font.name = BODY
    chart.font.size = Pt(size)
    chart.font.color.rgb = rgb(K)


# ---------------------------------------------------------------- data (from project outputs)
def data():
    fn = pd.read_csv(ROOT / "outputs/data/fy_national.csv")
    fys = [f"FY{y}-{str(y + 1)[2:]}" for y in range(2019, 2026)]
    dom = fn[(fn.series == "DOMESTIC_CONVENTIONAL_TOTAL") & fn.fy.isin(fys)].set_index("fy").fy_total_gwh.reindex(fys)
    src = fn[fn.series.isin(SRC_COL) & (fn.fy == "FY2025-26")].set_index("series").fy_total_gwh
    meta = pd.read_csv(ROOT / "outputs/data/node_metadata.csv")
    cells = meta[meta.level == "state_source"].source.value_counts()
    return dom, src, cells


SPEAKER = {}


def build():
    dom, src, cells = data()
    prs = Presentation(str(TEMPLATE))
    # template slide used as the base for each final slide (1-based template numbering)
    base = [1, 3, 31, 7, 11, 12, 29, 23, 25, 18, 30, 28]
    keep_slides(prs, base)
    S = list(prs.slides)

    # ============================================================ 1 TITLE (template slide 1)
    s = S[0]
    for sh in list(s.shapes):
        if sh.shape_type == 6:  # petroleum pump-jack illustration
            sh._element.getparent().remove(sh._element)
    ph = [sh for sh in s.shapes if sh.is_placeholder]
    tph, sph = ph[0], ph[1]
    tph.left, tph.top, tph.width, tph.height = Inches(0.6), Inches(1.15), Inches(4.75), Inches(2.45)
    tf = tph.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    for r in list(p.runs):
        r._r.getparent().remove(r._r)
    for t_, c_ in [("Forecasting India's Energy Production and ", K), ("Strategizing Its Fulfilment by 2047", RED)]:
        r = p.add_run()
        r.text = t_
        r.font.name, r.font.size, r.font.bold = HEAD, Pt(32), True
        r.font.color.rgb = rgb(c_)
    sph.left, sph.top, sph.width, sph.height = Inches(0.6), Inches(3.75), Inches(4.9), Inches(0.62)
    stf = sph.text_frame
    stf.word_wrap = True
    sp = stf.paragraphs[0]
    for r in list(sp.runs):
        r._r.getparent().remove(r._r)
    r = sp.add_run()
    r.text = "A Data-Driven National and Regional Energy Forecasting and Strategy Framework"
    r.font.name, r.font.size, r.font.color.rgb = BODY, Pt(13), rgb(MUTED)
    text(s, 0.6, 0.72, 4.5, 0.3, "INNOTHON  ·  FINAL SUBMISSION", size=11, color=RED, font=HEAD, bold=True)
    text(s, 0.6, 4.55, 4.9, 0.5, ["Domestic conventional generation · NPP / CEA actuals, Jul-2019 – Sep-2026",
                                  "Statistical forecasts · 2047 scenarios · regional strategy"], size=9.5, color=MUTED)
    # hero: energy network around a 2047 hub
    cx, cy = 7.7, 2.85
    hub = circle(s, cx - 0.95, cy - 0.95, 1.9, K)
    label_in(hub, [[("2047", {"size": 34, "color": Y})], [("INDIA · ENERGY", {"size": 10, "color": WHITE, "font": BODY})]])
    nodes = [("thermal", RED, -1.55, -1.45), ("hydro", G1, 0.55, -1.62), ("nuclear", Y, 1.55, -0.45),
             ("gas", AMB, 1.35, 0.95), ("coal", DRED, -1.75, 0.15), ("pylon", G3, -0.45, 1.45)]
    for nm, col, dx, dy in nodes:
        d = 0.78
        line(s, cx, cy, cx + dx, cy + dy, color=G2, w=2)
    hub2 = circle(s, cx - 0.95, cy - 0.95, 1.9, K)  # redraw hub above connectors
    label_in(hub2, [[("2047", {"size": 34, "color": Y})], [("INDIA · ENERGY", {"size": 10, "color": WHITE, "font": BODY})]])
    hub._element.getparent().remove(hub._element)
    for nm, col, dx, dy in nodes:
        d = 0.78
        icon_circle(s, nm, cx + dx - d / 2, cy + dy - d / 2, d, col, variant="d" if col == Y else "w")
    for nm, dx, dy in [("solar", 0.95, 1.75), ("wind", 1.85, 1.75)]:
        circle(s, cx + dx - 0.3, cy + dy - 0.3, 0.6, WHITE, line=G1, lw=1.25)
        icon(s, nm, cx + dx - 0.19, cy + dy - 0.19, 0.38, "d")
    text(s, cx + 0.55, cy + 2.12, 1.75, 0.3, "solar & wind: not quantified*", size=8, color=MUTED, align=PP_ALIGN.CENTER)
    text(s, 0.6, 5.3, 8.8, 0.22, "*No authorised actual-generation data for solar and wind; they are shown for context only and are outside all forecasts.",
         size=8, color=MUTED)
    notes(s, """
WHAT TO SAY (≈45 s): Good morning. Our project is "Forecasting India's Energy Production and Strategizing Its Fulfilment by 2047". We built a data-driven framework that forecasts India's domestic conventional electricity generation - nationally, by grid region and by state - and turns those forecasts into region-specific strategies towards 2047.
CONTEXT: Everything comes only from the two authorised sources - the National Power Portal (CEA monthly ACTUAL generation reports) and the organiser's GitHub dataset. Our results cover conventional generation: coal, lignite, gas, diesel, nuclear and large hydro.
THE VISUAL: The hub shows the conventional sources we model. Solar and wind are drawn as outlines on purpose - there was no authorised actual-generation data for them, so they are not forecast.
TRANSITION: Let me start with why a national number alone is not enough.
LIKELY QUESTION: "Why not total generation?" - Because the authorised data contains actual generation only for conventional sources; using renewable installed capacity as a proxy is explicitly prohibited.
""")

    # ============================================================ 2 CHALLENGE (template slide 3: three cards)
    s = S[1]
    rects = [i for i, sh in enumerate(s.shapes) if sh.shape_type == 1]
    strip(s, keep=rects)
    set_title(s, "India's Energy Future: From Historical Generation to 2047")
    text(s, 0.5, 0.9, 9.0, 0.35, "Long-term planning needs more than one national number - India's regions run very different generation portfolios.",
         size=12, color=MUTED, align=PP_ALIGN.CENTER)
    cards = sorted([sh for sh in s.shapes if sh.shape_type == 1], key=lambda z: z.left)
    spec = [("CHALLENGE", "target", RED, [("National projections alone hide regional differences.", None),
                                          ("Each grid region has a different generation portfolio.", None),
                                          ("Planning needs forecasts and region-specific strategy.", None)]),
            ("FORECAST", "spline", AMB, [("Forecast national, regional and state-level generation.", "1"),
                                         ("Understand the contribution of each conventional source.", "2")]),
            ("STRATEGY", "route", DRED, [("Develop evidence-based regional strategies towards 2047.", "3")])]
    for card, (hd, ic, col, items) in zip(cards, spec):
        x0, w0 = card.left / 914400, card.width / 914400
        card.top, card.height = Inches(1.45), Inches(3.55)
        card.fill.solid()
        card.fill.fore_color.rgb = rgb(CARD)
        icon_circle(s, ic, x0 + w0 / 2 - 0.4, 1.65, 0.8, col)
        text(s, x0 + 0.12, 2.55, w0 - 0.24, 0.35, hd, size=18, font=HEAD, bold=True, color=col, align=PP_ALIGN.CENTER)
        yy = 3.02
        for txt, num in items:
            if num:
                b = circle(s, x0 + 0.15, yy, 0.32, col)
                label_in(b, num, size=11)
                text(s, x0 + 0.55, yy - 0.02, w0 - 0.67, 0.62, [[("OBJECTIVE " + num, {"size": 8.5, "bold": True, "color": col})], txt], size=11)
                yy += 0.82
            else:
                text(s, x0 + 0.18, yy, w0 - 0.36, 0.5, [[("▪  ", {"color": col, "bold": True}), (txt, {})]], size=11)
                yy += 0.6
    x3 = cards[2].left / 914400
    text(s, x3 + 0.18, 4.08, cards[2].width / 914400 - 0.36, 0.85, [[("OUTPUTS", {"size": 8.5, "bold": True, "color": DRED})],
         "2047 scenarios · energy-mix policies · regional & state strategies · interactive dashboard"], size=9.5, color=MUTED)
    for xa in (3.36, 6.18):
        a = shape(s, MSO_SHAPE.CHEVRON, xa, 2.85, 0.42, 0.5, RED)
    source(s, "Objectives defined for this project; all results that follow use only the authorised NPP/CEA and organiser GitHub data.")
    notes(s, """
WHAT TO SAY (≈60 s): India needs a long-term view of electricity generation, but a single national projection hides an important fact: India's five grid regions generate electricity in very different ways - one is almost all coal, another is hydro and gas-led. So our framework moves from Challenge, to Forecast, to Strategy.
OBJECTIVES: (1) forecast generation at national, regional and state level; (2) understand how much each conventional source contributes; (3) build evidence-based regional strategies towards 2047.
THE VISUAL: Read left to right - the problem, the forecasting layer, and the strategy layer that uses the forecasts.
TRANSITION: Before any forecast, we had to build a trustworthy data foundation.
LIKELY QUESTION: "Is this a demand forecast?" - No. We forecast generation (production) from actual generation reports; demand and consumption data were not used, as required by the rules.
""")

    # ============================================================ 3 DATA FOUNDATION (template slide 31: icon grid)
    s = S[2]
    ovals = [i for i, sh in enumerate(s.shapes) if sh.shape_type == 1]
    strip(s, keep=ovals)
    set_title(s, "Building the Foundation: 1,745 Verified Source Files")
    tmpl_ovals = sorted([sh for sh in s.shapes if sh.shape_type == 1], key=lambda z: (round(z.top / 914400, 1), z.left))
    text(s, 0.5, 0.98, 3.6, 0.75, [[("1,745", {"size": 50, "bold": True, "font": HEAD, "color": RED})]], anchor=MSO_ANCHOR.MIDDLE)
    text(s, 2.25, 1.12, 1.95, 0.55, "verified source files (each checked: present, real file format, opens)", size=10, color=MUTED, anchor=MSO_ANCHOR.MIDDLE)
    rows = [("1,740", "NPP monthly reports (CEA ACTUAL, XLS)", RED, "filecheck"), ("4", "Organiser GitHub repository files", AMB, "folder"),
            ("1", "NPP dashboard snapshot (evidence)", G3, "dashboard")]
    yy = 1.85
    for num, lab, col, ic in rows:
        b = rrect(s, 0.5, yy, 0.95, 0.38, col, radius=0.25)
        label_in(b, num, size=14)
        text(s, 1.55, yy, 2.55, 0.38, lab, size=10.5, anchor=MSO_ANCHOR.MIDDLE)
        yy += 0.46
    chips = [("87", "months · Jul-2019 – Sep-2026"), ("5", "grid regions"), ("34", "states & UTs")]
    for i, (n, lab) in enumerate(chips):
        x = 0.5 + i * 1.22
        c = rrect(s, x, 3.3, 1.12, 0.72, CARD, radius=0.1)
        text(s, x + 0.05, 3.33, 1.02, 0.36, n, size=20, font=HEAD, bold=True, color=K, align=PP_ALIGN.CENTER)
        text(s, x + 0.05, 3.67, 1.02, 0.32, lab, size=8.5, color=MUTED, align=PP_ALIGN.CENTER)
    wbox = rrect(s, 0.5, 4.2, 3.58, 0.92, TINT_R, radius=0.08, line=RED, lw=1)
    icon(s, "warn", 0.65, 4.42, 0.45, "r")
    text(s, 1.22, 4.27, 2.78, 0.8, [[("Data limitation", {"bold": True, "color": RED})],
                                     "Solar and wind actual generation was not available in the authorised sources - they are not forecast."],
         size=10, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 4.31, 0.98, 5.2, 0.3, "GENERATION SOURCES WITH ACTUAL DATA", size=10, font=HEAD, bold=True, color=MUTED)
    ov = tmpl_ovals
    gen = [("coal", "Coal & lignite", "~84% of conventional output", RED), ("hydro", "Large hydro", ">25 MW stations", G1),
           ("nuclear", "Nuclear", "monitored stations", Y), ("gas", "Natural gas", "incl. liquid-fuel operation", AMB),
           ("diesel", "Diesel", "own series, inside domestic total", G3), ("plug", "Bhutan imports", "kept separate from domestic", DRED)]
    for o, (ic, hd, sub, col) in zip(ov, gen):
        o.top = o.top - Inches(0.08)
        o.width = o.height = Inches(0.86)
        o.fill.solid()
        o.fill.fore_color.rgb = rgb(col)
        x, y = o.left / 914400, o.top / 914400
        icon(s, ic, x + 0.2, y + 0.2, 0.46, "d" if col == Y else "w")
        text(s, x + 0.97, y + 0.08, 1.55, 0.72, [[(hd, {"bold": True, "size": 13, "font": HEAD})], [(sub, {"size": 9, "color": MUTED})]])
    source(s, "Source: data/metadata/download_manifest.csv; reports/data_audit.md; reports/data_availability.csv.")
    notes(s, """
WHAT TO SAY (≈60 s): Our foundation is 1,745 verified files: 1,740 monthly CEA "Actual" generation reports from the National Power Portal, the 4 files of the organiser's GitHub repository, and one dashboard snapshot kept as evidence. Every file was checked - it exists, it is genuinely an Excel or PDF file and it opens.
COVERAGE: 87 continuous months, July 2019 to September 2026 - the portal's archive has nothing earlier - across 5 grid regions and 34 states and UTs.
THE GRID: These are the sources with actual generation data: coal and lignite, large hydro, nuclear and natural gas. Diesel is tracked as its own series but is part of domestic generation; Bhutan imports are kept completely separate.
LIMITATION (be explicit): Solar and wind actual generation was not available in the authorised sources, and installed capacity cannot be used as a substitute - so renewables are not forecast.
TRANSITION: Next, how we turned these reports into a reliable dataset.
LIKELY QUESTIONS: "Why only from 2019?" - The NPP archive returns no monthly ACTUAL reports before July 2019; we queried back to 2010. "What did you use from GitHub?" - Only population/GSDP for an optional test; it was not adopted because values are partly model-imputed.
""")

    # ============================================================ 4 DATA ENGINEERING (template slide 7: numbered process)
    s = S[3]
    strip(s)
    set_title(s, "Turning Raw Reports into a Reliable Forecasting Dataset")
    steps = [("filecheck", "Raw NPP\nreports", Y), ("filter", "Data\nextraction", AMB), ("calendar", "Monthly actual\ngeneration", RED),
             ("layers", "State & regional\naggregation", DRED), ("shield", "Validation", G3), ("dbzap", "Forecast-ready\ndataset", K)]
    d, x0, gap = 0.9, 0.62, 1.58
    for i in range(5):
        line(s, x0 + i * gap + d + 0.05, 1.5, x0 + (i + 1) * gap - 0.05, 1.5, color=G1, w=2, arrow=True)
    for i, (ic, lab, col) in enumerate(steps):
        x = x0 + i * gap
        icon_circle(s, ic, x, 1.05, d, col, variant="d" if col == Y else "w")
        n = circle(s, x + d - 0.22, 0.98, 0.3, WHITE, line=col, lw=1.5)
        label_in(n, str(i + 1), size=10, color=col)
        text(s, x - 0.3, 2.05, d + 0.6, 0.5, lab.split("\n"), size=11, font=HEAD, bold=True, align=PP_ALIGN.CENTER)
    box = rrect(s, 0.5, 2.8, 4.75, 2.38, CARD, radius=0.05)
    text(s, 0.7, 2.9, 4.4, 0.3, "WHAT THE PIPELINE ENFORCES", size=10, font=HEAD, bold=True, color=MUTED)
    rules = ["Original raw files preserved, never modified", "Monthly actual separated from cumulative figures",
             "All energy converted to GWh (1 GWh = 1 MU)", "Station → state → region → national reconciled",
             "Bhutan imports kept separate from domestic", "Data-quality and consistency checks at every stage"]
    for i, rl in enumerate(rules):
        yy = 3.25 + i * 0.31
        icon(s, "check", 0.72, yy + 0.02, 0.2, "r")
        text(s, 1.02, yy, 4.1, 0.28, rl, size=10.5)
    text(s, 5.5, 2.83, 4.0, 0.3, "VALIDATION - THREE SEPARATE STAGES", size=10, font=HEAD, bold=True, color=MUTED)
    tiles = [("2.26%", RED, "Audit reconciliation", "All checks within 0.001% except Feb-2020 hydro (sector vs national report)."),
             ("13/14", AMB, "Data preparation", "Within 1 GWh; exception: extended-history overlap ≤0.10% → sensitivity only."),
             ("19/19", DRED, "Strategy & dashboard", "Final reconciliation and output checks passed.")]
    for i, (big, col, hd, body) in enumerate(tiles):
        yy = 3.15 + i * 0.7
        t = rrect(s, 5.5, yy, 4.0, 0.62, WHITE, radius=0.12, line=col, lw=1.25)
        text(s, 5.6, yy, 1.05, 0.62, big, size=20, font=HEAD, bold=True, color=col, anchor=MSO_ANCHOR.MIDDLE, align=PP_ALIGN.CENTER)
        text(s, 6.72, yy + 0.05, 2.72, 0.52, [[(hd, {"bold": True, "size": 10})], [(body, {"size": 8.5, "color": MUTED})]], anchor=MSO_ANCHOR.MIDDLE)
    source(s, "Source: reports/data_quality_report.md (audit); outputs/data/validation_checks.csv (preparation); outputs/strategy/validation_checks.csv (strategy).")
    notes(s, """
WHAT TO SAY (≈70 s): The CEA reports are formatted spreadsheets, not tables, so we built a six-step pipeline: raw reports, extraction, monthly actual generation, state and regional aggregation, validation, and a forecast-ready dataset.
KEY RULES: Raw files are never modified. Each report has both a monthly figure and a cumulative April-to-date figure - we use only the monthly actual as the forecasting target, so nothing is double-counted. Everything is in GWh. Station, state, regional and national totals are reconciled, and Bhutan imports are kept out of domestic generation.
VALIDATION - three different stages (keep them separate):
(1) Audit reconciliation: all cross-report checks agree within 0.001%; the single exception is February 2020 hydro, where the sector report and the national report differ by 2.26%.
(2) Data preparation: 13 of 14 identity checks within 1 GWh; the one exception is the extended 2018-19 history, which differs by at most 0.10% from originally published figures - so it is used only as a sensitivity test.
(3) Strategy and dashboard: 19 of 19 checks passed.
TRANSITION: With clean data, what does history tell us?
LIKELY QUESTION: "Did you fix the 2.26% difference?" - No; we never alter source data. It is documented, and it does not affect the national series we model.
""")

    # ============================================================ 5 HISTORICAL (template slide 11: chart + callouts)
    s = S[4]
    strip(s)
    set_title(s, "What Does India's Historical Generation Tell Us?")
    cd = CategoryChartData()
    cd.categories = list(dom.index)
    cd.add_series("Domestic conventional generation (TWh)", [round(v / 1000) for v in dom.values])
    gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.45), Inches(0.95), Inches(5.6), Inches(3.05), cd)
    ch = gf.chart
    style_chart(ch)
    ch.has_legend = False
    ch.has_title = True
    ch.chart_title.text_frame.text = "Domestic conventional generation by financial year (TWh)"
    tr = ch.chart_title.text_frame.paragraphs[0].runs[0]
    tr.font.size, tr.font.bold, tr.font.name, tr.font.color.rgb = Pt(11), True, HEAD, rgb(K)
    pl = ch.plots[0]
    pl.gap_width = 55
    pl.has_data_labels = True
    dl = pl.data_labels
    dl.number_format, dl.number_format_is_linked = "#,##0", False
    dl.position = XL_LABEL_POSITION.OUTSIDE_END
    dl.font.size, dl.font.bold = Pt(10), True
    ser = pl.series[0]
    for i in range(len(dom)):
        pt = ser.points[i]
        pt.format.fill.solid()
        pt.format.fill.fore_color.rgb = rgb({1: G1, 4: AMB, 6: RED}.get(i, Y))
    va = ch.value_axis
    va.minimum_scale, va.maximum_scale = 0, 1800
    va.has_major_gridlines = True
    va.major_gridlines.format.line.color.rgb = rgb("E3E3E3")
    va.format.line.fill.background()
    va.tick_labels.font.size = Pt(8)
    va.tick_labels.font.color.rgb = rgb(MUTED)
    ca = ch.category_axis
    ca.tick_labels.font.size = Pt(8.5)
    ca.format.line.color.rgb = rgb(G2)
    # right: growth stat + three callouts
    text(s, 6.35, 0.98, 3.2, 0.62, [[("≈3.5%", {"size": 32, "bold": True, "font": HEAD, "color": RED}), ("  per year", {"size": 12, "color": MUTED})]],
         anchor=MSO_ANCHOR.MIDDLE)
    text(s, 6.35, 1.55, 3.2, 0.25, "compound growth, FY2019-20 → FY2025-26", size=9.5, color=MUTED)
    calls = [("down", G1, "FY2020-21: −1.5%", "COVID-related decline"), ("hydro", AMB, "FY2023-24: hydro −17%", "weak monsoon; thermal filled the gap"),
             ("down", RED, "FY2025-26: −2.5%", "thermal fell, hydro recovered")]
    for i, (ic, col, hd, sub) in enumerate(calls):
        yy = 1.95 + i * 0.68
        icon_circle(s, ic, 6.35, yy, 0.56, col)
        text(s, 7.05, yy + 0.02, 2.5, 0.55, [[(hd, {"bold": True, "size": 12, "font": HEAD})], [(sub, {"size": 9.5, "color": MUTED})]])
    # bottom: FY2025-26 source mix bar
    text(s, 0.5, 4.13, 9.0, 0.25, "FY2025-26 CONVENTIONAL GENERATION MIX", size=10, font=HEAD, bold=True, color=MUTED)
    order = ["COAL", "HYDRO", "NUCLEAR", "LIGNITE", "NATURAL_GAS", "DIESEL"]
    tot = src[order].sum()
    x = 0.5
    W = 9.0
    for k in order:
        w = W * src[k] / tot
        if w > 0.005:
            shape(s, MSO_SHAPE.RECTANGLE, x, 4.42, w, 0.32, SRC_COL[k])
        x += w
    lab = [("Coal", "82%", "COAL"), ("Hydro", "11%", "HYDRO"), ("Nuclear", "3.6%", "NUCLEAR"), ("Lignite", "2.0%", "LIGNITE"),
           ("Natural gas", "1.7%", "NATURAL_GAS"), ("Diesel", "<0.1%", "DIESEL")]
    for i, (nm, v, k) in enumerate(lab):
        xx = 0.5 + i * 1.5
        shape(s, MSO_SHAPE.RECTANGLE, xx, 4.86, 0.16, 0.16, SRC_COL[k])
        text(s, xx + 0.22, 4.81, 1.25, 0.26, [[(v + " ", {"bold": True}), (nm, {"color": MUTED})]], size=10)
    source(s, "Source: outputs/data/fy_national.csv (FY totals; FY2019-20 from published March cumulative); reports/eda shares FY2025-26.")
    notes(s, """
WHAT TO SAY (≈70 s): This is seven years of actual domestic conventional generation. It grew from 1,245 TWh in FY2019-20 to a peak of 1,569 TWh in FY2024-25 - about 3.5% a year overall.
THREE EVENTS (the coloured bars): FY2020-21 dipped 1.5% because of COVID. FY2023-24 still grew, but hydro fell by about 17% in a weak monsoon year, and thermal filled the gap. FY2025-26 fell 2.5%: thermal declined while hydro recovered.
THE MIX: Coal alone is about 82% of conventional generation, large hydro 11%, nuclear 3.6%, lignite 2% and gas 1.7%.
WHY IT MATTERS: The series is short and has structural breaks, so the forecasting method must be validated carefully - which is the next slide.
LIKELY QUESTIONS: "Why did FY2025-26 fall?" - Our data shows thermal fell and hydro rose; we cannot attribute the cause because renewable generation is not in the authorised data. "Is FY2019-20 complete?" - Monthly files start in July 2019; the full-year value is CEA's own published April-to-March cumulative figure.
""")

    # ============================================================ 6 METHODOLOGY (template slide 12: numbered vertical list)
    s = S[5]
    strip(s)
    set_title(s, "How Do We Forecast India's Energy Generation?")
    pipe = [("Historical data", "87 monthly actuals · 120 series"), ("Exploratory data analysis", "trend, seasonality, structural breaks"),
            ("Model training", "expanding window, refit at every origin"), ("Rolling-origin backtesting", "horizons 1, 3, 6 and 12 months"),
            ("Model selection", "lowest out-of-sample MASE; must beat seasonal naive"), ("Forecast generation", "Oct-2026 → Mar-2028, with intervals"),
            ("Hierarchical reconciliation", "bottom-up: totals add up at every level")]
    cols = [Y, AMB, AMB, RED, RED, DRED, K]
    for i, (hd, sub) in enumerate(pipe):
        yy = 0.98 + i * 0.6
        if i < len(pipe) - 1:
            line(s, 5.21, yy + 0.42, 5.21, yy + 0.6, color=G1, w=1.5)
        b = circle(s, 5.0, yy, 0.42, cols[i])
        label_in(b, str(i + 1), size=12, color=K if cols[i] == Y else WHITE)
        text(s, 5.58, yy - 0.02, 3.95, 0.5, [[(hd, {"bold": True, "size": 12.5, "font": HEAD})], [(sub, {"size": 9.5, "color": MUTED})]])
    text(s, 0.5, 0.98, 4.2, 0.3, "MODELS EVALUATED", size=10, font=HEAD, bold=True, color=MUTED)
    groups = [("Baselines", Y, ["Naive", "Seasonal naive", "Linear trend"]),
              ("Statistical", AMB, ["Exponential smoothing / ETS", "Holt-Winters", "ARIMA / SARIMA"]),
              ("Machine learning", RED, ["Random Forest", "XGBoost"])]
    yy = 1.3
    for g, col, ms in groups:
        hb = rrect(s, 0.5, yy, 1.3, 0.32, col, radius=0.3)
        label_in(hb, g, size=10.5, color=K if col == Y else WHITE)
        xx = 1.9
        for m in ms:
            wch = 0.16 + 0.066 * len(m)
            if xx + wch > 4.65:
                xx, yy = 1.9, yy + 0.4
            c = rrect(s, xx, yy, wch, 0.32, WHITE, radius=0.3, line=col, lw=1.25)
            label_in(c, m, size=9, color=K, bold=False, font=BODY)
            xx += wch + 0.07
        yy += 0.46
    text(s, 0.5, 3.13, 4.2, 0.3, "ROLLING-ORIGIN BACKTEST HORIZONS", size=10, font=HEAD, bold=True, color=MUTED)
    for i, h in enumerate(["1", "3", "6", "12"]):
        c = circle(s, 0.5 + i * 0.95, 3.42, 0.72, [Y, AMB, RED, DRED][i])
        label_in(c, [[(h, {"size": 18, "color": K if i == 0 else WHITE})], [("month" + ("s" if h != "1" else ""), {"size": 8, "font": BODY, "bold": False, "color": K if i == 0 else WHITE})]])
    note = rrect(s, 0.5, 4.27, 4.15, 0.86, CARD, radius=0.08)
    text(s, 0.65, 4.3, 3.9, 0.8, [[("Strict chronological validation", {"bold": True})],
                                   "Each model only sees data up to the forecast origin - no random train/test splits, no future information."],
         size=10, anchor=MSO_ANCHOR.MIDDLE)
    source(s, "Source: reports/backtesting_report.md; reports/model_comparison.md; outputs/models/experiment_config.json.")
    notes(s, """
WHAT TO SAY (≈65 s): Our workflow has seven steps, shown on the right: historical data, exploratory analysis, model training, rolling-origin backtesting, model selection, forecast generation and hierarchical reconciliation.
MODELS: We compared simple baselines - naive, seasonal naive and linear trend - with statistical models - exponential smoothing (ETS), Holt-Winters and ARIMA/SARIMA - and machine learning - Random Forest and XGBoost, trained as global models across all series.
BACKTESTING: Rolling-origin means we repeatedly pretend to be at a past month, train only on data up to that point, and forecast 1, 3, 6 and 12 months ahead, then compare with what actually happened. Selection is based only on these out-of-sample errors, never on training fit.
COVID: A March-May 2020 intervention indicator was used for models that accept regressors.
TRANSITION: So which model won?
LIKELY QUESTIONS: "Why not deep learning (LSTM)?" - With 87 monthly points, deep models would overfit; our ML results already show that more complex models did not beat ETS. "How many forecast origins?" - 39 monthly origins for national, regional and source series; 13 quarterly origins for states.
""")

    # ============================================================ 7 MODEL PERFORMANCE (template slide 29: horizontal bars)
    s = S[6]
    strip(s)
    set_title(s, "Why Exponential Smoothing Was Selected")
    perf = [("National", "ETS", 0.710), ("Regions", "ETS", 0.710), ("National sources", "ETS", 0.799), ("Group A states", "ETS", 0.771),
            ("Group B states", "ETS", 0.976), ("Group C states", "Seasonal naive", 0.902), ("State × source", "ETS", 0.961)]
    bx, scale = 2.0, 3.3  # inches per 1.0 MASE
    text(s, 0.5, 0.98, 5.6, 0.28, "OUT-OF-SAMPLE MASE OF THE SELECTED MODEL (lower is better)", size=10, font=HEAD, bold=True, color=MUTED)
    top = 1.42
    for i, (lvl, mdl, v) in enumerate(perf):
        yy = top + i * 0.5
        text(s, 0.5, yy, 1.4, 0.36, lvl, size=11, font=HEAD, bold=True, align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)
        col = RED if mdl == "ETS" else G3
        b = rrect(s, bx, yy + 0.02, scale * v, 0.32, col, radius=0.2)
        label_in(b, "  " + mdl, size=10, align=PP_ALIGN.LEFT, font=BODY)
        text(s, bx + scale * v - 0.68, yy, 0.6, 0.36, f"{v:.3f}", size=11, bold=True, color=WHITE, align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)
    xr = bx + scale * 1.0
    line(s, xr, 1.3, xr, top + 7 * 0.5 - 0.05, color=K, w=1.25, dash=True)
    text(s, xr - 1.1, top + 7 * 0.5 - 0.02, 2.2, 0.3, "1.0 = seasonal-naive error scale", size=8.5, color=K, align=PP_ALIGN.CENTER)
    obs = [("badge", RED, "ETS best at 6 of 7 levels", "beats every baseline out of sample (national 0.710 vs 0.769)"),
           ("brain", AMB, "ML did not beat ETS", "national MASE: XGBoost 0.990, Random Forest 1.131"),
           ("alert", G3, "Group C → seasonal naive", "small, volatile series; no model beat the benchmark"),
           ("scale", DRED, "MASE < 1", "smaller errors than the seasonal-naive benchmark scale")]
    for i, (ic, col, hd, sub) in enumerate(obs):
        yy = 1.05 + i * 0.98
        icon_circle(s, ic, 6.75, yy, 0.62, col)
        text(s, 7.5, yy, 2.05, 0.8, [[(hd, {"bold": True, "size": 12, "font": HEAD})], [(sub, {"size": 9.5, "color": MUTED})]])
    source(s, "Source: outputs/models/selected_models_A.csv; outputs/backtesting/metrics_by_level_model_A.csv (Experiment A, h = 1-12 pooled).")
    notes(s, """
WHAT TO SAY (≈70 s): This chart shows the out-of-sample MASE of the model selected at each level. MASE compares forecast error with the error of a simple seasonal-naive forecast: below 1 means our model does better than that benchmark scale. The dashed line marks 1.0.
RESULT: Exponential smoothing, ETS, was the most accurate model at six of seven levels - 0.710 nationally and for regions, 0.799 for national sources, 0.771 for the largest states, 0.976 for group B states and 0.961 for state-by-source series.
ML: XGBoost and Random Forest did not outperform ETS - nationally they scored 0.990 and 1.131. With only 87 months, a well-specified smoothing model captures trend and seasonality more reliably than tree models.
GROUP C: For the eight small, volatile states, no model beat seasonal naive, so we keep the benchmark - simplest adequate model.
TRANSITION: Forecasting each level separately creates a new problem: the numbers do not add up. That is solved by reconciliation.
LIKELY QUESTIONS: "Why MASE and not MAPE?" - Some state-by-source series contain zeros, which break MAPE; MASE is scale-free and robust. "Was selection biased?" - The rule was fixed before results were seen: lowest out-of-sample MASE, and it must beat seasonal naive.
""")

    # ============================================================ 8 HIERARCHY (template slide 23: tree)
    s = S[7]
    strip(s)
    set_title(s, "One Consistent Forecast Across Every Geographic Level")
    lv = [("1", "National", 1.08), ("5", "Grid regions", 1.86), ("33", "State series", 2.62), ("73", "State × source series", 3.62)]
    for n, lab, yy in lv:
        text(s, 0.5, yy - 0.04, 0.85, 0.5, n, size=26, font=HEAD, bold=True, color=RED, align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)
        text(s, 1.45, yy - 0.04, 1.35, 0.5, lab, size=11, font=HEAD, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    cx = 4.25
    nat = circle(s, cx - 0.3, 1.0, 0.6, K)
    icon(s, "bolt", cx - 0.17, 1.13, 0.34, "w")
    rc8 = {"Northern": G1, "Western": RED, "Southern": Y, "Eastern": DRED, "North Eastern": AMB}
    order8 = ["Northern", "Western", "Southern", "Eastern", "North Eastern"]
    reg_cols = [rc8[r] for r in order8]
    meta8 = pd.read_csv(ROOT / "outputs/data/node_metadata.csv")
    st_counts = meta8[meta8.level == "state"].region.value_counts()
    state_cols = [rc8[r] for r in order8 for _ in range(int(st_counts.get(r, 0)))]
    rx = [cx - 1.4 + i * 0.7 for i in range(5)]
    for xx in rx:
        line(s, cx, 1.6, xx, 1.85, color=G1, w=1.25)
    for xx, col, rn in zip(rx, reg_cols, order8):
        circle(s, xx - 0.2, 1.85, 0.4, col)
        b8 = s.shapes[-1]
        label_in(b8, {"North Eastern": "NE"}.get(rn, rn[0]), size=9, color=K if col in (Y, G1) else WHITE)
    for xx in rx:
        line(s, xx, 2.25, xx, 2.55, color=G1, w=1)
    # 33 state dots in two rows
    for i in range(33):
        r_, c_ = divmod(i, 17)
        circle(s, cx - 1.7 + c_ * 0.2 + (0.1 if r_ else 0), 2.58 + r_ * 0.22, 0.15, state_cols[i])
    line(s, cx, 3.05, cx, 3.5, color=G1, w=1.25, arrow=True)
    # 73 cells coloured by source
    seq = []
    for k in ["COAL_LIGNITE", "HYDRO", "NATURAL_GAS", "NUCLEAR", "DIESEL"]:
        seq += [k] * int(cells.get(k, 0))
    for i, k in enumerate(seq):
        r_, c_ = divmod(i, 19)
        shape(s, MSO_SHAPE.RECTANGLE, cx - 1.5 + c_ * 0.158, 3.55 + r_ * 0.158, 0.12, 0.12, SRC_COL[k])
    leg = [("Coal+lignite", "COAL_LIGNITE"), ("Hydro", "HYDRO"), ("Gas", "NATURAL_GAS"), ("Nuclear", "NUCLEAR"), ("Diesel", "DIESEL")]
    for i, (nm, k) in enumerate(leg):
        xx = 1.0 + i * 1.08
        shape(s, MSO_SHAPE.RECTANGLE, xx, 4.33, 0.12, 0.12, SRC_COL[k])
        text(s, xx + 0.17, 4.28, 0.9, 0.22, f"{nm} {int(cells.get(k, 0))}", size=8.5, color=MUTED)
    text(s, 0.5, 4.62, 5.6, 0.62, ["33 state series = 34 states/UTs: Jammu & Kashmir and Ladakh are combined (Ladakh reported separately only from Dec-2019).",
                                   "State-level source split is limited: CEA reports lignite plants as coal, and sparse series are allocated."],
         size=9, color=MUTED, spacing=2)
    # right panel
    pnl = rrect(s, 6.35, 1.0, 3.15, 4.2, CARD, radius=0.05)
    text(s, 6.55, 1.1, 2.8, 0.3, "BOTTOM-UP RECONCILIATION", size=10, font=HEAD, bold=True, color=MUTED)
    text(s, 6.55, 1.38, 2.8, 0.7, "0.827", size=40, font=HEAD, bold=True, color=RED)
    text(s, 6.55, 2.08, 2.8, 0.4, "overall hierarchical MASE (equal-weight mean across levels)", size=9, color=MUTED)
    rows = [("National", "0.710", "0.741", "small cost", DRED), ("Regions", "0.716", "0.671", "improved", AMB)]
    text(s, 6.55, 2.62, 2.8, 0.25, [[("Before → after reconciliation (MASE)", {"bold": True, "size": 9.5})]])
    for i, (nm, a, b, tag, col) in enumerate(rows):
        yy = 2.92 + i * 0.62
        text(s, 6.55, yy, 0.9, 0.5, nm, size=11, font=HEAD, bold=True, anchor=MSO_ANCHOR.MIDDLE)
        text(s, 7.42, yy - 0.05, 1.9, 0.36, [[(a, {"color": MUTED}), ("  →  ", {"color": MUTED}), (b, {"bold": True, "color": col})]], size=13,
             anchor=MSO_ANCHOR.MIDDLE)
        text(s, 7.42, yy + 0.3, 1.9, 0.22, tag, size=8.5, color=col)
    text(s, 6.55, 4.2, 2.8, 0.9, "Every forecast now adds up exactly: states → regions → national, and sources → national.",
         size=10, anchor=MSO_ANCHOR.MIDDLE)
    source(s, "Source: reports/hierarchical_reconciliation.md; outputs/backtesting/hier_metrics_A.csv; outputs/data/node_metadata.csv.")
    notes(s, """
WHAT TO SAY (≈65 s): We forecast at four linked levels: one national total, five grid regions, 33 state series and 73 state-by-source series. If each is forecast independently, states would not add up to their region, and regions would not add up to the nation.
RECONCILIATION: We compared bottom-up, top-down, middle-out and least-squares reconciliation. Bottom-up was selected: forecasts are made at the state-by-source level and summed upwards, so every level is consistent by construction. Its overall hierarchical MASE is 0.827.
TRADE-OFF: Nationally the error rises slightly - from 0.710 before reconciliation to 0.741 after - but regional accuracy improves from 0.716 to 0.671. We accept that small national cost for a fully consistent picture.
COUNTING NOTE: 33 state series represent 34 states and UTs because Jammu & Kashmir and Ladakh are combined for continuity. Source splits at state level are limited because CEA reports lignite plants as coal.
TRANSITION: Short-term forecasts are validated for 12 months. For 2047 we move to scenarios.
LIKELY QUESTIONS: "Why not MinT/optimal reconciliation?" - Least-squares variants (OLS, WLS) broke down on very small series; bottom-up was most robust. "Which unreconciled forecast is better?" - The unreconciled national ETS is kept in the dashboard for comparison.
""")

    # ============================================================ 9 SCENARIOS (template slide 25: three big circles)
    s = S[8]
    ov = [i for i, sh in enumerate(s.shapes) if sh.shape_type == 1]
    strip(s, keep=ov)
    set_title(s, "Three Possible Pathways for India's Conventional Energy Generation in 2047", size=21)
    big = sorted([sh for sh in s.shapes if sh.shape_type == 1], key=lambda z: z.left)
    sc = [("LOW", Y, 1564, 1248, 1970, "0.7%", "−1.5%", 1.65), ("CENTRAL", RED, 2352, 1863, 2968, "3.5%", "0%", 1.95),
          ("HIGH", AMB, 3690, 2944, 4624, "6.4%", "+2%", 1.65)]
    centers = [1.85, 5.0, 8.15]
    for o, (nm, col, med, p10, p90, g0, gt, d), cxx in zip(big, sc, centers):
        o.left, o.top, o.width, o.height = Inches(cxx - d / 2), Inches(0.98 + (1.95 - d) / 2), Inches(d), Inches(d)
        o.fill.solid()
        o.fill.fore_color.rgb = rgb(col)
        tc = K if col == Y else WHITE
        label_in(o, [[(nm, {"size": 12, "color": tc})], [(f"{med:,}", {"size": 32 if nm == "CENTRAL" else 28, "color": tc})],
                     [("TWh · median (P50)", {"size": 9, "font": BODY, "bold": False, "color": tc})]])
        text(s, cxx - 1.45, 3.0, 2.9, 0.26, [[("P10–P90  ", {"color": MUTED}), (f"{p10:,} – {p90:,} TWh", {"bold": True})]], size=10.5, align=PP_ALIGN.CENTER)
        text(s, cxx - 1.45, 3.26, 2.9, 0.26, [[("growth  ", {"color": MUTED}), (f"{g0} → {gt}", {"bold": True}), (" by FY2046-47", {"color": MUTED})]],
             size=10, align=PP_ALIGN.CENTER)
    tag = rrect(s, 4.25, 0.86, 1.5, 0.26, K, radius=0.4)
    label_in(tag, "PLANNING BASELINE", size=9, color=Y)
    # common-scale range chart
    ax0, ax1, v0, v1 = 1.2, 9.3, 1000, 5000
    X = lambda v: ax0 + (ax1 - ax0) * (v - v0) / (v1 - v0)  # noqa: E731
    yax = 4.45
    line(s, ax0, yax, ax1, yax, color=G3, w=1)
    for v in range(1000, 5001, 1000):
        line(s, X(v), yax, X(v), yax + 0.06, color=G3, w=1)
        text(s, X(v) - 0.35, yax + 0.07, 0.7, 0.2, f"{v:,}", size=8, color=MUTED, align=PP_ALIGN.CENTER)
    text(s, 0.35, yax - 0.42, 0.85, 0.4, "FY2046-47 range (TWh)", size=8, color=MUTED, align=PP_ALIGN.RIGHT)
    for i, (nm, col, med, p10, p90, *_r) in enumerate(sc):
        yy = 3.7 + i * 0.22
        shape(s, MSO_SHAPE.RECTANGLE, X(p10), yy, X(p90) - X(p10), 0.12, col)
        circle(s, X(med) - 0.08, yy - 0.02, 0.16, K)
        text(s, X(p90) + 0.06, yy - 0.05, 0.8, 0.2, nm.title(), size=8, color=MUTED)
    disc = rrect(s, 0.5, 4.78, 9.0, 0.48, TINT_R, radius=0.15)
    text(s, 0.65, 4.8, 8.7, 0.44, [[("Assumption-driven scenarios, not predictions. ", {"bold": True, "color": RED}),
                                    ("Domestic conventional generation only. Not total energy requirement, and excludes renewables. Bands come from 5,000 simulated growth paths per scenario.", {})]],
         size=9.5, anchor=MSO_ANCHOR.MIDDLE)
    source(s, "Source: outputs/scenarios/fy_scenarios_national.csv; outputs/scenarios/scenario_assumptions.json; reports/forecast_uncertainty.md.")
    notes(s, """
WHAT TO SAY (≈80 s - key slide): Monthly models are validated only 12 months ahead, so 2047 is presented as three assumption-driven pathways, not as predictions.
HOW THEY ARE BUILT: Each scenario starts from a growth rate we actually observed and moves linearly to an assumed growth rate by FY2046-47. Low starts at 0.7% (the recent FY2023-24 to FY2025-26 slowdown) and ends at minus 1.5%. Central starts at 3.5% (the full FY2019-20 to FY2025-26 trend) and ends at 0%, a plateau. High starts at 6.4% (the post-COVID expansion) and ends at plus 2%. The launch point is our reconciled statistical forecast for FY2027-28.
RESULTS: Median 2047 conventional generation is 1,564 TWh (low), 2,352 TWh (central - our planning baseline) and 3,690 TWh (high). The P10-P90 bands come from 5,000 simulated paths with year-to-year shocks sized from history: 1,863 to 2,968 TWh for central.
READ THE BOTTOM CHART: On one common scale, the gap between scenarios is larger than any single band - the long-run assumption matters more than model precision.
CAVEAT: These are domestic conventional generation only - not total energy requirement, and not including renewables.
TRANSITION: Nationally that is the range; regionally the picture is very different.
LIKELY QUESTIONS: "Why should conventional growth go to zero?" - It is a stated assumption (plateau), not an estimate; the low and high cases bracket it. "Why not use population or GDP?" - Only six overlapping years, partly imputed values and no authorised projections to 2047.
""")

    # ============================================================ 10 REGIONAL (template slide 18: map + callouts)
    s = S[9]
    strip(s)
    set_title(s, "India Is Not One Energy Region: Five Regions, Different Priorities", size=21)
    rc = {"Northern": G1, "Western": RED, "Eastern": DRED, "North Eastern": AMB, "Southern": Y}
    n_ = shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 1.2, 1.0, 2.15, 1.05, rc["Northern"]); n_.adjustments[0] = 0.18
    label_in(n_, [[("NORTHERN", {"size": 12})], [("24.9%", {"size": 10, "font": BODY})]], color=K)
    w_ = shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 0.55, 2.12, 1.95, 1.15, rc["Western"]); w_.adjustments[0] = 0.18
    label_in(w_, [[("WESTERN", {"size": 12})], [("36.0%", {"size": 10, "font": BODY})]])
    e_ = shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 2.58, 2.12, 1.35, 1.0, rc["Eastern"]); e_.adjustments[0] = 0.18
    label_in(e_, [[("EASTERN", {"size": 12})], [("17.7%", {"size": 10, "font": BODY})]])
    ne = shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 3.55, 1.38, 0.95, 0.62, rc["North Eastern"]); ne.adjustments[0] = 0.25
    label_in(ne, [[("N-EASTERN", {"size": 9})], [("1.3%", {"size": 9, "font": BODY})]])
    so = shape(s, MSO_SHAPE.FLOWCHART_MERGE, 0.95, 3.37, 2.5, 1.45, rc["Southern"])
    text(s, 1.45, 3.62, 1.5, 0.5, [[("SOUTHERN", {"size": 12, "bold": True, "font": HEAD})], [("20.1%", {"size": 10, "bold": True})]],
         align=PP_ALIGN.CENTER)
    text(s, 0.5, 4.9, 4.2, 0.4, "Schematic grid-region layout (not to scale) · % = share of national conventional generation, FY2025-26",
         size=8, color=MUTED)
    cards = [("Western", "thermal", "Largest contributor", "≈36% of national conventional generation; ≈91% coal & lignite."),
             ("Eastern", "coal", "Fastest growth", "≈5.5% a year (FY2019-20 → FY2025-26); ≈95% coal & lignite."),
             ("North Eastern", "gas", "Most diversified mix", "≈40% large hydro and ≈39% natural gas."),
             ("Southern", "nuclear", "Highest nuclear share", "≈7% nuclear; 14% large hydro."),
             ("Northern", "hydro", "Hydro-strong", "large hydro ≈22% of regional generation.")]
    for i, (rg, ic, hd, body) in enumerate(cards):
        yy = 1.0 + i * 0.8
        c = rrect(s, 4.85, yy, 4.65, 0.72, CARD, radius=0.1)
        icon_circle(s, ic, 4.95, yy + 0.08, 0.56, rc[rg], variant="d" if rc[rg] in (Y, G1) else "w")
        text(s, 5.65, yy + 0.06, 3.8, 0.62, [[(rg.upper() + "  ·  ", {"bold": True, "size": 10.5, "color": MUTED, "font": HEAD}),
                                               (hd, {"bold": True, "size": 12, "font": HEAD})], [(body, {"size": 9.5})]], anchor=MSO_ANCHOR.MIDDLE)
    source(s, "Source: outputs/strategy/regional_summary.csv (FY2025-26 mix from state x source actuals). Generation characteristics only - not demand or resource potential.")
    notes(s, """
WHAT TO SAY (≈70 s): India's conventional generation is not one system. The schematic map shows each grid region's share of national conventional generation in FY2025-26.
WESTERN is the largest contributor - about 36% - and about 91% of its conventional output is coal and lignite.
EASTERN grew fastest, about 5.5% a year, but about 95% of its conventional mix is coal and lignite - a concentration risk.
NORTH EASTERN is small (1.3%) but the most diversified: about 40% large hydro and 39% natural gas.
SOUTHERN has the highest nuclear share, about 7%.
NORTHERN gets about 22% of its conventional generation from large hydro.
STRATEGY IMPLICATION: The same national target means different actions per region - protecting hydro against dry years in the North and North-East, retaining nuclear baseload in the South, and managing coal concentration in the East and West.
IMPORTANT CAVEAT: These describe where generation happens and with which sources - not electricity demand and not resource potential.
TRANSITION: How should the conventional mix evolve to 2047?
LIKELY QUESTIONS: "Why a schematic, not a real map?" - We only use authorised data; the layout shows CEA regions without importing an external boundary dataset. "Do regions trade power?" - Yes; generation location is not consumption, which is why we never call these regional requirements.
""")

    # ============================================================ 11 ENERGY MIX (template slide 30: two sides + donut)
    s = S[10]
    strip(s)
    set_title(s, "From Forecasting to Strategic Planning")
    text(s, 0.5, 0.95, 3.0, 0.3, "GAS SENSITIVITY - TREND REFERENCE", size=10, font=HEAD, bold=True, color=MUTED)
    tv = [("T1", "Original trend-based approach", "gas share falls to 0.11% - an artefact", G3, False),
          ("T2", "Hold FY2025-26 shares constant", "gas share 1.70%", G1, False),
          ("T3", "Stabilise gas at post-2022 avg.", "gas 1.87% · recommended baseline", RED, True)]
    for i, (t_, hd, sub, col, rec) in enumerate(tv):
        yy = 1.3 + i * 0.78
        c = rrect(s, 0.5, yy, 3.0, 0.68, TINT_R if rec else CARD, radius=0.1, line=RED if rec else None, lw=1.25)
        b = circle(s, 0.6, yy + 0.12, 0.44, col)
        label_in(b, t_, size=12)
        text(s, 1.15, yy + 0.06, 2.3, 0.58, [[(hd, {"bold": True, "size": 10})], [(sub, {"size": 9, "color": RED if rec else MUTED})]], anchor=MSO_ANCHOR.MIDDLE)
    # centre: before / after doughnuts (native charts)
    def donut(x, y, val, colr, lab, sub):
        cdd = CategoryChartData()
        cdd.categories = ["Coal + lignite", "Other conventional"]
        cdd.add_series("share", [val, 100 - val])
        g = s.shapes.add_chart(XL_CHART_TYPE.DOUGHNUT, Inches(x), Inches(y), Inches(1.55), Inches(1.55), cdd)
        c = g.chart
        c.has_legend = False
        c.has_title = False
        pl_ = c.plots[0]
        for j, cc in enumerate([colr, G2]):
            p_ = pl_.series[0].points[j]
            p_.format.fill.solid()
            p_.format.fill.fore_color.rgb = rgb(cc)
        hole = pl_._element.find(qn("c:holeSize"))
        if hole is None:
            hole = pl_._element.makeelement(qn("c:holeSize"), {})
            pl_._element.append(hole)
        hole.set("val", "68")
        text(s, x, y + 0.5, 1.55, 0.55, [[(f"{val:.1f}%", {"size": 17, "bold": True, "font": HEAD})], [("coal + lignite", {"size": 8, "color": MUTED})]],
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        text(s, x - 0.2, y + 1.58, 1.95, 0.42, [[(lab, {"bold": True, "size": 10.5})], [(sub, {"size": 8.5, "color": MUTED})]], align=PP_ALIGN.CENTER)
    donut(3.75, 1.25, 83.7, DRED, "P0 · today's mix", "FY2025-26 shares held")
    a = shape(s, MSO_SHAPE.RIGHT_ARROW, 5.36, 1.85, 0.36, 0.34, AMB)
    donut(5.78, 1.25, 79.6, RED, "P2 · preferred direction", "best historical shares")
    text(s, 3.7, 3.35, 3.7, 0.5, "Same 2047 conventional total (central, 2,352 TWh) allocated differently; no source percentage is invented.",
         size=9, color=MUTED, align=PP_ALIGN.CENTER)
    # right: policy table as bars
    text(s, 7.6, 0.95, 1.95, 0.3, "POLICY SCENARIOS", size=10, font=HEAD, bold=True, color=MUTED)
    text(s, 7.6, 1.18, 1.95, 0.25, "coal + lignite share, 2047", size=8.5, color=MUTED)
    pol = [("P0", "Maintain FY2025-26 mix", 83.7), ("P1", "Seven-year average mix", 82.9), ("P2", "Best historical hydro / nuclear / gas shares", 79.6),
           ("P3", "No source below its best historical output", 83.3)]
    for i, (pp, nm, v) in enumerate(pol):
        yy = 1.45 + i * 0.68
        rec = pp == "P2"
        text(s, 7.6, yy, 1.95, 0.36, [[(pp + " ", {"bold": True, "color": RED if rec else K}), (nm, {"size": 8.5, "color": MUTED})]], size=10)
        wv = 1.35 * (v - 75) / 10
        shape(s, MSO_SHAPE.RECTANGLE, 7.6, yy + 0.4, wv, 0.15, RED if rec else G1)
        text(s, 7.66 + wv, yy + 0.35, 0.6, 0.25, f"{v:.1f}%", size=9.5, bold=True, color=RED if rec else K)
    text(s, 7.6, 4.06, 1.95, 0.2, "bar axis starts at 75%", size=7.5, color=MUTED)
    disc = rrect(s, 0.5, 4.3, 9.0, 0.92, CARD, radius=0.08)
    text(s, 0.7, 4.34, 8.6, 0.85, [[("Policy scenarios are recommendations, not statistical forecasts. ", {"bold": True, "color": RED}),
                                    ("P2 is grounded in shares the existing system has already achieved (FY2019-20 – FY2025-26). It is ", {}),
                                    ("not", {"bold": True}), (" a least-cost or optimised plan: no cost, grid-constraint or resource-potential optimisation was performed. ", {}),
                                    ("Solar and wind are not quantified because their actual generation data was unavailable.", {"bold": True})]],
         size=9.5, anchor=MSO_ANCHOR.MIDDLE)
    source(s, "Source: reports/energy_mix_strategy.md; outputs/strategy/source_mix_scenarios.csv; outputs/strategy/source_trend_diagnostics.csv.")
    notes(s, """
WHAT TO SAY (≈70 s): The strategy layer has two parts that we keep strictly separate.
FIRST - the trend reference. Extrapolating source shares exposed an artefact: natural gas fell from 4.2% to 1.7% between FY2020-21 and FY2022-23 - a one-off step - and has been flat since. A straight trend (T1) keeps extending that step and drives gas to 0.11% by 2047. T2 simply holds today's shares. T3 stabilises gas at its post-2022 average of 1.87%; we recommend T3 as the planning baseline because it does not extrapolate an unusual decline forever.
SECOND - policy scenarios, which are recommendations, not forecasts. They allocate the same conventional total differently. P0 keeps today's mix (83.7% coal and lignite), P1 uses the seven-year average (82.9%), P3 guarantees no source falls below its best historical output (83.3%). P2 sets hydro, nuclear and gas at the best shares the existing system has already achieved, which lowers coal-plus-lignite to 79.6%. We recommend P2 as the preferred direction.
BE CLEAR: P2 is grounded in history, not optimised - no cost, grid or resource-potential modelling was done, and solar and wind are not quantified.
TRANSITION: How can decision-makers use all of this?
LIKELY QUESTIONS: "Is 79.6% achievable?" - Every share in P2 has already occurred in FY2019-20 to FY2025-26; feasibility in TWh terms needs capacity and cost studies outside our authorised data. "Where are renewables?" - They would come on top of, or substitute for, conventional generation; they can be added once authorised generation data exists.
""")

    # ============================================================ 12 DASHBOARD & CONCLUSION (template slide 28)
    s = S[11]
    ovs = [i for i, sh in enumerate(s.shapes) if sh.shape_type == 1]
    strip(s, keep=ovs)
    set_title(s, "A Decision-Support Framework for India's Energy Future")
    nums = sorted([sh for sh in s.shapes if sh.shape_type == 1], key=lambda z: z.top)
    concl = [("Data → framework", "Historical generation data can support a structured, validated forecasting framework."),
             ("Regions matter", "Regional differences require region-specific planning."),
             ("Transparency", "Transparent assumptions and uncertainty are essential for long-term energy strategy.")]
    for i, (o, (hd, body), col) in enumerate(zip(nums, concl, [Y, AMB, RED])):
        yy = 1.02 + i * 0.86
        o.left, o.top, o.width, o.height = Inches(0.5), Inches(yy), Inches(0.68), Inches(0.68)
        o.fill.solid()
        o.fill.fore_color.rgb = rgb(col)
        tf = o.text_frame
        for r in tf.paragraphs[0].runs:
            r.font.name, r.font.size, r.font.bold = HEAD, Pt(18), True
            r.font.color.rgb = rgb(K if col == Y else WHITE)
        text(s, 1.32, yy - 0.01, 3.6, 0.72, [[(hd, {"bold": True, "size": 13, "font": HEAD})], [(body, {"size": 10, "color": MUTED})]], anchor=MSO_ANCHOR.MIDDLE)
    # dashboard screenshot (real, cropped from the running app)
    im = Image.open(SHOTS / "01_executive.png")
    crop = im.crop((362, 50, 1540, 815))
    cp = TMP / "dash_crop.png"
    crop.save(cp)
    fr = rrect(s, 5.25, 0.98, 4.25, 2.82, WHITE, radius=0.03, line=G2, lw=1)
    pic = s.shapes.add_picture(str(cp), Inches(5.33), Inches(1.06), Inches(4.09), Inches(4.09 * crop.height / crop.width))
    pic.name = "Dashboard screenshot - Executive overview"
    text(s, 5.25, 3.88, 4.25, 0.48, [[("Interactive Streamlit dashboard · 9 pages", {"bold": True, "size": 10.5})],
                                      [("national & regional insights · state explorer · 2047 scenarios · energy-mix strategy · filters & CSV downloads", {"size": 8.5, "color": MUTED})]])
    text(s, 0.5, 3.75, 4.5, 0.5, [[("Run locally: ", {"bold": True}), ("streamlit run dashboard/app.py  →  http://localhost:8599", {"color": MUTED})]], size=9.5)
    q = rrect(s, 0.5, 4.42, 9.0, 0.82, K, radius=0.1)
    text(s, 0.7, 4.45, 6.0, 0.76, [[("From historical generation data to evidence-based regional strategies - building a transparent framework for India's conventional energy planning towards 2047.",
                                     {"italic": True})]], size=10.5, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 6.85, 4.45, 2.5, 0.76, [[("Thank You", {"color": Y, "size": 20}), ("  |  ", {"color": WHITE, "size": 16}), ("Questions?", {"color": WHITE, "size": 16})]],
         font=HEAD, bold=True, align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)
    source(s, "Screenshot: dashboard/app.py (Executive overview page), captured from the running app. All dashboard figures are read from saved project outputs.")
    notes(s, """
WHAT TO SAY (≈60 s): Everything we showed is packaged into an interactive Streamlit dashboard with nine pages: an executive overview, historical generation, national forecasts with uncertainty, regional analysis, a state explorer, energy sources, the 2047 strategy, model performance and an assumptions page. Every chart has filters and every table can be downloaded. It runs locally - "streamlit run dashboard/app.py" - and reads only our saved, validated outputs.
THREE MESSAGES: First, historical generation data, handled carefully, can support a structured and validated forecasting framework. Second, India's regions are very different, so planning must be region-specific. Third, for a horizon as long as 2047, transparent assumptions and uncertainty ranges matter more than a single number.
CLOSE: From historical generation data to evidence-based regional strategies - a transparent framework for India's conventional energy planning towards 2047. Thank you - we are happy to take questions.
LIKELY QUESTIONS: "What would you add next?" - Authorised actual generation data for solar and wind, so total production can be forecast with the same pipeline; then cost and grid constraints for optimised mixes. "Can it be updated?" - Yes; the pipeline is scripted end to end and re-runs when new monthly CEA reports are published.
""")

    prs.save(str(OUT))
    print("saved", OUT)


if __name__ == "__main__":
    build()
