# Known issues — Drillable P&L (Collectibles Forecast)

Everything this dashboard does not reproduce from its source deck
(`FC_Forecast Dashboard_Jul 2026 FC.html`), why, and what would close each gap.

This file is the **single home for that prose**. The app itself no longer carries
it: there are no gap badges, no "Known gaps" panel, no footnotes block and no
diagnostic toggle. The dashboard shows the figures it has; this document says how
far each one can be trusted. Anyone quoting a Gross Margin or EBITDA number out
of the app needs the context below.

The machine-readable half of the registry still lives in code, in
`transforms.py` — the gap-kind constants, the `GAPS` row map, `UNRECONCILED_ROWS`
and `BLOCKING_KINDS`. That is what decides which rows render. This file is the
narrative for those same kinds, and `tools/validate_vs_deck.py::check_gap_registry`
asserts the code side's invariants so the two cannot drift apart unnoticed.

---

## 0. 2026-09-29 — Compensation add-back DISABLED

`queries.APPLY_COMPENSATION_ADJUSTMENT = False`. The app now reports the
source's own `ACX_Gross Margin` and `ACX_EBITDA`, matching **EPM cube CARDPLN**,
which is the business standard.

**Why.** The add-back described in section 2 was double-correcting. Finance
already handles the Compensation double-count outside this app, so adding
`ACX_Compensation` back here on top of that inflated every cost row. The
deciding evidence, all three agreeing on the same figure:

| Source | Q1 FY26 North America EBITDA |
|---|---|
| EPM Smart View (CARDPLN, `Total - North America Gross`, `ACX_EBITDA`, CO_31000, all other dims Total) | **195.32** |
| `CARDPLN_PL_BY_LOB` | **195.32** |
| `CARDPLN_PL_BY_LOB_V` | **195.32** |
| This app, before the change | 244.22 |

The +48.90 was exactly `ACX_Compensation` for that cell
(195.3216765600 + 48.8998233100 = 244.2214998700).

The source's subtotal chain is also internally consistent, which section 2
assumed it was not — for Q1 FY26 NA:

```
Gross Margin = Net Revenue - COGS          668.8640 - 362.9056 = 305.9583  ✓ stored
EBITDA       = GM - Marketing - SG&A       305.9583 - 10.8743 - 99.7624 = 195.3217  ✓ stored
```

So `ACX_EBITDA` needed no correction at all.

**Effect.** Jul. FC Total EBITDA, as displayed ($M):

| Period | Before | After | Change |
|---|---|---|---|
| Q1 | 237 | 144 | −93.6 |
| Q2 | 629 | 523 | −106.3 |
| Q3 | 462 | 346 | −116.2 |
| Q4 | 527 | 397 | −129.6 |
| **FY** | **1,855** | **1,410** | **−445.6** |

All 19 cost rows move down by their Compensation amount. The figures now move
*away* from the deck (`FC_Forecast Dashboard_Jul 2026 FC.html`), which means the
deck's cost basis — not this source — is the thing that needs explaining. Revenue
is untouched and still ties exactly.

**Reversible.** Set the flag to `True` to restore the old behaviour; nothing else
changes. `COMPENSATION_LINE` is still fetched, `_apply_compensation()` is still
present, and `tools/test_compensation_flag.py::FLAG ON` asserts the add-back
returns at exactly the Compensation amount.

**Consequences for the gates.** `validate_vs_deck.py::check_compensation` is
skipped while the flag is False (it only ever justified the add-back) and prints
`compensation adjustment disabled - skipped`. **All nine gates pass** with the
flag off — verified 2026-09-29, 12 vintages / 796 rows:

```
FORMATTERS   pass                    COMP ADDITIV pass
GAP REGISTRY pass  (21 flagged)      ROW 22       pass  (153 cells, all grains)
BASE vs VIEW pass  (3,845 cells)     ADDITIVITY   pass  (199 cells)
COMPENSATION pass  (skipped)         REV ANNUAL / REALLOCATION / REV CELLS  pass
ALL GATES PASS
```

`ROW 22` was expected to need recalibrating and does **not**: Key Litigation
carries zero Compensation at every grain in the vintages that make up
`ROW22_TIES`, so removing the add-back leaves that row — and the tie pattern —
untouched.

**Open.** Keep the flag `False` until the cost-center alternate hierarchy exists.
Sections 2 and 3 below describe the add-back and its residual as they were, and
are retained as the record of why it was introduced.

