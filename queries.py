"""The single Snowflake statement behind every number in this app.

ONE query, no bind parameters, run once per session and pivoted in pandas.
That is a deliberate design choice for three reasons:

1.  It is small. 11 vintages x 17 periods x 4 P&L lines is ~730 rows, so
    fetching the whole cube costs less than fetching slices on demand.
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
is what makes the 7-month FY26 Actuals partial (Q3 = Jul only, no Q4) fall out
correctly instead of being fabricated.

WHY THE BASE TABLE, NOT THE VIEW. See BASE below. The view drops the one line
Gross Margin and EBITDA have to be corrected for.
"""
from __future__ import annotations

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
# yields NULL, which the >= DATE '2026-01-01' floor in _VINTAGE_FILTER then
# excludes -- the same behaviour the view gave us.
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
# A "vintage" is a (scenario, fiscal_year) pair, not a scenario -- the deck's
# '2025A' is the Actual scenario read at FY25 while '2026B' and every '<Mon>. FC'
# is read at FY26. Keys are derived, not enumerated, so a future SEP26RF shows up
# as 'Sep. FC' with no code change.
#
# The FORECAST_ASOF_DATE >= '2026-01-01' floor is what excludes three vintages
# that would otherwise pollute the dropdown:
#   * 'Rolling Forecast' -- VERSION='Working', FORECAST_ASOF='ROLLING_FORECAST',
#     NULL as-of date. It covers only 8 of 12 FY26 months.
#   * DEC25RF (as-of 2025-12-31) -- carries FY26 rows but $0 revenue.
#   * OCT25RF / NOV25RF -- FY25-only, already excluded by FISCAL_YEAR.
_VINTAGE_KEY = """
      CASE
        WHEN SCENARIO_LABEL = 'ACTUAL' THEN '20' || SUBSTR(FISCAL_YEAR, 3, 2) || 'A'
        WHEN SCENARIO_LABEL = 'BUDGET' THEN '20' || SUBSTR(FISCAL_YEAR, 3, 2) || 'B'
        ELSE MONTHNAME(FORECAST_ASOF_DATE) || '. FC'
      END"""

_VINTAGE_FILTER = """
         (SCENARIO_LABEL = 'ACTUAL'   AND FISCAL_YEAR IN ('FY25', 'FY26'))
      OR (SCENARIO_LABEL = 'BUDGET'   AND FISCAL_YEAR = 'FY26')
      OR (SCENARIO_LABEL = 'FORECAST' AND FISCAL_YEAR = 'FY26'
          AND FORECAST_ASOF_DATE >= DATE '2026-01-01')"""

# ---------------------------------------------------------------------------
# is_actual_month
# ---------------------------------------------------------------------------
# The deck hardcodes its 26A/26F month suffixes (MONTH_LBL, source JS line 237),
# so selecting Jan. FC there still labels Jan-Jun as actuals. This computes them
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
