# cfd-cash-ebitda-tile: FY26 Adjusted EBITDA ex Emerging Services on the Cash Flow tab

Recipe from Afriti Rahim (FP&A), email "Re: Cash and Capex Dashboards - Request Received",
2026-11-02 11:41 / 11:44 ET. Approved by Maya on 2026-11-03 (thread cfd-cash-ebitda-bridge).
Not ACX_EBITDA. There are no add-backs. The Pisa legal line (CC_40313 / AC_61002) is the "Key Litigation and
Regulatory" carve-out. (updated 2026-11-04)

## What changed
- `queries.py:676-719`: new `adj_ebitda_ex_es_sql(scenario="SEP26RF", fiscal_year="FY26")` (def at :685).
  Literal SELECT with no binds, built on `STG` / `STG_ENTITY` / `STG_ICP_TOTAL`. Copied from
  bridge N2, with one change: the final sum is in an outer CTE `s`, because the single-SELECT
  form gives "not a valid group by expression" (tcg_cc / pisa resolve to l's columns).
- `data.py:190-196`: new `load_adj_ebitda_ex_es()` with `@st.cache_data`, which calls `_q(...)`.
  It does not catch errors, same as load_master.
- `financial_app.py:62-67`: the Cash Flow block. The info text is now "Cash Flow (draft) (Afriti Rahim,
  Jack Braun)". It calls `_cash_ebitda_tile()` and then shows the unchanged Notion link and the 3 SharePoint links.
  `financial_app.py:74-100`: `EBITDA_ROWS` + `_cash_ebitda_tile()`, which shows an st.metric in $M with 1 decimal, a 7-row bridge
  st.table and the source caption. On a load error it shows st.warning instead, and the links still render.
- `tools/test_financial_app.py:29-32`: patches `data.load_adj_ebitda_ex_es` with the bridge values, so the tile
  needs no Snowflake. `:88-97`: new checks, (1) a metric containing "2,169.6" and (2) the SQL contains
  CARDPLN_PL_BY_LOB_STG / SEP26RF / FY26 and does not contain ACX_EBITDA.
  (updated 2026-11-04) `:88-92`: a new check that no Cash Flow table row label contains "add back". Line numbers
  after :88 move down by 5.

## SQL result (read-only, connection `fleet`)
query_id `01c82be8-031a-2fa8-69de-0701a0ac952f`. This is the function's SQL with one column added for the run,
`LAST_QUERY_ID()`, which returned NULL.

| column | USD |
|---|---|
| lb310 | 2,099,969,199.79 |
| live | -29,810,852.83 |
| collect | 19,665,524.69 |
| tcg | -9,764,158.91 |
| tcg_cc | 760,006.47 |
| pisa | 48,934,005.76 |
| **adj_ebitda_ex_es** | **2,169,572,699.07** |

This matches bridge N2 (2,169,572,699) exactly. It is 3,168 USD above Afriti's 2,169,569,531.

## Test output (`.venv/bin/python tools/test_financial_app.py`)
```
load_master calls during import: 0
cube global after import: False
top tabs: ['Income Statement', 'Balance Sheet', 'Cash Flow', 'SG&A']
header: ['(DRAFT) Collectibles Financial Dashboard']
cash flow link 'FCF Dashboard': ok
cash flow link 'Capex Dashboard': ok
cash flow link 'Cash & Revolver Dashboard': ok
cash flow metrics: ['$2,169.6M']
adj_ebitda_ex_es_sql: ok
Income Statement inner tabs: ['Forecast Table', 'Historical Trends']
Income Statement has old title: False
BU page na: ok   (intl, digital, collect: ok; headers True)
forecast carry-over: picked ('Sep 2026 FC', '') -> BU ('Sep 2026 FC', '') -> home ('Sep 2026 FC', '')
two sessions: A='Sep 2026 FC' B='Aug 2026 FC' (picked 'Sep 2026 FC', 'Aug 2026 FC')
shared streamlit_app module in sys.modules: none

OK -- financial_app.py
```
The Income Statement tab still logs in to Snowflake for the P&L cube; the Cash Flow tile does not.

## Self-check (2026-11-03)
- Re-ran the exact `adj_ebitda_ex_es_sql()` text (no extra column): query_id `01c82be9-031a-2c6e-69de-0701a0acc103`,
  adj_ebitda_ex_es = 2,169,572,699.07. Same as the first run. CONFIRMED.
