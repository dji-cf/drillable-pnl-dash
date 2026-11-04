"""SG&A tab of the Collectibles Financial Dashboard (Will Oswald's template).

One read-only SELECT on CARDPLN_PL_BY_LOB_STG, then a pandas join to Will's
mapping (reference/sga_mapping.csv, from his `SGA Template Mapping.xlsx`,
2026-10-14). Nothing is renamed or re-mapped here:

- accounts not in Will's file go to ONE line, "Not mapped" (the `_Other`
  parents and AC_61627 wait for Will);
- AC_61002 @ CC_40313 (Pisa) is "Key Litigation and Regulatory" (Will Oswald,
  2026-10-29; Maya yes 2026-11-03), shown BELOW the total;
- the check row = Oracle total (AC_50000 @ CC_30000) - template total - Key
  Litigation, and should be 0;
- lines follow Will's template (sheet "NASE Total", column M, rows 13-73 of
  `SG&A Consolidated - 2027 Bud (1st Sub).xlsx`) with its 6 subtotals.

SG&A rule (docs/fleet/cfd-sga-retie.md 1.1, LIKELY -- Vivek has not
confirmed): AC_60000..AC_62999 at cost centers outside CC_1xxxx, CC_30000 and
Total Cost Center, without the parents AC_60500 / AC_60597.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

import data
import queries

MAPPING_CSV = Path(__file__).with_name("reference") / "sga_mapping.csv"

SCENARIOS = ("SEP26RF", "2027B-09.28")
DEFAULT_LOB, DEFAULT_SCENARIO, DEFAULT_YEAR = "LB_302", "SEP26RF", "FY26"
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
FY = "FY total"

NOT_MAPPED = "Not mapped"
TOTAL = "Total SG&A (template)"
KEY_LIT = "Key Litigation and Regulatory"
CHECK = "Check vs Oracle total (AC_50000 @ CC_30000)"
KEY_LIT_ACCOUNT, KEY_LIT_CC = "AC_61002", "CC_40313"
TOTAL_ACCOUNT, TOTAL_CC = "AC_50000", "CC_30000"
PARENTS = ("AC_60500", "AC_60597")

#: Will's 52 lines in template order (LINE_ORDER in sga_mapping.csv = position).
TEMPLATE_ORDER = (
    "Salaries - Base Salaries", "Severance", "Bonus Expense", "Benefits",
    "Allocated Compensation", "Legal & Litigation", "Audit", "Tax Services",
    "Recruiting & Relocation", "Accounting (Oracle consultants)",
    "Marketing Consultants", "Computer/Tech - Outside services/Consulting Fees",
    "Outside Services (Temp Labor)", "Other Professional Services",
    "Meals (indiv)", "Entertainment (Client)", "Aviation (private jet)",
    "Trade Shows & Seminar attendance (tickets)", "Travel (air, hotel, taxi)",
    "Telephone & Cell phone reimbursement",
    "Rent (co-working space fees, office parking)",
    "Rent/Lease - Allocations IN from FHI/Commerce/FBG",
    "Lease Expense (formal lease amort, sublease income)",
    "Repairs and Maintenance", "Utilities", "Office Supplies", "Marketing",
    "Computer/Tech - Other", "Computer/Tech - Equipment",
    "Computer/Tech - Software Licenses & Maintenance",
    "Tech - Allocations IN from FHI/Commerce/FBG", "Insurance",
    "Insurance - Allocations IN from FHI/Commerce/FBG", "Licenses and Taxes",
    "Banking Fees", "Internet Commissions (Amazon, Walmart)", "Foreign Exchange",
    "Research & Development (incl Collect Credit)", "Donations",
    "Special Events (Athlete signings, holiday parties)",
    "Employee Relations (staff events, staff gifts, staff entertain)",
    "Bad Debt", "Postage", "Dues & Subscriptions",
    "Rev Share (MLB, other licenses)",
    "Rev Share - guarantee (NBA & NFL Settlement)", "Player Bonus",
    "Misc Contract Costs (Athlete 360 Deals Shortfall)",
    "Contract Costs (license rights signing bonus amort)",
    "Intercompany Service Charge",
    "Other SG&A - Allocations IN from FHI/Commerce/FBG", "Other/Miscellaneous",
)
#: Template subtotals: (name, first LINE_ORDER, last LINE_ORDER), shown after
#: the last line. Marketing (27) has none.
SUBTOTALS = (
    ("Total Compensation", 1, 5),
    ("Total Professional Services and Outside Services", 6, 14),
    ("Total Travel and Entertainment", 15, 20),
    ("Total Rent and Office", 21, 26),
    ("Total Technology", 28, 31),
    ("Total Other/Miscellaneous", 32, 52),
)
#: Display-only partial subtotal inside Total Compensation (template r17,
#: =SUM(N13:N16); Maya yes 2026-11-04). Not part of SUBTOTALS or any total.
PRE_ALLOC = ("Compensation (Pre-Allocations)", 1, 4)

SQL = f"""
SELECT LOB, SCENARIO, FISCAL_YEAR AS YEAR, PERIOD, ACCOUNT, COST_CENTER,
       SUM(AMOUNT) AS AMOUNT
