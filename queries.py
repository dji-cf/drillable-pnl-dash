"""The single Snowflake statement behind every number in this app.

ONE query, no bind parameters, run once per session and pivoted in pandas.
That is a deliberate design choice for three reasons:

1.  It is small. 15 vintages x 17 periods x 3-4 P&L lines is ~750-1,000
    rows, so fetching the whole cube costs less than fetching slices on
    demand.
2.  Both dropdowns and all three grain toggles become client-side. Changing the
    forecast, the comparison, or Annual/Quarterly/Monthly does not touch
    Snowflake at all.
3.  It sidesteps a real caching bug. Streamlit's SnowflakeConnection.query()
    memoizes on the SQL TEXT; on versions <= 1.51 the `params` argument is
    captured from a closure and is NOT part of the cache key, so a static SQL
    string with different binds silently returns the first result forever.
    A statement with no binds cannot hit that.

GRAIN. The view already materializes all three grains (PERIOD_TYPE in
'MONTH' / 'QUARTER' / 'YEAR', 17 periods per fiscal year), so nothing is
summed up in Python -- quarters and the year total come from the source, which
is what makes a partial-year Actuals vintage (FY26: Jan-Aug, no Q4) fall out
correctly instead of being fabricated.

WHY THE BASE TABLE, NOT THE VIEW. See BASE below. The view drops the one line
Gross Margin and EBITDA have to be corrected for.
"""
from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Source switch
# ---------------------------------------------------------------------------
#: "LEGACY" = ORACLE_DATA_PROD.FCT_EPM.CARDPLN_PL_BY_LOB (7 rolled-up segments,
#: source ACX_ subtotals). "STG" = CARDPLN_PL_BY_LOB_STG (Vivek, 2026-10-01): LOB
#: x account x cost-centre detail that replicates FP&A's Master Data Pull, with
#: Gross Margin and EBITDA computed here exactly as Megan Coleman's file does.
#:
#: The ONLY switch. Everything source-specific -- SEGMENTS, MASTER_SQL and the
#: STG row map -- is rebound at the bottom of this module from this one value,
#: so data.py, transforms.py and table.py carry no source-specific code. The env
#: var lets tools and a local `streamlit run` A/B the two without an edit:
#:     PNL_SOURCE=LEGACY streamlit run streamlit_app.py
#: STG is the default and the deployed behaviour since 2026-10-07 (Daniel Chen's
#: draft release): the STG gates in tools/validate_vs_deck.py pass, and the live
#: app ships these numbers marked DRAFT while Finance validates them. LEGACY
#: stays available as a fallback via PNL_SOURCE=LEGACY -- nothing else to edit.
SOURCE: str = os.environ.get("PNL_SOURCE", "STG").upper()
if SOURCE not in ("LEGACY", "STG"):
    raise ValueError(f"PNL_SOURCE must be LEGACY or STG, got {SOURCE!r}")

# ---------------------------------------------------------------------------
# Segment and line vocabulary
# ---------------------------------------------------------------------------
# The view's 7 LOB segments, pivoted to columns below. Short keys are what
# transforms.py's row expressions are written against.
#
# Note what is NOT here, because it is the source of most of this app's gap
# labels: there is no Digital segment (only the ex-Emerging residual), no split
# between Fanatics Live and Fanatics Collect, no TCG, and no unified
# eliminations group -- 'Total - Topps Eliminations' is the only elimination.
SEGMENTS: dict[str, str] = {
    "na":      "Total - North America Gross",
    "elim":    "Total - Topps Eliminations",
    "intl":    "Total - International incl Elims",
    "phys":    "Total - Physical Cards",
    "exem":    "Total - ex. Emerging Services",
    "fanlive": "Total - Fanatics Live and Collect",
    "keylit":  "Total - Key Litigation",
}

# The three SECTION='SUBTOTAL' lines the dashboard reports. Net Revenue is the
# reconciled one; the other two carry a corrected cost basis (see
# COMPENSATION_LINE) and still do not tie -- ISSUES.md has the detail.
PL_LINES: dict[str, str] = {
    "net_revenue":  "ACX_Net Revenue",
    "gross_margin": "ACX_Gross Margin",
    "ebitda":       "ACX_EBITDA",
}

