-- ===========================================================================
-- master_query.sql
-- How every number on the Drillable P&L dashboard is derived, end to end.
--
-- Generated from the app's own source. Four stages:
--
--   STAGE 1  raw / src / master   the app's literal query, VERBATIM
--   STAGE 2  wide                 pivot the 4 fetched P&L lines into columns
--   STAGE 3  corrected            undo the ACX_Compensation double-count
--   STAGE 4  statement            the deck's 26 rows, as displayed
--
-- Stage 1 is exactly what queries.MASTER_SQL sends to Snowflake. Stages 2-4
-- reproduce in SQL what the app does in Python (transforms.py), so this file
-- is a standalone check on the dashboard.
--
-- Live objects:
--   ORACLE_DATA_PROD.FCT_EPM.CARDPLN_PL_BY_LOB           <- read (base table)
--   ORACLE_DATA_PROD.FCT_EPM.CARDPLN_PL_BY_LOB_V         <- deliberately NOT read
--   ORACLE_DATA_PROD.FCT_EPM.CARDPLN_PL_ACCOUNT_LAYOUT   <- the view's join key
--
-- WHY THE BASE TABLE. _V inner-joins the layout table, which maps only 23 of
-- the base table's 42 PL_LINEs. That silently drops 19 lines -- 28,893 of
-- 79,809 rows -- including ACX_Compensation, the one line Gross Margin and
-- EBITDA must be corrected for. For the three REPORTED lines base and view are
-- byte-identical (2,545 / 2,653 / 2,907 rows, identical SUM(AMOUNT)), and the
-- layout table is 23 rows over 23 distinct PL_LINE values so the join cannot
-- fan out. Reading base can only ADD rows, never duplicate them.
--
-- Change the two filters in the final SELECT to move around. Everything else
-- is vintage- and grain-agnostic.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- STAGE 1 -- the app's literal query (queries.MASTER_SQL), verbatim
-- ---------------------------------------------------------------------------
-- One statement, no bind parameters, run once per session and cached for 2h.
-- No binds is deliberate: Streamlit's SnowflakeConnection.query() memoizes on
-- SQL TEXT, and on <= 1.51 the `params` argument is not part of the cache key,
-- so a static string with rotating binds returns the first result forever.
WITH raw AS (
  SELECT
      SCENARIO_LABEL,
      SCENARIO,
      FISCAL_YEAR,
      PERIOD,
      PERIOD_TYPE,
      PERIOD_DATE,
      -- Lifted verbatim from the _V DDL, because the base table has no such
      -- column. 'Rolling Forecast' fails the RLIKE and yields NULL, which the
      -- >= 2026-01-01 floor below then excludes -- same behaviour as the view.
     CASE
        WHEN SCENARIO RLIKE '^[A-Z]{3}[0-9]{2}RF$'
        THEN LAST_DAY(TO_DATE('20' || SUBSTR(SCENARIO, 4, 2) || '-'
                              || LEFT(SCENARIO, 3) || '-01', 'YYYY-MON-DD'))
        ELSE NULL
      END AS FORECAST_ASOF_DATE,
      PL_LINE,
      LOB_SEGMENT,
      AMOUNT
  FROM ORACLE_DATA_PROD.FCT_EPM.CARDPLN_PL_BY_LOB
  -- Three REPORTED lines + one ADJUSTMENT line. ACX_Compensation is never
  -- displayed; stage 3 folds it into the other two and discards it.
  WHERE PL_LINE IN ('ACX_Net Revenue', 'ACX_Gross Margin', 'ACX_EBITDA', 'ACX_Compensation')
),
src AS (
  SELECT
      -- A "vintage" is a (scenario, fiscal_year) PAIR, not a scenario: 2025A
      -- is Actual read at FY25, 2026B the Budget at FY26, 'Sep 2026 FC' is
      -- SEP26RF read at FY26. Every key carries its year; nothing is
      -- enumerated, so JAN27RF appears as 'Jan 2027 FC' with no code change.
      -- Mirrors queries._VINTAGE_KEY.
     CASE
        WHEN SCENARIO_LABEL = 'ACTUAL' THEN '20' || SUBSTR(FISCAL_YEAR, 3, 2) || 'A'
        WHEN SCENARIO_LABEL = 'BUDGET' THEN '20' || SUBSTR(FISCAL_YEAR, 3, 2) || 'B'
        ELSE MONTHNAME(FORECAST_ASOF_DATE) || ' '
             || TO_CHAR(YEAR(FORECAST_ASOF_DATE)) || ' FC'
      END AS vintage_key,
      SCENARIO_LABEL,
      FISCAL_YEAR,
      PERIOD,
      PERIOD_TYPE,
      PERIOD_DATE,
      FORECAST_ASOF_DATE,
      PL_LINE,
      LOB_SEGMENT,
      AMOUNT,
      -- The deck HARDCODES its 26A/26F month suffixes, so selecting its Jan FC
      -- there still labels Jan-Jun as actuals. This computes them. Only
      -- meaningful at MONTH grain; quarters/years roll up in stage 4.
     CASE
        WHEN SCENARIO_LABEL = 'ACTUAL' THEN TRUE
        WHEN SCENARIO_LABEL = 'BUDGET' THEN FALSE
        ELSE PERIOD_DATE < DATE_TRUNC('MONTH', FORECAST_ASOF_DATE)
      END AS is_actual_month
  FROM raw
  -- Mirrors queries._VINTAGE_FILTER. 'FY25' is a history floor
  -- (queries.FIRST_FISCAL_YEAR). A forecast is read ONLY at the year of its
  -- own as-of date: every RF is an ~18-month rolling horizon, so without the
  -- match SEP26RF's FY26 and FY27 rows would collide on one key. The same
  -- rule drops 'Rolling Forecast' (NULL as-of) and DEC25RF's $0 FY26 rows.
  -- Which admitted vintages the app OFFERS (no partial-year Actuals, no
  -- forecasts/budgets of a year whose actuals are final) is transforms'.
  WHERE ((SCENARIO_LABEL IN ('ACTUAL', 'BUDGET') AND FISCAL_YEAR >= 'FY25')
      OR (SCENARIO_LABEL = 'FORECAST' AND FISCAL_YEAR >= 'FY25'
          AND FISCAL_YEAR = 'FY' || TO_CHAR(FORECAST_ASOF_DATE, 'YY')))
),
master AS (
  -- Exactly the rows the app receives: 724 = 11 vintages x 4 lines x 181
  -- period-cells. All three grains come from the SOURCE (PERIOD_TYPE in
  -- MONTH / QUARTER / YEAR), nothing is summed up in Python -- which is what
  -- makes 7-month FY26 Actuals yield 3 quarters instead of a fabricated Q4.
  SELECT
      vintage_key,
      scenario_label,
      fiscal_year,
      period,
      period_type,
      MIN(period_date)         AS period_date,
      MIN(forecast_asof_date)  AS forecast_asof_date,
      pl_line,
      -- MONTH grain only; NULL at QUARTER/YEAR, where stage 4 rolls it up.
      MAX(IFF(period_type = 'MONTH', is_actual_month, NULL)) AS is_actual_month,
      -- The 7 LOB segments, pivoted to columns. ZEROIFNULL because a segment
      -- absent for a vintage/period must behave as 0 in the row arithmetic
      -- (Key Litigation carries EBITDA but no revenue at all), not poison the
      -- sum to NULL.
      --
      -- NOTE WHAT IS NOT HERE, because it drives most of the app's gap badges:
      -- no Digital segment (only the ex-Emerging minus Physical residual), no
      -- split between Fanatics Live and Fanatics Collect, no TCG, no Corporate,
      -- and 'Topps Eliminations' is the ONLY elimination segment.
      ZEROIFNULL(SUM(IFF(LOB_SEGMENT = 'Total - North America Gross', AMOUNT, NULL))) AS seg_na,
      ZEROIFNULL(SUM(IFF(LOB_SEGMENT = 'Total - Topps Eliminations', AMOUNT, NULL))) AS seg_elim,
      ZEROIFNULL(SUM(IFF(LOB_SEGMENT = 'Total - International incl Elims', AMOUNT, NULL))) AS seg_intl,
      ZEROIFNULL(SUM(IFF(LOB_SEGMENT = 'Total - Physical Cards', AMOUNT, NULL))) AS seg_phys,
      ZEROIFNULL(SUM(IFF(LOB_SEGMENT = 'Total - ex. Emerging Services', AMOUNT, NULL))) AS seg_exem,
      ZEROIFNULL(SUM(IFF(LOB_SEGMENT = 'Total - Fanatics Live and Collect', AMOUNT, NULL))) AS seg_fanlive,
      ZEROIFNULL(SUM(IFF(LOB_SEGMENT = 'Total - Key Litigation', AMOUNT, NULL))) AS seg_keylit
  FROM src
  GROUP BY vintage_key, scenario_label, fiscal_year, period, period_type, pl_line
),
-- === END OF THE APP'S QUERY. Everything below is transforms.py, in SQL. =====