- The single-SELECT form from the task fails to compile: query_id `01c82be9-031a-2bcc-69de-0701a0aca573`,
  "[L.TCG_CC] is not a valid group by expression". CONFIRMED. That is why queries.py has the outer CTE `s`.
- `git diff --name-only coco/cfd-shell` = data.py, financial_app.py, queries.py, tools/test_financial_app.py. New file
  = docs/fleet/cfd-cash-ebitda-tile.md. No changes to streamlit_app.py. CONFIRMED.
- `ACX_EBITDA` in queries.py: lines 76 and 104 are older code from before this task. Line 684 is only my comment.
  The new SQL does not use it. CONFIRMED.
- Bridge numbers (2,169,572,699 rebuild; Afriti 2,169,569,531; +3,168) are in
  `coco/cfd-cash-ebitda-bridge:docs/fleet/cfd-cash-ebitda-bridge.md:11-12,89`. CONFIRMED.
- Afriti's email and screenshot were not opened here. They need Claude.

## Follow-up 1 (labels) (updated 2026-11-04)
Why: Claude's check (checks/cfd-cash-ebitda-tile.md, Step 3, 2026-11-03 16:05) found that 2 row labels did not match
Afriti's words. Maya said yes to fix only the labels. Proof given by Claude:
- Afriti's email, 2026-11-02 11:41 ET: "we aren't including any add-backs ... We then also carve out key Litigation and Regulatory".
- Notion page https://app.notion.com/p/3ff6c07d730e80d6b26cc48245222081 (2026-10-20): "key lit is now 'Key Litigation and Regulatory'".

Changes:
- `financial_app.py:79`: "less TCG cost center CC_70123" -> "TCG cost center CC_70123 (carve-out)". It shows +0.8,
  so "less" looked wrong.
- `financial_app.py:80`: "add back Key Litigation - Pisa legal (CC_40313 / AC_61002)" -> "carve out Key Litigation and
  Regulatory (CC_40313 / AC_61002)".
- The keys and signs are unchanged (tcg_cc +1, pisa +1). The SQL, queries.py, data.py, the metric and the caption are unchanged.
- `tools/test_financial_app.py:88-92`: a new check that the Cash Flow table has rows and that no row label contains "add back".

`git diff --stat 510d989`: financial_app.py (2 lines), tools/test_financial_app.py (+5 lines), and this file.

Test output (`.venv/bin/python tools/test_financial_app.py`, 2026-11-04; Snowflake login and streamlit warning lines removed):
```
load_master calls during import: 0
cube global after import: False
top tabs: ['Income Statement', 'Balance Sheet', 'Cash Flow', 'SG&A']
header: ['(DRAFT) Collectibles Financial Dashboard']
cash flow link 'FCF Dashboard': ok
cash flow link 'Capex Dashboard': ok
cash flow link 'Cash & Revolver Dashboard': ok
cash flow table rows: ['Collectibles ex Other (LB_310) EBITDA', 'less Fanatics Live (LB_306)', 'less Collect / Marketplace (LB_307)', 'less Trading Card Games (LB_308)', 'TCG cost center CC_70123 (carve-out)', 'carve out Key Litigation and Regulatory (CC_40313 / AC_61002)', '= Adjusted EBITDA ex Emerging Services']
cash flow metrics: ['$2,169.6M']
adj_ebitda_ex_es_sql: ok
Income Statement inner tabs: ['Forecast Table', 'Historical Trends']
Income Statement has old title: False
BU page na: ok
BU page na header 'Collectibles Financial Dashboard': True
BU page intl: ok
BU page intl header 'Collectibles Financial Dashboard': True
BU page digital: ok
BU page digital header 'Collectibles Financial Dashboard': True
BU page collect: ok
BU page collect header 'Collectibles Financial Dashboard': True
forecast carry-over: picked ('Sep 2026 FC', '') -> BU ('Sep 2026 FC', '') -> home ('Sep 2026 FC', '')
two sessions: A='Sep 2026 FC' B='Aug 2026 FC' (picked 'Sep 2026 FC', 'Aug 2026 FC')
shared streamlit_app module in sys.modules: none

OK -- financial_app.py
```
