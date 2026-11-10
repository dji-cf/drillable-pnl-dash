# cfd-prodrev-na — Product Revenue (NA) tab (DRAFT)

Requester: Megan Coleman (FP&A). Priority #1 per Dan Chen (2026-11-02). North America only.
Branch `coco/cfd-prodrev-na` (from `coco/cfd-shell` 58125ff). Checked 2026-11-03 on connection `fleet`.

## (a) Columns of both views (from INFORMATION_SCHEMA.COLUMNS)

**ORACLE_DATA_PROD.FCT_EPM.GMPLN_PL_BY_SKU_CHANNEL_V**

| Column | Type | Column | Type |
| --- | --- | --- | --- |
| SCENARIO | TEXT | SKU | TEXT |
| VERSION | TEXT | COA | TEXT |
| ENTITY | TEXT | ACX_LINE | TEXT |
| ENTITY_DESC | TEXT | PL_LINE | TEXT |
| LOB | TEXT | PL_PARENT | TEXT |
| FISCAL_YEAR | TEXT | PL_SECTION | TEXT |
| MONTH | TEXT | PL_SORT_ORDER | NUMBER |
| PERIOD_DATE | DATE | INDENT_LEVEL | NUMBER |
| CHANNEL | TEXT | IS_SUBTOTAL | BOOLEAN |
| CHANNEL_DESC | TEXT | AMOUNT | NUMBER |

Distinct values (whole view): SCENARIO = `SEP26RF` only; VERSION = `Final` only; ENTITY = `CO_31010` (NASE) only;
LOB = `LB_312` only; FISCAL_YEAR = FY26 / FY27 / FY28; MONTH = Jan..Dec only (no Q1..Q4 / YearTotal rows in this
view, the SQL still filters the 12 months); 35 ACX_LINE values (account lines, e.g. `ACX_Net Revenue` (subtotal),
`ACX_Intercompany Revenue`, `ACX_Gross Sales`, `ACX_Gross to Net`, ...); 29 channels (incl. `Internal - Japan`, which is a
channel inside the NA entity, not a separate international entity).

**ORACLE_DATA_PROD.FCT_EPM.GMPLN_PRODUCT_RELEASE_BY_COA_MONTHLY_V** (one row per COA, wide)

FORECAST_ASOF TEXT, COA TEXT, PRODUCT_NAME TEXT, STREET_DATE DATE, PFC_STREET_DATE DATE, BUDGET_STREET_DATE DATE,
SKU_COUNT NUMBER, CURRENT_FY TEXT, QUARTER TEXT, NETREV_JAN26 .. NETREV_DEC26 NUMBER (12 cols), FCST_Q1..FCST_Q4 NUMBER,
FCST_CUR_FY NUMBER, FCST_NEXT_FY NUMBER, FCST_LIFETIME NUMBER, BUDGET NUMBER, PY_NETREV FLOAT, LIFETIME FLOAT,
CM_CUR_FY NUMBER, CM_NEXT_FY NUMBER, CM_LIFETIME NUMBER, BUDGET_CM NUMBER, PY_CM FLOAT, LIFETIME_CM FLOAT, CM_PCT FLOAT,
B_PCT NUMBER, PY_PCT FLOAT, VS_BUDGET_PCT FLOAT, VOL_CUR_FY NUMBER, VOL_NEXT_FY NUMBER, VOL_LIFETIME NUMBER.

Distinct: FORECAST_ASOF = `SEP26RF` only, CURRENT_FY = `FY26` only, 1,913 COAs. No MONTH column (months are columns),
no entity/LOB column. FY27 is only a single total (FCST_NEXT_FY), no months.

**North America / international:** neither view has an international split. The SKU view holds only entity CO_31010
(NASE) / LB_312; the COA view has no entity column at all. So both views are NA-only by content. No international data used.

## (b) Filter picked and why

- `SEP26RF` = Megan's POV (Rolling Forecast / Working, Sep 2026 FC). It is the only scenario in both views; filters are
  still explicit in the SQL (`scenario='SEP26RF' AND version='Final' AND entity='CO_31010' AND lob='LB_312'`,
  `forecast_asof='SEP26RF' AND current_fy='FY26'`).