# ---------------------------------------------------------------------------
# The Compensation correction
# ---------------------------------------------------------------------------
# Not a reported line. It is fetched because ACX_Cost of Goods Sold is NOT the
# sum of its seven mapped children -- it is those children PLUS
# ACX_Compensation, verified at 100% of cells across 11 vintages x 181
# period-cells. Since ACX_Gross Margin = ACX_Net Revenue - ACX_Cost of Goods
# Sold, Compensation lands in Gross Margin and (through it) EBITDA as cost.
#
# It is a DOUBLE-COUNT, not a misclassification. A COGS -> opex reclass would
# leave EBITDA untouched, yet EBITDA only ties to the deck when Compensation is
# subtracted ONCE -- so it already sits inside ACX_Other SG&A and is
# additionally summed into COGS. transforms.build_cube adds it back to both
# subtotals; the arithmetic is gated by tools/validate_vs_deck.py::COMPENSATION.
#
# $445.6M for Jul. FC. Correcting it closes 88-100% of the Gross Margin gap and
# makes the six FORECAST months of Jul. FC tie to the deck (GM +$3.4M, EBITDA
# -$0.1M). The residual is confined to actual months and is unexplained.
COMPENSATION_LINE = "ACX_Compensation"

#: False = show source ACX_ values as in EPM CARDPLN. True = add ACX_Compensation
#: back to gross_margin and ebitda (old behavior). Keep False until the
#: cost-center alternate hierarchy exists.
#:
#: Disabled 2026-09-29. EPM (cube CARDPLN) is the business standard and its
#: ACX_EBITDA is authoritative: Q1 FY26 North America = $195.32M, where the
#: add-back produced $244.22M. Finance handles the Compensation double-count
#: outside this app, so correcting it here double-corrects it. The line is still
#: FETCHED (below) so flipping this back to True restores the old behaviour with
#: no other edit.
APPLY_COMPENSATION_ADJUSTMENT: bool = False

#: Everything the query pulls: the three reported lines plus the adjustment.
#: COMPENSATION_LINE stays in the pull regardless of
#: APPLY_COMPENSATION_ADJUSTMENT -- tools/validate_vs_deck.py's source-identity
#: gates read it, and keeping it makes the flag a one-line switch.
FETCHED_LINES: tuple[str, ...] = tuple(PL_LINES.values()) + (COMPENSATION_LINE,)

# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------
# The BASE TABLE, deliberately, not CARDPLN_PL_BY_LOB_V.
#
# The view is a thin passthrough that INNER JOINs CARDPLN_PL_ACCOUNT_LAYOUT on
# PL_LINE, and that layout maps only 23 of the base table's 42 lines -- so 19
# lines are dropped silently, ACX_Compensation among them. The line is therefore
# invisible in the view yet fully loaded into the COGS subtotal the view does
# expose, which is how the gap went unnoticed.
#
# Reading the base table costs us the layout metadata (PL_LABEL, SECTION,
# SORT_ORDER), none of which this app uses -- it names its three lines and seven
# segments explicitly. It also costs us FORECAST_ASOF_DATE, which the view
# derives; _FORECAST_ASOF below reproduces that expression verbatim.
#
# Verified equivalent for the three reported lines: 3,505 rows, 3,505 distinct
# cells, identical SUM(AMOUNT). Gated by validate_vs_deck.py::BASE vs VIEW so a
# future change to the view cannot drift away from us unnoticed.
BASE = "ORACLE_DATA_PROD.FCT_EPM.CARDPLN_PL_BY_LOB"
VIEW = "ORACLE_DATA_PROD.FCT_EPM.CARDPLN_PL_BY_LOB_V"   # parity check only

# Lifted verbatim from the view's DDL. 'Rolling Forecast' fails the RLIKE and
# yields NULL, which _VINTAGE_FILTER then excludes: its fiscal-year match
# (FISCAL_YEAR = 'FY' || as-of year) is never true for a NULL as-of date --
# the same behaviour the view gave us.
_FORECAST_ASOF = """
      CASE
        WHEN SCENARIO RLIKE '^[A-Z]{3}[0-9]{2}RF$'
        THEN LAST_DAY(TO_DATE('20' || SUBSTR(SCENARIO, 4, 2) || '-'
                              || LEFT(SCENARIO, 3) || '-01', 'YYYY-MON-DD'))
        ELSE NULL
      END"""

