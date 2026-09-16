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

## 1. What reconciles

**All 7 Revenue rows match the deck exactly** — at all three grains (annual,
quarterly, monthly), for all 9 shared vintages. Verified cell-for-cell by
`tools/validate_vs_deck.py`, which asserts character-identical formatted output,
not merely close figures.

**No cost row reconciles.** All 19 of them (the 7 Gross Margin % rows, the 11
EBITDA rows, EBITDA Margin) carry a cost basis that is corrected for a real
source defect but is still short in actual months. Sections 2 and 3 explain the
two halves of that.

Row 22 (EBITDA Key Litigation Costs) is the near miss and has its own note in
section 6.2.

---

## 2. The Compensation double-count — found and corrected

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
**Affects:** rows 3, 18, 19 (Revenue Digital, EBITDA Digital, EBITDA Corporate)

The view has no Digital and no Corporate segment — only the
ex-Emerging-Services minus Physical-Cards residual, which is Digital **and**
Corporate combined.

**Needs:** a Digital and a Corporate segment (or column) in the view.

### `COMBINED` — two deck lines are one source segment
**Affects:** rows 5, 21 (Revenue Fanatics Collect, EBITDA Fanatics Collect)

Fanatics Live and Fanatics Collect are one segment in the source
(`Total - Fanatics Live and Collect`); the deck reports Collect alone.

**Needs:** separate Fanatics Live and Fanatics Collect segments.

### `PARTIAL` — only one of several elimination segments
**Affects:** row 16 (EBITDA Eliminations)

The only elimination segment in the view is Topps Eliminations. The deck's
Eliminations line is a unified group.

**Needs:** the remaining elimination segments.

### `ABSENT` — no such segment at all
**Affects:** row 23 (EBITDA TCG)

No TCG segment exists in the view at any grain.

**Needs:** a TCG segment in the view.

### `HIERARCHY` — the residual is broken, not merely approximate
**Affects:** rows 10, 18 (Gross Margin % Digital, EBITDA Digital)

These are derived as ex-Emerging Services minus Physical Cards, but the source
has ex-Emerging **smaller than its own subset** on 34 of 42 lines — for EBITDA,
in 180 of 181 period-cells, worst −$179.4M. The residual is therefore not a real
segment: for Jul. FC it computes a **108.5% gross margin** against the deck's
35.6%.

This is the only kind in `BLOCKING_KINDS`. Rows carrying it render as an em-dash
unconditionally, because the number that would appear is not off — it is
meaningless.

**Needs:** a Digital segment in the source, or a corrected LOB rollup in which
ex-Emerging Services actually contains Physical Cards.

### `UNRECONCILED` — cost basis only partly ties
**Affects:** all 19 cost rows (7–25)

The Compensation double-count of section 2 is corrected here and accounts for
most of the gap. What remains is the actual-month shortfall of section 3.

**Needs:** an actual-month cost basis that ties to the deck. Revenue on those
same months already does.

---

## 5. Per-row status

Four rows render as an em-dash. Every other row shows its live figure.

| # | Section | Label | Kinds | Renders |
|---|---|---|---|---|
| 0 | Revenue | North America † | — | yes |
| 1 | Revenue | International | — | yes |
| 2 | Revenue | Total Physical Cards | — | yes |
| 3 | Revenue | Digital | `SPLIT` | yes |
| 4 | Revenue | Total ex-Emerging Svcs | — | yes |
| 5 | Revenue | Fanatics Collect | `COMBINED` | yes |
| 6 | Revenue | Total Revenue | — | yes |
| 7 | Gross Margin | North America | `UNRECONCILED` | yes |
| 8 | Gross Margin | International | `UNRECONCILED` | yes |
| 9 | Gross Margin | Total Physical Cards | `UNRECONCILED` | yes |
| 10 | Gross Margin | Digital | `UNRECONCILED`, `HIERARCHY` | **no** — broken residual |
| 11 | Gross Margin | Total ex-Emerging Svcs | `UNRECONCILED` | yes |
| 12 | Gross Margin | Fanatics Collect | `UNRECONCILED` | yes |
| 13 | Gross Margin | Total Gross Margin | `UNRECONCILED` | yes |
| 14 | EBITDA | North America | `UNRECONCILED` | yes |
| 15 | EBITDA | International | `UNRECONCILED` | yes |
| 16 | EBITDA | Eliminations | `UNRECONCILED`, `PARTIAL` | yes |
| 17 | EBITDA | Total Physical Cards | `UNRECONCILED` | yes |
| 18 | EBITDA | Digital | `UNRECONCILED`, `SPLIT`, `HIERARCHY` | **no** — broken residual |
| 19 | EBITDA | Corporate | `UNRECONCILED`, `SPLIT` | **no** — no expression |
| 20 | EBITDA | Total ex-Emerging Svcs | `UNRECONCILED` | yes |
| 21 | EBITDA | Fanatics Collect | `UNRECONCILED`, `COMBINED` | yes |
| 22 | EBITDA | Key Litigation Costs | `UNRECONCILED` | yes — see 6.2 |
| 23 | EBITDA | TCG | `UNRECONCILED`, `ABSENT` | **no** — no expression |
| 24 | EBITDA | Total EBITDA | `UNRECONCILED` | yes |
| 25 | EBITDA Margin | EBITDA Margin | `UNRECONCILED` | yes |

21 of 26 rows carry at least one kind; 19 of those are `UNRECONCILED`. Both
counts are asserted by `tools/validate_vs_deck.py::check_gap_registry`.

`ROWS` index **is** the deck's row index — `reference/deck_jul2026.json` keys on
it, so the tuple must never be reordered.

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

**† North America revenue folds in Topps Eliminations.** This reproduces the deck
exactly: 4,074.8 − 121.5 = 3,953.3, its printed value. EBITDA keeps Eliminations
on its own row, as the deck does — folding there would double-count.

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

**`VERSION$1`, deployed 2026-09-14, is STALE.** It predates the Compensation
correction of section 2. Redeploy before trusting any Gross Margin or EBITDA
figure in the live app.

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
