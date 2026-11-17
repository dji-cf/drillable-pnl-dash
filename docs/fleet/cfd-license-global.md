# (DRAFT) Revenue by License (Global) — fleet report cfd-license-global

CoCo for Maya Iwabuchi, 2026-11-17. Requester James Dillon; content owner Megan Coleman.
Source: `ORACLE_DATA_PROD.FCT_EPM.CARDPLN_PL_BY_LEAGUE_V` (read-only SQL, connection `fleet`).

## STEP 1 — data proof

### 1a. DESCRIBE VIEW
26 columns, the same names as Vivek's 2026-09-22 list: SCENARIO_LABEL, SCENARIO, VERSION, FORECAST_ASOF,
FORECAST_ASOF_DATE (DATE), FISCAL_YEAR, PERIOD, PERIOD_TYPE, PERIOD_DATE (DATE), LOB, LOB_LABEL,
PRODUCT_GROUP, LEAGUE, CATEGORY, PL_LINE, PL_LABEL, PARENT_LINE, SECTION, SORT_ORDER (NUMBER), INDENT_LEVEL
(NUMBER), IS_SUBTOTAL (BOOLEAN), SANKEY_STAGE, CURRENCY, AMOUNT / HEDGE / UNHEDGED (NUMBER(38,4)). **No difference in column names.**
Difference in values: CATEGORY also has `Sports - Other` and `Entertainment - Other` (Vivek listed Sports|Entertainment|Other).

### 1b. FY27 ACX_Net Revenue: LOB × category × league (row counts)
| LOB | Leagues (count) | Notes |
|---|---|---|
| LB_302 North America | 20: Disney, GPK, Marvel, Star Wars, Entertainment - Other, Baseball, Bundesliga, Club Exclusives, EPL, Formula 1, MLS, NBA, NFL, NIL, Tennis, UEFA, UEFA Euro, UFC, WWE, Sports - Other | 7–22 rows each; Sports - Other has 134 rows |
| LB_303 International | 19 (no NIL) | 56–144 rows |
| LB_305 Digital | 12: Disney, Marvel, Star Wars, Entertainment - Other, Baseball, EPL, MLS, NBA, NFL, UEFA, WWE, Sports - Other | 144 each |
| Total LOB | 20 | 35–144 |

PRODUCT_GROUP maps 1:1 to LEAGUE (for example PG_20001 = NFL and PG_10000 = Sports - Other). The view has no MOG,
Licensing, carryover or supplies league. The only "Other"-like leagues are `Sports - Other` and
`Entertainment - Other`. Each one is shown under its own name and marked P3.

### 1c. Scenarios
| SCENARIO_LABEL | SCENARIO | VERSION | FORECAST_ASOF | ASOF_DATE | FY min | FY max | rows |
|---|---|---|---|---|---|---|---|
| ACTUAL | Actual | Final | – | – | FY23 | FY26 | 55,243 |
| BUDGET | Plan_2026 | Final | – | – | FY26 | FY26 | 12,820 |
| FORECAST | OCT25RF / NOV25RF / DEC25RF | Final | same | 2025-10/11/12 month-end | FY25 | FY25 | 15–16.5k |
| FORECAST | JAN26RF … JUL26RF | Final | same | 2026 month-ends | FY26 | FY27 | 15.9–26.7k |
| FORECAST | AUG26RF, SEP26RF | Final | same | 2026-08-31, 2026-09-30 | FY26 | FY28 | 27.4k, 27.9k |
| FORECAST | Rolling Forecast | Working | ROLLING_FORECAST | – | FY25 | FY28 | 52,435 |

**The view has no Plan_2027 rows.** The newest budget is Plan_2026/Final, and it covers FY26 only. So the FY27 tie-out uses
the FY27 forecasts.

### 1d. Tie-out (PERIOD_TYPE='YEAR', USD_Reporting, ACX_Net Revenue, $M)
| Scenario / FY | LOB | AMOUNT | UNHEDGED | HEDGE | leagues |
|---|---|---|---|---|---|
| Rolling Forecast Working FY27 | LB_302 | 9,423.5 | 9,685.0 | -261.6 | 20 |
| | LB_303 | 2,393.3 | 2,481.5 | -88.2 | 19 |
| | LB_305 | 153.0 | 153.0 | 0.0 | 12 |
| | Total LOB | 12,555.1 | 12,904.9 | -349.8 | 20 |
| SEP26RF Final FY27 (AUG26RF identical) | LB_302 | 4,471.2 | 4,471.2 | 0.0 | **1 (all in Sports - Other)** |
| | LB_303 | 1,705.9 | 1,705.9 | 0.0 | 19 |
| | LB_305 | 184.0 | 184.0 | 0.0 | 12 |
| | Total LOB | 6,361.1 | 6,361.1 | 0.0 | 19 |
| Plan_2026 Final FY26 | LB_302 | 5,493.2 | 5,852.6 | -359.5 | 19 |
| | LB_303 | 1,184.4 | 1,184.4 | 0.0 | 19 |
| | LB_305 | 160.4 | 160.4 | 0.0 | 12 |
| | Total LOB | 7,396.9 | 7,756.3 | -359.5 | 20 |