# ---------------------------------------------------------------------------
# Vintage selection
# ---------------------------------------------------------------------------
# A "vintage" is a (scenario, fiscal_year) pair, not a scenario: '2025A' is the
# Actual scenario read at FY25, '2026B' the Budget read at FY26, and
# 'Sep 2026 FC' is SEP26RF read at FY26. Every key carries its year and nothing
# is enumerated, so JAN27RF shows up as 'Jan 2027 FC' and FY27's budget as
# '2027B' with no code change. transforms.vintage_parts() is the one parser of
# these keys.
#
# A forecast is read ONLY at the fiscal year of its own as-of date. That is not
# cosmetic: every RF scenario is an ~18-month rolling horizon (verified
# 2026-10-06 -- JAN26RF carries 6 FY27 months, SEP26RF all 12 FY27 months plus
# one FY28 month), so without the year match SEP26RF's FY26 and FY27 rows would
# collide on one key. The same rule excludes:
#   * 'Rolling Forecast' -- NULL as-of date, so the equality is never true;
#   * DEC25RF's FY26 rows -- $0 revenue, as-of year 2025.
#
# FIRST_FISCAL_YEAR is a history floor, not a label: FY23/FY24 actuals exist in
# both sources and are left out. Which of the admitted vintages are offered on
# screen -- partial-year actuals and "retired" forecasts/budgets are not -- is
# decided in transforms (Cube.visible), from the data.
FIRST_FISCAL_YEAR = "FY25"

_VINTAGE_KEY = """
      CASE
        WHEN SCENARIO_LABEL = 'ACTUAL' THEN '20' || SUBSTR(FISCAL_YEAR, 3, 2) || 'A'
        WHEN SCENARIO_LABEL = 'BUDGET' THEN '20' || SUBSTR(FISCAL_YEAR, 3, 2) || 'B'
        ELSE MONTHNAME(FORECAST_ASOF_DATE) || ' '
             || TO_CHAR(YEAR(FORECAST_ASOF_DATE)) || ' FC'
      END"""

_VINTAGE_FILTER = f"""
         (SCENARIO_LABEL IN ('ACTUAL', 'BUDGET') AND FISCAL_YEAR >= '{FIRST_FISCAL_YEAR}')
      OR (SCENARIO_LABEL = 'FORECAST' AND FISCAL_YEAR >= '{FIRST_FISCAL_YEAR}'
          AND FISCAL_YEAR = 'FY' || TO_CHAR(FORECAST_ASOF_DATE, 'YY'))"""

# ---------------------------------------------------------------------------
# is_actual_month
# ---------------------------------------------------------------------------
# The deck hardcodes its 26A/26F month suffixes (MONTH_LBL, source JS line 237),
# so selecting the Jan FC there still labels Jan-Jun as actuals. This computes them
# instead. Verified: for JUL26RF (as-of 2026-07-31) it yields Jan-Jun TRUE and
# Jul-Dec FALSE, reproducing the deck's labels exactly -- while also being
# correct for every other vintage.
#
# Only meaningful at MONTH grain. Quarter and year labels are rolled up in
# transforms.period_labels(), where a quarter counts as actual only when ALL of
# its months are (which is what produces the deck's Q1 26A / Q2 26A / Q3 26F /
# Q4 26F).
_IS_ACTUAL_MONTH = """
      CASE
        WHEN SCENARIO_LABEL = 'ACTUAL' THEN TRUE
        WHEN SCENARIO_LABEL = 'BUDGET' THEN FALSE
        ELSE PERIOD_DATE < DATE_TRUNC('MONTH', FORECAST_ASOF_DATE)
      END"""


def _segment_pivot() -> str:
    """One ZEROIFNULL(SUM(IFF(...))) column per LOB segment.

    ZEROIFNULL because a segment absent for a given vintage/period must behave
    as 0 in the row arithmetic (e.g. Key Litigation carries EBITDA but no
    revenue at all), not poison the sum to NULL.
    """
    return ",\n".join(
        f"    ZEROIFNULL(SUM(IFF(LOB_SEGMENT = '{lob}', AMOUNT, NULL))) AS seg_{key}"
        for key, lob in SEGMENTS.items()
    )


