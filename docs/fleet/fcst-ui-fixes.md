# fcst-ui-fixes: A4, A8, A10 (James's UI asks)

Base: `coco/fcst-ui-audit` (origin/dji a886ebc + audit 2d6a066). Decisions: Maya, 2026-11-03 07:45
(thread fcst-ui-audit): "1 Fanatics Live and Collect, 2 yes"; A10 rule = Option B.

| Item | What changed | file:line | How to see it in the app (which View / dropdown) | Test run |
| --- | --- | --- | --- | --- |
| A4 | Display name "Fanatics Collect" -> "Fanatics Live and Collect": BU page name (nav + page title), the consolidated row label on Revenue / Gross Margin / EBITDA (rows 5, 12, 21, so also the Excel/CSV "Line Item" column), the GM metric label, the row tooltip key, and the drill map. Row-keyed maps (`STG_ROW_MAP`, `BU_DEFS`, validator labels) follow the new label. Kept as-is: source member `queries.py:66` "Total - Fanatics Live and Collect", dict key `"collect"`, `URL_PATHS` (`/collect`). The validator renames the deck JSON's printed "Fanatics Collect" on load (`_p7_labels`); the reference JSON is unchanged. | `bu.py:1,40`; `transforms.py:451,462,474,492`; `table.py:43`; `queries.py:575,589,608,631`; `streamlit_app.py:11`; `tools/validate_vs_deck.py:733,737,742,759,762-767,886-887` | The sidebar page list and the BU page title read "Fanatics Live and Collect". On the consolidated Forecast Table the Revenue, Gross Margin and EBITDA rows read "Fanatics Live and Collect", and clicking the label still opens the BU page. | `python3 tools/test_vintages.py`: ALL VINTAGE CHECKS PASS |
| A8 | YTD is now a View. `GRAIN_LABELS` / `GRAINS` / export `GRAIN_TITLES` get `"ytd"` (order Annual, Quarterly, Monthly, YTD). `Cube.periods()` no longer adds a YTD column to Annual / Quarterly / Monthly. The `"ytd"` grain returns only the vintage's YTD period (e.g. `YTD Aug 26A`), so the grid looks like Annual: Reference, Main, Delta. The reference block is read at the same key, so it shows the same months of the reference scenario (`YTD Aug 25A`, not FY 2025A). A vintage with no YTD (Budget, Jan FC, complete Actuals) falls back to its FY column, labelled `FY 2026B` etc. table.py / export.py / style.py already handle a YTD key by `is_ytd()` (no grain branching), so no KeyError and the Delta column is kept. KPI tiles stay on FY (as before). | `streamlit_app.py:52-57,197`; `transforms.py:81,901-924`; `export.py:30-35` | View control (segmented control above the grid, consolidated and BU pages): pick **YTD**. Annual / Quarterly / Monthly no longer show a YTD column. Excel title reads "... — YTD", file name ends `_ytd.xlsx`. | `test_vintages.py` (new checks: no YTD column at the 3 grains; `periods(...,"ytd")`; 2025A ref label `YTD Aug 25A`; Budget fallback `FY 2026B`; grid HTML + export shape at `ytd`): PASS |
| A10 | `comp_options()` now offers only: None; the Budget of the same fiscal year; complete Actuals of the prior fiscal year; forecasts of the same fiscal year with an earlier as-of month. No later scenarios and no Budget / forecast of another year, even with "show prior-year" on. It uses `Cube.fiscal_year` and the as-of month parsed from the vintage key (`vintage_parts`, the parser of `queries._VINTAGE_KEY`), with no hard-coded years. Main = Budget: only None and the prior-year Actuals. `resolve_comp()` is unchanged: a stored comparison that is no longer allowed resets to the first entry (None). | `transforms.py:631-664` | "vs." dropdown in the sidebar. With Forecast = Aug 2026 FC it lists None, 2026 Budget, 2025 Actuals (no Sep FC). With Sep 2026 FC: None, 2026 Budget, 2025 Actuals, Aug 2026 FC. An FY25 forecast no longer offers 2026B (this removes the -37% compare). | `test_vintages.py` (new checks: Aug FC excludes Sep FC; retired toggle adds no other-year items; 2026B main; FY25 FC gets no FY26 items; reset of a disallowed stored comp; Feb 2027 FC drops 2025A): PASS |

