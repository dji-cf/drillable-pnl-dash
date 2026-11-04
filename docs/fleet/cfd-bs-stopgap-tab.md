# Balance Sheet tab: DRAFT stop-gap (US GL roll-forward, 48 tying lines)

For Maya Iwabuchi. Requester Tara Petrucci (Accounting). GL feed owner Vivek Srinivasan.
Base: coco/port-cfd-cogs-drill (114adbc). Approvals: Maya 2026-11-03 15:24, 2026-11-04 09:21.

## Files changed

| File | Change |
|---|---|
| `queries.py` | `BS_PERIODS = ["Aug-26", "Sep-26"]`, `BS_TIE_ROWS` (48 rows), `bs_stopgap_sql(period)`. SQL = report `docs/fleet/cfd-bs-gl-rollforward.md` "Step 5" (commit 8d1ec26), only the CTE `p` value is filled in. Any period not in `BS_PERIODS` raises `ValueError`. |
| `data.py` | `load_bs_stopgap(period)`: `@st.cache_data` + `_q()`, errors not caught (same as `load_adj_ebitda_ex_es`). |
| `financial_app.py` | `import queries`; the `with balance:` block only. "Coming soon" info -> "Balance Sheet (draft, stop-gap) (Tara Petrucci)", period select box (default Aug-26), table Line / FCCS code / US GL amount $ (2 decimals, thousands separator) filtered in pandas to `BS_TIE_ROWS`, try/except -> `st.warning("Balance Sheet could not load: ...")`, Raw Materials / Finished Goods footnote, the "US ledger only ..." caption (exact text), the Sep-26 caption. Notion link kept. No totals. |
| `tools/test_financial_app.py` | Mocks `data.load_bs_stopgap` with 3 rows (24 Cash = not tying, 28, 37). Checks the caption, that Cash is filtered out, the footnote, no "Coming soon", `bs_stopgap_sql("Oct-26")` raises `ValueError`, `bs_stopgap_sql("Aug-26")` has `300000004289455`, `status = 'P'`, `'Mar-26'`. |

No new `.py` file, so `snowflake.yml` and `tools/preflight_artifacts.py` are unchanged.

## Test output

```
balance sheet caption shown: True
balance sheet table lines: ['Accounts Receivable - Accruals', 'Raw Materials'] warnings: []
bs_stopgap_sql('Oct-26'): ValueError ok
bs_stopgap_sql('Aug-26'): ok
... (all existing checks: tabs, header, Cash Flow links/tile, SG&A, 4 BU pages, carry-over, two sessions: ok)
OK -- financial_app.py
```

`python -c "import queries; print(queries.bs_stopgap_sql('Aug-26')[:200])"` prints the SQL header. A Python comparison of `bs_stopgap_sql('Aug-26')` against the report's Step 5 code block gave `IDENTICAL to report Step 5`.

## Step 9: read-only grant check

Login `SVC_ORACLE_CORTEX_CODE`, role `SVC_ORACLE_CORTEX_CODE_ROLE` (query 01c83094-031a-3d2b-69de-0701a15d011b):

| Table | `SELECT 1 ... LIMIT 1` |
|---|---|
| ORACLE_DATA_PROD.FCT_GL.GL_JE_LINES | works |
| ORACLE_DATA_PROD.FCT_GL.GL_BALANCES | works |
| ORACLE_DATA_PROD.FCT_GL.GL_CODE_COMBINATIONS | works |

Deploy role POWER_ANALYST_ORACLE_PROD: **NOT CHECKED - needs Claude/Maya**. This login cannot use it (available roles: SVC_ORACLE_CORTEX_CODE_ROLE, PUBLIC, SNOWFLAKE_LEARNING_ROLE). Run the three SELECTs under `USE ROLE POWER_ANALYST_ORACLE_PROD; USE SECONDARY ROLES NONE;` before deploying (data.py role note).

## Step 10: Aug-26 run vs report Step 2 "GL (US ledger)"

Query 01c83095-031a-40fb-69de-0701a15cad6b: the Step 5 SELECT for Aug-26 as a subquery, joined to the 48 expected values typed from the Step 2 table. I left out the three `--` comments and the final ORDER BY in that subquery; the logic is the same. **48 of 48 rows, diff = 0.00 on every row.**

