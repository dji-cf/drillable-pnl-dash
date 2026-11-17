# megan-prodrev-skufix — Product Revenue tab: PRICING_SKU_V 002057 fallback

Requester: Dan Chen (demo to Glenn, Wed 2026-11-18). Built by CoCo for Maya Iwabuchi, 2026-11-17.
Branch: coco/megan-prodrev-skufix (base 55917ae). Files: `product_revenue.py`, this doc.

## Symptom
Live app, under Period: `Could not load product revenue: 002057 (42601): SQL compilation error:
View definition for 'ORACLE_DATA_PROD.FCT_EPM.PRICING_SKU_V' declared 45 column(s), but view query produces 61 column(s).`

## View chain (GET_DDL, 2026-11-17) — CONFIRMED
| app source (product_revenue.py, base) | reads | status |
|---|---|---|
| `GMPLN_PL_BY_SKU_CHANNEL_V` (:50) | GMPLN_PL_BY_SKU_CHANNEL, GMPLN_PL_CHANNEL_DIM, GMPLN_PL_ACCOUNT_LAYOUT, LAUNCHPAD_SKUS_V (= SELECT * FROM LAUNCHPAD_SKUS) | works (query 01c879c6-081a-fcb0-69de-0701ab6272a3). No PRICING_SKU_V. |
| `GMPLN_PRODUCT_RELEASE_BY_COA_MONTHLY_V` (:70) | GMPLN_REVENUE_FORECAST_HISTORY, LAUNCHPAD_SKUS_V, **PRODUCT_RELEASE_BY_COA_V** | **fails 002057** (query 01c879c6-081a-fcaf-69de-0701ab6227e7) |
| → `PRODUCT_RELEASE_BY_COA_V` | GMPLN_BUDGET, LAUNCHPAD_SKUS_V, PRODUCT_COA_LIFETIME_PY_V, FC_MARKETING_COA, GMPLN_REVENUE_FORECAST_HISTORY, FC_STREET_DATE_MASTER, **PRODUCT_RELEASE_SKU_V** (3x) | broken via child |
| → → `PRODUCT_RELEASE_SKU_V` | GMPLN_REVENUE_FORECAST_HISTORY, GMPLN_BUDGET, LAUNCHPAD_SKUS_V, FCT_CMN.FND_VS_VALUES_VL, PRODUCT_COA_LIFETIME_PY_V, **PRICING_SKU_V** (CTE `pr`: PRICING_COA, PRICING_STREET_DATE, PRICING_PRODUCT_NAME) | broken |
| → → → `PRICING_SKU_V` | 45-col SELECT * over PRICING_SKU (now 61 cols) | root cause |

PRODUCT_COA_LIFETIME_PY_V reads only COA_FC_HISTORY (no PRICING_SKU_V). DDL query ids:
01c879c6-081a-fdf8-69de-0701ab61bccb, 01c879c6-081a-fcb0-69de-0701ab621f47, 01c879c6-081a-fcaa-69de-0701ab61cb7f.
The three PRICING_SKU columns used are positions 4, 5, 12 (inside the first 45) — query 01c879c6-081a-fcd1-69de-0701ab6251ef.

## Change (product_revenue.py) — CONFIRMED
- :106-113 comment + `BROKEN_VIEW_ERROR = "002057"`.
- :115-188 `_LOCAL_PRODUCT_RELEASE_SKU_V` — verbatim PRODUCT_RELEASE_SKU_V body; only change `PRICING_SKU_V` → `ORACLE_DATA_PROD.FCT_EPM.PRICING_SKU` (:158; already explicit columns).
- :190-313 `_LOCAL_PRODUCT_RELEASE_BY_COA_V` — verbatim body; `PRODUCT_RELEASE_SKU_V` → local CTE.
- :315-365 `_LOCAL_GMPLN_PRODUCT_RELEASE_BY_COA_MONTHLY_V` — verbatim body; `PRODUCT_RELEASE_BY_COA_V` → local CTE.
- :367-376 `PRODUCT_REVENUE_LOCAL_SQL` = `PRODUCT_REVENUE_SQL` with the three local views prepended as **sibling** CTEs and the MONTHLY_V reference swapped. (Nesting them as subqueries failed: the outer `lp` CTE shadowed the inner one — `invalid identifier LP.PRODUCT_NAME`, query 01c879ca-081a-fe6b-69de-0701ab62c3e7.)
- :379-383 pure `pick_sql(error)` — real SQL unless the error text has 002057.
- :386-393 `load()` — try the normal SQL; on 002057 run the local copy; any other error re-raises (same red box as before). No other logic, chart, placeholder (P1-P3) or FY27 caption change.

"Verbatim" = same SQL tokens as GET_DDL, except: SQL comments and blank lines removed, and the
MONTHLY_V select list joined onto fewer lines. Checked by eye, not by a machine diff (LIKELY); the
exact FY26 tie below is the strong proof that the logic is unchanged.
No SELECT * on any source table in the local copies. When the owner fixes PRICING_SKU_V the normal SQL works again and the fallback is never used.

## Tie — CONFIRMED
Exact local-copy SQL (generated from the code's constants via `ast`, not by importing the app), wrapped as `SELECT fiscal_year, ROUND(SUM(net_rev),2) ... GROUP BY 1`:
- **FY26 = 4,086,943,019.71** (1,724 rows) — matches docs/fleet/cfd-prodrev-na.md.
- FY27 = 4,393,213,211.77 (1,016 rows; FY27 does not use the broken chain).
- Query id **01c879cc-081a-fdf8-69de-0701ab62b637**. Self-check re-read via RESULT_SCAN: same values (01c879cd-081a-fcad-69de-0701ab634187).

## Checks
- `python3 -m py_compile product_revenue.py` — OK. CONFIRMED
- `python3 tools/test_prodrev_viz.py` — 9 passed (imports only prodrev_viz). CONFIRMED
- No app file imported/run (HARD RULE). Render not checked: Claude checks in Chrome after Maya publishes.

## Labels
- LIKELY: the live app's exception text contains "002057" (the red box shows it), so `pick_sql` will choose the fallback. Not run in the app per HARD RULE.
- LIKELY: fallback adds query time (three view bodies inline); not measured in the app.
- I DON'T KNOW: when SC_W_FCT_EPM will rebuild PRICING_SKU_V.