-- ---------------------------------------------------------------------------
-- STAGE 2 -- pivot the 4 P&L lines into columns
-- ---------------------------------------------------------------------------
-- Collapses 4 rows per (vintage, period) into 1 row of 28 measures, so the
-- percent rows can divide one line by another. Prefixes:
--   nr_ = ACX_Net Revenue    gm_ = ACX_Gross Margin (RAW, uncorrected)
--   eb_ = ACX_EBITDA (RAW)   cp_ = ACX_Compensation (the adjustment)
wide AS (
  SELECT
      vintage_key,
      scenario_label,
      fiscal_year,
      period,
      period_type,
      MIN(period_date)          AS period_date,
      MAX(is_actual_month)      AS is_actual_month,

      SUM(IFF(pl_line = 'ACX_Net Revenue',   seg_na,      0)) AS nr_na,
      SUM(IFF(pl_line = 'ACX_Net Revenue',   seg_elim,    0)) AS nr_elim,
      SUM(IFF(pl_line = 'ACX_Net Revenue',   seg_intl,    0)) AS nr_intl,
      SUM(IFF(pl_line = 'ACX_Net Revenue',   seg_phys,    0)) AS nr_phys,
      SUM(IFF(pl_line = 'ACX_Net Revenue',   seg_exem,    0)) AS nr_exem,
      SUM(IFF(pl_line = 'ACX_Net Revenue',   seg_fanlive, 0)) AS nr_fanlive,
      SUM(IFF(pl_line = 'ACX_Net Revenue',   seg_keylit,  0)) AS nr_keylit,

      SUM(IFF(pl_line = 'ACX_Gross Margin',  seg_na,      0)) AS gm_raw_na,
      SUM(IFF(pl_line = 'ACX_Gross Margin',  seg_elim,    0)) AS gm_raw_elim,
      SUM(IFF(pl_line = 'ACX_Gross Margin',  seg_intl,    0)) AS gm_raw_intl,
      SUM(IFF(pl_line = 'ACX_Gross Margin',  seg_phys,    0)) AS gm_raw_phys,
      SUM(IFF(pl_line = 'ACX_Gross Margin',  seg_exem,    0)) AS gm_raw_exem,
      SUM(IFF(pl_line = 'ACX_Gross Margin',  seg_fanlive, 0)) AS gm_raw_fanlive,
      SUM(IFF(pl_line = 'ACX_Gross Margin',  seg_keylit,  0)) AS gm_raw_keylit,

      SUM(IFF(pl_line = 'ACX_EBITDA',        seg_na,      0)) AS eb_raw_na,
      SUM(IFF(pl_line = 'ACX_EBITDA',        seg_elim,    0)) AS eb_raw_elim,
      SUM(IFF(pl_line = 'ACX_EBITDA',        seg_intl,    0)) AS eb_raw_intl,
      SUM(IFF(pl_line = 'ACX_EBITDA',        seg_phys,    0)) AS eb_raw_phys,
      SUM(IFF(pl_line = 'ACX_EBITDA',        seg_exem,    0)) AS eb_raw_exem,
      SUM(IFF(pl_line = 'ACX_EBITDA',        seg_fanlive, 0)) AS eb_raw_fanlive,
      SUM(IFF(pl_line = 'ACX_EBITDA',        seg_keylit,  0)) AS eb_raw_keylit,

      SUM(IFF(pl_line = 'ACX_Compensation',  seg_na,      0)) AS cp_na,
      SUM(IFF(pl_line = 'ACX_Compensation',  seg_elim,    0)) AS cp_elim,
      SUM(IFF(pl_line = 'ACX_Compensation',  seg_intl,    0)) AS cp_intl,
      SUM(IFF(pl_line = 'ACX_Compensation',  seg_phys,    0)) AS cp_phys,
      SUM(IFF(pl_line = 'ACX_Compensation',  seg_exem,    0)) AS cp_exem,
      SUM(IFF(pl_line = 'ACX_Compensation',  seg_fanlive, 0)) AS cp_fanlive,
      SUM(IFF(pl_line = 'ACX_Compensation',  seg_keylit,  0)) AS cp_keylit
  FROM master
  GROUP BY vintage_key, scenario_label, fiscal_year, period, period_type
),