FROM {queries.STG}
WHERE ENTITY = '{queries.STG_ENTITY}'
  AND INTERCOMPANY = '{queries.STG_ICP_TOTAL}'
  AND CHANNEL = 'Total Channel'
  AND PLAN_ELEMENT = 'Total_Budget'
  AND CURRENCY = 'USD_Reporting'
  AND PERIOD_TYPE = 'MONTH'
  AND SCENARIO IN ({", ".join(f"'{s}'" for s in SCENARIOS)})
  AND ((ACCOUNT BETWEEN 'AC_60000' AND 'AC_62999'
        AND COST_CENTER NOT LIKE 'CC_1%'
        AND COST_CENTER NOT IN ('{TOTAL_CC}', 'Total Cost Center')
        AND ACCOUNT NOT IN ({", ".join(f"'{a}'" for a in PARENTS)}))
       OR (ACCOUNT = '{TOTAL_ACCOUNT}' AND COST_CENTER = '{TOTAL_CC}'))
GROUP BY ALL
"""


def mapping() -> pd.DataFrame:
    return pd.read_csv(MAPPING_CSV)


def lines() -> list[str]:
    """Will's 52 lines in LINE_ORDER."""
    m = mapping()
    return m.drop_duplicates("LINE").sort_values("LINE_ORDER")["LINE"].tolist()


def load() -> pd.DataFrame:
    """Every SG&A leaf + the Oracle total, with its template line ('line')."""
    df = data._q(SQL)
    df["amount"] = df["amount"].astype(float)
    m = mapping().rename(columns={"ACCOUNT": "account", "LINE": "line"})
    df = df.merge(m[["account", "line"]], on="account", how="left")
    df["line"] = df["line"].fillna(NOT_MAPPED)
    is_lit = (df["account"] == KEY_LIT_ACCOUNT) & (df["cost_center"] == KEY_LIT_CC)
    df.loc[is_lit, "line"] = KEY_LIT
    is_total = (df["account"] == TOTAL_ACCOUNT) & (df["cost_center"] == TOTAL_CC)
    df.loc[is_total, "line"] = "__oracle_total__"
    return df


def _pivot(df: pd.DataFrame, index) -> pd.DataFrame:
    p = df.pivot_table(index=index, columns="period", values="amount",
                       aggfunc="sum", fill_value=0.0)
    p = p.reindex(columns=list(MONTHS), fill_value=0.0)
    p[FY] = p.sum(axis=1)
    return p


def report(df: pd.DataFrame, lob: str, scenario: str, year: str) -> pd.DataFrame:
    """Will's lines with the template subtotals, Not mapped, total, Key
    Litigation and the check row. The total sums lines + Not mapped only."""
    sl = df[(df["lob"] == lob) & (df["scenario"] == scenario) & (df["year"] == year)]
    p = _pivot(sl, "line") if not sl.empty else pd.DataFrame(columns=[*MONTHS, FY])
    p = p.reindex([*lines(), NOT_MAPPED, KEY_LIT, "__oracle_total__"], fill_value=0.0)
    body = p.loc[[*lines(), NOT_MAPPED]]
    total = body.sum()
    check = p.loc["__oracle_total__"] - total - p.loc[KEY_LIT]
    ordered = lines()
    shown = []
    for i, line in enumerate(ordered, start=1):
        shown.append(p.loc[[line]])
        for name, first, last in (PRE_ALLOC, *SUBTOTALS):
            if last == i:
                sub = p.loc[ordered[first - 1:last]].sum()
                shown.append(sub.to_frame(name).T)
    out = pd.concat([*shown, p.loc[[NOT_MAPPED]], total.to_frame(TOTAL).T,
                     p.loc[[KEY_LIT]], check.to_frame(CHECK).T])
    out.index.name = "Line"
    return out


def oracle_total(df: pd.DataFrame, lob: str, scenario: str, year: str) -> float:
    sl = df[(df["lob"] == lob) & (df["scenario"] == scenario)
            & (df["year"] == year) & (df["line"] == "__oracle_total__")]
    return float(sl["amount"].sum())


def detail(df: pd.DataFrame, lob: str, scenario: str, year: str,
           line: str) -> pd.DataFrame:
    """Account x cost center rows behind one line."""
    sl = df[(df["lob"] == lob) & (df["scenario"] == scenario)
            & (df["year"] == year) & (df["line"] == line)]
    if sl.empty:
        return pd.DataFrame(columns=[*MONTHS, FY])
    return _pivot(sl, ["account", "cost_center"])


def render() -> None:
    """The SG&A tab body (called inside `with sga:` in financial_app.py)."""
    import streamlit as st

    df = load()
    lobs = sorted(df["lob"].unique()) or [DEFAULT_LOB]
    years = sorted(df["year"].unique()) or [DEFAULT_YEAR]
    c1, c2, c3 = st.columns(3)
    lob = c1.selectbox("LOB", lobs, key="sga_lob",
                       index=lobs.index(DEFAULT_LOB) if DEFAULT_LOB in lobs else 0)
    scenario = c2.selectbox("Scenario", list(SCENARIOS), key="sga_scenario",
                            index=SCENARIOS.index(DEFAULT_SCENARIO))
    year = c3.selectbox("Year", years, key="sga_year",
                        index=years.index(DEFAULT_YEAR) if DEFAULT_YEAR in years else 0)

    st.dataframe(report(df, lob, scenario, year).style.format("{:,.2f}"),
                 use_container_width=True, height=35 * 66)
    st.caption("Mapping = Will Oswald's SGA Template Mapping.xlsx (2026-10-14). "
               "LOBs LB_303, LB_305-LB_308 show large 'Not mapped' amounts "
               "until Will maps the _Other accounts.")

    with st.expander("Drill: account x cost center by line"):
        line = st.selectbox("Line", [*lines(), NOT_MAPPED, KEY_LIT], key="sga_line")
        st.dataframe(detail(df, lob, scenario, year, line).style.format("{:,.2f}"),
                     use_container_width=True)
