"""Collectibles Financial Dashboard -- the entrypoint of a SEPARATE app.

Top tabs Income Statement, Balance Sheet, Cash Flow and SG&A. Income Statement
is the Drillable P&L's consolidated page, reused from streamlit_app.py (whose
shell and pages only render when called); the other three are placeholders.

The BU drill still works: this file registers its own home page plus the four
BU pages in its own st.navigation, and points streamlit_app.CONSOLIDATED and
streamlit_app.BU_PAGES at them, so the st.switch_page / st.page_link calls in
streamlit_app resolve to pages this entrypoint knows.

Local: streamlit run financial_app.py   (same .venv as streamlit_app.py)
"""
from __future__ import annotations

import streamlit as st

import bu
import streamlit_app as pnl

APP_TITLE = "Collectibles Financial Dashboard"
TABS = ["Income Statement", "Balance Sheet", "Cash Flow", "SG&A"]

BALANCE_SHEET_NOTION = "https://app.notion.com/p/3d76c07d730e812fad34c04a1b70e937"
SGA_NOTION = "https://app.notion.com/p/3f16c07d730e8125b03ad305ac5b6985"
CASH_FLOW_NOTION = "https://app.notion.com/p/80df73e54a2b4513b7aa0b1ea13ea317"
CASH_FLOW_LINKS: dict[str, str] = {
    "FCF Dashboard": "https://collectfanatics.sharepoint.com/:u:/r/sites/CollectiblesFinance/Corporate%20FPA/Cash%20%26%20Capex%20Dashboards/FCF%20Dashboard/FCF%20Dashboard.html?d=w5ba6f4ba10df4a42a16b5127e9f8c775&csf=1&web=1&e=rUOXBF",
    "Capex Dashboard": "https://collectfanatics.sharepoint.com/:u:/r/sites/CollectiblesFinance/Corporate%20FPA/Cash%20%26%20Capex%20Dashboards/Capex%20Dashboard/Capex%20Dashboard.html?csf=1&web=1",
    "Cash & Revolver Dashboard": "https://collectfanatics.sharepoint.com/:u:/r/sites/CollectiblesFinance/Corporate%20FPA/Cash%20%26%20Capex%20Dashboards/Cash%20and%20Revolver%20Dashboard/Cash%20and%20Revolver%20Dashboard.html?d=w01abe3375b6b4589a263bd76a3861b3e&csf=1&web=1&e=111WTY",
}

st.set_page_config(page_title=pnl._tab(APP_TITLE), layout="wide")


def home() -> None:
    st.title(pnl._drafted(APP_TITLE))
    income, balance, cash, sga = st.tabs(TABS)

    with income:
        pnl.render_shell()
        pnl.consolidated_page()

    with balance:
        st.info("Coming soon: Balance Sheet (Tara Petrucci)")
        st.markdown(f"[Balance Sheet notes (Notion)]({BALANCE_SHEET_NOTION})")

    with cash:
        st.info("Coming soon: Cash Flow (Afriti Rahim, Jack Braun)")
        st.markdown(f"[Cash Flow notes (Notion)]({CASH_FLOW_NOTION})")
        for label, url in CASH_FLOW_LINKS.items():
            st.markdown(f"- [{label}]({url})")

    with sga:
        st.info("Coming soon: SG&A report (Will Oswald)")
        st.markdown(f"[SG&A notes (Notion)]({SGA_NOTION})")


def _bu_wrapper(key: str):
    def page() -> None:
        pnl.render_shell()
        pnl.bu_page(key)
    page.__name__ = f"{key}_page"   # st.Page infers names from the callable
    return page


HOME = st.Page(home, title=pnl._tab(APP_TITLE), default=True)
BU_PAGES: dict[str, st.Page] = {
    key: st.Page(_bu_wrapper(key), title=pnl._tab(bu.subject(key)),
                 url_path=bu.URL_PATHS[key])
    for key in bu.BU_KEYS
} if bu.AVAILABLE else {}

# Before navigation runs: streamlit_app's switch_page / page_link targets.
pnl.CONSOLIDATED = HOME
pnl.BU_PAGES = BU_PAGES

st.navigation([HOME, *BU_PAGES.values()], position="hidden").run()
