# cfd-prodrev-na-viz (DRAFT) - Product Revenue (NA) chart: quarterly bars by license / size tier

For Maya Iwabuchi; requester Megan Coleman (FP&A). NASE (CO_31010, LB_312) only. Branch `coco/cfd-prodrev-na-viz`
off `coco/megan-prodrev-app` (945b597). App: snowflake.yml entity `product_revenue_dash`
(ORACLE_DATA_PROD.SANDBOX.PRODUCT_REVENUE_DASH, main_file product_revenue_app.py). Not deployed.

## (a) Where things are / what changed

Before (on 945b597): `PRODUCT_REVENUE_SQL` product_revenue.py:26, `render()` :135, snowflake.yml
`product_revenue_dash` `artifacts:` :142-148.

| file:line | change |
| --- | --- |
| product_revenue.py:18 | `import altair as alt` (already a pyproject dependency, altair>=5) |
| product_revenue.py:23 | `import prodrev_viz as viz` |
| product_revenue.py:27 | `PENDING = "PENDING"` |
| product_revenue.py:30 | `TIER_EDGES = (10e6, 25e6, 35e6, 50e6)` - the one tier constant (rule 4) |
| product_revenue.py:31 | `TIER_NOTE` - visible PENDING caption in the size-tier view |
| product_revenue.py:34 | `LABEL_MIN_SHARE = 0.03` - design default, PENDING |
| product_revenue.py:36 | `PRODUCT_REVENUE_SQL` - unchanged (moved down 10 lines) |
| product_revenue.py:134-141 | `pivot()`: new column "COA license" (rule 1) next to "License" (PRICING_LICENSE); filled on release rows |
| product_revenue.py:147-176 | new `render_chart()`: toggle "View: License / Size tier" (:149), stacked altair bars (:169), captions |
| product_revenue.py:179 | `render()` - unchanged except :197 `render_chart(df)` above the table and :199 "COA license" added to the non-numeric list |
| product_revenue.py:196 / :200 / :203 | FY27 caption, `st.dataframe`, `download_button "Download CSV (flat, $)"` - text unchanged; CSV still the flat `load()` frame |
| prodrev_viz.py (new) | pure pandas: `license_from_coa`, `quarter_summary` (release / Other / chip %), `size_tier`, `tier_labels`, `release_counts` (peak quarter), `bar_frame` (stack order, Other = 0, labels) |
| tools/test_prodrev_viz.py (new) | pure test, imports only prodrev_viz + pandas |
| snowflake.yml:145 | `      - prodrev_viz.py` in `product_revenue_dash` artifacts (only line changed) |

