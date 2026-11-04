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
| `sga.py` (new) | `SQL` (one SELECT on `CARDPLN_PL_BY_LOB_STG`, rule from cfd-sga-retie 1.1, grouped LOB/SCENARIO/YEAR/PERIOD/ACCOUNT/COST_CENTER, plus AC_50000 @ CC_30000 in the same query); `load()` uses `data._q` (cached, existing connection); pandas join to the CSV; unmapped -> "Not mapped"; AC_61002 @ CC_40313 -> "Key Litigation and Regulatory" (updated 2026-11-03; was "Key Litigation Costs"); `report()`, `detail()`, `render()`. |
| `financial_app.py:66-70` | `with sga:` block only: imports `sga`, subheader, `sga_tab.render()`, Notion link kept. Title / (DRAFT) header untouched. |
| `snowflake.yml:122-123` | `sga.py` and `reference/sga_mapping.csv` added to `collectibles_financial_dash` artifacts only. `drillable_pnl_dash` unchanged. |
| `tools/preflight_artifacts.py:55-69` | Needed so preflight passes: a module that another entity ships and that none of this entity's files import is not required in this entity (otherwise it demanded `sga.py` in `drillable_pnl_dash`). |
| `tools/test_financial_app.py:80-92` | SG&A check now asserts the report table shows "Total SG&A (template)" and the "Will Oswald" header (the old "Coming soon" info check is gone). |
| `tools/test_sga_numbers.py` (new) | Read-only tie-out (step 6) + AppTest of the SG&A tab body alone. |

Tab layout: pickers LOB (default LB_302), Scenario (SEP26RF / 2027B-09.28), Year (default FY26); table = Will's 52 lines in template order with 6 subtotals (updated 2026-11-03), Not mapped, Total SG&A (template), Key Litigation and Regulatory (updated 2026-11-03), Check vs Oracle total; columns Jan..Dec + FY total; the requested caption. Drill: ONE expander with a line picker showing account x cost center rows (not one expander per line, to keep the page short).

## 2. Test output

`python3 tools/test_sga_numbers.py` (first run, before the follow-up; new output in "Follow-up"):

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
| LINE_ORDER = Will's template order | (updated 2026-11-03, self-check) CONFIRMED. I read sheet "NASE Total" column M rows 13-74 with openpyxl (read only). The 52 line names there are in the same order as `sga.TEMPLATE_ORDER` ("xlsx order == TEMPLATE_ORDER: True 52"). |
| SG&A tab renders inside the full financial_app.py | I DON'T KNOW (sga.render() alone passes AppTest; the full app run broke on xlsxwriter) |
| Open with Will, not decided in code: AC_61014 line, 20 `_Other` + AC_61627, Digital Marketing FY27 gap 10,576.79 | open |

## Follow-up (updated 2026-11-03)

WHY: Will Oswald asked to rename the line (email "RE: SG&A Consolidated Dashboard - Request Received", 2026-10-29 15:04 ET). Maya said yes on 2026-11-03 15:24 to the rename AND to Will's template line order with its 6 subtotals. `tools/preflight_artifacts.py` was NOT changed (it stays as committed on coco/cfd-sga-tab, 066c9af).

What changed:

| File:line | Change |
|---|---|
| `sga.py:9-14` | Docstring: new name, template order source. |
| `sga.py:39` | `KEY_LIT = "Key Litigation and Regulatory"`. Rule unchanged: AC_61002 @ CC_40313 (`sga.py:41`). The drill list (`sga.py:199`) uses `KEY_LIT`, so it shows the new name. |
| `sga.py:45-74` | `TEMPLATE_ORDER`: the 52 lines in the order of sheet "NASE Total" column M rows 13-73 (list from the instruction; self-check: matches the xlsx, see Labels below). |
| `sga.py:75-84` | `SUBTOTALS`: Total Compensation 1-5, Total Professional Services and Outside Services 6-14, Total Travel and Entertainment 15-20, Total Rent and Office 21-26, Total Technology 28-31, Total Other/Miscellaneous 32-52. Marketing (27) has none. |
| `sga.py:138-158` | `report()` puts each subtotal after its last line. "Total SG&A (template)" is still the sum of the 52 lines + Not mapped. Subtotals are NOT added into it. |
| `sga.py:193` | Table height 35 x 65 (62 rows now). |
| `reference/sga_mapping.csv` | LINE_ORDER = position 1-52 in `TEMPLATE_ORDER`. All 245 ACCOUNT -> LINE pairs are the same (checked against `git show HEAD:reference/sga_mapping.csv`: "pairs same: True rows: 245"). |
| `reference/sga_mapping.README.md:8-12` | LINE_ORDER source note. |
| `tools/test_sga_numbers.py:39-53, 85-92` | New checks: 62 rows, template order, each subtotal = sum of its lines, subtotals + Marketing + Not mapped = template total. AppTest prints the first 8 rows and the subtotal rows. |