---

## 0b. 2026-09-29 — One North America definition on the whole page

**Decision by Anoop Tiwari (EPM owner):** North America means the EPM cube's
`Total - North America Gross` LOB (segment `na`) in **every** section of this
page. Before this change it meant two different things: `na` under EBITDA, and
`na + elim` under Revenue and Gross Margin.

**What changed.** `transforms._na_folded` (`na + elim`) is **deleted**. Rows 0
and 8 now use `_na_gross`, the same expression EBITDA already used. Eliminations
gets its own Revenue row and its own Gross Margin row, mirroring the EBITDA row
it always had. Two rows were inserted, so `ROWS` is now **28** rows.

**Effect on North America revenue** (SEP26RF, $M) — the old figure was short by
exactly the Topps eliminations in every cell:

| | Q1 | Q2 | Q3 | Q4 | FY |
|---|---|---|---|---|---|
| Revenue NA, was (`na + elim`) | 652.0 | 1,289.2 | 1,076.8 | 1,070.7 | 4,088.7 |
| Revenue NA, now (`na`) | **668.9** | **1,313.9** | **1,132.3** | **1,124.1** | **4,239.2** |
| new Eliminations row | -16.9 | -24.7 | -55.5 | -53.4 | -150.5 |
| Gross Margin NA %, was | 47.39% | — | — | — | 53.21% |
| Gross Margin NA %, now | **45.74%** | 53.85% | 54.16% | 48.54% | **51.25%** |

All of those now agree with the EPM reference query to **0.0000** — every
pure-read row across SEP26RF / AUG26RF / JUL26RF × Q1–Q4 × FY, 0 mismatches.

**Nothing else moved.** Total Physical Cards, Total Revenue, Total EBITDA and
EBITDA Margin are unchanged, because the fold only ever moved value *between*
two rows inside the same subtotal. The block is still additive, now in three
terms instead of two:

```
NA + Eliminations + International == Total Physical Cards
668.9 +   (-16.9)  +    139.6     ==        791.6          (Q1, residual 0.0000)
```

`tools/validate_vs_deck.py::check_additivity` asserts that form — 199 cells pass.

**Gross Margin Eliminations % is withheld** (renders `—`). Eliminations revenue
is **negative** in every cell (SEP26RF: -16.9 / -24.7 / -55.5 / -53.4 / -150.5),
so a margin over it is sign-inverted and means nothing: the raw quotient swings
-17.94% (Q1) → +8.39% (Q2) → -2.67% (Q3). This is a new gap kind, **SIGN**, in
`BLOCKING_KINDS` alongside `HIERARCHY`, on row 10. The numerator and denominator
are both real, so the row is `is_live` — `SIGN` is what withholds it, and
`check_gap_registry` asserts it can never render.

**Relabel.** "Fanatics Collect" → **"Fanatics Live and Collect"** in all three
sections (rows 6, 14, 23). The segment was always
`Total - Fanatics Live and Collect`; the old label understated it, which is the
`COMBINED` gap in section 4 and is now at least named honestly on screen.

**Row indices moved, and the deck reference did not.** `reference/deck_jul2026.json`
still has the deck's **26** rows, and the deck has no Eliminations line under
Revenue or Gross Margin. Rather than inserting placeholder rows into that file —
which `tools/extract_deck.py` regenerates wholesale, so the edit would be
silently lost — `Row` gained a **`deck_idx`** field. `ROWS` position and deck
position are now separate numberings, `deck_value()` takes the deck one, and the
two new rows carry `deck_idx=None` so the deck gates skip them instead of
comparing against the wrong row. An assertion guards the mapping:

```python
assert [r.deck_idx for r in ROWS if r.deck_idx is not None] == list(range(26))
```

The deck's single folded North America row is still gated, via
`validate_vs_deck.REVENUE_UNITS`, which compares deck row 0 against the **sum of
app rows 0 and 2**. The fold now lives in the validator, where it is a statement
about the deck rather than about the business — REV CELLS passes 1,071 cells.

Old → new row index: 0→0, 1→1, **2 = Revenue Eliminations (new)**, 2→3, 3→4,
4→5, 5→6, 6→7, 7→8, 8→9, **10 = Gross Margin Eliminations % (new)**, 9→11,
10→12, 11→13, 12→14, 13→15, 14→16 … 25→27.

**Verified.** All nine gates pass (22 flagged, 20 unreconciled). All four
compensation-flag gates pass — the anchor is now `ROWS[16]` and still reads
`195.3217M`.