MASTER_SQL = f"""
WITH raw AS (
  SELECT
      SCENARIO_LABEL,
      SCENARIO,
      FISCAL_YEAR,
      PERIOD,
      PERIOD_TYPE,
      PERIOD_DATE,
     {_FORECAST_ASOF.strip()} AS FORECAST_ASOF_DATE,
      PL_LINE,
      LOB_SEGMENT,
      AMOUNT
  FROM {BASE}
  WHERE PL_LINE IN ({", ".join(f"'{v}'" for v in FETCHED_LINES)})
),
src AS (
  SELECT
     {_VINTAGE_KEY.strip()} AS vintage_key,
      SCENARIO_LABEL,
      FISCAL_YEAR,
      PERIOD,
      PERIOD_TYPE,
      PERIOD_DATE,
      FORECAST_ASOF_DATE,
      PL_LINE,
      LOB_SEGMENT,
      AMOUNT,
     {_IS_ACTUAL_MONTH.strip()} AS is_actual_month
  FROM raw
  WHERE ({_VINTAGE_FILTER.strip()})
)
SELECT
    vintage_key,
    scenario_label,
    fiscal_year,
    period,
    period_type,
    MIN(period_date)         AS period_date,
    MIN(forecast_asof_date)  AS forecast_asof_date,
    pl_line,
    -- MONTH grain only; NULL at QUARTER/YEAR, where transforms.py rolls it up.
    MAX(IFF(period_type = 'MONTH', is_actual_month, NULL)) AS is_actual_month,
{_segment_pivot()}
FROM src
GROUP BY vintage_key, scenario_label, fiscal_year, period, period_type, pl_line
ORDER BY vintage_key, pl_line, period_type, period_date
"""


# ===========================================================================
# STG source -- ORACLE_DATA_PROD.FCT_EPM.CARDPLN_PL_BY_LOB_STG
# ===========================================================================
# Different grain from the legacy table: one row per LOB x ACCOUNT x COST_CENTER
# x CHANNEL x PLAN_ELEMENT, with NO computed subtotals. It originally had no
# entity or intercompany column either; Vivek added ENTITY and INTERCOMPANY on
# 2026-10-01 and MASTER_SQL now filters on both (see STG_ENTITY / STG_ICP_*).
# Gross Margin and EBITDA are still built
# here from account lines, per Megan Coleman's `Collectibles FC - 9.2026.xlsx`
# (tab `Collectibles (Monthly)`):
#     Gross Margin = Revenue - COGS                  (file: =EN7-SUM(EN8:EN16))
#     EBITDA       = Gross Margin - SG&A             (file: =EN17-SUM(EN18:EN20))
#
# Each term was proven against the table before it was written down
# (2026-10-01, all scenarios, every slice):
#
#   Revenue = ACX_Net Revenue + AC_40001. AC_40001 only exists in LB_394, where
#       it is the GCP intercompany revenue elimination (-286.2 SEP26RF FY).
#
#   COGS = AC_50000 @ CC_10000 where that cell exists, else the sum of the eight
#       ACX_ COGS lines @ CC_10000. AC_50000 @ CC_10000 is the COGS PARENT, not a
#       separate Purchase Accounting line: in all 752 slices where it coexists
#       with the ACX_ lines (LB_392, Topps eliminations) it equals their sum
#       exactly, so adding it on top would double-count. It stands alone in
#       LB_394, LB_301 and LB_308; it is absent in LB_302-307. If a genuine PAA
#       amount ever lands in the parent, this rule picks it up.
#       ACX_Compensation stays inside COGS. Nothing is added back.
#
#   SG&A = AC_50000 @ CC_30000. Also a parent: Megan's three lines (Marketing
#       AC_60001, Bonus AC_60597, Other SG&A AC_61623) are only part of it --
#       98.3 of 405.2 for LB_302 SEP26RF FY. It is present in every one of 4,153
#       slices that carry SG&A children. It is already on the AEBITDA basis:
#       for LB_301 SEP26RF FY it is 169.45 = EBITDA 280.4 less the Collectibles
#       Allocation 111.7 (AC_61623 @ CC_70104), which reproduces the file's
#       Corporate AEBITDA of -168.7 once TCG's CC_70123 is taken out.
#       CC_30000 (Total SGA) is a cost-centre PARENT: CC_40313 (PISA legal),
#       CC_70104 (allocations) and CC_70123 (TCG) are inside it. That is why the
#       carve-outs below are ADDED BACK to their LOB rather than ignored.
#
# Filters: CHANNEL='Total Channel' (DTC + Wholesale sum to it exactly),
# PLAN_ELEMENT='Total_Budget' (the only value present -- so OTI_ADJ rows, if
# any, cannot be seen separately), VERSION='Final', CURRENCY='USD_Reporting'.
#
# ENTITY / INTERCOMPANY (added by Vivek 2026-10-01). Every tuple is pinned to
# ENTITY='CO_31000' (the parent: LB_302 revenue there is 4,239.0 = Megan's TOTAL
# NASE, already including CO_31037, CO_31010 and the 150.0 NASE interco) and
# INTERCOMPANY='Total Intercompany' (the parent of every ICP_ code). The child
# slices -- LB_302/CO_31010/ICP_31000, LB_301/CC_70104/ICP_310xx, LB_394/
# ICP_31005 -- are therefore never read; adding them would double-count.
#
# The ONE exception is International eliminations: LB_392 / CO_31000 /
# ICP_32002 (file row 403, FY26 -5.44 revenue, -5.44 manufacturing, EBITDA
# 0.0). LB_392 at Total Intercompany is NOT read at all: it is Topps elims +
# ICP_32002 on revenue, but carries 0.77M more COGS than those two pieces
# (SEP26RF FY -159.97 vs -153.76 - 5.44), which was the old Intl-elims residue.
STG = "ORACLE_DATA_PROD.FCT_EPM.CARDPLN_PL_BY_LOB_STG"
STG_ENTITY = "CO_31000"
STG_ICP_TOTAL = "Total Intercompany"
STG_ICP_INTL_ELIMS = "ICP_32002"

