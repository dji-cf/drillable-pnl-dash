# Forecast dashboard UI audit: James Dillon's items vs. origin/dji

Branch audited: `origin/dji` @ `a886ebc` ("Added chat sidebar", 10/27). Report only, no code changed.
Source in use: `queries.py:46` `PNL_SOURCE` defaults to `STG` = `ORACLE_DATA_PROD.FCT_EPM.CARDPLN_PL_BY_LOB_STG` (`queries.py:324`).

| Item | State | Proof file:line | What is left (1 line) | Size |
|---|---|---|---|---|
| A1 Delta label "Change vs. [comparator]" | DONE | `transforms.py:574-576` `change_label()` returns `f"Change vs. {vintage_label(comp)}"`; used in header `table.py:89`; export block `export.py:41` | Nothing | S |
| A2 $ / % toggle on Delta | DONE | `table.py:23,69` `.dmode` buttons (`MODE_TIP` "Show the change as a % or as $M"); state `streamlit_app.py:242-244,298-299` `delta_mode`; export honours it `export.py:93-96,220` | Nothing (margin rows always bps, by design) | S |
| A3 Data-driven labels, FC names with year, hide closed-year FCs/Budget | DONE | `transforms.py:555-571` `vintage_label()` (docstring: no "(PY)"/"(partial)"); FC key `queries.py:174-180` `MONTHNAME(asof) ' ' YEAR ' FC'` -> "Sep 2026 FC"; `transforms.py:716-731` `final_years`/`is_retired`; `streamlit_app.py:124-138` "Show prior-year forecasts & budgets" checkbox, off by default | Nothing. Watch: FY26 has 2 budget scenarios (`Plan_2026`, `2027B-09.28`) and both map to key `2026B` (`queries.py:177`), see note 2 | S |
| A4 "Fanatics Collect" name | PARTLY | Display name is "Fanatics Collect" (`bu.py:1,40`; `queries.py:575,589,608`). Source member still `queries.py:66` `"fanlive": "Total - Fanatics Live and Collect"` (EPM member name, not a UI label) | Maya to confirm the wanted name (her 9/29 rename went the other way); UI string is one line in `bu.py:40` | S |
| A5 "FY26 Actuals (Partial)" | DONE (removed) | `transforms.py:733-746` `Cube.visible()` drops ACTUAL vintages that are not 12 months complete; YTD column replaces it. SQL: FY26 `Actual` exists in STG but is partial, so not offered | Nothing, unless James wants it back | S |
| A6 Monthly: sticky labels, no overlap, Delta greyed for actualized months | DONE | Sticky opaque label column `style.py:18-19,54-55,85-87,107-111` (`position: sticky; left: 0; background:#fff`); greyed cell `table.py:209` `class="gc gact"` with em dash, rule `transforms.py:759-773`, CSS `style.py:17,123` | Visual check on a narrow screen only | S |
| A7 Excel / CSV export | DONE | `export.py:153-161` `to_csv`, `export.py:187+` `to_xlsx`, buttons `streamlit_app.py:257-262` `st.download_button` | Nothing | S |
| A8 YTD as a View toggle (Annual-style) | NOT DONE | View options are only Annual/Quarterly/Monthly `streamlit_app.py:53-55` `GRAIN_LABELS`, `streamlit_app.py:210`; YTD is an always-on extra column `transforms.py:884-892` (`tail.insert(0, ytd)`), `table.py:105-106` `ytd-col` | Add "YTD" grain giving Main / Reference / Delta like Annual; drop the always-on column | M |
| A9 Delta cell shading follows font color | DONE | `style.py:119-121` `td.gpos {color:#16a34a; background:#f0faf3}`, `td.gneg {color:#dc2626; background:#fff5f5}`, `td.gflat`; class picked per row incl. cost flip `transforms.py:184,246,263`; Subtotal / Total Physical Cards rows `transforms.py:448-473` | Visual check of the 2 named rows only | S |
| A10 Reference dropdown only earlier scenarios, no cross-year | NOT DONE | `transforms.py:631-643` `comp_options()` offers every visible Budget, Actual and Forecast except the selected one (later FCs like Aug FC stay offered for Jun FC); no fiscal-year filter. Only collision reset `transforms.py:646-650` `resolve_comp` | Filter to vintages older than the main one and same fiscal year (plus prior-year Actuals?); decide rule with James | M |
| A11 Remove old 2025F scenarios | PARTLY | Still loaded: `queries.py:172` `FIRST_FISCAL_YEAR = "FY25"`, filter `queries.py:182-185`. SQL: STG has `OCT25RF`/`NOV25RF`/`DEC25RF` for FY25. Hidden by default only because FY25 actuals are final (`transforms.py:723-731`); come back with the sidebar checkbox | Exclude FY25 forecasts in `_VINTAGE_FILTER` (keep 2025A) or drop from the checkbox | S |
| A12 Trends tab: 3 charts | DONE | `charts.py:7-11` outlook line by vintage, sections `charts.py:206` "1. Outlook across forecasts", `charts.py:335` "2. Monthly values by forecast", `charts.py:470` "3. Change by business unit"; tab `streamlit_app.py:316,327-410` "Historical Trends" | James said "open to discussion": needs his sign-off only | S |