Checks run:
- `python3 -m py_compile` on bu.py, export.py, queries.py, streamlit_app.py, table.py, transforms.py, tools/test_vintages.py, tools/validate_vs_deck.py: pass.
- `python3 tools/test_vintages.py` (offline, synthetic cube, no Snowflake): ALL VINTAGE CHECKS PASS. I updated its old expectations: YTD is no longer in Quarterly, and the Feb 2027 FC comparison list no longer has 2025A.
- grep "Fanatics Collect" (outside output/bundle/): no user-facing app string is left. Remaining hits: code comments (`queries.py:58`), the dev script `tools/gap_analysis.py:222`, the validator's load-time rename, the reference deck JSONs (the deck's own printed label), ISSUES.md / audit doc, and `master_query.sql` (a standalone SQL reference that no .py file loads).

Not run: streamlit, the Snowflake-backed validators (validate_vs_deck, validate_bu, smoke_render), and tools/test_compensation_flag.py (the sandbox did not allow it).

## Budget double-count fix (updated 2026-11-03)

**Who / when:** Maya said yes on 2026-11-03 08:46 (thread fcst-ui-audit: fix it now, and drop the fake "2028 Budget") and at 08:47 (thread fcst-ui-fixes: add the fix to this branch, do not push yet). The cause is in the "Budget double-count check" part of `git show coco/fcst-ui-audit:docs/fleet/fcst-ui-audit.md` (commit 2849828).

**Cause:** The STG raw CTE had no SCENARIO filter. The budget key is `'20'||SUBSTR(FISCAL_YEAR,3,2)||'B'` (`queries.py:177`), so the FY26 rows of `2027B-09.28` (a copy of SEP26RF) were added into "2026B" together with `Plan_2026`. Its FY28 rows made a "2028B" vintage.

**Change:** `queries.py:490-494`, in the `STG_SQL` raw CTE WHERE:
```sql
    AND NOT (SCENARIO_LABEL = 'BUDGET' AND COALESCE(SCENARIO, '') LIKE '20__B-%'
             AND FISCAL_YEAR <> 'FY' || SUBSTR(SCENARIO, 3, 2))
```
A `20YYB-...` budget keeps only its own year (FY`YY`). Other budget names (e.g. `Plan_2026`) are not matched and pass as before. No scenario names are hard-coded. This is the only code change after 37a0f5d (`git diff --stat 37a0f5d`: `queries.py | 5 +++++`).

**Rows (read-only, query id 01c82a3d-031a-2f84-69de-0701a06aeb2f):**

| SCENARIO | FISCAL_YEAR | Kept | Rows |
| --- | --- | --- | --- |
| 2027B-09.28 | FY26 | no | 40,971 |
| 2027B-09.28 | FY27 | yes | 39,026 |
| 2027B-09.28 | FY28 | no | 1,244 |
| Plan_2026 | FY26 | yes | 18,615 |

**Before / after ($M, FY total, all LOBs, same WHERE and rev / cogs / sga logic as `STG_SQL`; query id 01c82a3d-031a-364f-69de-0701a06b164f):**

| Budget | Before revenue | Before EBITDA | After revenue | After EBITDA | Proof |
| --- | --- | --- | --- | --- | --- |
| 2026B (FY26) | 9,071.9 | 3,180.2 | **3,646.7** | **1,080.2** | Before = the audit figure. After = `9.2026 Collectibles Fcst Deck FHI.xlsx`, sheet "One-Pager", column "Budget": Revenue 3646.710224098943 / Adj. EBITDA 1080.1960405868285 (rows 9 and 12, read with openpyxl, read-only, in the self-check (updated 2026-11-03)) |
| 2027B (FY27) | 6,272.6 | 2,138.0 | 6,272.6 | 2,138.0 | unchanged |
| 2028B (FY28) | 58.4 | 25.0 | **no row** | **no row** | no "2028 Budget" label |

