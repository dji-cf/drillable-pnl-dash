# (DRAFT) Revenue by License (Global) — fleet report cfd-license-global

CoCo for Maya Iwabuchi, 2026-11-17. Requester James Dillon; content owner Megan Coleman.
Source: `ORACLE_DATA_PROD.FCT_EPM.CARDPLN_PL_BY_LEAGUE_V` (read-only SQL, connection `fleet`).

## STEP 1 — data proof

> **(updated 2026-11-17)** The 1d tie-out and the "Gap vs Megan" table below include PG_10000 ("Sports - Other").
> PG_10000 is the parent of the sports leagues, so sports is counted 2x in those numbers. See
> "Follow-up: PG_10000 parent rule" at the end for the corrected numbers.

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
- `tools/test_license_revenue.py` (new): 8 pure tests, all pass (updated 2026-11-17: +2 tests for the PG_10000 parent rule).

## Placeholders (updated 2026-11-17, follow-up)
| P# | file:line | what is missing | text shown | who can answer |
|---|---|---|---|---|
| P1 | license_revenue_core.py:54, shown license_revenue.py:88 | Intl release-level data | PENDING - Megan Coleman / Vivek Srinivasan: International release-level data is not in Snowflake (Excel only). | Megan / Vivek |
| P2 | license_revenue_core.py:56, shown license_revenue.py:53 | Pricing go-get source | PENDING - Vivek Srinivasan: no Snowflake source found for pricing go-get. | Vivek |
| P3 | license_revenue_core.py:59, shown license_revenue.py:94 | Grouping of "Entertainment - Other" (PG_50000) | PENDING - Megan Coleman: group into Other? | Megan |
| P4 | license_revenue_core.py:35-37, shown license_revenue.py:52 | FY27 Budget by license | PENDING - Vivek Srinivasan: FY27 Budget by license is not in Snowflake (CARDPLN_PL_BY_LEAGUE last loaded 2026-09-29; budget 2027B-09.28 has no league split). Showing the FY26 Budget (Plan_2026) instead. | Vivek |

Self-check fix: `megan_gaps` skips a region with no rows (no $0 stand-in).

The scenario list shows every (scenario, version, FY) pair the view has. The default is Plan_2027/Final/FY27 when it
exists. Today it does not, so the default is **(updated 2026-11-17)** Plan_2026/Final/FY26 (Maya picked default B).
The FY27 Rolling Forecast stays in the list, but it is not the default.

## Follow-up: PG_10000 parent rule (updated 2026-11-17)

**Why:** Maya ran read-only SQL in Snowsight on 2026-11-17 and approved this fix. PG_10000 ("Sports - Other") is the
PARENT of the sports leagues. The view adds PG_10000 on top of its children, so sports is counted 2x. Example: RF FY27 NA
9,423.5 = PG_10000 4,459.7 + leagues 4,963.8. Vivek has not confirmed this yet.

### Maya's tests (Snowsight, 2026-11-17; as given in the instruction)
**Test A: PG_10000 vs the sum of leagues with category = 'Sports' ($M)**
| Scenario / FY / LOB | PG_10000 | Sum of Sports leagues |
|---|---|---|
| Actual FY26 NA | 2,530.6 | 2,500.0 |
| Plan_2026 FY26 NA | 2,590.5 | 2,576.8 |
| Plan_2026 FY26 Intl | 541.0 | 541.0 |
| RF FY26 NA | 3,985.7 | 3,904.3 |
| RF FY27 NA | 4,459.7 | 4,323.3 |

The range PG_10001–PG_19999 matched no rows. The league codes are PG_20xxx and PG_6xxxx.

**Test B: league view with PG_10000 / without PG_10000 / CARDPLN_PL_BY_LOB_V2 ($M)**
V2 filter: ACCOUNT='ACX_Net Revenue', ENTITY='CO_31000', Total Intercompany, Total Channel, USD_Reporting.
| Scenario / FY / LOB | with | without | LOB_V2 |
|---|---|---|---|
| Actual FY26 NA | 5,378.1 | 2,847.5 | 3,105.0 |
| Plan_2026 FY26 NA | 5,493.2 | 2,902.7 | 2,838.0 |
| SEP26RF FY26 NA | 8,358.3 | 4,372.6 | 4,239.0 |
| SEP26RF FY27 NA | 4,471.2 | 0.0 | 4,471.2 (only PG_10000 is loaded) |
| SEP26RF FY27 Intl | 1,705.9 | 897.5 | 869.0 |