---

## 1. What reconciles

**All 8 Revenue rows match the source exactly** — at all three grains (annual,
quarterly, monthly), for all 9 shared vintages. Verified cell-for-cell by
`tools/validate_vs_deck.py`, which asserts character-identical formatted output,
not merely close figures. Against the *deck*, North America and the new
Eliminations row are compared as a folded pair (section 0b); against the EPM
reference query every row matches to 0.0000 individually.

**No cost row reconciles.** All 20 of them (the 8 Gross Margin % rows, the 11
EBITDA rows, EBITDA Margin) carry a cost basis that is corrected for a real
source defect but is still short in actual months. Sections 2 and 3 explain the
two halves of that.

Row 24 (EBITDA Key Litigation Costs, deck row 22) is the near miss and has its
own note in section 6.2.

---

## 2. The Compensation double-count — found and corrected

> **Superseded by section 0 (2026-09-29).** The correction described here is
> now **disabled** (`queries.APPLY_COMPENSATION_ADJUSTMENT = False`); its premise
> — that the source's EBITDA chain double-charges Compensation — did not hold
> against EPM. This section is retained as the record of why it was introduced
> and of what flipping the flag back to `True` would do.

`ACX_Compensation` is charged **twice** in the source: once into
`ACX_Cost of Goods Sold` and again into `ACX_Other SG&A`.

`ACX_Cost of Goods Sold` is not the sum of its seven mapped children — it is
those children **plus** `ACX_Compensation`, verified at 100% of cells across 11
vintages × 181 period-cells. Since `ACX_Gross Margin = ACX_Net Revenue −
ACX_Cost of Goods Sold`, Compensation lands in Gross Margin and, through it,
EBITDA as cost.

It is a **double-count, not a misclassification**. A COGS → opex reclass would
leave EBITDA untouched, yet EBITDA only ties to the deck when Compensation is
subtracted *once* — so it already sits inside `ACX_Other SG&A` and is
*additionally* summed into COGS.

**The correction.** `queries.py` fetches the line (`COMPENSATION_LINE`) and
`transforms._apply_compensation()` adds it back to both subtotals. The arithmetic
is gated by `tools/validate_vs_deck.py::COMPENSATION`.

**Effect for Jul. FC** — $445.6M:

| Metric | Before correction | After correction | Deck |
|---|---|---|---|
| Gross margin | 45.0% | 53.6% | 54.8% |
| EBITDA | $1,409.7M | $1,855.3M | $1,993.3M (like-for-like) |

That closes 88–100% of the Gross Margin gap and makes the six **forecast** months
of Jul. FC tie to the deck (GM +$3.4M, EBITDA −$0.1M on ~$1B).

---

## 3. The residual gap — confined to actual months, unexplained

What the Compensation fix does **not** close sits entirely in **actual months**.

At month grain for Jul. FC:

* the six forecast months tie — gross margin +$3.4M, EBITDA −$0.1M on ~$1B;
* **Jan–Jun are short $63.1M of gross margin and $137.9M of EBITDA.**

**It is not a restatement.** Those actual months are byte-identical across the
ACTUAL scenario and the JUL26RF and AUG26RF snapshots, and revenue on the same
months ties exactly. The deck's actual-month *cost* basis comes from somewhere
this source does not reproduce.

**Status:** raised with the data team. Reproduce with `tools/gap_analysis.py`,
which runs five checks (COGS COMPOSITION / SUBTOTAL CHAIN / SUPERSET / BRIDGE /
UNEXPLAINED).

**What would close it:** an actual-month cost basis that ties to the deck.
Revenue on those same months already does.

---

## 4. Gap registry

One subsection per kind. *Affects* lists row indices as they appear in
`transforms.ROWS`; *Needs* is what would have to change in the source for the gap
to close.

### `SPLIT` — not separable in the source
**Affects:** rows 4, 20, 21 (Revenue Digital, EBITDA Digital, EBITDA Corporate)

The view has no Digital and no Corporate segment — only the
ex-Emerging-Services minus Physical-Cards residual, which is Digital **and**
Corporate combined.

**Needs:** a Digital and a Corporate segment (or column) in the view.

### `COMBINED` — two deck lines are one source segment
**Affects:** rows 6, 23 (Revenue and EBITDA Fanatics Live and Collect)

Fanatics Live and Fanatics Collect are one segment in the source
(`Total - Fanatics Live and Collect`); the deck reports Collect alone.

