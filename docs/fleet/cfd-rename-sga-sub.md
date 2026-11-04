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
- SG&A renders inside Income Statement at runtime: LIKELY (code at financial_app.py:55-63; AppTest not run, needs Snowflake login).
- tools/test_sga_numbers.py:86 docstring still says "SG&A tab body" (developer comment, not user-facing; left as is).
