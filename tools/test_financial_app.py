"""Headless checks for financial_app.py (Collectibles Financial Dashboard).

1. `import streamlit_app` renders nothing and never calls data.load_master.
2. An AppTest run of financial_app.py raises nothing, shows the four top tabs
   in order, the draft header, the three SharePoint links under Cash Flow, and
   the SG&A tab's report table with its "Total SG&A (template)" row.
3. Each BU page (same url_paths as the Drillable P&L) runs without exception.

AppTest cannot click the custom-component drill; that needs a browser.

    .venv\\Scripts\\python.exe tools\\test_financial_app.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402
from streamlit.util import calc_hash  # noqa: E402

import bu  # noqa: E402

APP = ROOT / "financial_app.py"
TABS = ["Income Statement", "Balance Sheet", "Cash Flow", "SG&A"]
HEADER = "(DRAFT) Collectibles Financial Dashboard"
#: Copied from the request, independent of financial_app.py (importing that
#: file would run it).
SHAREPOINT = {
    "FCF Dashboard": "https://collectfanatics.sharepoint.com/:u:/r/sites/CollectiblesFinance/Corporate%20FPA/Cash%20%26%20Capex%20Dashboards/FCF%20Dashboard/FCF%20Dashboard.html?d=w5ba6f4ba10df4a42a16b5127e9f8c775&csf=1&web=1&e=rUOXBF",
    "Capex Dashboard": "https://collectfanatics.sharepoint.com/:u:/r/sites/CollectiblesFinance/Corporate%20FPA/Cash%20%26%20Capex%20Dashboards/Capex%20Dashboard/Capex%20Dashboard.html?csf=1&web=1",
    "Cash & Revolver Dashboard": "https://collectfanatics.sharepoint.com/:u:/r/sites/CollectiblesFinance/Corporate%20FPA/Cash%20%26%20Capex%20Dashboards/Cash%20and%20Revolver%20Dashboard/Cash%20and%20Revolver%20Dashboard.html?d=w01abe3375b6b4589a263bd76a3861b3e&csf=1&web=1&e=111WTY",
}

IMPORT_PROBE = """
import data
calls = []
_orig = data.load_master
data.load_master = lambda *a, **k: (calls.append(1), _orig(*a, **k))[1]
import streamlit_app
print("load_master calls during import:", len(calls))
print("cube global after import:", hasattr(streamlit_app, "cube"))
raise SystemExit(1 if calls or hasattr(streamlit_app, "cube") else 0)
"""


def main() -> None:
    problems: list[str] = []

    probe = subprocess.run([sys.executable, "-c", IMPORT_PROBE], cwd=ROOT,
                           capture_output=True, text=True)
    print(probe.stdout.strip())
    if probe.returncode:
        problems.append(f"import streamlit_app is not side-effect free: {probe.stderr[-500:]}")

    at = AppTest.from_file(str(APP), default_timeout=180).run()
    if at.exception:
        problems.append("home: " + "; ".join(str(e.value) for e in at.exception))
    # at.tabs walks depth-first: the consolidated page's own two tabs sit
    # inside Income Statement, between it and Balance Sheet.
    inner_labels = ["Forecast Table", "Historical Trends"]
    by_label = {t.label: t for t in at.tabs}
    labels = [t.label for t in at.tabs if t.label not in inner_labels]
    print("top tabs:", labels)
    if labels != TABS:
        problems.append(f"top tabs {labels} != {TABS}")
    titles = [t.value for t in at.title]
    print("header:", titles)
    if HEADER not in titles:
        problems.append(f"header {HEADER!r} missing")

    cash_md = " ".join(m.value for m in by_label["Cash Flow"].markdown)
    for label, url in SHAREPOINT.items():
        ok = f"[{label}]({url})" in cash_md
        print(f"cash flow link {label!r}: {'ok' if ok else 'MISSING'}")
        if not ok:
            problems.append(f"Cash Flow link {label} missing")
    for tab, who in [("Balance Sheet", "Tara Petrucci"),
                     ("Cash Flow", "Afriti Rahim, Jack Braun")]:
        if not any(who in x.value for x in by_label[tab].info):
            problems.append(f"tab {tab}: info with {who!r} missing")
    # SG&A tab: the report table renders with its total row.
    sga_tables = by_label["SG&A"].dataframe
    sga_rows = list(sga_tables[0].value.index) if sga_tables else []
    has_total = "Total SG&A (template)" in sga_rows
    print(f"SG&A tab rows: {len(sga_rows)}, 'Total SG&A (template)' shown: {has_total}")
    if not has_total:
        problems.append("SG&A tab: 'Total SG&A (template)' row missing")
    if not any("Will Oswald" in s.value for s in by_label["SG&A"].subheader):
        problems.append("SG&A tab: header with 'Will Oswald' missing")
    inner = [t.label for t in by_label["Income Statement"].tabs
             if t.label != "Income Statement"]
    print("Income Statement inner tabs:", inner)
    if inner != inner_labels:
        problems.append(f"consolidated page tabs missing: {inner}")
    # One title only: render_shell(title=None) drops the old app's <h1>.
    income_md = " ".join(m.value for m in by_label["Income Statement"].markdown)
    old_title = "Collectibles Forecast Dashboard" in income_md
    print(f"Income Statement has old title: {old_title}")
    if old_title:
        problems.append("Income Statement tab still shows 'Collectibles Forecast Dashboard'")

    for key in bu.BU_KEYS if bu.AVAILABLE else []:
        at._page_hash = calc_hash(bu.URL_PATHS[key])
        at.run()
        err = "; ".join(str(e.value) for e in at.exception)
        print(f"BU page {key}: {err or 'ok'}")
        if err:
            problems.append(f"BU {key}: {err}")
        md = " ".join(m.value for m in at.markdown)
        has_new = "<h1>" in md and "Collectibles Financial Dashboard</h1>" in md
        print(f"BU page {key} header 'Collectibles Financial Dashboard': {has_new}")
        if not has_new or "Collectibles Forecast Dashboard" in md:
            problems.append(f"BU {key}: header is not 'Collectibles Financial Dashboard'")

    # The shell renders inside pages here, not in the entrypoint, so the
    # Forecast / vs. widget keys drop on a page switch; FC_SHADOW / COMP_SHADOW
    # in streamlit_app.py put them back. The pick must survive the drill.
    if bu.AVAILABLE:
        at._page_hash = ""
        at.run()
        pick = at.selectbox(key="fc_sel").options[1]
        at.selectbox(key="fc_sel").set_value(pick).run()
        comp_pick = at.selectbox(key="comp_sel").value
        at._page_hash = calc_hash(bu.URL_PATHS[bu.BU_KEYS[0]])
        at.run()
        on_bu = (at.selectbox(key="fc_sel").value, at.selectbox(key="comp_sel").value)
        at._page_hash = ""
        at.run()
        back = (at.selectbox(key="fc_sel").value, at.selectbox(key="comp_sel").value)
        print(f"forecast carry-over: picked {(pick, comp_pick)!r} -> BU {on_bu!r} "
              f"-> home {back!r}")
        if not (on_bu == back == (pick, comp_pick)):
            problems.append("Forecast / vs. selection does not survive the BU drill")

    # Two sessions, two picks: each keeps its own. AppTest runs sessions one
    # after another in this thread, so this shows isolation of state, not a
    # true race; the race is closed by financial_app.py loading a fresh
    # streamlit_app per run, never one shared module (checked below).
    a = AppTest.from_file(str(APP), default_timeout=180).run()
    b = AppTest.from_file(str(APP), default_timeout=180).run()
    opts = a.selectbox(key="fc_sel").options
    a.selectbox(key="fc_sel").set_value(opts[1]).run()
    b.selectbox(key="fc_sel").set_value(opts[2]).run()
    a.run()
    got = (a.selectbox(key="fc_sel").value, b.selectbox(key="fc_sel").value)
    print(f"two sessions: A={got[0]!r} B={got[1]!r} (picked {opts[1]!r}, {opts[2]!r})")
    if got != (opts[1], opts[2]):
        problems.append(f"two sessions do not keep separate picks: {got}")
    shared = [m for m in ("streamlit_app", "streamlit_app_fin") if m in sys.modules]
    print(f"shared streamlit_app module in sys.modules: {shared or 'none'}")
    if shared:
        problems.append(f"financial_app.py left a shared module: {shared}")

    if problems:
        print("\nPROBLEMS:", *problems, sep="\n  ")
        raise SystemExit(1)
    print("\nOK -- financial_app.py")


if __name__ == "__main__":
    main()