**Needs:** separate Fanatics Live and Fanatics Collect segments.

### `PARTIAL` — only one of several elimination segments
**Affects:** row 18 (EBITDA Eliminations)

The only elimination segment in the view is Topps Eliminations. The deck's
Eliminations line is a unified group.

**Needs:** the remaining elimination segments.

### `ABSENT` — no such segment at all
**Affects:** row 25 (EBITDA TCG)

No TCG segment exists in the view at any grain.

**Needs:** a TCG segment in the view.

### `HIERARCHY` — the residual is broken, not merely approximate
**Affects:** rows 12, 20 (Gross Margin % Digital, EBITDA Digital)

These are derived as ex-Emerging Services minus Physical Cards, but the source
has ex-Emerging **smaller than its own subset** on 34 of 42 lines — for EBITDA,
in 180 of 181 period-cells, worst −$179.4M. The residual is therefore not a real
segment: for Jul. FC it computes a **108.5% gross margin** against the deck's
35.6%.

This is one of two kinds in `BLOCKING_KINDS` (with `SIGN`). Rows carrying it
render as an em-dash unconditionally, because the number that would appear is not
off — it is meaningless.

**Needs:** a Digital segment in the source, or a corrected LOB rollup in which
ex-Emerging Services actually contains Physical Cards.

### `SIGN` — the denominator is negative, so the ratio is nonsense
**Affects:** row 10 (Gross Margin Eliminations %)

Eliminations revenue is negative in every cell (SEP26RF: -16.9 / -24.7 / -55.5 /
-53.4 / -150.5 $M), because eliminations remove intercompany revenue. A margin
computed over it is sign-inverted and swings arbitrarily: -17.94% in Q1, +8.39%
in Q2, -2.67% in Q3. Both the numerator and the denominator are real figures, so
the row is `is_live` — `SIGN` is what withholds it.

The dollar Eliminations rows (Revenue row 2, EBITDA row 18) are unaffected and
render normally; only the *percentage* is meaningless.

**Needs:** nothing in the source. A margin on an eliminations line is not a
meaningful quantity, so this kind is permanent by design.

### `UNRECONCILED` — cost basis only partly ties
**Affects:** all 20 cost rows (8–27)

The Compensation double-count of section 2 is corrected here and accounts for
most of the gap. What remains is the actual-month shortfall of section 3.

**Needs:** an actual-month cost basis that ties to the deck. Revenue on those
same months already does.

---

## 5. Per-row status

Five rows render as an em-dash. Every other row shows its live figure.

`#` is the app's `ROWS` index; `deck` is the position in
`reference/deck_jul2026.json` (`Row.deck_idx`). They diverged on 2026-09-29 —
see section 0b.

| # | deck | Section | Label | Kinds | Renders |
|---|---|---|---|---|---|
| 0 | 0 | Revenue | North America † | — | yes |
| 1 | 1 | Revenue | International | — | yes |
| 2 | — | Revenue | Eliminations | — | yes |
| 3 | 2 | Revenue | Total Physical Cards | — | yes |
| 4 | 3 | Revenue | Digital | `SPLIT` | yes |
| 5 | 4 | Revenue | Total ex-Emerging Svcs | — | yes |
| 6 | 5 | Revenue | Fanatics Live and Collect | `COMBINED` | yes |
| 7 | 6 | Revenue | Total Revenue | — | yes |
| 8 | 7 | Gross Margin | North America | `UNRECONCILED` | yes |
| 9 | 8 | Gross Margin | International | `UNRECONCILED` | yes |
| 10 | — | Gross Margin | Eliminations | `UNRECONCILED`, `SIGN` | **no** — negative denominator |
| 11 | 9 | Gross Margin | Total Physical Cards | `UNRECONCILED` | yes |
| 12 | 10 | Gross Margin | Digital | `UNRECONCILED`, `HIERARCHY` | **no** — broken residual |
| 13 | 11 | Gross Margin | Total ex-Emerging Svcs | `UNRECONCILED` | yes |
| 14 | 12 | Gross Margin | Fanatics Live and Collect | `UNRECONCILED` | yes |
| 15 | 13 | Gross Margin | Total Gross Margin | `UNRECONCILED` | yes |
| 16 | 14 | EBITDA | North America | `UNRECONCILED` | yes |
| 17 | 15 | EBITDA | International | `UNRECONCILED` | yes |
| 18 | 16 | EBITDA | Eliminations | `UNRECONCILED`, `PARTIAL` | yes |
| 19 | 17 | EBITDA | Total Physical Cards | `UNRECONCILED` | yes |
| 20 | 18 | EBITDA | Digital | `UNRECONCILED`, `SPLIT`, `HIERARCHY` | **no** — broken residual |
| 21 | 19 | EBITDA | Corporate | `UNRECONCILED`, `SPLIT` | **no** — no expression |
| 22 | 20 | EBITDA | Total ex-Emerging Svcs | `UNRECONCILED` | yes |
| 23 | 21 | EBITDA | Fanatics Live and Collect | `UNRECONCILED`, `COMBINED` | yes |
| 24 | 22 | EBITDA | Key Litigation Costs | `UNRECONCILED` | yes — see 6.2 |
| 25 | 23 | EBITDA | TCG | `UNRECONCILED`, `ABSENT` | **no** — no expression |
| 26 | 24 | EBITDA | Total EBITDA | `UNRECONCILED` | yes |
| 27 | 25 | EBITDA Margin | EBITDA Margin | `UNRECONCILED` | yes |