_STG_REVENUE_ACCOUNTS: tuple[str, ...] = ("ACX_Net Revenue", "AC_40001")
_STG_COGS_ACCOUNTS: tuple[str, ...] = (
    "ACX_Manufacturing", "ACX_Net Freight Expense", "ACX_Royalties",
    "ACX_MG Shortfall", "ACX_Autos & Relics", "ACX_Obsolescence",
    "ACX_Compensation", "ACX_Product Development",
)

#: Segment columns the STG query emits. The ten base LOBs carry the line's own
#: value (revenue / GM / EBITDA). The three CARVE-OUTS are COSTS (positive
#: amounts) that sit inside a LOB's SG&A but belong to a different deck row;
#: they are non-zero on the ebitda line only.
STG_SEGMENTS: dict[str, str] = {
    "l301":  "LB_301",                      # Corporate OH - Collectibles
    "l302":  "LB_302",                      # Physical Collectibles - Domestic
    "l303":  "LB_303",                      # Physical Collectibles - International
    "l304":  "LB_304",                      # Manufacturing and Packaging (GCP)
    "l305":  "LB_305",                      # Digital Collectibles - Domestic
    "l306":  "LB_306",                      # Fanatics Live - Total
    "l307":  "LB_307",                      # Marketplace - Total (PWCC)
    "l308":  "LB_308",                      # Trading Card Games - Total
    "ie":    "LB_392",                      # Elims International = LB_392 @ ICP_32002 only
    "l394":  "LB_394",                      # Elims, Manufacturing and Packaging - Gross
    "topps": "Total - Topps Eliminations",
    "pisa301": "LB_301 AC_61002 @ CC_40313",   # carve-out: Pisa Costs
    "pisa302": "LB_302 AC_61002 @ CC_40313",   # carve-out: NASE Key Litigations
    "tcgcc":   "LB_301 AC_50000 @ CC_70123",   # carve-out: TCG, old method
}

_STG_LINES: tuple[str, ...] = tuple(PL_LINES.values())

