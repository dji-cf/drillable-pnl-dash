# sga_mapping.csv

Source: `SGA Template Mapping.xlsx`, sheet `3. Account`, from Will Oswald
(email 2026-10-14 11:05 ET). Static copy for the SG&A tab (`sga.py`):
245 accounts on 52 template lines.

- ACCOUNT = `AC_` + column L (Child), else the last non-empty of columns C-K.
- LINE = column B (the template line), stripped. LINE_ORDER = order of first
  appearance in the sheet.
- AC_61014 stays on "Other Professional Services", as in Will's file (open
  question with Will: the 2027 Bud file shows it under Legal).
- No `_Other` accounts and no AC_61627 (not in Will's file, not approved).

Regenerate only from a new file from Will; do not hand-edit lines.