| Row | Line | FCCS code | US GL $ | Report GL $ | Diff |
|---:|---|---|---:|---:|---:|
| 28 | Accounts Receivable - Accruals | AC_11009 | -749,129.72 | -749,129.72 | 0.00 |
| 31 | Allowance for Doubtful Accounts | AC_11903 | -3,451,863.98 | -3,451,863.98 | 0.00 |
| 32 | Unapplied Deposits | AC_11553 | -1,309,781.90 | -1,309,781.90 | 0.00 |
| 33 | Accrued Returns | AC_11010 | -3,242,192.14 | -3,242,192.14 | 0.00 |
| 37 | Raw Materials | AC_13001 | 364,730,187.79 | 364,730,187.79 | 0.00 |
| 38 | Work in Progress | AC_13100 | 136,402,842.49 | 136,402,842.49 | 0.00 |
| 39 | Finished Goods | AC_13200 | 66,559,299.99 | 66,559,299.99 | 0.00 |
| 40 | Inventory Reserves | AC_13800 | -44,843,058.86 | -44,843,058.86 | 0.00 |
| 45 | Prepaid Royalties | AC_14025 | 28,294,293.61 | 28,294,293.61 | 0.00 |
| 47 | Prepaid Autos | AC_14152 AC_14161 | 9,775,842.19 | 9,775,842.19 | 0.00 |
| 48 | Prepaid Marketing/Sponsorship | AC_14050 AC_14159 | 2,141,577.19 | 2,141,577.19 | 0.00 |
| 49 | Prepaid Lic/Maint expenses | AC_14075 | 8,351,140.99 | 8,351,140.99 | 0.00 |
| 50 | Prepaid Sales Tax | AC_14100 | 193,745.56 | 193,745.56 | 0.00 |
| 51 | Prepaid Sign-on Bonuses | AC_14167 | 1,342,494.59 | 1,342,494.59 | 0.00 |
| 52 | Prepaid Inventory | AC_14163 | 0.00 | 0.00 | 0.00 |
| 53 | Prepaid - Image Rights Legends | AC_14165 | 906,600.85 | 906,600.85 | 0.00 |
| 55 | Prepaid Insurance | AC_14154 | 549,718.32 | 549,718.32 | 0.00 |
| 58 | Strategic partner contract cost | AC_14250 | 27,036,189.94 | 27,036,189.94 | 0.00 |
| 67 | Intangible Assets | AC_17100 | 72,058,595.77 | 72,058,595.77 | 0.00 |
| 72 | Strategic Partner Contract Costs | AC_18101 | 322,629,276.34 | 322,629,276.34 | 0.00 |
| 74 | Investments | AC_18175 AC_18125 | 19,167,122.55 | 19,167,122.55 | 0.00 |
| 75 | Long Term Revolver Debt Issuance Costs | AC_18315 | 5,903,868.25 | 5,903,868.25 | 0.00 |
| 76 | Cloud Computing Implementation Costs | AC_18275 | 1,493,932.24 | 1,493,932.24 | 0.00 |
| 78 | Image Rights - Legends | AC_18231 | 1,452,070.77 | 1,452,070.77 | 0.00 |
| 79 | Long Term Deposits | AC_18250 | 1,108,258.58 | 1,108,258.58 | 0.00 |
| 80 | Indemnification Asset | AC_18300 | 738,421.00 | 738,421.00 | 0.00 |
| 81 | Prepaid Sign-on Bonuses | AC_18233 | 501,304.47 | 501,304.47 | 0.00 |
| 82 | Prepaid Insurance | AC_18230 | 167,943.90 | 167,943.90 | 0.00 |
| 85 | Intercompany Note Receivables | AC_18800 | 1,506,783,000.00 | 1,506,783,000.00 | 0.00 |
| 94 | Accrued Royalties | AC_21250 | 436,698,178.08 | 436,698,178.08 | 0.00 |
| 97 | Accrued Legal and professional fees | AC_21175 | 21,976,980.28 | 21,976,980.28 | 0.00 |
| 100 | Accrued Sales Tax | AC_21100 | 11,814,407.49 | 11,814,407.49 | 0.00 |
| 101 | Accrued Marketing | AC_21200 | 4,139,577.91 | 4,139,577.91 | 0.00 |
| 102 | Accrued Temp Labor | AC_21425 | 1,864,012.28 | 1,864,012.28 | 0.00 |
| 103 | Accrued Capex | AC_21416 | 1,464,979.51 | 1,464,979.51 | 0.00 |
| 104 | Accrued Shipping | AC_21150 | 231,027.56 | 231,027.56 | 0.00 |
| 105 | Interest Accrual | AC_21275 | 1,612,498.43 | 1,612,498.43 | 0.00 |
| 107 | Deferred Revenue | AC_23000 | 49,521,516.77 | 49,521,516.77 | 0.00 |
| 109 | Current Portion of Long Term Debt | AC_24000 | 221,856.05 | 221,856.05 | 0.00 |
| 113 | Deposits / On Account Liability | AC_24208 | 41,253,591.54 | 41,253,591.54 | 0.00 |
| 114 | Buyback Program | AC_24211 AC_24215 | 14,436,750.20 | 14,436,750.20 | 0.00 |
| 115 | Marketplace Seller Payables | AC_24175 | 72,366,253.77 | 72,366,253.77 | 0.00 |
| 116 | Other Current Liabilities | AC_24201 AC_24210 AC_24125 AC_24102 AC_24209 | 5,023,633.00 | 5,023,633.00 | 0.00 |
| 122 | Long Term Debt | AC_26000 | 230,279,894.36 | 230,279,894.36 | 0.00 |
| 127 | NBA Guarantee | AC_27126 | 3,131,897.26 | 3,131,897.26 | 0.00 |
| 128 | Other Long Term Liabilities | AC_27201 AC_27051 | 1,771,341.93 | 1,771,341.93 | 0.00 |
| 129 | Buyback programs | AC_27206 | 4,430,984.46 | 4,430,984.46 | 0.00 |
| 130 | Royalties | AC_27151 | 140,595.32 | 140,595.32 | 0.00 |