22 of 28 rows carry at least one kind; 20 of those are `UNRECONCILED`. Both
counts are asserted by `tools/validate_vs_deck.py::check_gap_registry`.

`ROWS` index is **not** the deck's row index any more. `Row.deck_idx` carries the
deck position, and an assertion in `transforms.py` requires the non-None
`deck_idx` values to be exactly `range(26)` in order, so the tuple still cannot
be reordered silently.

---

## 6. Row-specific notes

### 6.1 Row 3 (Revenue Digital) ties by luck
It currently matches the deck to the cent, because Corporate has no revenue, so
the residual happens to be Digital alone. It is still flagged `SPLIT`: the moment
any Corporate revenue appears it will be silently absorbed into this row with no
other symptom.

### 6.2 Row 22 (EBITDA Key Litigation Costs) ties in only 5 of 9 vintages
This row was a candidate to ship unflagged — it ties to the cent for Jul. FC,
which made it look like the one reconciled cost row. The `ROW 22` gate in
`tools/validate_vs_deck.py` proved otherwise. It ties in `ROW22_TIES` =
{2026B, Apr. FC, May. FC, Jun. FC, Jul. FC} and differs in the rest:

* **2025A** ties annually (+$0.26) and differs sub-annually, worst −$19.0M in
  Jun — the FY25 Key Litigation Compensation that `KNOWN_COGS_MISTAG` covers.
* The deck's **Jan/Feb/Mar FC** columns carry the 2026 BUDGET figure for this
  line (−$33,432,594) while those refreshes had already moved it. The deck is
  stale there rather than the source being wrong, but the annual does not tie, so
  it fails the bar `KNOWN_REALLOCATIONS` sets for excusal.

Every one of those differences is pre-existing: verified against a cube built
with the Compensation rows dropped, the correction introduces none of them.

The gate is **two-way**, so a vintage that starts tying is reported too — that
would be the signal to move row 22 off `UNRECONCILED`.

Specific regression risk: Key Litigation has zero Compensation at YEAR grain in
every vintage, but 2025A carries non-zero amounts at MONTH and QUARTER grain
(Jan +0.27M … Jun −6.34M, summing to zero — which is exactly why the annual
figure is clean). So the correction can move this row sub-annually even where it
cannot move it annually.

### 6.3 Why the Gross Margin % rows are not double-flagged
Rows 7–13 inherit the same structural limits as the Revenue rows they sit under
(row 10 is the same residual, row 12 the same combined segment). They are not
also flagged `SPLIT`/`COMBINED` because all 7 already carry `UNRECONCILED`, which
strictly dominates. Rows 10 and 18 are the exception: `HIERARCHY` is not
dominated, because it withholds the figure where `UNRECONCILED` alone would
release it.

---

## 7. Presentation notes

These are deliberate, verified departures from a naive reading of the source —
not defects.

**† North America is the source's gross segment, in every section.** As of
2026-09-29 (section 0b) Revenue and Gross Margin no longer fold Topps
Eliminations into North America; Eliminations has its own row in all three
sections. The deck printed the folded figure (4,074.8 − 121.5 = 3,953.3), so the
deck comparison folds the two app rows back together in
`validate_vs_deck.REVENUE_UNITS` rather than the page folding them.