**Gap vs Megan (FY27 hedged, ex Digital).** Megan's numbers are after her true-ups and her MOG/Licensing adds. The view has neither.
| Scenario | Region | View $M | Megan $M | Gap $M | Gap % |
|---|---|---|---|---|---|
| Rolling Forecast (app default) | NA | 9,423.5 | 3,976 | +5,447.5 | +137.0% |
| | International | 2,393.3 | 1,182 | +1,211.3 | +102.5% |
| | Total | 11,816.8 | 5,158 | +6,658.8 | +129.1% |
| | Unhedged total | 12,166.5 | ~5,706 | +6,460.5 | +113.2% |
| SEP26RF | NA | 4,471.2 | 3,976 | +495.2 | +12.5% |
| | International | 1,705.9 | 1,182 | +523.9 | +44.3% |
| | Total | 6,177.1 | 5,158 | +1,019.1 | +19.8% |

No scenario ties within 1%. The app shows these numbers in an `st.warning` and does not explain the cause.
Not checked: whether Rolling Forecast FY27 really covers FY27 only, or holds more than one forecast vintage. Each league has exactly 1 YEAR row,
so there are no duplicate rows, but the total is about 2× SEP26RF. **Vivek must confirm this.**

**Other checks**
- Quarters = YEAR and Months = YEAR: **yes**, to $0.001M, for every LOB in Rolling Forecast FY27 and SEP26RF FY27.
- LB_302 + LB_303 + LB_305 = Total LOB: **only SEP26RF FY27** (6,361.1). It does not hold for the others: Actual FY26 6,260.1 vs 6,634.7, Plan_2026 FY26
  6,837.9 vs 7,396.9, RF FY26 9,940.0 vs 10,515.0, RF FY27 11,969.8 vs 12,555.1. So the app never loads 'Total LOB'.

## What is built
- `license_revenue_core.py` (new, pure pandas). Holds the constants `LEAGUE_VIEW` (:13), `REGIONS` (:14) and `TOTAL_LOB` (:17), the region choices (:19), the hedge pick (:27),
  and the scenario default with its fallback (:34-38). It also has the PENDING texts (:11, :37, :44, :46, :49), `select` (:75), `region_split`,
  `quarter_frame`, `license_table` (Total row last) and `megan_gaps`.
- `license_revenue.py` (new). One SQL string (:18). The SQL keeps only the 3 LOB codes and QUARTER/YEAR rows. `load()` uses `data._q`. `render()` (:37) has:
  - the Region, Scenario and Hedge controls (keys `licrev_*`) and a summary line with the region split;
  - the gap warning;
  - the altair stacked bar per quarter (tableau20, with a tooltip for license, $M and share of quarter);
  - the source caption, the P1 caption, the P2 caption, and the table in $M with 1 decimal, with P3 marked on the -Other rows;
  - a flat CSV download in $.
- `product_revenue_app.py:11-20`: the page title is now "(DRAFT) Product Revenue". The DRAFT line is kept. The page has `st.tabs`: tab 1 runs `product_revenue.render()` unchanged, and tab 2 runs
  `license_revenue.render()`.
- `snowflake.yml:145-146`: adds `license_revenue.py` and `license_revenue_core.py` to the product_revenue_dash artifacts.
- `tools/test_license_revenue.py` (new): 6 pure tests, all pass.

## Placeholders (self-check 2026-11-17)
| P# | file:line | what is missing | text shown | who can answer |
|---|---|---|---|---|
| P1 | license_revenue_core.py:44, shown license_revenue.py:84 | Intl release-level data | PENDING - Megan Coleman / Vivek Srinivasan: International release-level data is not in Snowflake (Excel only). | Megan / Vivek |
| P2 | license_revenue_core.py:46, shown license_revenue.py:53 | Pricing go-get source | PENDING - Vivek Srinivasan: no Snowflake source found for pricing go-get. | Vivek |
| P3 | license_revenue_core.py:49, shown license_revenue.py:90 | -Other leagues grouping | PENDING - Megan Coleman: group into Other? | Megan |
| P4 | license_revenue_core.py:37, shown license_revenue.py:52 | Plan_2027 missing (default falls back to RF) | PENDING - Vivek Srinivasan: Plan_2027 (FY27 Budget) is not in CARDPLN_PL_BY_LEAGUE_V yet; ... | Vivek |

Self-check fix: `megan_gaps` skips a region with no rows (no $0 stand-in).

The scenario list shows every (scenario, version, FY) pair the view has, for example "FY27 Rolling Forecast (Working)",
"FY27 Forecast (SEP26RF, Final)" and "FY26 Budget (Plan_2026, Final)". The default is Plan_2027/Final/FY27 when it exists. Today it does not, so the fallback is
Rolling Forecast/Working/FY27, shown with a PENDING caption.
