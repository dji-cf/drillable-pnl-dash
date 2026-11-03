# CFD SG&A tab: Will's template in the Collectibles Financial Dashboard

Run 2026-11-03. Prepared by CoCo for Maya Iwabuchi. Requester: Will Oswald (SG&A). Data owner: Vivek Srinivasan.
Built under option A (Maya, 2026-11-03 07:46): Will's `SGA Template Mapping.xlsx` is the only map (no EPM alternate hierarchy exists, Will 2026-11-02).
All SQL was SELECT. Nothing written to Snowflake; no deploy, no Streamlit server.

Labels: **CONFIRMED** = re-run and tied to the cent. **LIKELY** = evidence points one way, not proven. **I DON'T KNOW** = not checked or not checkable.

## 1. What changed

| File | Change |
|---|---|
| `reference/sga_mapping.csv` (new) | 245 accounts / 52 lines (ACCOUNT, LINE, LINE_ORDER) from Will's sheet `3. Account`, built with python3/openpyxl read-only. AC_61014 = Other Professional Services (as in his file). No `_Other` rows, no AC_61627. |
| `reference/sga_mapping.README.md` (new) | Source note: file name, Will Oswald, email 2026-10-14 11:05 ET; parse rule. |
| `sga.py` (new) | `SQL` (one SELECT on `CARDPLN_PL_BY_LOB_STG`, rule from cfd-sga-retie 1.1, grouped LOB/SCENARIO/YEAR/PERIOD/ACCOUNT/COST_CENTER, plus AC_50000 @ CC_30000 in the same query); `load()` uses `data._q` (cached, existing connection); pandas join to the CSV; unmapped -> "Not mapped"; AC_61002 @ CC_40313 -> "Key Litigation Costs"; `report()`, `detail()`, `render()`. |
| `financial_app.py:66-70` | `with sga:` block only: imports `sga`, subheader, `sga_tab.render()`, Notion link kept. Title / (DRAFT) header untouched. |
| `snowflake.yml:122-123` | `sga.py` and `reference/sga_mapping.csv` added to `collectibles_financial_dash` artifacts only. `drillable_pnl_dash` unchanged. |
| `tools/preflight_artifacts.py:55-69` | Needed so preflight passes: a module that another entity ships and that none of this entity's files import is not required in this entity (otherwise it demanded `sga.py` in `drillable_pnl_dash`). |
| `tools/test_financial_app.py:80-92` | SG&A check now asserts the report table shows "Total SG&A (template)" and the "Will Oswald" header (the old "Coming soon" info check is gone). |
| `tools/test_sga_numbers.py` (new) | Read-only tie-out (step 6) + AppTest of the SG&A tab body alone. |

Tab layout: pickers LOB (default LB_302), Scenario (SEP26RF / 2027B-09.28), Year (default FY26); table = Will's 52 lines in LINE_ORDER, Not mapped, Total SG&A (template), Key Litigation Costs, Check vs Oracle total; columns Jan..Dec + FY total; the requested caption. Drill: ONE expander with a line picker showing account x cost center rows (not one expander per line, to keep the page short).

## 2. Test output

`python3 tools/test_sga_numbers.py`:

```
lines in table: 56 (52 Will + Not mapped + total + Key Lit + check)
LB_302 SEP26RF FY26 template total                          402,433,283.86  want     402,433,283.86  ok
LB_302 SEP26RF FY26 Key Litigation                            2,778,538.51  want       2,778,538.51  ok
LB_302 SEP26RF FY26 Oracle total                            405,211,822.37  want     405,211,822.37  ok
LB_302 SEP26RF FY26 check row (FY)                                    0.00  want               0.00  ok
LB_302 SEP26RF FY26 check row (worst month, abs)                      0.00  want               0.00  ok
LB_302 SEP26RF FY26 Not mapped                                        0.00  want               0.00  ok
LB_302 2027B-09.28 FY27 Oracle total                        483,119,838.51  want     483,119,838.51  ok

Not mapped, 2027B-09.28 FY27, vs cfd-sga-retie section 4:
LB_301 0.00 | LB_302 188,000.00 | LB_303 34,561,724.22 | LB_304 0.00
LB_305 9,827,811.41 | LB_306 84,972,355.48 | LB_307 43,024,723.29 | LB_308 16,898,596.53   -- all ok
check row FY = 0.00 for every LOB

OK -- sga.py ties
AppTest sga.render(): exception=none, rows=56, total row shown=True, first=['Marketing'],
  last=['Total SG&A (template)', 'Key Litigation Costs', 'Check vs Oracle total (AC_50000 @ CC_30000)']
pickers: [('LOB', 'LB_302'), ('Scenario', 'SEP26RF'), ('Year', 'FY26'), ('Line', 'Marketing')]
```

`python3 tools/preflight_artifacts.py`: `checked 29 artifact path(s) ... OK`.

`python3 tools/test_financial_app.py` (full app): **FAILED in this environment** with `No module named 'xlsxwriter'`, raised by `export.py:203` in the Income Statement tab, before the other tabs render. This worktree has no `.venv` and installing packages was not permitted, so the global python3 lacks a pyproject dependency. Not caused by this change (export.py untouched). The new SG&A assertions in that file have not yet run end to end. Re-run it from the project `.venv`.

## 3. Labels

| Claim | Label |
|---|---|
| Template / Key Lit / Oracle total / check 0 / Not mapped numbers above | CONFIRMED (re-run today) |
| SG&A cost-center rule (CC_1xxxx excluded, etc.) is the business definition | LIKELY (ties to the cent; Vivek has not confirmed) |
| LINE_ORDER = order of first appearance in Will's sheet matches his template's row order | LIKELY (not checked against the F1 template layout) |
| SG&A tab renders inside the full financial_app.py | I DON'T KNOW (sga.render() alone passes AppTest; the full app run broke on xlsxwriter) |
| Open with Will, not decided in code: AC_61014 line, 20 `_Other` + AC_61627, Digital Marketing FY27 gap 10,576.79 | open |