# FY 'FY26' -> 2026, for building PERIOD_DATE, which STG does not carry.
_STG_YEAR = "'20' || SUBSTR(FISCAL_YEAR, 3, 2)"
_STG_PERIOD_DATE = f"""
      CASE PERIOD_TYPE
        WHEN 'MONTH'   THEN TO_DATE({_STG_YEAR} || '-' || PERIOD || '-01', 'YYYY-MON-DD')
        WHEN 'QUARTER' THEN DATEADD(MONTH, 3 * (TO_NUMBER(SUBSTR(PERIOD, 2, 1)) - 1),
                                    TO_DATE({_STG_YEAR} || '-01-01'))
        ELSE TO_DATE({_STG_YEAR} || '-01-01')
      END"""


def _sql_list(names: tuple[str, ...]) -> str:
    return ", ".join(f"'{n}'" for n in names)


def _stg_pivot() -> str:
    rev, gm, eb = PL_LINES["net_revenue"], PL_LINES["gross_margin"], PL_LINES["ebitda"]
    cols = [
        f"    ZEROIFNULL(SUM(IFF(lob = '{lob}', CASE pl_line"
        f" WHEN '{rev}' THEN rev WHEN '{gm}' THEN rev - cogs"
        f" ELSE rev - cogs - sga END, NULL))) AS seg_{key}"
        for key, lob in STG_SEGMENTS.items()
        if not key.startswith(("pisa", "tcg"))
    ]
    cols += [
        f"    ZEROIFNULL(SUM(IFF(pl_line = '{eb}' AND lob = 'LB_301', pisa,  NULL))) AS seg_pisa301",
        f"    ZEROIFNULL(SUM(IFF(pl_line = '{eb}' AND lob = 'LB_302', pisa,  NULL))) AS seg_pisa302",
        f"    ZEROIFNULL(SUM(IFF(pl_line = '{eb}' AND lob = 'LB_301', tcgcc, NULL))) AS seg_tcgcc",
    ]
    return ",\n".join(cols)


STG_SQL = f"""
WITH raw AS (
  SELECT
      SCENARIO_LABEL, SCENARIO, FISCAL_YEAR, PERIOD, PERIOD_TYPE,
     {_STG_PERIOD_DATE.strip()} AS PERIOD_DATE,
     {_FORECAST_ASOF.strip()} AS FORECAST_ASOF_DATE,
      LOB, ACCOUNT, COST_CENTER, ENTITY, INTERCOMPANY, AMOUNT
  FROM {STG}
  WHERE CHANNEL = 'Total Channel' AND PLAN_ELEMENT = 'Total_Budget'
    AND VERSION = 'Final' AND CURRENCY = 'USD_Reporting'
    AND ENTITY = '{STG_ENTITY}'
    AND (   (LOB <> 'LB_392' AND INTERCOMPANY = '{STG_ICP_TOTAL}')
         OR (LOB =  'LB_392' AND INTERCOMPANY = '{STG_ICP_INTL_ELIMS}'))
),
src AS (
  SELECT
     {_VINTAGE_KEY.strip()} AS vintage_key,
      SCENARIO_LABEL, FISCAL_YEAR, PERIOD, PERIOD_TYPE, PERIOD_DATE,
      FORECAST_ASOF_DATE, LOB, ACCOUNT, COST_CENTER, ENTITY, INTERCOMPANY, AMOUNT,
     {_IS_ACTUAL_MONTH.strip()} AS is_actual_month
  FROM raw
  WHERE ({_VINTAGE_FILTER.strip()})
),
by_lob AS (
  SELECT
      vintage_key, scenario_label, fiscal_year, period, period_type, lob,
      MIN(period_date)        AS period_date,
      MIN(forecast_asof_date) AS forecast_asof_date,
      MAX(IFF(period_type = 'MONTH', is_actual_month, NULL)) AS is_actual_month,
      SUM(IFF(account IN ({_sql_list(_STG_REVENUE_ACCOUNTS)}), amount, 0)) AS rev,
      COALESCE(
        SUM(IFF(account = 'AC_50000' AND cost_center = 'CC_10000', amount, NULL)),
        SUM(IFF(account IN ({_sql_list(_STG_COGS_ACCOUNTS)}) AND cost_center = 'CC_10000', amount, NULL)),
        0) AS cogs,
      SUM(IFF(account = 'AC_50000' AND cost_center = 'CC_30000', amount, 0)) AS sga,
      SUM(IFF(account = 'AC_61002' AND cost_center = 'CC_40313', amount, 0)) AS pisa,
      SUM(IFF(account = 'AC_50000' AND cost_center = 'CC_70123', amount, 0)) AS tcgcc,
      COUNT(DISTINCT entity)       AS n_entity,
      COUNT(DISTINCT intercompany) AS n_icp
  FROM src
  GROUP BY vintage_key, scenario_label, fiscal_year, period, period_type, lob
),
lines AS (
  SELECT column1 AS pl_line FROM VALUES {", ".join(f"('{l}')" for l in _STG_LINES)}
)
SELECT
    vintage_key, scenario_label, fiscal_year, period, period_type,
    MIN(period_date)        AS period_date,
    MIN(forecast_asof_date) AS forecast_asof_date,
    pl_line,
    MAX(is_actual_month)    AS is_actual_month,
    -- Guard: every LOB tuple must resolve to exactly one ENTITY and one
    -- INTERCOMPANY. tools/validate_vs_deck.py fails if either exceeds 1.
    MAX(n_entity)           AS max_n_entity,
    MAX(n_icp)              AS max_n_icp,
{_stg_pivot()}
FROM by_lob CROSS JOIN lines
GROUP BY vintage_key, scenario_label, fiscal_year, period, period_type, pl_line
ORDER BY vintage_key, pl_line, period_type, period_date
"""

