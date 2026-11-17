"""Headless smoke + interaction test for dashboard/app.py (python dashboard/test_app.py)."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).with_name("app.py"))
PAGES = ["1 · Executive overview", "2 · Historical generation", "3 · National forecast", "4 · Regional analysis", "5 · State explorer",
         "6 · Energy sources", "7 · 2047 energy strategy", "8 · Model performance", "9 · Assumptions & limitations"]
results = []


def run_page(page, actions=()):
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    at.sidebar.radio(key="page").set_value(page).run()
    for kind, key, val in actions:
        getattr(at, kind)(key=key).set_value(val).run()
    ok = not at.exception
    results.append((page, [a[1] for a in actions], ok, len(at.get("plotly_chart")), len(at.get("download_button")),
                    [e.value for e in at.exception][:1]))
    return at


for p in PAGES:
    run_page(p)
run_page(PAGES[1], [("multiselect", "h_series", ["Coal", "Natural gas", "Bhutan import (separate)"]), ("selectbox", "h_seas", "HYDRO")])
run_page(PAGES[2], [("checkbox", "nf_un", False), ("multiselect", "nf_scen", ["central"])])
run_page(PAGES[3], [("multiselect", "r_sel", ["Eastern", "North Eastern"]), ("selectbox", "r_one", "North Eastern")])
for st_ in ["JAMMU AND KASHMIR + LADAKH", "LAKSHADWEEP", "GUJARAT", "UTTAR PRADESH"]:
    run_page(PAGES[4], [("selectbox", "s_state", st_)])
run_page(PAGES[4], [("selectbox", "s_grp", "C")])
run_page(PAGES[5], [("selectbox", "src_one", "NUCLEAR"), ("multiselect", "src_sel", ["NATURAL_GAS", "HYDRO"])])
run_page(PAGES[6], [("selectbox", "t_scn", "low"), ("selectbox", "p_scn", "high"), ("selectbox", "p_q", "p10"), ("selectbox", "rs_scn", "low"), ("selectbox", "sa_reg", "Southern")])
for lvl in ["States group C", "State x source (eligible)", "Bhutan import (separate)"]:
    run_page(PAGES[7], [("selectbox", "mp_lvl", lvl), ("radio", "mp_met", "WAPE_%")])

fails = [r for r in results if not r[2]]
for r in results:
    print(("OK  " if r[2] else "FAIL"), r[0], r[1], f"charts={r[3]} downloads={r[4]}", r[5] if not r[2] else "")
print(f"\n{len(results) - len(fails)}/{len(results)} runs passed")
