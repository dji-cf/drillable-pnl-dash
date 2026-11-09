# Port: coco/cfd-cogs-drill onto coco/cfd-rename-sga-sub

Moves the BU page COGS drill (commit 141aa9b) onto the new base (dbe4767).
Done by editing files by hand, without merge or cherry-pick. Source:
`git diff coco/cfd-rename-sga-sub...coco/cfd-cogs-drill`, which holds only
the branch's own changes. A two-dot diff would also show the old base's
missing work as removals.

## Moved changes (line numbers are in this worktree)

| File | Lines | Change |
| --- | --- | --- |
| bu.py | 71-76 | `TOTAL_COGS` row key, `COGS_BUCKET_LABELS` |
| queries.py | 675-775 | COGS drill block: `LAYOUT`, `COGS_*` constants, `COGS_ACCOUNT_BUCKET`, `bu_base_lobs`, `_lit`, `cogs_drill_sql` |
| data.py | 199-211 | `load_cogs_drill` (cached, errors not caught) |
| interactive.py | 94-99, 104, 130-131, 146 | JS `data-cogs` click handler, `"cogs"` trigger, docstring, `on_cogs_change` |
| table.py | 143, 188-190, 249, 257-258, 283 | `cogs=` mapping puts `data-cogs` on the label cell |
| style.py | 167-169 | `td.lbl[data-cogs]` gets the same pointer and hover style as `data-bu` |
| streamlit_app.py | 60-61, 291-298, 343, 365, 503-554 | imports, `cogs=` param, returns the 'cogs' click, `bu_page` passes `cogs={bu.TOTAL_COGS: key}`, new `_cogs_drill` |
| tools/test_cogs_drill.py | new | AppTest tie-out (needs a Snowflake login; not run here) |

## Conflicts

None. The old branch did not touch `financial_app.py`, the title, or the tabs.
Every hunk's context matched the new base exactly. These are unchanged:
the new name "Collectibles Consolidated Financials Dashboard", the 3 top tabs,
the Income Statement sub-tabs (Consolidated P&L | SG&A Detail), the Cash EBITDA
tile, and the Forecast fixes. In `data.py`, the new `load_cogs_drill` sits
after the base's `load_adj_ebitda_ex_es`, so both are kept. In `queries.py`,
the COGS block sits before "Rebind for the chosen source", as on the old branch.
The base's Cash Flow block after the rebind is unchanged.

## Not available

The task asked to copy `docs/fleet/cfd-cogs-drill.md` and to read
`queue/cfd-cogs-drill.json`. Neither exists on coco/cfd-cogs-drill or in this
worktree, so nothing was copied. The original rules were taken from the
branch's own code comments and test docstring.

## Checks

- `python3 -m py_compile` on all 8 changed files: OK
- `queries.cogs_drill_sql('Sep 2026 FC','FY26', bu_base_lobs('na'))` builds offline. The NA LOBs are LB_302, LB_304 and LB_394.
- `tools/test_agent_chat.py`: ALL PASS
- `tools/test_vintages.py`: ALL VINTAGE CHECKS PASS
- `tools/preflight_artifacts.py`: OK
- Not run (they need a login): `tools/test_cogs_drill.py`, `tools/test_financial_app.py`, and the browser click check.

## Self-check (2026-11-04)

- CONFIRMED: the port is the same as the branch. The +/- lines of
  `git diff HEAD` on the 7 code files match the +/- lines of
  `git diff coco/cfd-rename-sga-sub...coco/cfd-cogs-drill`: 212 lines each,
  and the sorted lists are equal. `tools/test_cogs_drill.py` is the same as the
  branch file, byte for byte.
- CONFIRMED: `git log --all -- docs/fleet/cfd-cogs-drill.md queue/cfd-cogs-drill.json`
  returns nothing. These files were never in git.
- CONFIRMED: a read-only run of the drill SQL for NA, Sep 2026 FC, FY26
  (query 01c83080-031a-3d29-69de-0701a1599bc3) returned 9 rows. The 8 child
  lines include ACX_Compensation (123.371 $M, sort_order NULL, as expected from
  the LEFT JOIN), plus the AC_50000 residual of -286.229 $M. Total: 1,789.963 $M.
- CONFIRMED: the residual comes from LB_394 only. LB_394 has parent -286.229
  and no children; LB_302 has 1,824.932 and LB_304 has 251.260, both with no
  parent (query 01c83080-031a-3f52-69de-0701a159c9e3).
  1,824.932 + 251.260 - 286.229 = 1,789.963.
- LIKELY: 1,789.963 $M equals the NA "Total COGS" on the grid. It follows the
  COALESCE(parent, children) rule in queries.py, but I did not read the grid's
  own value. Check: run `tools/test_cogs_drill.py` with a login.
