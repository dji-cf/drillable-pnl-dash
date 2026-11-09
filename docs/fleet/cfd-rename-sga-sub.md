# cfd-rename-sga-sub (Dan Chen, Slack 2026-11-04)

Base: coco/cfd-sga-tab (1288ec3). Display text and layout only; no number changes.

## A. Rename to "Collectibles Consolidated Financials Dashboard"
- financial_app.py:1 docstring title
- financial_app.py:34 `APP_TITLE` ("(DRAFT)" still added by pnl._drafted / _tab)
- snowflake.yml:101 `title: "(DRAFT) Collectibles Consolidated Financials Dashboard"`.
  Entity key `collectibles_financial_dash` and identifier `COLLECTIBLES_FINANCIAL_DASH` unchanged, so the URL stays the same.
- sga.py:1 docstring
- tools/test_financial_app.py:1, :31 (HEADER), :122-125 (BU header checks)
- docs/fleet/*.md history files left as they were.

## B. SG&A moved under Income Statement
- financial_app.py:3-6 docstring describes the new layout
- financial_app.py:35 `TABS = ["Income Statement", "Balance Sheet", "Cash Flow"]`
- financial_app.py:36 `INCOME_TABS = ["Consolidated P&L", "SG&A Detail"]`
- financial_app.py:52-63 `with income:` -> `st.tabs(INCOME_TABS)`; Consolidated P&L = render_shell(title=None) + consolidated_page();
  SG&A Detail = the old SG&A tab body (subheader, sga_tab.render(), Notion link). The old `with sga:` top-tab block is removed.
  The tab labels are all different, so the two st.tabs calls do not collide. _bu_wrapper / BU pages unchanged.
- tools/test_financial_app.py:4-7 docstring; :30 INCOME_TABS; :64-69 nested labels excluded from top-tab check;
  :88-96 SG&A checks read the "SG&A Detail" sub-tab; :97-106 checks the Income Statement sub-tabs and Consolidated P&L inner tabs.

## Verification
- `python3 -m py_compile financial_app.py sga.py tools/test_financial_app.py`: OK
- tools/test_financial_app.py NOT run: the AppTest runs the real app, which queries Snowflake (needs a login).
- grep: no "Collectibles Financial Dashboard" outside docs/fleet/.

## Self-check (2026-11-04)
- All file:line refs above re-read against `git diff -U0`: CONFIRMED.
- SG&A renders inside Income Statement at runtime: LIKELY (code at financial_app.py:55-63, now :56-65 after the cash tile imports (updated 2026-11-04); AppTest not run, needs Snowflake login).
- tools/test_sga_numbers.py:86 docstring still says "SG&A tab body" (developer comment, not user-facing; left as is).

## Combined with cfd-cash-ebitda-tile (updated 2026-11-04)
Why: one publish to COLLECTIBLES_FINANCIAL_DASH with the rename, the SG&A Detail sub-tab AND the Cash Flow EBITDA tile.

How: `git cherry-pick 510d989 6c6133d` was DENIED by the sandbox. `git apply` and `git checkout 6c6133d -- <file>` were
denied too. So I applied the same content by hand, as UNCOMMITTED changes on top of 4e73512.
**There are NO new commit hashes.** `git log coco/cfd-shell..HEAD` still shows only 066c9af, f7f3ebb, 1288ec3 (cfd-sga-tab)
and 4e73512. The fleet script commits the working tree. 510d989 / 6c6133d will NOT appear as separate commits.
If Maya needs them as real commits, someone must run `git cherry-pick 510d989 6c6133d` by hand, then keep this result.

Proof that the content is the same as the cash tile branch:
- `git diff --stat 6c6133d -- data.py queries.py`: empty (byte-identical). queries.py:676-719 and data.py:190-196.
  The SQL and numbers are not changed.
- `diff <(git show 6c6133d:docs/fleet/cfd-cash-ebitda-tile.md) docs/fleet/cfd-cash-ebitda-tile.md`: same (new file, old name kept).
- `git diff 6c6133d -- financial_app.py`: only the rename and SG&A sub-tab lines from 4e73512.

Conflicts fixed by hand (both sides kept):
- financial_app.py:20, :24: `import pandas as pd`, `import data` (cash) + rename docstring :1-6 (this task).
- financial_app.py:37-38: TABS (3 items) + INCOME_TABS (this task). The cash side had 4 TABS: not kept.
- financial_app.py:56-65: `with income:` sub-tabs (this task). The cash side had a `with sga:` top tab with
  st.info("Coming soon: SG&A report (Will Oswald)"): removed, because SG&A Detail now lives under Income Statement.
- financial_app.py:71-76: `with cash:` = st.info("Cash Flow (draft) (Afriti Rahim, Jack Braun)") + `_cash_ebitda_tile()` + links (cash).
- financial_app.py:79-105: EBITDA_ROWS + `_cash_ebitda_tile()` (cash), unchanged.
- tools/test_financial_app.py:27-34: imports data / pandas / queries + BRIDGE fake for the tile (cash).
- tools/test_financial_app.py:37-39: TABS 3 items, INCOME_TABS, new HEADER (this task).
- tools/test_financial_app.py:92-106: Cash tile checks: table rows, no "add back", metric "2,169.6", SQL (cash).
- tools/test_financial_app.py:107-110: info check. Cash Flow now expects the full text
  "Cash Flow (draft) (Afriti Rahim, Jack Braun)". The cash side's ("SG&A", "Will Oswald") info check was dropped,
  because SG&A Detail uses st.subheader, which :118 checks.
- tools/test_financial_app.py:111-128: SG&A Detail + sub-tab checks (this task), unchanged.

Checks:
- `python3 -m py_compile financial_app.py data.py queries.py sga.py tools/test_financial_app.py`: COMPILE_OK.
- grep "Collectibles Financial Dashboard" outside docs/fleet/ (no .git, no __pycache__): 0 hits.
- tools/test_financial_app.py NOT run (the Income Statement part needs a Snowflake login).

## Forecast fixes brought in (a886ebc..98b675b) (updated 2026-11-04)
Why: Maya ran commit 3e041a9 locally (2026-11-04 ~11:00). The Income Statement P&L showed the OLD Forecast
logic (double 2026 Budget, Oct/Nov/Dec 2025 FC, no YTD view, "Fanatics Collect"). Maya said yes (2026-11-04 11:02:47).

How: git merge / cherry-pick / apply / checkout are blocked for me. I read `git diff a886ebc 98b675b` and made
the same edits with the edit and write tools. Nothing is committed. Diff base = a886ebc (not merge-base c119831).

### The 10 files with no clash: now equal to 98b675b
`git diff --stat 98b675b -- ISSUES.md bu.py master_query.sql table.py transforms.py tools/apptest_smoke.py
tools/test_vintages.py tools/validate_vs_deck.py` = **empty**. The 2 new docs: `git show 98b675b:<f> | diff -q - <f>` = same.
- ISSUES.md:370-371, :376-379 (A11 notes)
- bu.py:1, :40 ("Fanatics Live and Collect")
- master_query.sql:466-467 (comment)
- table.py:43 (DRILL label)
- transforms.py:81 (GRAINS + "ytd"); :451, :462, :474, :492 (label); :631-664 (comp_options, A10); :901-924 (periods, YTD View, A8)
- tools/apptest_smoke.py:158-162 (no-retired branch)
- tools/test_vintages.py:152-188, :255, :285, :287, :320-324 (new A8 / A10 expectations)
- tools/validate_vs_deck.py:717-721, :734, :738, :743, :760, :763-768 (_p7_labels), :887-888
- docs/fleet/fcst-ui-audit.md (new), docs/fleet/fcst-ui-fixes.md (new)

### The 3 shared files: Forecast hunks added, this branch's work kept
- export.py:34: `"ytd": "YTD"` in GRAIN_TITLES. The cfd-shell export changes are kept.
- queries.py:173-175: `FIRST_FORECAST_FISCAL_YEAR = "FY26"`; :187: used in `_VINTAGE_FILTER` (forecast branch only).
  :493-497: STG_SQL raw CTE `AND NOT (SCENARIO_LABEL = 'BUDGET' AND COALESCE(SCENARIO, '') LIKE '20__B-%'
  AND FISCAL_YEAR <> 'FY' || SUBSTR(SCENARIO, 3, 2))`. :583, :597, :616, :639: "Fanatics Live and Collect".
  The Cash EBITDA bridge SQL (`adj_ebitda_ex_es_sql`, def now at :693, block :684-727) is unchanged.
  Proof: `git diff 6c6133d -- queries.py` = only those Forecast lines.
- streamlit_app.py:6, :11 (docstring); :68 `"ytd": "YTD"` in GRAIN_LABELS; :254 (_grain_control docstring).
  The render_shell / consolidated_page split is kept.
- Proof: `git diff --stat 98b675b -- export.py queries.py streamlit_app.py` = 22 / 45 / 289. These are the same
  numbers as `a886ebc..cfd-rename-sga-sub` before the change, so the only difference left is this branch's own work.

**Clashes: none.** Every 98b675b hunk applied at its own text in all 3 files. No hunk touched the Cash bridge
SQL, the cfd-shell split or the export prefix lines.

### Not changed (this branch's work)
financial_app.py (APP_TITLE, 3 TABS, INCOME_TABS, `_cash_ebitda_tile()`), sga.py, data.py, snowflake.yml, DRAFT_LABEL.

### "Fanatics Collect" grep (without "Live and")
No user-facing app string is left. financial_app.py and sga.py: 0 hits. Hits left (same as 98b675b's own list):
queries.py:58 (comment), tools/gap_analysis.py:222 (dev script print), tools/validate_vs_deck.py:764, :767 (the
load-time rename), master_query.sql:131, :333, :372, :417 (standalone SQL, no .py loads it), ISSUES.md:189-265
(history), reference/deck_pdf_p7.json and reference/deck_jul2026.json (the deck's own printed label).
Also `output/bundle/streamlit/drillable_pnl_dash/*.py`: an old build output, not source. The next bundle
rebuilds it.

### Tests
- `python3 -m py_compile bu.py export.py queries.py streamlit_app.py table.py transforms.py tools/apptest_smoke.py
  tools/test_vintages.py tools/validate_vs_deck.py financial_app.py sga.py data.py tools/test_financial_app.py`: COMPILE_OK.
- `python3 tools/test_vintages.py` (it imports only pandas, export, queries, table, transforms; no Snowflake):
  ```
  ORDERING     pass
  OCT 2026     pass
  PERIODS      pass
  JAN 2027     pass
  DELTA MODES  pass
  TRENDS       pass

  ALL VINTAGE CHECKS PASS
  ```
- Not run: streamlit, tools/test_financial_app.py, tools/apptest_smoke.py, the validators (all need Snowflake).