Chart: one bar per quarter Q1'26..Q4'27 (x label format `<quarter> · <chip %> of <FY>`; Q1'26 = 15.9 % per table (c)), one color per COA-prefix license,
Other always the bottom block. License label format `<CODE> <bar %> · <n>` (bar % of release $ excl. Other, n = release
count in peak quarter; format proven by test `WWE 100.0% · 2`, real NA label values not read because the app was not run). Size-tier view stacks `<10M / 10-25M / 25-35M / 35-50M / Tentpole` (+ Other at bottom), label = tier %
of release $. Labels only on segments >= 3% of the bar; all segments have tooltips.

## (b) License $ by both methods ($M, app SQL, read-only)

| | FY26 | FY27 |
| --- | --- | --- |
| Total | 4,086.9 | 4,393.2 |
| **(No license)** - PRICING_LICENSE method | **387.5** (387,518,585.92) | **3,475.6** (3,475,635,692.51 = 79.1 %) |
| **Other** - COA-prefix method (rule 1) | **352.4** (352,370,765.66) | **220.6** (220,573,140.49) |

Top licenses, COA-prefix method: MLB 1,188.4 / 1,099.9; NBA 981.4 / 1,181.9; NFL 929.8 / 1,162.6; CHP 90.2 / 114.5;
MRV 81.2 / 145.1; WWE 76.0 / 74.3; DIS 70.6 / 79.2; FOR 57.2 / 50.5; UFC 47.9 / 34.9; STW 37.4 / 39.8;
EPL 36.6 / 43.5; SIM 0.0 / 34.3; NIL 23.2 / 8.0; TEN 20.6 / 10.2. 49 prefix codes incl. Other.
PRICING method: MLB 1,189.5 / 211.9; NBA 981.4 / 310.4; NFL 929.8 / 311.3; UEFA 92.7 / 27.1; Marvel 81.2 / 28.3;
WWE 76.3 / 1.4; Disney 70.6 / 3.4; Formula 1 57.2 / 1.2; UFC 47.9 / 0.0; Star Wars 37.4 / 8.1.
The prefix method fixes the FY27 "(No license)" gap: FY27 unassigned drops from $3,475.6M to $220.6M.
The two methods use different names (PRICING "Marvel" vs prefix "MRV"), so no code-to-name map is shown.

## (c) Quarter tie (chart = table = Megan FY26)

Chart bars and table both sum the same `load()` frame (all rows, incl. Other); `test_bar_pct_excludes_other` asserts
bar total = quarter total. Numbers below = app SQL run read-only, grouped by quarter.

| Quarter | Chart/table total $ | Megan file $ (row 3) | diff | Release $ | Other $ | Other % | Chip % |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Q1'26 | 651,564,292.34 | 651,564,292.35 | 0.0007 (unrounded .3444 vs .3451) | 613,624,845.15 | 37,939,447.19 | 5.82 | 15.94 |
| Q2'26 | 1,292,121,169.09 | 1,292,121,169.09 | 0.00 | 1,252,165,752.76 | 39,955,416.33 | 3.09 | 31.62 |
| Q3'26 | 1,072,629,552.22 | 1,072,629,552.22 | 0.00 | 991,579,060.52 | 81,050,491.70 | 7.56 | 26.25 |
| Q4'26 | 1,070,628,006.06 | 1,070,628,006.06 | 0.00 | 877,202,595.62 | 193,425,410.44 | 18.07 | 26.20 |
| FY26 | 4,086,943,019.71 | 4,086,943,019.71 | 0.00 | 3,734,572,254.05 | 352,370,765.66 | 8.62 | 100 |
| Q1'27 | 1,345,309,124.03 | - | - | 1,218,902,711.70 | 126,406,412.34 | 9.40 | 30.62 |
| Q2'27 | 1,265,936,505.94 | - | - | 1,136,793,486.04 | 129,143,019.90 | 10.20 | 28.82 |
| Q3'27 | 944,514,086.80 | - | - | 977,127,674.47 | -32,613,587.67 | -3.45 | 21.50 |
| Q4'27 | 837,453,494.99 | - | - | 839,816,199.08 | -2,362,704.09 | -0.28 | 19.06 |
| FY27 | 4,393,213,211.77 | 4,550,615,776.83 | -157,402,565.06 | 4,172,640,071.28 | 220,573,140.49 | 5.02 | 100 |

Chip % = quarter / FY (computed from the totals; the SQL's window column was halved by the rollup row, so it was
recomputed). FY27 gap = the known $157M (caption kept). Megan's Q1'27 $1,458M / NBA 43.3 % are GLOBAL - not tied.

## (d) COAs in "Other" (top 20 by |FY26|+|FY27|, $)

| COA | Name | FY26 | FY27 |
| --- | --- | --- | --- |
| 10004 | NBA - General | 67,060,503.53 | 150,000,000.00 |
| 10003 | NFL - General | 64,077,910.03 | 150,000,000.00 |
| 10517 | NBA - Hedge | 0.00 | -119,138,584.22 |
| 10509 | NFL - Hedge | 0.00 | -95,199,062.65 |
| 10426 | MLB - Topps Now | 37,302,147.65 | 35,275,208.58 |
| 10434 | NBA - Topps Now | 27,291,140.11 | 32,251,619.27 |
| 19998 | Un-allocatable - League - General | 21,705,646.66 | 28,800,000.00 |
| 50199 | Simpsons - Hedge | 0.00 | -34,349,021.25 |
| 10002 | MLB - General | 29,748,477.48 | 0.00 |
| 50116 | Brand - Other - Supplies | 6,405,793.15 | 22,377,673.64 |
| 10444 | NFL - Topps Now | 11,391,276.08 | 16,125,809.63 |
| 10007 | UEFA Champions League - General | 15,191,909.05 | 10,000,000.00 |
| 50193 | Marvel - Hedge | 0.00 | -18,105,523.93 |
| 10025 | F1 Racing - General | 1,310,163.94 | 10,000,000.00 |
| 10581 | MLB - Hedge | 0.00 | -11,190,491.59 |
| 50002 | Disney - General | 0.00 | 10,000,000.00 |
| 10408 | English Premiere League - General | 4,035,225.13 | 5,000,000.00 |
| 10522 | UEFA Champions League - Hedge | 0.00 | -7,674,941.52 |
| 10491 | WWE - Topps Now | 3,698,086.75 | 3,023,589.31 |
| 50009 | Star Wars - General | 1,831,210.28 | 5,000,000.00 |

All 20 are "(No license)" under PRICING too. 219 COAs are Other with non-zero $ in the app rows (FY26+FY27). The FY26 release view lists 420 non-prefix COAs, most with no $.

## (e) Checks

```
$ python3 -m py_compile product_revenue.py product_revenue_app.py prodrev_viz.py tools/test_prodrev_viz.py
COMPILE_OK
$ python3 tools/test_prodrev_viz.py
PASS test_bar_pct_excludes_other
PASS test_chip_pct
PASS test_peak_quarter_count
PASS test_prefix_rule
PASS test_tier_edges
PASS test_tier_view_pct
6 passed
```

## (f) AppTest not run (HARD RULE). The chart was not rendered; streamlit was not run.

## (g) Findings

1. CONFIRMED - FY26 chart/table quarter totals = Megan file row 3 to $0.01 (max diff $0.0007, Q1).
2. CONFIRMED - COA-prefix method cuts FY27 unassigned $ from 3,475.6M (79.1 %) to 220.6M (5.0 %).
3. CONFIRMED - The prefix rule must be "3 letters + a digit": GMPLN has COA `UNKNOWN` ($1.2M FY26) and `PD02624`-style
   codes that "first 3 letters" alone would turn into licenses "UNK" / "PD0". These go to Other.
4. LIKELY - FY27 Other holds negative Hedge COAs (NBA -119.1M, NFL -95.2M, ...), so Other is negative in Q3'27 / Q4'27
   and the bottom block draws below zero. Hedges are in the source data; nothing was added. Megan should say whether
   hedges belong in Other.
5. LIKELY - `XXX9999` COAs (NFL9999, ZCC9999, ...) look like plugs; they have no FY26 $ in the release view, so they
   change nothing today, but by rule 1 they would count as releases if they ever get $.
6. LIKELY - Size tiers above $35M (35-50M, Tentpole >= 50M) are not confirmed by Megan (visible PENDING caption).
7. I DON'T KNOW - Release count tie-break: equal peak quarters go to the earlier quarter (my choice, tested).
8. I DON'T KNOW - Whether the chart renders as intended in the container runtime (not run, HARD RULE).

## (h) git diff --stat coco/megan-prodrev-app

Tracked: `product_revenue.py | 53 ++++-` and `snowflake.yml | 1 +`. New (untracked until the fleet commits):
`prodrev_viz.py`, `tools/test_prodrev_viz.py`, `docs/fleet/cfd-prodrev-na-viz.md`. No other files.