## Scenario values in the source (read-only SQL, STG, grouped)

`SELECT SCENARIO_LABEL, SCENARIO, FISCAL_YEAR, COUNT(*) ... FROM ORACLE_DATA_PROD.FCT_EPM.CARDPLN_PL_BY_LOB_STG GROUP BY 1,2,3` (34 rows):

- ACTUAL `Actual`: FY23, FY24, FY25, FY26 (FY23/24 cut by `FIRST_FISCAL_YEAR = FY25`).
- FORECAST FY25: `OCT25RF`, `NOV25RF`, `DEC25RF`. These are the 2025F items in A11.
- FORECAST FY26: `DEC25RF` (1,397 rows, dropped by the as-of-year = fiscal-year rule `queries.py:184-185`), `JAN26RF` .. `OCT26RF`.
- BUDGET FY26: `Plan_2026` and `2027B-09.28`. BUDGET FY27: `2027B-09.28`. FY28: small `2027B-09.28`, `AUG26RF`, `SEP26RF` rows.
- FY27/FY28 rows of 2026 forecasts are dropped by the same rule; FY27 `2027B-09.28` comes through as `2027B`.

Notes:
1. A5: the partial FY26 `Actual` is in the data but `Cube.visible()` hides it, so the dropdown does not show it.
2. Outside the 12 items (CONFIRMED in code and data, LIKELY on screen): STG has 2 FY26 budgets. Each has 12 months: `Plan_2026` (sum of AMOUNT over all accounts = $13,553.8M) and `2027B-09.28` ($18,822.4M). The STG query has no SCENARIO filter (`queries.py:477-484`). The Budget key is built from FISCAL_YEAR only (`queries.py:177`). So both scenarios are summed into `2026B`. I could not run the app to see the number on screen. Also, `ISSUES.md:418` says "STG has no FY27 budget yet". That is now out of date: STG has `2027B-09.28` for FY27 (39,400 rows). Check this before James approves.
3. A3 and A11 depend on FY25 being "final". CONFIRMED: FY25 `Actual` has 12 distinct months, FY26 `Actual` has 9.

```sql
SELECT SCENARIO_LABEL, SCENARIO, FISCAL_YEAR, COUNT(DISTINCT PERIOD) months, ROUND(SUM(AMOUNT)/1e6,1) amt_m
FROM ORACLE_DATA_PROD.FCT_EPM.CARDPLN_PL_BY_LOB_STG
WHERE SCENARIO_LABEL IN ('ACTUAL','BUDGET') AND FISCAL_YEAR IN ('FY25','FY26') AND PERIOD_TYPE='MONTH'
GROUP BY 1,2,3;
-- ACTUAL Actual FY25 12 | ACTUAL Actual FY26 9 | BUDGET 2027B-09.28 FY26 12 | BUDGET Plan_2026 FY26 12
```

## origin/dji vs coco/cfd-shell

`git diff origin/dji coco/cfd-shell --stat`: `export.py` (22), `financial_app.py` (+90, new), `snowflake.yml` (+33), `streamlit_app.py` (289), `tools/preflight_artifacts.py`, `tools/test_financial_app.py`. `transforms.py`, `table.py`, `style.py`, `charts.py`, `bu.py`, `queries.py` are **identical**.

- A1, A2, A3, A5, A6, A9, A10, A11, A12 live in the identical files, so cfd-shell has **the same state**. The retired-vintage checkbox moved inside a function there (`coco/cfd-shell:streamlit_app.py:175-183`), same behaviour.
- A7: same; the export changes are only a filename/title prefix and a draft flag.
- A8: same (NOT DONE); `GRAIN_LABELS` still has 3 views (`coco/cfd-shell:streamlit_app.py:64`).
- A4: same.
- A fix in `transforms.py`/`queries.py` (A10, A11, most of A8) lands in both apps if both branches take it. `streamlit_app.py` differs, so the UI part of A8 needs a separate change in each.