# ---------------------------------------------------------------------------
# STG row map -- the ONLY place deck rows are grouped from LOBs
# ---------------------------------------------------------------------------
# (section, deck label) -> signed terms over STG_SEGMENTS. One entry per row of
# James Dillon's Forecast Deck p.7. "file" = row(s) of Megan's
# `Collectibles (Monthly)` tab the entry reproduces. The file's Entity (CO_) and
# intercompany (ICP_) filters DO have STG columns -- ENTITY and INTERCOMPANY were
# added to CARDPLN_PL_BY_LOB_STG by Vivek 2026-10-01 -- and MASTER_SQL applies
# them itself (see the base CTE: ENTITY = STG_ENTITY, plus the LB_392/ICP_32002
# International-eliminations exception). So these terms are already entity- and
# intercompany-scoped and do NOT depend on Vivek's pull pre-filtering them;
# tools/validate_vs_deck.py's ONE ENTITY gate asserts exactly one of each per
# LOB tuple. See the STG_ENTITY / STG_ICP_* block above for why CO_31000 and
# 'Total Intercompany' are the right parents and why the child slices are not read.
# Every Gross Margin % row uses the SAME terms as the Revenue row above it.
_T = tuple[tuple[int, str], ...]

_NA_REV:   _T = ((1, "l302"), (1, "l304"), (1, "l394"), (1, "topps"))
_INTL:     _T = ((1, "l303"), (1, "ie"))
_DIGITAL:  _T = ((1, "l305"),)
_CORP_REV: _T = ((1, "l301"),)
_FANCOL:   _T = ((1, "l306"), (1, "l307"))
_ALL_LOBS: _T = tuple((1, k) for k in ("l301", "l302", "l303", "l304", "l305",
                                       "l306", "l307", "l308", "l394", "topps",
                                       "ie"))
_NA_EB:    _T = ((1, "l302"), (1, "l304"), (1, "l394"), (1, "pisa302"))
_ELIM_EB:  _T = ((1, "topps"),)
_CORP_EB:  _T = ((1, "l301"), (1, "pisa301"), (1, "tcgcc"))
_PHYS_EB:  _T = _NA_EB + _INTL + _ELIM_EB