**Period labels are computed, not hardcoded.** They come per vintage from
`period_date < DATE_TRUNC('MONTH', forecast_asof_date)`. The deck hardcoded its
26A/26F suffixes, so it mislabelled every vintage other than Jul. FC. A quarter
counts as actual only when all of its months are.

**FY25 actuals have been restated** since the deck was exported: some 2025A
months were reallocated within H1. Annual and quarterly totals are unaffected;
the figures here are the current ones.

**FY26 Actuals is a 7-month partial year** (Q1–Q3, no Q4) and its FY total is a
7-month sum. It is not a like-for-like comparison against a full-year vintage.
This one *is* still warned about in the app, because it changes how a number
should be read the moment it is selected.

**Percent metrics are plotted on a percent scale.** The deck read `def.is_pct`
while its row definitions supplied `isPct`, so all 7 Gross Margin rows and EBITDA
Margin were plotted and labelled on the dollar scale. Fixed here.

---

## 8. Source selection

The app reads the **base table** `ORACLE_DATA_PROD.FCT_EPM.CARDPLN_PL_BY_LOB`,
not `CARDPLN_PL_BY_LOB_V`.

The view is a thin passthrough that INNER JOINs `CARDPLN_PL_ACCOUNT_LAYOUT` on
`PL_LINE`, and that layout maps only 23 of the base table's 42 lines — so 19
lines are dropped silently, `ACX_Compensation` among them. The line is therefore
invisible in the view yet fully loaded into the COGS subtotal the view does
expose, which is how the double-count of section 2 went unnoticed.

Reading the base table costs the layout metadata (`PL_LABEL`, `SECTION`,
`SORT_ORDER`), none of which this app uses, and `FORECAST_ASOF_DATE`, which
`queries._FORECAST_ASOF` reproduces verbatim.

Verified equivalent for the three reported lines: 3,505 rows, 3,505 distinct
cells, identical `SUM(AMOUNT)`. Gated by `validate_vs_deck.py::BASE vs VIEW` so a
future change to the view cannot drift away unnoticed.

---

## 9. Deployment status

**`VERSION$1`, deployed 2026-09-15, is byte-identical to the working copy** —
verified 2026-09-29 by downloading
`snow://streamlit/ORACLE_DATA_PROD.SANDBOX.DRILLABLE_PNL_DASH/versions/live/` and
diffing: `queries.py` and `transforms.py` match the local files exactly once CRLF
line endings are normalised (live is CRLF, local LF; the byte deltas of +221 and
+646 are precisely the line counts). Same MD5 after normalisation.

The earlier note here — that `VERSION$1` predated the Compensation correction —
was **wrong**. The correction was live, which is why the deployed app showed
1,855 (the post-add-back figure) rather than 1,409.7.

**It is now stale for a different reason:** the live version still has the
add-back enabled and therefore still shows 244 for Q1 FY26 North America. Redeploy
to ship section 0.

```
snow streamlit deploy drillable_pnl_dash --replace --role POWER_ANALYST_ORACLE_PROD
```

Run `tools/preflight_artifacts.py` first: `snow streamlit deploy` does not
validate `snowflake.yml::artifacts`, and a missing path uploads as a zero-byte
stage entry, exits 0, and kills the app on first import.

---

## 10. Corrections of record

Two claims that were previously stated in this project's own documentation and
were wrong. Recorded so they are not re-derived.

1. **Row 22 was described as tying to the deck, unqualified.** That was true of
   the vintage everyone looked at (Jul. FC) and false elsewhere — see 6.2.
2. **The deck's TCG (−$12.2M) and Corporate (−$120.9M) lines were blamed for
   most of the remaining difference.** Both are negative, so including them
   *widens* the gap rather than closing it.

---

## 11. What the app still says on screen

Removed: the gap badges and their tooltips, the "Known gaps" sidebar panel, the
footnotes block, the KPI tile notes, the variance-vs-deck badges, the
"Show unreconciled cost lines" diagnostic toggle, and the Trends withheld-metric
explanations. All of it is in this file.

Kept, because each is a live operational fact rather than a caveat:

* the **partial-year warning** when FY26 Actuals is selected (section 7);
* the **data-freshness caption** — pull time, row count, vintage list;
* the **section-collapse fallback message**, when the Streamlit runtime is below
  1.57 or the table component fails to register.

The four non-derivable rows render as an em-dash with no on-screen explanation.
The explanation is section 4 (`HIERARCHY`, `SPLIT`, `ABSENT`).
