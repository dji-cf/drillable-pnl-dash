# sga_mapping.csv

Source: `SGA Template Mapping.xlsx`, sheet `3. Account`, from Will Oswald
(email 2026-10-14 11:05 ET). Static copy for the SG&A tab (`sga.py`):
245 accounts on 52 template lines.

- ACCOUNT = `AC_` + column L (Child), else the last non-empty of columns C-K.
- LINE = column B (the template line), stripped.
- LINE_ORDER = row order of sheet 'NASE Total' column M rows 13-73 of
  SG&A Consolidated - 2027 Bud (1st Sub).xlsx (Will Oswald, 2026-10-14).
  (updated 2026-11-03; before, it was the order of first appearance in
  sheet `3. Account`. No ACCOUNT -> LINE pair changed.)
- AC_61014 stays on "Other Professional Services", as in Will's file (open
  question with Will: the 2027 Bud file shows it under Legal).
- No `_Other` accounts and no AC_61627 (not in Will's file, not approved).

Regenerate only from a new file from Will; do not hand-edit lines.