STG_ROW_MAP: dict[tuple[str, str], _T] = {
    # -- Revenue ----------------------------------------------------------
    # file 6-179 NASE + 314-333 GCP + 358-377 Elims GCP (LB_394 @ ICP_31005)
    # + 380-399 Elims Topps. Folded, as the deck prints it: 652/1,289/1,077/1,071.
    ("Revenue", "North America"):          _NA_REV,
    # file 182-223 + 402-421 "Elims International" (LB_392 / CO_31000 / ICP_32002).
    ("Revenue", "International"):          _INTL,
    ("Revenue", "Total Physical Cards"):   _NA_REV + _INTL,
    # file 248-311 (CO_31000 Apps + CO_31032 Blockchain)
    ("Revenue", "Digital"):                _DIGITAL,
    # file 601 = NASE+INTL+DIGITAL+GCP+ELIMS+CORP OH (+HEDGE, 0.0 FY26F)
    ("Revenue", "Subtotal"):               _NA_REV + _INTL + _DIGITAL + _CORP_REV,
    # file 446-465 LIVE + 490-509 PWCC
    ("Revenue", "Fanatics Collect"):       _FANCOL,
    # file 579 -- every block.
    ("Revenue", "Total Revenue"):          _ALL_LOBS,
    # -- Gross Margin % (same terms as the Revenue row, ONE exception) -----
    # North America GM% EXCLUDES the Topps eliminations, as the deck footnote
    # says ("North America Gross Margins exclude eliminations; Total Gross Margin
    # includes eliminations"). Measured 2026-10-01: this reproduces the Jul FC
    # deck to 0.1pt in every cell (55.9/59.6/57.9/53.1/56.7) and rounds to every
    # Sep FC cell; with the Topps elims folded in it runs ~+2pt high everywhere.
    ("Gross Margin", "North America"):          ((1, "l302"), (1, "l304"), (1, "l394")),
    ("Gross Margin", "International"):          _INTL,
    ("Gross Margin", "Total Physical Cards"):   _NA_REV + _INTL,
    ("Gross Margin", "Digital"):                _DIGITAL,
    ("Gross Margin", "Subtotal"):               _NA_REV + _INTL + _DIGITAL + _CORP_REV,
    ("Gross Margin", "Fanatics Collect"):       _FANCOL,
    ("Gross Margin", "Total Gross Margin"):     _ALL_LOBS,
    # -- Adj. EBITDA (= AEBITDA in the file) -------------------------------
    # file 6-179 NASE + 314-333 GCP + 358-377 Elims GCP. Topps elims are the
    # deck's Eliminations row; file 627 "NASE: Key Litigations" (LB_302 /
    # CC_40313 / AC_61002) moves to Key Litigation, so it is added back here.
    ("EBITDA", "North America"):          _NA_EB,
    # file 182-223 + 402-421
    ("EBITDA", "International"):          _INTL,
    # file 380-399 Elims Topps
    ("EBITDA", "Eliminations"):           _ELIM_EB,
    ("EBITDA", "Total Physical Cards"):   _PHYS_EB,
    # file 248-311
    ("EBITDA", "Digital"):                _DIGITAL,
    # file 468-488 Corporate OH = LB_301 @ CC_30000, less file 568 (TCG,
    # CC_70123) and less file 624 "Pisa Costs" (CC_40313 / AC_61002).
    ("EBITDA", "Corporate"):              _CORP_EB,
    ("EBITDA", "Subtotal"):               _PHYS_EB + _DIGITAL + _CORP_EB,
    # file 446-465 LIVE + 490-509 PWCC
    ("EBITDA", "Fanatics Collect"):       _FANCOL,
    # file 624 Pisa Costs + 627 NASE Key Litigations. Costs, so negated.
    ("EBITDA", "Key Litigation Costs"):   ((-1, "pisa301"), (-1, "pisa302")),
    # file 556-575: LB_308 (new LOB) + LB_301 @ CC_70123 (old method).
    ("EBITDA", "TCG"):                    ((1, "l308"), (-1, "tcgcc")),
    # file 579. The three carve-outs net to zero across rows, so the total is
    # simply every base LOB -- an identity the validator asserts.
    ("EBITDA", "Total EBITDA"):           _ALL_LOBS,
    ("EBITDA Margin", "EBITDA Margin"):   _ALL_LOBS,
}

# ---------------------------------------------------------------------------
# Rebind for the chosen source
# ---------------------------------------------------------------------------
LEGACY_SEGMENTS = SEGMENTS
LEGACY_SQL = MASTER_SQL
if SOURCE == "STG":
    SEGMENTS = STG_SEGMENTS
    MASTER_SQL = STG_SQL
