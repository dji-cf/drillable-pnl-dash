"""Product Revenue (NA) -- the 5th top tab of the Collectibles Financial Dashboard.

Net Revenue excluding intercompany, by license > product release (COA), by
month / quarter / FY. North America only: the GM plan (Sep 2026 FC, SEP26RF)
covers entity CO_31010 (NASE), LOB LB_312 and nothing else. Requested by Megan
Coleman (FP&A); see docs/fleet/cfd-prodrev-na.md for the tie-out to her file.

- FY26 months come from GMPLN_PRODUCT_RELEASE_BY_COA_MONTHLY_V (the view behind
  Megan's "Product Release" file; ties to her FY26 4,086,943,019.71 exactly).
- Later FYs come from GMPLN_PL_BY_SKU_CHANNEL_V: Net Revenue minus
  Intercompany Revenue, 12 real months only.
- GMPLN has no license. Each COA takes the PRICING_LICENSE of its SKUs
  (DESA_SILVER.PRICING.SKU, first 9 chars of the base SKU); COAs with no match
  are kept under "(No license)".
"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

import data
import prodrev_viz as viz

NO_LICENSE = "(No license)"
TOTAL = "Total"
PENDING = "PENDING"
# Megan's size tiers per COA per quarter ($): <10M, 10-25M, 25-35M, 35-50M,
# >=50M = Tentpole. Edges above 35M not confirmed by Megan yet.
TIER_EDGES = (10e6, 25e6, 35e6, 50e6)
TIER_NOTE = f"{PENDING} - Megan Coleman: confirm size-tier edges above $35M (35-50M, Tentpole >= 50M)."
# Hedge COAs (e.g. 10517 "NBA - Hedge"): "other" keeps them inside Other (today's
# numbers); "own_block" draws them as a separate "Hedge" block below Other.
HEDGE_MODE = "other"  # "other" | "own_block"
HEDGE_NOTE = f"{PENDING} - Megan Coleman: hedge COAs in Other or own Hedge block?"
# Design default (nobody specified): bar labels only on segments >= 3% of the
# bar; every segment keeps a tooltip.
LABEL_MIN_SHARE = 0.03  # PENDING - Megan Coleman: label threshold

PRODUCT_REVENUE_SQL = """
WITH px AS (
    SELECT LEFT(sku, 9) AS sku9, MAX(pricing_license) AS license
    FROM DESA_SILVER.PRICING.SKU
    WHERE pricing_license IS NOT NULL
    GROUP BY 1
),
sku_rev AS (
    SELECT v.coa, v.fiscal_year, v.period_date, px.license,
           SUM(IFF(v.acx_line = 'ACX_Net Revenue', v.amount, -v.amount)) AS net_rev
    FROM ORACLE_DATA_PROD.FCT_EPM.GMPLN_PL_BY_SKU_CHANNEL_V v
    LEFT JOIN px ON LEFT(SPLIT_PART(v.sku, '-', 1), 9) = px.sku9
    WHERE v.scenario = 'SEP26RF' AND v.version = 'Final'
      AND v.entity = 'CO_31010' AND v.lob = 'LB_312'
      AND v.month IN ('Jan','Feb','Mar','Apr','May','Jun',
                      'Jul','Aug','Sep','Oct','Nov','Dec')
      AND v.acx_line IN ('ACX_Net Revenue', 'ACX_Intercompany Revenue')
    GROUP BY 1, 2, 3, 4
),
coa_license AS (
    SELECT coa, license FROM (
        SELECT coa, license, SUM(ABS(net_rev)) AS w
        FROM sku_rev WHERE license IS NOT NULL GROUP BY 1, 2)
    QUALIFY ROW_NUMBER() OVER (PARTITION BY coa ORDER BY w DESC, license) = 1
),
rel AS (
    SELECT coa, product_name,
           netrev_jan26, netrev_feb26, netrev_mar26, netrev_apr26,
           netrev_may26, netrev_jun26, netrev_jul26, netrev_aug26,
           netrev_sep26, netrev_oct26, netrev_nov26, netrev_dec26
    FROM ORACLE_DATA_PROD.FCT_EPM.GMPLN_PRODUCT_RELEASE_BY_COA_MONTHLY_V
    WHERE forecast_asof = 'SEP26RF' AND current_fy = 'FY26'
),
fy26 AS (
    SELECT coa, 'FY26' AS fiscal_year,
           DATE_FROM_PARTS(2026, TO_NUMBER(DECODE(mon,
               'NETREV_JAN26', 1, 'NETREV_FEB26', 2, 'NETREV_MAR26', 3,
               'NETREV_APR26', 4, 'NETREV_MAY26', 5, 'NETREV_JUN26', 6,
               'NETREV_JUL26', 7, 'NETREV_AUG26', 8, 'NETREV_SEP26', 9,
               'NETREV_OCT26', 10, 'NETREV_NOV26', 11, 'NETREV_DEC26', 12)), 1)
               AS period_date,
           net_rev
    FROM rel UNPIVOT (net_rev FOR mon IN (
        netrev_jan26, netrev_feb26, netrev_mar26, netrev_apr26,
        netrev_may26, netrev_jun26, netrev_jul26, netrev_aug26,
        netrev_sep26, netrev_oct26, netrev_nov26, netrev_dec26))
),
later AS (
    SELECT coa, fiscal_year, period_date, SUM(net_rev) AS net_rev
    FROM sku_rev WHERE fiscal_year = 'FY27' GROUP BY 1, 2, 3
),
allrev AS (SELECT * FROM fy26 UNION ALL SELECT * FROM later)
SELECT COALESCE(l.license, '(No license)') AS license,
       a.coa,
       COALESCE(r.product_name, a.coa) AS product_name,
       a.fiscal_year,
       a.period_date,
       SUM(a.net_rev) AS net_rev