## Findings

- **CONFIRMED**: `bs_stopgap_sql("Aug-26")` is identical to the report's Step 5 SQL (Python string compare).
- **CONFIRMED**: Aug-26 matches the report's GL (US ledger) column on all 48 `BS_TIE_ROWS` (diff 0.00).
- **CONFIRMED**: My login can read GL_JE_LINES, GL_BALANCES and GL_CODE_COMBINATIONS.
- **CONFIRMED**: The app shows only `BS_TIE_ROWS`, with no total rows; the AppTest shows a non-tying row (Cash) is filtered out. Oct-26 and other periods raise `ValueError` before any SQL is built.
- **LIKELY**: Sep-26 loads the same way (the report tested Sep-26 with this SQL on 2026-11-03). I did not run Sep-26 today, and it is not tied to a Tara file (caption says so).
- **LIKELY**: Row 52 Prepaid Inventory is 0.00 on the US ledger; Tara's 1,854,573.75 is all International. So the tab shows $0.00 for a line Tara shows as non-zero. It is in Maya's 48-row list, so I kept it. Tara may find this confusing.
- **I DON'T KNOW**: Whether POWER_ANALYST_ORACLE_PROD (deploy owner role, no secondary roles) can read the three FCT_GL tables. NOT CHECKED - needs Claude/Maya.
- **I DON'T KNOW**: Raw Materials / Finished Goods (rows 37, 39) tie only to Tara's final file after her hand-typed +/-1,852,926 move. Still waiting on Tara; the tab shows a footnote and does not hide the rows.
- Self-check 2026-11-04: SQL string compare again IDENTICAL; `BS_TIE_ROWS` re-derived from the report Step 2 table = 48 rows (35 starred + 8 zero-both excluded: 59, 61, 71, 117, 131, 133, 138, 147), equal to the constant; RESULT_SCAN of 01c83095-031a-40fb-69de-0701a15cad6b = 48 rows, 0 with |diff| > 0.01; grants re-run OK (01c83097-031a-3d29-69de-0701a15cf8ff); test re-run OK.
- Numbers drift if posted Apr..Aug journal lines change after 2026-11-03 (live GL_JE_LINES; cache TTL 2 h).