- LB_312: Megan's POV says LB_312, it is the only LOB present, and the totals tie (below).
- Net Revenue ex interco:
  - **FY26 months** from the COA view `NETREV_JAN26..DEC26` (unpivoted). This is the source of Megan's file and ties to the cent.
  - **FY27 months** from the SKU view: `ACX_Net Revenue − ACX_Intercompany Revenue`, 12 real months. FY27 total
    4,393,213,211.77 = COA view FCST_NEXT_FY 4,393,213,211.78 (the view has no FY27 Intercompany Revenue rows).
    This is $157.4M below Megan's file FY27; see (c).
  - Not used for FY26: the SKU view gives Net Rev 4,155.03M − Interco 66.09M = 4,088.95M, which is +2.0M (0.05%) off
    Megan (Q4 ties exactly, Q1 +2.97M, Q2 −3.24M, Q3 +2.27M). The COA view is exact, so it wins for FY26.
  - FY28 (74.4M, Jan–Jun 2028 in SKU view) left out: the brief asked for FY26 + FY27.
- License: per COA, the PRICING_LICENSE of its SKUs (`LEFT(SPLIT_PART(sku,'-',1),9) = LEFT(DESA_SILVER.PRICING.SKU.SKU,9)`).
  Checked: no SKU key maps to >1 license, and no COA has SKUs of >1 license, so a COA-level license is exact.
  COAs with no matching SKU → `(No license)`, kept.

## (c) Tie-out: dashboard SQL vs Megan's file (Sep 2026 FC, Net Rev excl. interco)

| Period | Dashboard SQL ($) | Megan file ($) | Gap $ | Gap % |
| --- | --- | --- | --- | --- |
| Q1'26 | 651,564,292.34 | 651,564,292.35 | −0.01 | 0.000% |
| Q2'26 | 1,292,121,169.09 | 1,292,121,169.09 | 0.00 | 0.000% |
| Q3'26 | 1,072,629,552.22 | 1,072,629,552.22 | 0.00 | 0.000% |
| Q4'26 | 1,070,628,006.06 | 1,070,628,006.06 | 0.00 | 0.000% |
| FY26 | 4,086,943,019.71 | 4,086,943,019.71 | 0.00 | 0.000% |