Test output (`python3 tools/test_sga_numbers.py`, 2026-11-03 15:58):

```
rows in table: 62 (52 Will + 6 subtotals + Not mapped + total + Key Litigation and Regulatory + check)
52 lines in template order: True
subtotal Total Compensation                                  82,215,347.56  ok
subtotal Total Professional Services and Outside Services      18,207,923.54  ok
subtotal Total Travel and Entertainment                       5,549,884.54  ok
subtotal Total Rent and Office                                6,389,111.92  ok
subtotal Total Technology                                    12,280,587.33  ok
subtotal Total Other/Miscellaneous                          189,939,435.70  ok
6 subtotals + Marketing + Not mapped = template total       402,433,283.86  ok
LB_302 SEP26RF FY26 template total                          402,433,283.86  ok
LB_302 SEP26RF FY26 Key Litigation                            2,778,538.51  ok
LB_302 SEP26RF FY26 Oracle total                            405,211,822.37  ok
LB_302 SEP26RF FY26 check row (FY)                                    0.00  ok
LB_302 SEP26RF FY26 check row (worst month, abs)                      0.00  ok
LB_302 SEP26RF FY26 Not mapped                                        0.00  ok
LB_302 2027B-09.28 FY27 Oracle total                        483,119,838.51  ok
Not mapped FY27 2027B-09.28: LB_301 0.00, LB_302 188,000.00, LB_303 34,561,724.22, LB_304 0.00,
  LB_305 9,827,811.41, LB_306 84,972,355.48, LB_307 43,024,723.29, LB_308 16,898,596.53 -- all ok, check row 0.00 each
OK -- sga.py ties

AppTest sga.render(): exception=none, rows=62, total row shown=True, 'Key Litigation and Regulatory' shown=True
first 8 rows: ['Salaries - Base Salaries', 'Severance', 'Bonus Expense', 'Benefits', 'Allocated Compensation',
               'Total Compensation', 'Legal & Litigation', 'Audit']
subtotal rows (0-based): (5, Total Compensation), (15, Total Professional Services and Outside Services),
  (22, Total Travel and Entertainment), (29, Total Rent and Office), (35, Total Technology), (57, Total Other/Miscellaneous)
last 4 rows: ['Not mapped', 'Total SG&A (template)', 'Key Litigation and Regulatory', 'Check vs Oracle total (AC_50000 @ CC_30000)']
pickers: LOB LB_302, Scenario SEP26RF, Year FY26
```

`python3 tools/preflight_artifacts.py`: `OK -- every artifact exists and every top-level module ships`.

Labels:
- Rename, template order, 6 subtotals, all numbers unchanged: **CONFIRMED** (output above).
- The order matches the xlsx: **CONFIRMED** (updated 2026-11-03, self-check). openpyxl read of sheet "NASE Total" column M rows 13-74: the 52 lines match `sga.TEMPLATE_ORDER` in order. The subtotal rows are at r19, r31, r38, r45, r51 and r74, as in the instruction.
- Two template rows that the instruction does not cover (self-check, 2026-11-03). Not built; Will or Maya must decide:
  - r17 "Compensation (Pre-Allocations)": (updated 2026-11-04) now in the tab, see Follow-up 2.
  - r70 "Contingency": a template line inside "Total Other/Miscellaneous". It is not in Will's mapping file (AC_61627 Contingency is one of the open accounts), so its amount shows in "Not mapped". "Total Other/Miscellaneous" in the tab therefore does not include Contingency.
- Full-app AppTest (`tools/test_financial_app.py`): **I DON'T KNOW**. Not re-run; the xlsxwriter problem in this Python is still there (section 2).
- Note: `sga.py:196` and `:204` (line refs updated 2026-11-04) use `use_container_width`. Streamlit 1.62 warns that this is deprecated. It works now. Not changed.

## Follow-up 2 (updated 2026-11-04)

WHY: Maya said yes (thread, 2026-11-04 09:20:50) to (1) add Will's template row r17 "Compensation (Pre-Allocations)" and (2) keep the `tools/preflight_artifacts.py:55-69` change from commit 066c9af as it is. Maya runs the full-app test from `.venv` herself.
Source: `SG&A Consolidated - 2027 Bud (1st Sub).xlsx`, sheet "NASE Total", column M r17, formula `=SUM(N13:N16)` = LINE_ORDER 1-4 (fact from the instruction).

What changed:

| File:line | Change |
|---|---|
| `sga.py:85-87` | New `PRE_ALLOC = ("Compensation (Pre-Allocations)", 1, 4)`. Display only. It is NOT in `SUBTOTALS` (the 6 subtotals are unchanged) and NOT in any total. |
| `sga.py:154` | `report()` loops over `(PRE_ALLOC, *SUBTOTALS)`, so the row shows after Benefits (line 4) and before Allocated Compensation (line 5). "Total SG&A (template)" is still the sum of the 52 lines + Not mapped (`sga.py:147-148`, unchanged; line ref corrected 2026-11-04 self-check). |
| `sga.py:196` | Table height 35 x 66 (63 rows now). |
| `tools/test_sga_numbers.py:40-55` | Expects 63 rows. Checks that the row is between Benefits and Allocated Compensation and that it equals the sum of lines 1-4. |

Not changed: `reference/sga_mapping.csv`, `tools/preflight_artifacts.py`, `financial_app.py`, `snowflake.yml`, `streamlit_app.py`, `export.py`. `git status` shows only `sga.py`, `tools/test_sga_numbers.py` and this file.

Test output (`python3 tools/test_sga_numbers.py`, 2026-11-04):

```
rows in table: 63 (52 Will + 6 subtotals + Pre-Allocations + Not mapped + total + Key Litigation and Regulatory + check)
52 lines in template order: True
'Compensation (Pre-Allocations)' between Benefits and Allocated Compensation: True
subtotal Compensation (Pre-Allocations) (lines 1-4)          82,215,347.56  ok
subtotal Total Compensation                                  82,215,347.56  ok
subtotal Total Professional Services and Outside Services      18,207,923.54  ok
subtotal Total Travel and Entertainment                       5,549,884.54  ok
subtotal Total Rent and Office                                6,389,111.92  ok
subtotal Total Technology                                    12,280,587.33  ok
subtotal Total Other/Miscellaneous                          189,939,435.70  ok
6 subtotals + Marketing + Not mapped = template total       402,433,283.86  ok
LB_302 SEP26RF FY26 template total                          402,433,283.86  ok
LB_302 SEP26RF FY26 Key Litigation                            2,778,538.51  ok
LB_302 SEP26RF FY26 Oracle total                            405,211,822.37  ok
LB_302 SEP26RF FY26 check row (FY)                                    0.00  ok
LB_302 SEP26RF FY26 check row (worst month, abs)                      0.00  ok
LB_302 SEP26RF FY26 Not mapped                                        0.00  ok
LB_302 2027B-09.28 FY27 Oracle total                        483,119,838.51  ok
Not mapped FY27 2027B-09.28: LB_301 0.00, LB_302 188,000.00, LB_303 34,561,724.22, LB_304 0.00,
  LB_305 9,827,811.41, LB_306 84,972,355.48, LB_307 43,024,723.29, LB_308 16,898,596.53 -- all ok, check row 0.00 each
OK -- sga.py ties

AppTest sga.render(): exception=none, rows=63, total row shown=True, 'Key Litigation and Regulatory' shown=True
first 8 rows: ['Salaries - Base Salaries', 'Severance', 'Bonus Expense', 'Benefits', 'Compensation (Pre-Allocations)',
               'Allocated Compensation', 'Total Compensation', 'Legal & Litigation']
subtotal rows (0-based): (6, Total Compensation), (16, Total Professional Services and Outside Services),
  (23, Total Travel and Entertainment), (30, Total Rent and Office), (36, Total Technology), (58, Total Other/Miscellaneous)
last 4 rows: ['Not mapped', 'Total SG&A (template)', 'Key Litigation and Regulatory', 'Check vs Oracle total (AC_50000 @ CC_30000)']
```

`python3 tools/preflight_artifacts.py`: `OK -- every artifact exists and every top-level module ships`.

Labels:
- The new row is in the right place and equals lines 1-4. All numbers are unchanged, preflight is OK and the SG&A AppTest passes: **CONFIRMED** (output above).
- For LB_302 / SEP26RF / FY26, Pre-Allocations = Total Compensation = 82,215,347.56. So Allocated Compensation is 0.00 in this slice: **CONFIRMED** (output above, and an independent SQL `01c83000-031a-3f52-69de-0701a145c96f` (updated 2026-11-04, self-check): lines 1-4 = 82,215,347.56, Allocated Compensation accounts = 0). I did not check other LOBs or years line by line.
- The r17 formula `=SUM(N13:N16)`: **CONFIRMED** (updated 2026-11-04, self-check). I read the formulas with openpyxl (read only): M17 "Compensation (Pre-Allocations)" has `=SUM(N13:N16)` (Salaries .. Benefits). M19 "Total Compensation" has `=N17+N18`.
- Full-app AppTest: I did not run it (Maya runs it from `.venv`): **I DON'T KNOW**.
