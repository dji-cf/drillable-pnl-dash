"""Collectibles Consolidated Financials Dashboard -- the entrypoint of a SEPARATE app.

Top tabs Income Statement, Balance Sheet and Cash Flow. Income Statement has
sub-tabs Consolidated P&L (the Drillable P&L's consolidated page, reused from
streamlit_app.py, whose shell and pages only render when called) and SG&A
Detail (sga.py); the other two top tabs are placeholders.

The BU drill still works: this file registers its own home page plus the four
BU pages in its own st.navigation, and points streamlit_app.CONSOLIDATED and
streamlit_app.BU_PAGES at them, so the st.switch_page / st.page_link calls in
streamlit_app resolve to pages this entrypoint knows.

Local: streamlit run financial_app.py   (same .venv as streamlit_app.py)
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import streamlit as st

import bu
import data

# A fresh copy of streamlit_app for every script run, NOT a plain import: an
# imported module is one object shared by every browser session on the server,
# and render_shell() writes the globals its pages read (cube, forecast, comp,
# ...), so two users at the same time would read each other's picks. Not named
# "__main__" (its own entrypoint block must not run) and not put in sys.modules.
_spec = importlib.util.spec_from_file_location(
    "streamlit_app_fin", Path(__file__).with_name("streamlit_app.py"))
pnl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pnl)

APP_TITLE = "Collectibles Consolidated Financials Dashboard"
TABS = ["Income Statement", "Balance Sheet", "Cash Flow"]
INCOME_TABS = ["Consolidated P&L", "SG&A Detail"]

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
    income, balance, cash = st.tabs(TABS)

    with income:
        consolidated, sga = st.tabs(INCOME_TABS)
        with consolidated:
            pnl.render_shell(title=None)    # the st.title above is the one title
            pnl.consolidated_page()
        with sga:
            import sga as sga_tab           # SG&A Detail: Will Oswald's template
            st.subheader("SG&A report (Will Oswald)")
            sga_tab.render()
            st.markdown(f"[SG&A notes (Notion)]({SGA_NOTION})")

    with balance:
        st.info("Coming soon: Balance Sheet (Tara Petrucci)")
        st.markdown(f"[Balance Sheet notes (Notion)]({BALANCE_SHEET_NOTION})")

    with cash:
        st.info("Cash Flow (draft) (Afriti Rahim, Jack Braun)")
        _cash_ebitda_tile()
        st.markdown(f"[Cash Flow notes (Notion)]({CASH_FLOW_NOTION})")
        for label, url in CASH_FLOW_LINKS.items():
            st.markdown(f"- [{label}]({url})")


EBITDA_ROWS: list[tuple[str, str, int]] = [
    ("Collectibles ex Other (LB_310) EBITDA", "lb310", 1),
    ("less Fanatics Live (LB_306)", "live", -1),
    ("less Collect / Marketplace (LB_307)", "collect", -1),
    ("less Trading Card Games (LB_308)", "tcg", -1),
    ("TCG cost center CC_70123 (carve-out)", "tcg_cc", 1),
    ("carve out Key Litigation and Regulatory (CC_40313 / AC_61002)", "pisa", 1),
    ("= Adjusted EBITDA ex Emerging Services", "adj_ebitda_ex_es", 1),
]


def _cash_ebitda_tile() -> None:
    """Afriti's FY26 Adjusted EBITDA ex Emerging Services (not ACX_EBITDA)."""
    try:
        row = data.load_adj_ebitda_ex_es("SEP26RF", "FY26").iloc[0]
    except Exception as e:
        st.warning(f"Adjusted EBITDA ex Emerging Services could not load: {e}")
        return
    total = float(row["adj_ebitda_ex_es"]) / 1e6
    st.metric("Adjusted EBITDA ex Emerging Services - FY26 (Sep 2026 forecast, SEP26RF)",
              f"${total:,.1f}M")
    st.table(pd.DataFrame({
        "Line": [label for label, _, _ in EBITDA_ROWS],
        "$M": [f"{sign * float(row[col]) / 1e6:,.1f}" for _, col, sign in EBITDA_ROWS],
    }).set_index("Line"))
    st.caption("Recipe from Afriti Rahim (FP&A), 2026-11-02. Source: "
               "ORACLE_DATA_PROD.FCT_EPM.CARDPLN_PL_BY_LOB_STG. Not ACX_EBITDA.")


def _bu_wrapper(key: str):
    def page() -> None:
        pnl.render_shell(title=APP_TITLE)   # the header's tag adds "(DRAFT)"
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