(Same totals in the AppTest-rendered table's Total row: 651.6 / 1,292.1 / 1,072.6 / 1,070.6 $M.)
FY27 by quarter (Megan's file has no FY27 quarters): 1,345.31 / 1,265.94 / 944.51 / 837.45 $M = 4,393,213,211.77.

**FY27 does NOT tie (found in self-check, 2026-11-03).** Megan's "USE for Filtering" row 3, "FY27 - Rev" (col J) =
**4,550,615,776.83**. The dashboard = 4,393,213,211.77 (= COA view FCST_NEXT_FY 4,393,213,211.78). Gap
**−157,402,565.06 (−3.46%)**. Named releases tie (NBA2702 193,925,954.96; NFL2702 160,816,367.59; NBA2734
150,947,315.55; MLB2726 129,073,415.58; NFL2640 120,120,907.36; NFL2602 2,417,591.33 — same in both). Most of the gap
is in placeholder "General" COAs, where Megan's file is higher than the view:

| COA | View PRODUCT_NAME | Megan FY27 | View FY27 | Gap |
| --- | --- | --- | --- | --- |
| 10003 | NFL - General | 200,000,000.00 | 150,000,000.00 | −50,000,000 |
| 10004 | NBA - General | 200,000,000.00 | 150,000,000.00 | −50,000,000 |
| 10002 | MLB - General | 25,000,000.00 | 0.00 | −25,000,000 |
| 10007 | UEFA Champions League - General | 20,000,000.00 | 10,000,000.00 | −10,000,000 |
| 50002 | Disney - General | 20,000,000.00 | 10,000,000.00 | −10,000,000 |

These 5 explain −145.0M. (updated 2026-11-03: a 6th General COA, 10408 English Premiere League - General, Megan
10,000,000 vs view 5,000,000 = −5M, brings it to −150.0M; the rest is −7,402,565.06, see below. The old "−12.4M" is replaced.) LIKELY reason: the file is "(Updated)" and has manual
FY27 plugs that are not in GM plan SEP26RF. Not confirmed: ask Megan. Megan's file also has a COA row "#VALUE!"
(FY27 767,937.73), which is an Excel error in her file.

(updated 2026-11-03) Checker query 01c82a56-031a-2bcc-69de-0701a06eea17: 6 General COAs explain −150,000,000:
10003 −50M, 10004 −50M, 10002 −25M, 10007 −10M, 50002 −10M, 10408 −5M. The rest, about −7.4M, is not explained.
Maya chose option A (2026-11-03 15:24): keep FY27 on the tab, with the caption "FY27 is $157M below Megan's file;
under review with Megan." (product_revenue.py:150-152). Maya asks Megan.

Top 5 COAs by FY26 Rev ("USE for Filtering", 1,056 COA rows summing to 4,086,943,019.71):

| COA | Megan Product Name | License | Megan FY26 ($) | SQL FY26 ($) | Gap $ |
| --- | --- | --- | --- | --- | --- |
| NFL2502 | 2025 Topps Chrome Football | NFL | 236,002,727.61 | 236,002,727.61 | 0.00 |
| NBA2634 | 2025/26 Topps NBA Chrome Updates Basketball | NBA | 186,908,801.82 | 186,908,801.82 | 0.00 |
| NFL2602 | 2026 Topps NFL Chrome Football | NFL | 180,268,832.77 | 180,268,832.77 | 0.00 |
| MLB2626 | 2026 Topps Chrome Baseball | MLB | 148,882,199.60 | 148,882,199.60 | 0.00 |
| NBA2633 | 2025/26 Topps NBA Bowman Basketball | NBA | 148,844,331.64 | 148,844,331.64 | 0.00 |

Note: names differ in wording — the view's PRODUCT_NAME is e.g. "2025 NFL - Chrome"; Megan's file has "2025 Topps
Chrome Football". The dashboard shows the view's name.

## (d) $ with no license

| Period | No-license $ | % of Net Rev |
| --- | --- | --- |
| Q1'26 | 56,033,540.37 | 8.6% |
| Q2'26 | 45,186,764.64 | 3.5% |
| Q3'26 | 85,725,982.93 | 8.0% |
| Q4'26 | 202,328,991.94 | 18.9% |
| FY26 | 389,275,279.88 | 9.5% |
| FY27 | 3,475,635,692.51 | 79.1% |

FY27 is mostly `(No license)` because most future SKUs are not in DESA_SILVER.PRICING.SKU yet. Totals are still
complete; only the license split is weak for FY27. A better license source (e.g. from COA prefix NFL/NBA/MLB) is a follow-up
for Megan to decide — not done here.

## (e) Changes (file:line)

- `product_revenue.py` (new): docstring 1-15; `PRODUCT_REVENUE_SQL` 26-90 (FY27 filter at 75); `load()` 93 (calls
  `data._q`, cached 2h); `_period()` 101; `pivot()` 110 (license subtotal rows, releases under each, Total row, $M);
  `render()` 135 (subheader, Month/Quarter/FY `st.segmented_control` at 140, dataframe 1-decimal at 152, CSV download at 155).
- `financial_app.py`: docstring 3-6; `import product_revenue` 23; `TABS` 36-37 (5th item "Product Revenue (NA)");
  `st.title(pnl._drafted(APP_TITLE))` 52 (unchanged); `st.tabs` unpack 53; new tab 73-75 (caption "North America only (GM plan). International comes later." +
  `product_revenue.render()`). `pnl._drafted(APP_TITLE)` unchanged, so "(DRAFT)" still shows.
- `snowflake.yml:111`: `product_revenue.py` added to `collectibles_financial_dash` artifacts only.
- Not changed: streamlit_app.py, queries.py, data.py, bu.py, the drillable_pnl_dash entity.

## Self-test

- `python3 -m py_compile financial_app.py product_revenue.py` → OK.
- AppTest (`streamlit.testing.v1`, `AppTest.from_file('financial_app.py')`, repo .venv, default Snowflake connection,
  SSO token was cached): no exceptions, no st.error; the Product Revenue subheader rendered; table 734 rows × 11 cols
  (Quarter grain, Q1'26..Q4'27), Total row as in (c). Month / FY grains and the download click were not driven in AppTest.
- (updated 2026-11-03) py_compile OK again. AppTest re-run on financial_app.py, period control set with
  `at.button_group(key='prodrev_grain').set_value(...)`: Quarter 734×11 (Total Q1'26 651.6), Month 734×27
  (2026-01..2027-12, Total Jan-26 255.0), FY 734×5 (FY26, FY27; Total FY26 4,086.9). 0 exceptions, 0 st.error in all
  three. The FY27 caption shows in all three. The download click was not tested.