SQL used (after = rows with `keep_new`; before = all rows):
```sql
WITH raw AS (
  SELECT SCENARIO_LABEL, SCENARIO, FISCAL_YEAR, PERIOD_TYPE, LOB, ACCOUNT, COST_CENTER, AMOUNT,
         NOT (SCENARIO_LABEL = 'BUDGET' AND COALESCE(SCENARIO, '') LIKE '20__B-%'
              AND FISCAL_YEAR <> 'FY' || SUBSTR(SCENARIO, 3, 2)) AS keep_new
  FROM ORACLE_DATA_PROD.FCT_EPM.CARDPLN_PL_BY_LOB_STG
  WHERE CHANNEL = 'Total Channel' AND PLAN_ELEMENT = 'Total_Budget'
    AND VERSION = 'Final' AND CURRENCY = 'USD_Reporting' AND ENTITY = 'CO_31000'
    AND ((LOB <> 'LB_392' AND INTERCOMPANY = 'Total Intercompany') OR (LOB = 'LB_392' AND INTERCOMPANY = 'ICP_32002'))
    AND SCENARIO_LABEL = 'BUDGET' AND FISCAL_YEAR >= 'FY25' AND PERIOD_TYPE = 'YEAR'
    AND LOB IN ('LB_301','LB_302','LB_303','LB_304','LB_305','LB_306','LB_307','LB_308','LB_392','LB_394','Total - Topps Eliminations')
), by_lob AS (
  SELECT keep_new, FISCAL_YEAR, LOB,
    SUM(IFF(ACCOUNT IN ('ACX_Net Revenue','AC_40001'), AMOUNT, 0)) AS rev,
    COALESCE(SUM(IFF(ACCOUNT = 'AC_50000' AND COST_CENTER = 'CC_10000', AMOUNT, NULL)),
             SUM(IFF(ACCOUNT IN ('ACX_Manufacturing','ACX_Net Freight Expense','ACX_Royalties','ACX_MG Shortfall','ACX_Autos & Relics','ACX_Obsolescence','ACX_Compensation','ACX_Product Development') AND COST_CENTER = 'CC_10000', AMOUNT, NULL)), 0) AS cogs,
    SUM(IFF(ACCOUNT = 'AC_50000' AND COST_CENTER = 'CC_30000', AMOUNT, 0)) AS sga
  FROM raw GROUP BY 1,2,3
), filt AS (
  SELECT 'after' AS run, FISCAL_YEAR, LOB, rev, cogs, sga FROM (
    SELECT FISCAL_YEAR, LOB, SUM(rev) rev, SUM(cogs) cogs, SUM(sga) sga FROM by_lob WHERE keep_new GROUP BY 1,2)
  UNION ALL
  SELECT 'before', FISCAL_YEAR, LOB, SUM(rev), SUM(cogs), SUM(sga) FROM by_lob GROUP BY 2,3
)
SELECT run, FISCAL_YEAR, ROUND(SUM(rev)/1e6,1) AS revenue_m, ROUND(SUM(rev-cogs-sga)/1e6,1) AS ebitda_m
FROM filt GROUP BY 1,2 ORDER BY 1,2 LIMIT 50
```
The query uses the same total as the app: Total Revenue / Total EBITDA = the sum of all base LOB segments (`queries.STG_ROW_MAP[("EBITDA","Total EBITDA")]`). The Pisa and TCG carve-outs net to zero. I did not run the full generated `STG_SQL`. This query is a shorter copy of the same filter and sums. Its "before" result (9,071.9 / 3,180.2) is the same as the audit's number for the app (`git show coco/fcst-ui-audit:docs/fleet/fcst-ui-audit.md`, line 66), so the short query gives the same totals as the app. Self-check re-run (updated 2026-11-03): query id 01c82a3f-031a-2bcc-69de-0701a06acb0f gave FY26 3646.7 / 1080.2 and FY27 6272.6 / 2138, with no FY28 row.

**No "2028B" in the app:** The vintage list comes only from the `vintage_key` values the SQL returns (`transforms.py:955` in `build_cube`). With no FY28 BUDGET rows left, `'20'||'28'||'B'` cannot be built. Forecast rows were already limited to their own year (`queries.py` `_VINTAGE_FILTER`). How to see it: the Forecast and "vs." dropdowns no longer offer "2028 Budget". "2026 Budget" FY Total Revenue reads $3,646.7M.

**Tests:** `python3 -m py_compile queries.py` passes. `python3 tools/test_vintages.py` prints ALL VINTAGE CHECKS PASS (offline; this test does not use STG_SQL, so it does not cover the filter). The SQL above is the proof. I did not run streamlit.