**Test C:** only CARDPLN_PL_BY_LEAGUE and CARDPLN_PL_BY_LEAGUE_V have both scenario and product/league columns. Both have 0 rows for
the FY27 budget scenario '2027B-09.28'. The budget exists only in CARDPLN_PL_BY_LOB_STG / V2, which have no league split.
CARDPLN_PL_BY_LEAGUE was last altered on 2026-09-29.

### The rule in the app
`license_revenue_core.py:85-91` `drop_sports_parent`. It is called first in `select()` (`license_revenue_core.py:99`), so every
summary, chart and table gets it. The constants are at `license_revenue_core.py:39-48`.
- The group key is (scenario, version, fiscal_year, period_type, period, lob).
- If a group has any row that is not PG_10000, the PG_10000 rows in that group are dropped.
- If a group has only PG_10000 rows, those rows are kept, with league = "Sports - total (no league split)".

The SQL now also selects `product_group` (`license_revenue.py:19`). A new caption sits under the source caption
(`license_revenue.py:86-87`). For any selection that is not FY27, the app shows `st.info("Budget artifact targets are FY27; not compared to <label>.")`
instead of the gap warning (`license_revenue.py:63-65`). The FY27 warning is kept.

**OTHER_LIKE / P3:** I checked the whole view with read-only SQL. The league "Sports - Other" is only PG_10000 (1,838 rows).
"Entertainment - Other" is only PG_50000 (1,735 rows). So after the rule, "Sports - Other" never shows under that name.
It is either dropped, or shown as "Sports - total (no league split)". Its OTHER_LIKE entry is kept as the task says, but it
has no effect now. P3 applies only to "Entertainment - Other".

### Step 8: FY totals per LOB after the rule (read-only SQL, same rule in SQL, PERIOD_TYPE='YEAR', USD_Reporting, $M)
The gap is view minus V2. There is a V2 number only where Maya's Test B has one.
| Scenario / FY | LOB | AMOUNT | UNHEDGED | of which "Sports - total" | rows | V2 (Test B) | Gap $M | Gap % |
|---|---|---|---|---|---|---|---|---|
| Plan_2026 Final FY26 | NA | 2,902.7 | 3,262.2 | 0.0 | 18 | 2,838.0 | +64.7 | +2.3% |
| | Intl | 643.4 | 643.4 | 0.0 | 18 | PENDING - Maya Iwabuchi: V2 Intl Plan_2026 FY26 not run | – | – |
| | Digital | 101.6 | 101.6 | 0.0 | 11 | PENDING - Maya Iwabuchi: V2 Digital not run | – | – |
| Actual Final FY26 | NA | 2,847.5 | 2,847.5 | 0.0 | 20 | 3,105.0 | -257.5 | -8.3% |
| | Intl | 414.2 | 414.2 | 0.0 | 19 | PENDING - Maya Iwabuchi: V2 not run | – | – |
| | Digital | 57.6 | 57.6 | 0.0 | 12 | PENDING - Maya Iwabuchi: V2 not run | – | – |
| SEP26RF Final FY26 | NA | 4,372.6 | 4,372.6 | 0.0 | 20 | 4,239.0 | +133.6 | +3.2% |
| | Intl | 753.4 | 766.9 | 0.0 | 19 | PENDING - Maya Iwabuchi: V2 not run | – | – |
| | Digital | 87.8 | 87.8 | 0.0 | 12 | PENDING - Maya Iwabuchi: V2 not run | – | – |
| SEP26RF Final FY27 | NA | 4,471.2 | 4,471.2 | **4,471.2** | 1 | 4,471.2 | 0.0 | 0.0% |
| | Intl | 897.5 | 897.5 | 0.0 | 18 | 869.0 | +28.5 | +3.3% |
| | Digital | 114.0 | 114.0 | 0.0 | 11 | PENDING - Maya Iwabuchi: V2 not run | – | – |
| Rolling Forecast Working FY27 | NA | 4,963.7 | 5,225.3 | 0.0 | 19 | PENDING - Maya Iwabuchi: V2 RF FY27 not run | – | – |
| | Intl | 1,284.4 | 1,372.6 | 0.0 | 18 | PENDING - Maya Iwabuchi: V2 not run | – | – |
| | Digital | 94.3 | 94.3 | 0.0 | 11 | PENDING - Maya Iwabuchi: V2 not run | – | – |