-- ---------------------------------------------------------------------------
-- STAGE 3 -- the ACX_Compensation correction  (transforms._apply_compensation)
-- ---------------------------------------------------------------------------
-- THE ONLY PLACE THE APP CHANGES A SOURCE FIGURE. $445.6M for Jul. FC annual.
--
-- WHAT IS PROVEN FROM THE SOURCE. The layout table declares exactly 7 children
-- for ACX_Cost of Goods Sold (Manufacturing, Royalties, Net Freight Expense,
-- Product Development, Autos & Relics, MG Shortfall, Obsolescence).
-- ACX_Compensation is NOT one of them -- it is not in the layout table at all.
-- Yet COGS does not equal those 7 children; it equals children + Compensation,
-- at 100% of cells on na/elim/intl/phys/fanlive (exem 95.6%, keylit 85.7%,
-- worst residual $44.4M). Without Compensation the worst gap is $553.7M.
--
-- SCOPE MATTERS. That identity is NOT universal. Unscoped across all
-- scenarios, versions and FY23-FY28 it holds on only 94.5% of 2,651 cells. It
-- holds at 100% on the five core segments WITHIN the vintage filter in stage 1.
--
-- WHAT IS INFERRED, NOT PROVEN. For "add it back" to be right, Compensation
-- must ALSO already sit inside ACX_Other SG&A. That is not provable: Other
-- SG&A is a LEAF (it is ACX_SG&A's only child -- SG&A == Other SG&A exactly),
-- so nothing decomposes it. Only shown numerically possible: on ex-Emerging,
-- Compensation 391.3 <= Other SG&A 687.6. THIS INFERENCE CARRIES THE $445.6M.
--
-- WHY IT IS A DOUBLE-COUNT AND NOT A RECLASS. The source computes
--     Gross Margin = Net Revenue - Cost of Goods Sold
--     EBITDA       = Gross Margin - Marketing - SG&A
-- A pure COGS -> opex reclass leaves EBITDA UNCHANGED, because both are
-- subtracted. EBITDA only agrees with the deck when Compensation is subtracted
-- ONCE instead of twice -- so it was being subtracted twice.
--
-- IT IS CALCULATED, NOT A PLUG. A plug is (deck - live) and zeroes the residual
-- by construction. This does not: actual months keep -$137.9M after correction.
-- Compensation (30.4 -> 44.4/mo, smooth payroll ramp) and the monthly deck gap
-- (-36.0 -> -75.0) are uncorrelated series; neither is derivable from the other.
-- See tools/plug_test.py.
--
-- SIGN. COGS is stored POSITIVE and SUBTRACTED to reach Gross Margin, so
-- removing Compensation from COGS is "+ compensation" on both subtotals.
--
-- SAFE PER SEGMENT. Compensation satisfies na + elim + intl == phys at 428/428
-- cells (worst residual $0.0001), so correcting all 7 segments independently
-- keeps every row expression below coherent -- including the exem - phys
-- residual and the exem + fanlive + keylit grand total.
--
-- VALIDATION LIMIT. Only forecast months are validated. For Jul. FC the six
-- forecast months come to -$0.1M against the deck on $989M -- but that is the
-- SIX-MONTH SUM and involves real cancellation (Sep +7.7, Dec -8.8, i.e. ~5%
-- at month level). Source and deck agree on the forecast TOTAL to 0.01% but
-- PHASE differently. Do not reconcile a single forecast month in isolation.
-- The six ACTUAL months remain -$137.9M short, unexplained, open with the
-- data team.
--
-- Net Revenue is NOT corrected -- it reconciles to the deck exactly as shipped,
-- at all three grains, for all 9 shared vintages.
corrected AS (
  SELECT
      vintage_key, scenario_label, fiscal_year, period, period_type,
      period_date, is_actual_month,

      nr_na, nr_elim, nr_intl, nr_phys, nr_exem, nr_fanlive, nr_keylit,

      gm_raw_na      + cp_na      AS gm_na,
      gm_raw_elim    + cp_elim    AS gm_elim,
      gm_raw_intl    + cp_intl    AS gm_intl,
      gm_raw_phys    + cp_phys    AS gm_phys,
      gm_raw_exem    + cp_exem    AS gm_exem,
      gm_raw_fanlive + cp_fanlive AS gm_fanlive,
      gm_raw_keylit  + cp_keylit  AS gm_keylit,

      eb_raw_na      + cp_na      AS eb_na,
      eb_raw_elim    + cp_elim    AS eb_elim,
      eb_raw_intl    + cp_intl    AS eb_intl,
      eb_raw_phys    + cp_phys    AS eb_phys,
      eb_raw_exem    + cp_exem    AS eb_exem,
      eb_raw_fanlive + cp_fanlive AS eb_fanlive,
      eb_raw_keylit  + cp_keylit  AS eb_keylit,

      -- Kept only so stage 4 can report the pre-correction figure side by side.
      gm_raw_na, gm_raw_elim, gm_raw_intl, gm_raw_phys,
      gm_raw_exem, gm_raw_fanlive, gm_raw_keylit,
      eb_raw_na, eb_raw_elim, eb_raw_intl, eb_raw_phys,
      eb_raw_exem, eb_raw_fanlive, eb_raw_keylit
  FROM wide
),


-- ---------------------------------------------------------------------------
-- STAGE 4 -- the deck's 26 rows  (transforms.ROWS)
-- ---------------------------------------------------------------------------
-- row_idx IS the deck's row index. The reference JSON and the variance badges
-- key on it, so never renumber.
--
-- shown_by_default = FALSE means the dashboard renders an em-dash until the
-- sidebar diagnostic toggle is on. blocked = TRUE means NO toggle releases it,
-- because the figure would be meaningless rather than merely off.
--
-- TWO GOTCHAS, both real and both easy to get backwards:
--
--  1. NORTH AMERICA IS FOLDED DIFFERENTLY IN THE TWO BLOCKS. Revenue row 0 and
--     Gross Margin row 7 use na + elim, because the deck folds Topps
--     Eliminations into North America revenue (4,074.8 - 121.5 = 3,953.3, its
--     exact printed value). EBITDA row 14 uses na ALONE, because the deck gives
--     Eliminations its own EBITDA row (16) -- folding there would double-count.
--
--  2. PERCENT ROWS APPLY THE SAME SEGMENT EXPRESSION TO BOTH SIDES. Row 7 is
--     gm(na + elim) / nr(na + elim), not a ratio of two differently-scoped
--     figures. IFF(den = 0, NULL, ...) mirrors the Python exactly: a zero
--     denominator yields NULL, never 0 and never a divide error.
statement AS (
  -- === Revenue -- rows 0-6. LIVE AND RECONCILED. Ties the deck to the cent at
  -- === all three grains for all 9 shared vintages. No correction applied.
  SELECT 0 AS row_idx, 'Revenue' AS section, 'North America' AS label,
         'sub' AS row_type, FALSE AS is_pct,
         nr_na + nr_elim AS value, nr_na + nr_elim AS value_precorrection,
         TRUE AS shown_by_default, FALSE AS blocked, '' AS gap_badges,
         'nr_na + nr_elim (elim FOLDED, deck convention)' AS expression,
         vintage_key, period, period_type, period_date, is_actual_month
  FROM corrected
  UNION ALL SELECT 1, 'Revenue', 'International', 'sub', FALSE,
         nr_intl, nr_intl, TRUE, FALSE, '', 'nr_intl',
         vintage_key, period, period_type, period_date, is_actual_month FROM corrected
  UNION ALL SELECT 2, 'Revenue', 'Total Physical Cards', 'subtotal', FALSE,
         nr_phys, nr_phys, TRUE, FALSE, '', 'nr_phys',
         vintage_key, period, period_type, period_date, is_actual_month FROM corrected
  -- Row 3 matches the deck to the cent TODAY, because Corporate has no revenue
  -- so the residual happens to be Digital alone. Still badged: the moment any
  -- Corporate revenue appears it is silently absorbed here with no other symptom.
  UNION ALL SELECT 3, 'Revenue', 'Digital', 'sub', FALSE,
         nr_exem - nr_phys, nr_exem - nr_phys, TRUE, FALSE, 'residual',
         'nr_exem - nr_phys (Digital AND Corporate combined)',
         vintage_key, period, period_type, period_date, is_actual_month FROM corrected
  UNION ALL SELECT 4, 'Revenue', 'Total ex-Emerging Svcs', 'subtotal', FALSE,
         nr_exem, nr_exem, TRUE, FALSE, '', 'nr_exem',
         vintage_key, period, period_type, period_date, is_actual_month FROM corrected
  UNION ALL SELECT 5, 'Revenue', 'Fanatics Collect', 'sub', FALSE,
         nr_fanlive, nr_fanlive, TRUE, FALSE, 'combined',
         'nr_fanlive (Live + Collect are ONE segment; deck reports Collect alone)',
         vintage_key, period, period_type, period_date, is_actual_month FROM corrected
  UNION ALL SELECT 6, 'Revenue', 'Total Revenue', 'total', FALSE,
         nr_exem + nr_fanlive + nr_keylit, nr_exem + nr_fanlive + nr_keylit,
         TRUE, FALSE, '', 'nr_exem + nr_fanlive + nr_keylit',
         vintage_key, period, period_type, period_date, is_actual_month FROM corrected

  -- === Gross Margin % -- rows 7-13. UNRECONCILED (corrected, still short in
  -- === actual months). Each row's basis is the Revenue row directly above it.
  UNION ALL SELECT 7, 'Gross Margin', 'North America', 'sub', TRUE,
         IFF(nr_na + nr_elim = 0, NULL, (gm_na + gm_elim) / (nr_na + nr_elim)),
         IFF(nr_na + nr_elim = 0, NULL, (gm_raw_na + gm_raw_elim) / (nr_na + nr_elim)),
         FALSE, FALSE, 'unreconciled', 'gm(na+elim) / nr(na+elim)',
         vintage_key, period, period_type, period_date, is_actual_month FROM corrected
  UNION ALL SELECT 8, 'Gross Margin', 'International', 'sub', TRUE,
         IFF(nr_intl = 0, NULL, gm_intl / nr_intl),
         IFF(nr_intl = 0, NULL, gm_raw_intl / nr_intl),
         FALSE, FALSE, 'unreconciled', 'gm_intl / nr_intl',
         vintage_key, period, period_type, period_date, is_actual_month FROM corrected
  UNION ALL SELECT 9, 'Gross Margin', 'Total Physical Cards', 'subtotal', TRUE,
         IFF(nr_phys = 0, NULL, gm_phys / nr_phys),
         IFF(nr_phys = 0, NULL, gm_raw_phys / nr_phys),
         FALSE, FALSE, 'unreconciled', 'gm_phys / nr_phys',
         vintage_key, period, period_type, period_date, is_actual_month FROM corrected
  -- BLOCKED. The expression exists but the residual it evaluates over is
  -- structurally broken: the source has ex-Emerging SMALLER than its own subset
  -- Physical Cards on 34 of 42 lines. For Jul. FC this computes a 108.5% gross
  -- margin against the deck's 35.6%, so it stays withheld even in diagnostics.
  UNION ALL SELECT 10, 'Gross Margin', 'Digital', 'sub', TRUE,
         NULL, NULL, FALSE, TRUE, 'unreconciled + broken residual',
         'WITHHELD -- would be gm(exem-phys) / nr(exem-phys)',
         vintage_key, period, period_type, period_date, is_actual_month FROM corrected
  UNION ALL SELECT 11, 'Gross Margin', 'Total ex-Emerging Svcs', 'subtotal', TRUE,
         IFF(nr_exem = 0, NULL, gm_exem / nr_exem),
         IFF(nr_exem = 0, NULL, gm_raw_exem / nr_exem),
         FALSE, FALSE, 'unreconciled', 'gm_exem / nr_exem',
         vintage_key, period, period_type, period_date, is_actual_month FROM corrected
  UNION ALL SELECT 12, 'Gross Margin', 'Fanatics Collect', 'sub', TRUE,
         IFF(nr_fanlive = 0, NULL, gm_fanlive / nr_fanlive),
         IFF(nr_fanlive = 0, NULL, gm_raw_fanlive / nr_fanlive),
         FALSE, FALSE, 'unreconciled', 'gm_fanlive / nr_fanlive',
         vintage_key, period, period_type, period_date, is_actual_month FROM corrected
  UNION ALL SELECT 13, 'Gross Margin', 'Total Gross Margin', 'total', TRUE,
         IFF(nr_exem + nr_fanlive + nr_keylit = 0, NULL,
             (gm_exem + gm_fanlive + gm_keylit) / (nr_exem + nr_fanlive + nr_keylit)),
         IFF(nr_exem + nr_fanlive + nr_keylit = 0, NULL,
             (gm_raw_exem + gm_raw_fanlive + gm_raw_keylit) / (nr_exem + nr_fanlive + nr_keylit)),
         FALSE, FALSE, 'unreconciled',
         'gm(exem+fanlive+keylit) / nr(exem+fanlive+keylit)',
         vintage_key, period, period_type, period_date, is_actual_month FROM corrected

  -- === EBITDA -- rows 14-24. UNRECONCILED. NOTE: na is NOT folded with elim
  -- === here (row 16 carries Eliminations separately).
  UNION ALL SELECT 14, 'EBITDA', 'North America', 'sub', FALSE,
         eb_na, eb_raw_na, FALSE, FALSE, 'unreconciled',
         'eb_na (NOT folded with elim -- see row 16)',
         vintage_key, period, period_type, period_date, is_actual_month FROM corrected
  UNION ALL SELECT 15, 'EBITDA', 'International', 'sub', FALSE,
         eb_intl, eb_raw_intl, FALSE, FALSE, 'unreconciled', 'eb_intl',
         vintage_key, period, period_type, period_date, is_actual_month FROM corrected
  UNION ALL SELECT 16, 'EBITDA', 'Eliminations', 'sub', FALSE,
         eb_elim, eb_raw_elim, FALSE, FALSE, 'unreconciled + Topps only',
         'eb_elim (Topps is the ONLY elimination segment; deck''s line is unified)',
         vintage_key, period, period_type, period_date, is_actual_month FROM corrected
  UNION ALL SELECT 17, 'EBITDA', 'Total Physical Cards', 'subtotal', FALSE,
         eb_phys, eb_raw_phys, FALSE, FALSE, 'unreconciled', 'eb_phys',
         vintage_key, period, period_type, period_date, is_actual_month FROM corrected
  -- BLOCKED, same broken residual as row 10. EBITDA violates containment in
  -- 180 of 181 period-cells, worst -$179.4M: this computes -$179.4M against
  -- the deck's +$9.4M.
  UNION ALL SELECT 18, 'EBITDA', 'Digital', 'sub', FALSE,
         NULL, NULL, FALSE, TRUE, 'unreconciled + residual + broken residual',
         'WITHHELD -- would be eb_exem - eb_phys',
         vintage_key, period, period_type, period_date, is_actual_month FROM corrected
  -- NO EXPRESSION AT ALL. The source carries no Corporate segment at any grain.
  UNION ALL SELECT 19, 'EBITDA', 'Corporate', 'sub', FALSE,
         NULL, NULL, FALSE, TRUE, 'unreconciled + residual',
         'NO SEGMENT EXISTS -- unreproducible by construction',
         vintage_key, period, period_type, period_date, is_actual_month FROM corrected
  UNION ALL SELECT 20, 'EBITDA', 'Total ex-Emerging Svcs', 'subtotal', FALSE,
         eb_exem, eb_raw_exem, FALSE, FALSE, 'unreconciled', 'eb_exem',
         vintage_key, period, period_type, period_date, is_actual_month FROM corrected
  UNION ALL SELECT 21, 'EBITDA', 'Fanatics Collect', 'sub', FALSE,
         eb_fanlive, eb_raw_fanlive, FALSE, FALSE, 'unreconciled + combined',
         'eb_fanlive', vintage_key, period, period_type, period_date, is_actual_month FROM corrected
  -- Row 22 was a candidate to ship UNFLAGGED -- it ties to the cent for
  -- Jul. FC. The ROW 22 gate in tools/validate_vs_deck.py proved that holds for
  -- only 5 of 9 shared vintages (2025A ties annually but not sub-annually; the
  -- deck's Jan/Feb/Mar FC columns carry the stale 2026 BUDGET figure), so it
  -- keeps its badge.
  UNION ALL SELECT 22, 'EBITDA', 'Key Litigation Costs', 'sub', FALSE,
         eb_keylit, eb_raw_keylit, FALSE, FALSE, 'unreconciled', 'eb_keylit',
         vintage_key, period, period_type, period_date, is_actual_month FROM corrected
  -- NO EXPRESSION AT ALL. No TCG segment exists in the source.
  UNION ALL SELECT 23, 'EBITDA', 'TCG', 'sub', FALSE,
         NULL, NULL, FALSE, TRUE, 'unreconciled + no segment',
         'NO SEGMENT EXISTS -- unreproducible by construction',
         vintage_key, period, period_type, period_date, is_actual_month FROM corrected
  -- The KPI tile figure. Jul. FC annual: raw $1,409.7M -> corrected $1,855.3M.
  -- The app's var-badge here reads -125.9M because it compares against DECK
  -- row 24, which INCLUDES TCG ($1,981.1M). The like-for-like basis is deck
  -- rows 20+21+22, giving -$138.0M. Both are correct for their basis.
  UNION ALL SELECT 24, 'EBITDA', 'Total EBITDA', 'total', FALSE,
         eb_exem + eb_fanlive + eb_keylit,
         eb_raw_exem + eb_raw_fanlive + eb_raw_keylit,
         FALSE, FALSE, 'unreconciled', 'eb_exem + eb_fanlive + eb_keylit',
         vintage_key, period, period_type, period_date, is_actual_month FROM corrected

  -- === EBITDA Margin % -- row 25. The deck prints no section header for this
  -- === single-row section.
  UNION ALL SELECT 25, 'EBITDA Margin', 'EBITDA Margin', 'margin', TRUE,
         IFF(nr_exem + nr_fanlive + nr_keylit = 0, NULL,
             (eb_exem + eb_fanlive + eb_keylit) / (nr_exem + nr_fanlive + nr_keylit)),
         IFF(nr_exem + nr_fanlive + nr_keylit = 0, NULL,
             (eb_raw_exem + eb_raw_fanlive + eb_raw_keylit) / (nr_exem + nr_fanlive + nr_keylit)),
         FALSE, FALSE, 'unreconciled',
         'eb(exem+fanlive+keylit) / nr(exem+fanlive+keylit)',
         vintage_key, period, period_type, period_date, is_actual_month FROM corrected
)


-- ---------------------------------------------------------------------------
-- OUTPUT -- the statement as rendered
-- ---------------------------------------------------------------------------
-- display_value reproduces the deck's formatters (transforms.fmt_m / fmt_pct):
-- dollars in whole millions with negatives parenthesised, percents to whole
-- percent. Both use ROUND HALF UP, which is JavaScript's Math.round -- Snowflake
-- ROUND() and the deck agree; Python's round() does NOT (it rounds half to
-- EVEN), which is why transforms.round_half_up exists.
--
-- Change the two filters below to move around:
--   vintage_key  '2025A' | '2026B' | '2026A' | 'Oct 2025 FC' .. 'Sep 2026 FC'
--   period_type  'YEAR' | 'QUARTER' | 'MONTH'
SELECT
    row_idx,
    section,
    label,
    row_type,
    gap_badges,
    expression,
    CASE
      WHEN blocked THEN '(withheld)'
      WHEN value IS NULL THEN '--'
      WHEN is_pct THEN TO_VARCHAR(ROUND(value * 100, 0)) || '%'
      -- TRIM because TO_VARCHAR with a format model left-pads to the mask width.
      WHEN value < 0 THEN '(' || TRIM(TO_VARCHAR(ROUND(ABS(value) / 1e6, 0), '999,999,999')) || ')'
      ELSE TRIM(TO_VARCHAR(ROUND(value / 1e6, 0), '999,999,999'))
    END                                              AS display_value,
    -- What the dashboard ACTUALLY shows: default hides every unreconciled row.
    IFF(blocked OR NOT shown_by_default, '--', 'shown') AS default_state,
    -- Dollar rows and percent rows are reported in separate columns on purpose.
    -- A ratio divided by 1e6 rounds to 0.0, which reads as a real zero -- so
    -- each column is NULL where it does not apply rather than misleadingly 0.
    IFF(is_pct, NULL, ROUND(value / 1e6, 1))                    AS value_m,
    IFF(is_pct, ROUND(value * 100, 2), NULL)                    AS value_pct,
    IFF(is_pct, NULL, ROUND(value_precorrection / 1e6, 1))      AS precorr_m,
    IFF(is_pct, ROUND(value_precorrection * 100, 2), NULL)      AS precorr_pct,
    -- The Compensation correction's effect on this row: dollars for dollar
    -- rows, basis points for percent rows (the deck's own unit for pct deltas).
    IFF(is_pct, NULL, ROUND((value - value_precorrection) / 1e6, 1))     AS comp_effect_m,
    IFF(is_pct, ROUND((value - value_precorrection) * 10000, 0), NULL)   AS comp_effect_bps
FROM statement
WHERE vintage_key = 'Jul 2026 FC'
  AND period_type = 'YEAR'
ORDER BY row_idx
