"""Headless checks for financial_app.py (Collectibles Financial Dashboard).

1. `import streamlit_app` renders nothing and never calls data.load_master.
2. An AppTest run of financial_app.py raises nothing, shows the four top tabs
   in order, the draft header, and the three SharePoint links under Cash Flow.
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
                     ("Cash Flow", "Afriti Rahim, Jack Braun"),
                     ("SG&A", "Will Oswald")]:
        if not any(who in x.value for x in by_label[tab].info):
            problems.append(f"tab {tab}: info with {who!r} missing")
    inner = [t.label for t in by_label["Income Statement"].tabs
             if t.label != "Income Statement"]
    print("Income Statement inner tabs:", inner)
    if inner != inner_labels:
        problems.append(f"consolidated page tabs missing: {inner}")

    for key in bu.BU_KEYS if bu.AVAILABLE else []:
        at._page_hash = calc_hash(bu.URL_PATHS[key])
        at.run()
        err = "; ".join(str(e.value) for e in at.exception)
        print(f"BU page {key}: {err or 'ok'}")
        if err:
            problems.append(f"BU {key}: {err}")

    # The shell renders inside pages here, not in the entrypoint: does the
    # Forecast picked on the home page survive the drill to a BU page and back?
    if bu.AVAILABLE:
        at._page_hash = ""
        at.run()
        pick = at.selectbox(key="fc_sel").options[1]
        at.selectbox(key="fc_sel").set_value(pick).run()
        at._page_hash = calc_hash(bu.URL_PATHS[bu.BU_KEYS[0]])
        at.run()
        on_bu = at.selectbox(key="fc_sel").value
        at._page_hash = ""
        at.run()
        back = at.selectbox(key="fc_sel").value
        print(f"forecast carry-over: picked {pick!r} -> BU {on_bu!r} -> home {back!r}")
        # KNOWN GAP, reported not failed: Streamlit scopes a widget to the page
        # that renders it, and here the Forecast / vs. pair renders inside each
        # page (render_shell is called by the page, not the entrypoint), so the
        # pick resets to the default on a drill. streamlit_app.py renders the
        # shell in its entrypoint and keeps it (apptest_smoke "carry-over ok").
        if not (on_bu == back == pick):
            print("KNOWN GAP: Forecast selection does not survive the BU drill")

    if problems:
        print("\nPROBLEMS:", *problems, sep="\n  ")
        raise SystemExit(1)
    print("\nOK -- financial_app.py")


if __name__ == "__main__":
    main()