FROM allrev a
LEFT JOIN coa_license l ON l.coa = a.coa
LEFT JOIN rel r ON r.coa = a.coa
WHERE a.net_rev <> 0
GROUP BY 1, 2, 3, 4, 5
ORDER BY 1, 2, 5
"""

# --- PRICING_SKU_V workaround (same pattern as Hyder hyd-pricing-sku-remap) ---
# 2026-11-13 SC_W_FCT_EPM rebuilt FCT_EPM.PRICING_SKU (61 cols) but not the
# SELECT * view PRICING_SKU_V (45 cols), so every view on top of it fails with
# 002057. Chain: GMPLN_PRODUCT_RELEASE_BY_COA_MONTHLY_V -> PRODUCT_RELEASE_BY_COA_V
# -> PRODUCT_RELEASE_SKU_V -> PRICING_SKU_V. Below: verbatim copies of those three
# view bodies (GET_DDL 2026-11-17), with PRICING_SKU_V -> PRICING_SKU (explicit
# columns). Used only when the real view fails with 002057; no logic change.
BROKEN_VIEW_ERROR = "002057"

_LOCAL_PRODUCT_RELEASE_SKU_V = """(
WITH years AS (
  SELECT 'FY'||yy AS cur_fy, 'FY'||TO_VARCHAR((yy::int)+1) AS next_fy FROM (
    SELECT SUBSTR(forecast_asof,4,2) AS yy
    FROM ORACLE_DATA_PROD.FCT_EPM.GMPLN_REVENUE_FORECAST_HISTORY
    WHERE forecast_asof RLIKE '^[A-Z]{3}[0-9]{2}RF$'
    QUALIFY ROW_NUMBER() OVER (ORDER BY forecast_asof_date DESC NULLS LAST, forecast_asof DESC) = 1
  )
),
h AS (
  SELECT fh.forecast_asof, fh.sku, fh.fiscal_year AS fy, fh.month AS mth,
         fh.net_rev_ex_interco AS netrev, fh.cm, fh.volume_cases AS vol
  FROM ORACLE_DATA_PROD.FCT_EPM.GMPLN_REVENUE_FORECAST_HISTORY fh
  JOIN years y ON fh.fiscal_year >= y.cur_fy
  WHERE fh.grain='BY_SKU'
),
agg AS (
  SELECT h.forecast_asof, h.sku,
    SUM(IFF(h.fy=y.cur_fy AND h.mth='Q1',netrev,0)) fcst_q1,
    SUM(IFF(h.fy=y.cur_fy AND h.mth='Q2',netrev,0)) fcst_q2,
    SUM(IFF(h.fy=y.cur_fy AND h.mth='Q3',netrev,0)) fcst_q3,
    SUM(IFF(h.fy=y.cur_fy AND h.mth='Q4',netrev,0)) fcst_q4,
    SUM(IFF(h.fy=y.cur_fy AND h.mth='YearTotal',netrev,0)) fcst_cur_fy,
    SUM(IFF(h.fy=y.next_fy AND h.mth='YearTotal',netrev,0)) fcst_next_fy,
    SUM(IFF(h.mth='YearTotal',netrev,0)) fcst_lifetime,
    SUM(IFF(h.fy=y.cur_fy AND h.mth='YearTotal',cm,0)) cm_cur_fy,
    SUM(IFF(h.fy=y.next_fy AND h.mth='YearTotal',cm,0)) cm_next_fy,
    SUM(IFF(h.mth='YearTotal',h.cm,0)) cm_lifetime,
    SUM(IFF(h.fy=y.cur_fy AND h.mth='YearTotal',vol,0)) vol_cur_fy,
    SUM(IFF(h.fy=y.next_fy AND h.mth='YearTotal',vol,0)) vol_next_fy,
    SUM(IFF(h.mth='YearTotal',h.vol,0)) vol_lifetime
  FROM h CROSS JOIN years y GROUP BY h.forecast_asof, h.sku
),
bud AS (
  SELECT sku, SUM(net_rev_ex_interco) budget, SUM(cm) budget_cm
  FROM ORACLE_DATA_PROD.FCT_EPM.GMPLN_BUDGET
  WHERE grain='BY_SKU'
    AND budget_version = (SELECT MAX(budget_version) FROM ORACLE_DATA_PROD.FCT_EPM.GMPLN_BUDGET)
  GROUP BY sku
),
lp AS (SELECT item_number, MAX(chart_of_accounts) coa, MAX(product_name) product_name
       FROM ORACLE_DATA_PROD.FCT_EPM.LAUNCHPAD_SKUS_V GROUP BY item_number),
pr AS (SELECT PRICING_COA coa, MIN(PRICING_STREET_DATE) street_date, MAX(PRICING_PRODUCT_NAME) nm
       FROM ORACLE_DATA_PROD.FCT_EPM.PRICING_SKU GROUP BY PRICING_COA),
lsd AS (SELECT chart_of_accounts AS coa, MIN(street_date) AS street_date
        FROM ORACLE_DATA_PROD.FCT_EPM.LAUNCHPAD_SKUS_V WHERE chart_of_accounts IS NOT NULL GROUP BY chart_of_accounts),
vs AS (SELECT value AS coa, MAX(description) AS nm
       FROM ORACLE_DATA_PROD.FCT_CMN.FND_VS_VALUES_VL WHERE valuesetid=81006 GROUP BY value),
prior AS (
  SELECT coa, py_netrev, py_cm
  FROM ORACLE_DATA_PROD.FCT_EPM.PRODUCT_COA_LIFETIME_PY_V
)
SELECT
  a.forecast_asof, a.sku,
  COALESCE(CASE WHEN a.sku LIKE 'APP%' THEN 'APR0101' WHEN a.sku LIKE 'PLS%' THEN 'SUP2301' END, lp.coa, REGEXP_SUBSTR(a.sku,'PG_([0-9]+)',1,1,'e',1), 'UNKNOWN') AS coa,
  COALESCE(lp.product_name, pr.nm, vs.nm) AS product_name,
  COALESCE(pr.street_date, lsd.street_date)::DATE AS street_date,
  (SELECT cur_fy FROM years) AS current_fy,
  a.fcst_q1, a.fcst_q2, a.fcst_q3, a.fcst_q4, a.fcst_cur_fy, a.fcst_next_fy, a.fcst_lifetime,
  b.budget,
  a.cm_cur_fy, a.cm_next_fy, a.cm_lifetime, b.budget_cm,
  a.vol_cur_fy, a.vol_next_fy, a.vol_lifetime,
  prior.py_netrev, prior.py_cm,
  ROUND(100*a.cm_lifetime/NULLIF(a.fcst_lifetime,0),1) AS lifetime_cm_pct,
  ROUND(100*b.budget_cm  /NULLIF(b.budget,0),1)        AS budget_cm_pct,
  IFF(prior.py_netrev>0, ROUND(100*prior.py_cm/NULLIF(prior.py_netrev,0),1), NULL) AS py_cm_pct
FROM agg a
LEFT JOIN bud b ON b.sku = a.sku
LEFT JOIN lp   ON lp.item_number = a.sku
LEFT JOIN pr   ON pr.coa    = COALESCE(CASE WHEN a.sku LIKE 'APP%' THEN 'APR0101' WHEN a.sku LIKE 'PLS%' THEN 'SUP2301' END, lp.coa, REGEXP_SUBSTR(a.sku,'PG_([0-9]+)',1,1,'e',1), 'UNKNOWN')
LEFT JOIN lsd  ON lsd.coa   = COALESCE(CASE WHEN a.sku LIKE 'APP%' THEN 'APR0101' WHEN a.sku LIKE 'PLS%' THEN 'SUP2301' END, lp.coa, REGEXP_SUBSTR(a.sku,'PG_([0-9]+)',1,1,'e',1), 'UNKNOWN')
LEFT JOIN vs   ON vs.coa    = COALESCE(CASE WHEN a.sku LIKE 'APP%' THEN 'APR0101' WHEN a.sku LIKE 'PLS%' THEN 'SUP2301' END, lp.coa, REGEXP_SUBSTR(a.sku,'PG_([0-9]+)',1,1,'e',1), 'UNKNOWN')
LEFT JOIN prior ON prior.coa = COALESCE(CASE WHEN a.sku LIKE 'APP%' THEN 'APR0101' WHEN a.sku LIKE 'PLS%' THEN 'SUP2301' END, lp.coa, REGEXP_SUBSTR(a.sku,'PG_([0-9]+)',1,1,'e',1), 'UNKNOWN')
)"""

_LOCAL_PRODUCT_RELEASE_BY_COA_V = """(
WITH bud AS (
  SELECT COALESCE(CASE WHEN gb.sku LIKE 'APP%' THEN 'APR0101'
                       WHEN gb.sku LIKE 'PLS%' THEN 'SUP2301' END,
                  lp.coa,
                  REGEXP_SUBSTR(gb.sku,'PG_([0-9]+)',1,1,'e',1),
                  'UNKNOWN') AS coa,
         SUM(gb.net_rev_ex_interco) AS budget, SUM(gb.cm) AS budget_cm
  FROM ORACLE_DATA_PROD.FCT_EPM.GMPLN_BUDGET gb
  LEFT JOIN (SELECT item_number, MAX(chart_of_accounts) AS coa
             FROM ORACLE_DATA_PROD.FCT_EPM.LAUNCHPAD_SKUS_V GROUP BY item_number) lp
    ON lp.item_number = gb.sku
  WHERE gb.grain='BY_SKU'
    AND gb.budget_version = (SELECT MAX(budget_version) FROM ORACLE_DATA_PROD.FCT_EPM.GMPLN_BUDGET)
  GROUP BY 1
),
lpv AS (SELECT coa, lifetime_netrev, lifetime_cm, py_netrev, py_cm
        FROM ORACLE_DATA_PROD.FCT_EPM.PRODUCT_COA_LIFETIME_PY_V),
mkt AS (SELECT coa, marketing_2026_fcst m FROM ORACLE_DATA_PROD.FCT_EPM.FC_MARKETING_COA),
latest AS (
  SELECT forecast_asof FROM ORACLE_DATA_PROD.FCT_EPM.GMPLN_REVENUE_FORECAST_HISTORY
  WHERE forecast_asof RLIKE '^[A-Z]{3}[0-9]{2}RF$'
  QUALIFY ROW_NUMBER() OVER (ORDER BY forecast_asof_date DESC NULLS LAST, forecast_asof DESC)=1
)
SELECT
    v.forecast_asof,
    v.coa,
    MAX(v.product_name) AS product_name,
    COALESCE(MAX(sd.fc_street_date), MIN(v.street_date)) AS street_date,
    COUNT(*)            AS sku_count,
    MAX(v.current_fy)   AS current_fy,
    IFF(COALESCE(MAX(sd.fc_street_date), MIN(v.street_date)) IS NULL, NULL,
        'Q'||QUARTER(COALESCE(MAX(sd.fc_street_date), MIN(v.street_date)))||''''||
        RIGHT(YEAR(COALESCE(MAX(sd.fc_street_date), MIN(v.street_date)))::string,2)) AS quarter,
    SUM(v.fcst_q1) AS fcst_q1, SUM(v.fcst_q2) AS fcst_q2, SUM(v.fcst_q3) AS fcst_q3, SUM(v.fcst_q4) AS fcst_q4,
    SUM(v.fcst_cur_fy) AS fcst_cur_fy, SUM(v.fcst_next_fy) AS fcst_next_fy, SUM(v.fcst_lifetime) AS fcst_lifetime,
    MAX(bud.budget)      AS budget,
    MAX(lpv.py_netrev)   AS py_netrev,
    MAX(lpv.lifetime_netrev) AS lifetime,
    SUM(v.cm_cur_fy) - COALESCE(MAX(mkt.m),0) AS cm_cur_fy, SUM(v.cm_next_fy) AS cm_next_fy, SUM(v.cm_lifetime) AS cm_lifetime,
    SUM(v.vol_cur_fy) AS vol_cur_fy, SUM(v.vol_next_fy) AS vol_next_fy, SUM(v.vol_lifetime) AS vol_lifetime,
    MAX(bud.budget_cm)   AS budget_cm,
    MAX(lpv.py_cm)       AS py_cm,
    MAX(lpv.lifetime_cm) - COALESCE(MAX(mkt.m),0) AS lifetime_cm,
    ROUND(100*(MAX(lpv.lifetime_cm)-COALESCE(MAX(mkt.m),0))/NULLIF(MAX(lpv.lifetime_netrev),0),1) AS cm_pct,
    ROUND(100*MAX(bud.budget_cm)/NULLIF(MAX(bud.budget),0),1)            AS b_pct,
    IFF(MAX(lpv.py_netrev)>0, ROUND(100*MAX(lpv.py_cm)/NULLIF(MAX(lpv.py_netrev),0),1), NULL) AS py_pct,
    ROUND(100*(MAX(lpv.lifetime_cm)-COALESCE(MAX(mkt.m),0))/NULLIF(MAX(lpv.lifetime_netrev),0),1)
      - ROUND(100*MAX(bud.budget_cm)/NULLIF(MAX(bud.budget),0),1) AS vs_budget_pct,
    MAX(sd.pfc_street_date)    AS pfc_street_date,
    MAX(sd.budget_street_date) AS budget_street_date
FROM ORACLE_DATA_PROD.FCT_EPM.PRODUCT_RELEASE_SKU_V v
LEFT JOIN bud ON bud.coa = v.coa
LEFT JOIN lpv ON lpv.coa = v.coa
LEFT JOIN mkt ON mkt.coa = v.coa
LEFT JOIN ORACLE_DATA_PROD.FCT_EPM.FC_STREET_DATE_MASTER sd ON sd.coa = v.coa
WHERE v.coa IS NOT NULL
GROUP BY v.forecast_asof, v.coa

UNION ALL

SELECT
    (SELECT forecast_asof FROM latest) AS forecast_asof,
    lpv.coa,
    NULL AS product_name,
    sd.fc_street_date AS street_date,
    0 AS sku_count,
    (SELECT DISTINCT current_fy FROM ORACLE_DATA_PROD.FCT_EPM.PRODUCT_RELEASE_SKU_V LIMIT 1) AS current_fy,
    IFF(sd.fc_street_date IS NULL, NULL,
        'Q'||QUARTER(sd.fc_street_date)||''''||RIGHT(YEAR(sd.fc_street_date)::string,2)) AS quarter,
    0,0,0,0, 0,0,0,
    bud.budget AS budget,
    lpv.py_netrev,
    lpv.lifetime_netrev AS lifetime,
    (0 - COALESCE(mkt.m,0)),0,0, 0,0,0,
    bud.budget_cm AS budget_cm,
    lpv.py_cm,
    lpv.lifetime_cm - COALESCE(mkt.m,0),
    ROUND(100*(lpv.lifetime_cm-COALESCE(mkt.m,0))/NULLIF(lpv.lifetime_netrev,0),1) AS cm_pct,
    ROUND(100*bud.budget_cm/NULLIF(bud.budget,0),1) AS b_pct,
    IFF(lpv.py_netrev>0, ROUND(100*lpv.py_cm/NULLIF(lpv.py_netrev,0),1), NULL) AS py_pct,
    ROUND(100*(lpv.lifetime_cm-COALESCE(mkt.m,0))/NULLIF(lpv.lifetime_netrev,0),1)
      - ROUND(100*bud.budget_cm/NULLIF(bud.budget,0),1) AS vs_budget_pct,
    sd.pfc_street_date, sd.budget_street_date
FROM lpv
LEFT JOIN bud ON bud.coa = lpv.coa
LEFT JOIN mkt ON mkt.coa = lpv.coa
LEFT JOIN ORACLE_DATA_PROD.FCT_EPM.FC_STREET_DATE_MASTER sd ON sd.coa = lpv.coa
WHERE lpv.coa NOT IN (
    SELECT DISTINCT coa FROM ORACLE_DATA_PROD.FCT_EPM.PRODUCT_RELEASE_SKU_V
    WHERE forecast_asof=(SELECT forecast_asof FROM latest) AND coa IS NOT NULL)

UNION ALL

SELECT
    (SELECT forecast_asof FROM latest) AS forecast_asof,
    bud.coa,
    NULL AS product_name,
    sd.fc_street_date AS street_date,
    0 AS sku_count,
    (SELECT DISTINCT current_fy FROM ORACLE_DATA_PROD.FCT_EPM.PRODUCT_RELEASE_SKU_V LIMIT 1) AS current_fy,
    IFF(sd.fc_street_date IS NULL, NULL,
        'Q'||QUARTER(sd.fc_street_date)||''''||RIGHT(YEAR(sd.fc_street_date)::string,2)) AS quarter,
    0,0,0,0, 0,0,0,
    bud.budget AS budget,
    NULL AS py_netrev,
    NULL AS lifetime,
    0,0,0, 0,0,0,
    bud.budget_cm AS budget_cm,
    NULL AS py_cm,
    NULL AS lifetime_cm,
    NULL AS cm_pct,
    ROUND(100*bud.budget_cm/NULLIF(bud.budget,0),1) AS b_pct,
    NULL AS py_pct,
    NULL AS vs_budget_pct,
    sd.pfc_street_date, sd.budget_street_date
FROM bud
LEFT JOIN ORACLE_DATA_PROD.FCT_EPM.FC_STREET_DATE_MASTER sd ON sd.coa = bud.coa
WHERE bud.coa NOT IN (
    SELECT DISTINCT coa FROM ORACLE_DATA_PROD.FCT_EPM.PRODUCT_RELEASE_SKU_V
    WHERE forecast_asof=(SELECT forecast_asof FROM latest) AND coa IS NOT NULL)
  AND bud.coa NOT IN (SELECT coa FROM lpv)
  AND ABS(bud.budget) >= 1
)""".replace("ORACLE_DATA_PROD.FCT_EPM.PRODUCT_RELEASE_SKU_V", "local_product_release_sku_v")

_LOCAL_GMPLN_PRODUCT_RELEASE_BY_COA_MONTHLY_V = """(
WITH latest AS (
  SELECT forecast_asof AS fa
  FROM ORACLE_DATA_PROD.FCT_EPM.GMPLN_REVENUE_FORECAST_HISTORY
  WHERE forecast_asof RLIKE '^[A-Z]{3}[0-9]{2}RF$'
  QUALIFY ROW_NUMBER() OVER (ORDER BY forecast_asof_date DESC NULLS LAST, forecast_asof DESC) = 1
),
lp AS (SELECT item_number, MAX(chart_of_accounts) AS coa
       FROM ORACLE_DATA_PROD.FCT_EPM.LAUNCHPAD_SKUS_V GROUP BY item_number),
mo AS (
  SELECT COALESCE(CASE WHEN fh.sku LIKE 'APP%' THEN 'APR0101'
                       WHEN fh.sku LIKE 'PLS%' THEN 'SUP2301' END,
                  lp.coa,
                  REGEXP_SUBSTR(fh.sku,'PG_([0-9]+)',1,1,'e',1),
                  'UNKNOWN') AS coa,
         SUM(IFF(fh.month='Jan', fh.net_rev_ex_interco, 0)) AS mrev_jan26,
         SUM(IFF(fh.month='Feb', fh.net_rev_ex_interco, 0)) AS mrev_feb26,
         SUM(IFF(fh.month='Mar', fh.net_rev_ex_interco, 0)) AS mrev_mar26,
         SUM(IFF(fh.month='Apr', fh.net_rev_ex_interco, 0)) AS mrev_apr26,
         SUM(IFF(fh.month='May', fh.net_rev_ex_interco, 0)) AS mrev_may26,
         SUM(IFF(fh.month='Jun', fh.net_rev_ex_interco, 0)) AS mrev_jun26,
         SUM(IFF(fh.month='Jul', fh.net_rev_ex_interco, 0)) AS mrev_jul26,
         SUM(IFF(fh.month='Aug', fh.net_rev_ex_interco, 0)) AS mrev_aug26,
         SUM(IFF(fh.month='Sep', fh.net_rev_ex_interco, 0)) AS mrev_sep26,
         SUM(IFF(fh.month='Oct', fh.net_rev_ex_interco, 0)) AS mrev_oct26,
         SUM(IFF(fh.month='Nov', fh.net_rev_ex_interco, 0)) AS mrev_nov26,
         SUM(IFF(fh.month='Dec', fh.net_rev_ex_interco, 0)) AS mrev_dec26
  FROM ORACLE_DATA_PROD.FCT_EPM.GMPLN_REVENUE_FORECAST_HISTORY fh
  JOIN latest y ON fh.forecast_asof = y.fa
  LEFT JOIN lp ON lp.item_number = fh.sku
  WHERE fh.grain = 'BY_SKU' AND fh.fiscal_year = 'FY26'
  GROUP BY 1
)
SELECT
    r.FORECAST_ASOF, r.COA, r.PRODUCT_NAME,
    r.STREET_DATE, r.PFC_STREET_DATE, r.BUDGET_STREET_DATE, r.SKU_COUNT, r.CURRENT_FY, r.QUARTER,
    mo.mrev_jan26 AS NETREV_JAN26, mo.mrev_feb26 AS NETREV_FEB26, mo.mrev_mar26 AS NETREV_MAR26,
    mo.mrev_apr26 AS NETREV_APR26, mo.mrev_may26 AS NETREV_MAY26, mo.mrev_jun26 AS NETREV_JUN26,
    mo.mrev_jul26 AS NETREV_JUL26, mo.mrev_aug26 AS NETREV_AUG26, mo.mrev_sep26 AS NETREV_SEP26,
    mo.mrev_oct26 AS NETREV_OCT26, mo.mrev_nov26 AS NETREV_NOV26, mo.mrev_dec26 AS NETREV_DEC26,
    r.FCST_Q1, r.FCST_Q2, r.FCST_Q3, r.FCST_Q4,
    r.FCST_CUR_FY, r.FCST_NEXT_FY, r.FCST_LIFETIME,
    r.BUDGET, r.PY_NETREV, r.LIFETIME,
    r.CM_CUR_FY, r.CM_NEXT_FY, r.CM_LIFETIME,
    r.BUDGET_CM, r.PY_CM, r.LIFETIME_CM,
    r.CM_PCT, r.B_PCT, r.PY_PCT, r.VS_BUDGET_PCT,
    r.VOL_CUR_FY, r.VOL_NEXT_FY, r.VOL_LIFETIME
FROM ORACLE_DATA_PROD.FCT_EPM.PRODUCT_RELEASE_BY_COA_V r
JOIN latest y ON r.FORECAST_ASOF = y.fa
LEFT JOIN mo ON mo.coa = r.COA
)""".replace("ORACLE_DATA_PROD.FCT_EPM.PRODUCT_RELEASE_BY_COA_V", "local_product_release_by_coa_v")

# Sibling CTEs, not nested subqueries: nested, the outer "lp" CTE shadows the
# inner one (invalid identifier LP.PRODUCT_NAME).
PRODUCT_REVENUE_LOCAL_SQL = PRODUCT_REVENUE_SQL.replace(
    "\nWITH px AS (",
    "\nWITH local_product_release_sku_v AS " + _LOCAL_PRODUCT_RELEASE_SKU_V + ",\n"
    "local_product_release_by_coa_v AS " + _LOCAL_PRODUCT_RELEASE_BY_COA_V + ",\n"
    "local_gmpln_product_release_by_coa_monthly_v AS " + _LOCAL_GMPLN_PRODUCT_RELEASE_BY_COA_MONTHLY_V + ",\n"
    "px AS (", 1,
).replace("ORACLE_DATA_PROD.FCT_EPM.GMPLN_PRODUCT_RELEASE_BY_COA_MONTHLY_V",
          "local_gmpln_product_release_by_coa_monthly_v")


def pick_sql(error: Exception | None) -> str:
    """Real views unless they failed with the PRICING_SKU_V column error."""
    if error is not None and BROKEN_VIEW_ERROR in str(error):
        return PRODUCT_REVENUE_LOCAL_SQL
    return PRODUCT_REVENUE_SQL


def load() -> pd.DataFrame:
    """Flat rows: license, coa, product_name, fiscal_year, period_date, net_rev ($)."""
    try:
        df = data._q(PRODUCT_REVENUE_SQL)
    except Exception as e:  # noqa: BLE001 -- only 002057 falls back; anything else re-raises
        if pick_sql(e) is PRODUCT_REVENUE_SQL:
            raise
        df = data._q(PRODUCT_REVENUE_LOCAL_SQL)
    df["period_date"] = pd.to_datetime(df["period_date"])
    df["net_rev"] = pd.to_numeric(df["net_rev"]).astype(float)
    return df


def _period(df: pd.DataFrame, grain: str) -> pd.Series:
    d = df["period_date"]
    if grain == "Month":
        return d.dt.strftime("%Y-%m")
    if grain == "Quarter":
        return "Q" + d.dt.quarter.astype(str) + "'" + d.dt.strftime("%y")
    return df["fiscal_year"]


def pivot(df: pd.DataFrame, grain: str) -> pd.DataFrame:
    """License subtotal row, then its releases, then a Total row; values in $M."""
    df = df.assign(period=_period(df, grain))
    cols = sorted(df["period"].unique(), key=lambda p: df.loc[df["period"] == p, "period_date"].min())
    rel = df.pivot_table(index=["license", "coa", "product_name"], columns="period",
                         values="net_rev", aggfunc="sum", fill_value=0.0)[cols]
    lic = rel.groupby(level="license").sum()
    # Biggest license first, "(No license)" last.
    order = lic.sum(axis=1).sort_values(ascending=False).index.tolist()
    if NO_LICENSE in order:
        order.remove(NO_LICENSE)
        order.append(NO_LICENSE)
    rows = []
    for name in order:
        rows.append({"License": name, "COA license": "", "COA": "",
                     "Product release": f"{name} total", **lic.loc[name]})
        part = rel.loc[name]
        part = part.loc[part.sum(axis=1).sort_values(ascending=False).index]
        for (coa, prod), vals in part.iterrows():
            rows.append({"License": name, "COA license": viz.license_from_coa(coa), "COA": coa,
                         "Product release": prod, **vals})
    rows.append({"License": TOTAL, "COA license": "", "COA": "", "Product release": "", **rel.sum()})
    out = pd.DataFrame(rows)
    out[cols] = out[cols] / 1e6
    return out


def render_chart(df: pd.DataFrame) -> None:
    """Stacked quarterly bars (FY26 + FY27) per Megan's artifact rules, $M."""
    view = st.segmented_control("View", ["License", "Size tier"], default="License",
                                key="prodrev_view") or "License"
    by = "tier" if view == "Size tier" else "license"
    bars = viz.bar_frame(df, by, TIER_EDGES, HEDGE_MODE)
    bars[["net_rev", "y0", "y1"]] = bars[["net_rev", "y0", "y1"]] / 1e6
    bars["mid"] = (bars["y0"] + bars["y1"]) / 2
    bar_tot = bars.groupby("quarter")["net_rev"].transform("sum")
    bars["show"] = (bars["net_rev"] / bar_tot).abs() >= LABEL_MIN_SHARE
    chips = bars.drop_duplicates("quarter")["chip"].tolist()
    segs = bars.sort_values("stack")["segment"].drop_duplicates().tolist()
    # Two-line chip label ("Q1'26" / "15.9% of FY26"); labelLimit=0 stops the cut.
    x = alt.X("chip:N", sort=chips, title=None,
              axis=alt.Axis(labelAngle=0, labelLimit=0, labelExpr="split(datum.label, ' · ')"))
    color = alt.Color("segment:N", sort=segs, title=view,
                      scale=alt.Scale(scheme="tableau20"))
    base = alt.Chart(bars)
    bar = base.mark_bar().encode(
        x=x, y=alt.Y("y0:Q", title="Net Revenue $M"), y2="y1:Q", color=color,
        tooltip=["quarter", "segment", alt.Tooltip("net_rev:Q", format=",.1f", title="$M"),
                 alt.Tooltip("pct:Q", format=".1%"), "label"])
    text = base.transform_filter("datum.show").mark_text(fontSize=10, color="white").encode(
        x=x, y="mid:Q", text="label:N")
    st.altair_chart((bar + text).properties(height=520), width="stretch")
    pct_note = ("tier % of quarter release $ (excl. Other)" if by == "tier"
                else "license % of quarter release $ (excl. Other); '· n' = releases, counted in peak quarter")
    st.caption("License = first 3 letters of the COA code; other COAs are 'Other' (bottom block). "
               f"Bar labels: {pct_note}. Chip % under each bar = quarter $ (incl. Other) / FY $. "
               "NA (NASE) only - not comparable to Megan's global artifact.")
    if by == "tier":
        st.caption(TIER_NOTE)
    if HEDGE_MODE == "own_block":
        st.caption("Hedge COAs are drawn as their own block below Other. " + HEDGE_NOTE)
    else:
        summ = viz.quarter_summary(df, HEDGE_MODE)
        neg = summ.loc[summ["other"] < 0, "quarter"].tolist()
        if neg:
            st.caption(f"Other is below zero in {', '.join(neg)}: it includes negative hedge "
                       "COAs (for example NBA - Hedge). " + HEDGE_NOTE)


def render() -> None:
    st.subheader("Product Revenue (NA) - Net Revenue ex intercompany, $M")
    st.caption("GM plan, Sep 2026 FC (SEP26RF), entity CO_31010, LOB LB_312. "
               "License from DESA_SILVER.PRICING.SKU; unmatched releases under "
               f"\"{NO_LICENSE}\".")
    grain = st.segmented_control("Period", ["Month", "Quarter", "FY"],
                                 default="Quarter", key="prodrev_grain") or "Quarter"
    try:
        df = load()
    except Exception as e:  # noqa: BLE001 -- show the error, keep the other tabs alive
        st.error(f"Could not load product revenue: {e}")
        return
    if df.empty:
        st.info("No product revenue rows.")
        return
    if (df["fiscal_year"] == "FY27").any():
        # Maya, 2026-11-03 15:24: keep FY27, flag the gap to Megan's file.
        st.caption("FY27 is $157M below Megan's file; under review with Megan.")
    render_chart(df)
    table = pivot(df, grain)
    num_cols = [c for c in table.columns if c not in ("License", "COA license", "COA", "Product release")]
    st.dataframe(table, hide_index=True, width="stretch",
                 column_config={c: st.column_config.NumberColumn(c, format="%.1f")
                                for c in num_cols})
    st.download_button("Download CSV (flat, $)",
                       df.to_csv(index=False).encode("utf-8"),
                       file_name="product_revenue_na.csv", mime="text/csv",
                       key="prodrev_csv")