The expected values tie: Plan_2026 FY26 NA is 2,902.7, and SEP26RF FY27 NA is 4,471.2 (all of it "Sports - total"). Every "without"
number in Maya's Test B matches this run exactly. The RF FY27 NA total is 4,963.7; Maya's "leagues 4,963.8" is a $0.1M rounding difference.

**FY27 vs Megan after the rule (hedged, ex Digital, $M):**
| Scenario | NA view / Megan | Intl view / Megan | Total view / Megan |
|---|---|---|---|
| Rolling Forecast Working | 4,963.7 / 3,976 (+987.7, +24.8%) | 1,284.4 / 1,182 (+102.4, +8.7%) | 6,248.1 / 5,158 (+1,090.1, +21.1%) |
| SEP26RF Final | 4,471.2 / 3,976 (+495.2, +12.5%) | 897.5 / 1,182 (-284.5, -24.1%) | 5,368.7 / 5,158 (+210.7, +4.1%) |

Megan's targets are the FY27 budget, and no league-level FY27 budget exists (Test C). So these are not like-for-like
comparisons.

Hedge check (self-check 2026-11-17, read-only SQL on PRODUCT_GROUP='PG_10000', YEAR): HEDGE = 0.0 for NA and Intl in
Plan_2026 FY26, RF FY27 and SEP26RF FY27. So dropping PG_10000 does not move the hedge. The PG_10000 AMOUNT values
(Plan_2026 NA 2,590.5, Intl 541.0; RF FY27 NA 4,459.7) match Maya's Test A.

## Standalone app (2026-11-17)

**Why:** Maya, Cowork chat 2026-11-17 ~14:35 ET: "can we publish as it's own standalone dashboard for now?" Revenue by
License is now its OWN Streamlit app. It is not a 2nd tab in PRODUCT_REVENUE_DASH any more. **(updated 2026-11-17)**: the
"What is built" lines above about `product_revenue_app.py:11-20` (tabs) and `snowflake.yml:145-146` are replaced by this section.

**Restored (equal to live commit ae167de; `git diff ae167de -- <file>` is empty):**
- `product_revenue_app.py`: written from `git show ae167de:product_revenue_app.py`. It has no license_revenue import, no
  st.tabs, and page_title "(DRAFT) NA Product Revenue".
- `snowflake.yml` entity `product_revenue_dash` (:128-149): the 2 lines `license_revenue.py` and `license_revenue_core.py` are removed.

**New entity** `snowflake.yml:150-172` `license_revenue_dash`:
- comment at :150; identifier `ORACLE_DATA_PROD.SANDBOX.LICENSE_REVENUE_DASH`; title "(DRAFT) Revenue by License (Global)";
- the same stage, runtime, compute pool, EAI and warehouse as product_revenue_dash;
- `main_file: license_revenue_app.py` (:164);
- artifacts (:166-172): license_revenue_app.py, license_revenue.py, license_revenue_core.py, data.py, queries.py,
  pyproject.toml, .streamlit/config.toml.

**New entrypoint** `license_revenue_app.py`: docstring :1-4; `st.set_page_config(page_title="(DRAFT) Revenue by License")` :11;
DRAFT line :12; `license_revenue.render()` :13.

**`license_revenue.py`:**
- :1 docstring now says "standalone app license_revenue_dash (LICENSE_REVENUE_DASH)".
- :38 subheader is now "Revenue by License (Global)". I removed "(DRAFT)" because the page already shows the DRAFT line
  (`license_revenue_app.py:12`). This keeps exactly one visible DRAFT label in the page body.

**Import check:**
| File | Imports | In the artifacts? |
|---|---|---|
| license_revenue.py | altair, pandas, streamlit, data, license_revenue_core | data.py and license_revenue_core.py: yes. altair is in pyproject.toml:19 (`"altair>=5"`) |
| license_revenue_core.py | pandas only | – |
| data.py | os, datetime, pandas, streamlit, queries | queries.py: yes |

Neither file imports prodrev_viz.py or product_revenue.py, so those two files are not in the new entity.
