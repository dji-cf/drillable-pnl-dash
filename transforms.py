"""The 26-row P&L model, the gap registry, and the deck's formatters.

This is the correctness centre of the app. Three things live here:

1.  ROWS -- the deck's 26 line items in deck order, each with the expression
    that derives it from the view's 7 LOB segments (or None where the view
    cannot express it at all).
2.  GAPS -- the machine-readable registry of every way the live figures fall
    short of the deck. It decides which rows can render a figure at all
    (Row.is_derivable). The PROSE for each kind -- what is wrong and what would
    close it -- lives in ISSUES.md, not here and not in the UI.
3.  The number formatters, ported from the deck's JS so a cell rendered here is
    character-identical to the same cell in the source HTML.

In short: all 7 Revenue rows reconcile to the deck exactly, no cost row does,
and four rows (10 and 18 Digital, 19 Corporate, 23 TCG) cannot be derived from
the source at all and render as em-dashes. Every cost row shows its live figure.

ISSUES.md is the full account -- including the ACX_Compensation double-count that
_apply_compensation() below can correct (disabled by default since 2026-09-29, so
gross_margin and ebitda are the source's own ACX_ values as EPM reports them),
and why row 22 stays flagged despite tying for Jul. FC.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

import pandas as pd

import queries

# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------
# FY == calendar year in this view (FY26 spans 2026-01-01..2026-12-01), so the
# quarters are calendar quarters.
MONTHS: tuple[str, ...] = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
QUARTERS: tuple[str, ...] = ("Q1", "Q2", "Q3", "Q4")
QUARTER_MONTHS: dict[str, tuple[str, ...]] = {
    "Q1": ("Jan", "Feb", "Mar"),
    "Q2": ("Apr", "May", "Jun"),
    "Q3": ("Jul", "Aug", "Sep"),
    "Q4": ("Oct", "Nov", "Dec"),
}
ANNUAL = "annual"

GRAINS: tuple[str, ...] = ("annual", "quarterly", "monthly")

SECTIONS: tuple[str, ...] = ("Revenue", "Gross Margin", "EBITDA", "EBITDA Margin")
# The deck prints no section header for the single-row margin section
# (source JS line 357).
SECTIONS_WITH_HEADER: tuple[str, ...] = ("Revenue", "Gross Margin", "EBITDA")

# ---------------------------------------------------------------------------
# Deck colors, ported verbatim
# ---------------------------------------------------------------------------
PERIOD_COLORS: dict[str, str] = {
    "2025A": "#7a9ab8", "2026B": "#a0b4c8", "2026A": "#c0864a",
    "Jan. FC": "#93c5fd", "Feb. FC": "#60a5fa", "Mar. FC": "#3b82f6",
    "Apr. FC": "#1d4ed8", "May. FC": "#1e3a8a", "Jun. FC": "#172554",
    "Jul. FC": "#0b1220", "Aug. FC": "#4c1d95",
}
MONTH_SUB_COLORS: dict[str, str] = {
    "Jan": "#3b82f6", "Feb": "#0ea5e9", "Mar": "#06b6d4",
    "Apr": "#f59e0b", "May": "#f97316", "Jun": "#ef4444",
    "Jul": "#10b981", "Aug": "#14b8a6", "Sep": "#22c55e",
    "Oct": "#8b5cf6", "Nov": "#a855f7", "Dec": "#ec4899",
}
QTR_SUB_COLORS: dict[str, str] = {
    "Q1": "#3b82f6", "Q2": "#f59e0b", "Q3": "#10b981", "Q4": "#8b5cf6",
}

# ---------------------------------------------------------------------------
# Formatters -- ported from the deck's JS (source lines 263-286)
# ---------------------------------------------------------------------------
EM_DASH = "\u2014"


def round_half_up(x: float) -> int:
    """Exactly JavaScript's Math.round, which Python's round() is not.

    Python rounds half to EVEN (round(0.5) == 0, round(2.5) == 2); JS rounds
    half toward +Infinity (Math.round(0.5) == 1, Math.round(-2.5) == -2).
    floor(x + 0.5) reproduces JS for both signs. This matters because
    tools/validate_vs_deck.py asserts character-identical output against the
    deck, and a .5 boundary would otherwise show up as a spurious mismatch.
    """
    if x != x or x in (float("inf"), float("-inf")):  # NaN / inf
        raise ValueError(f"cannot round {x!r}")
    return int(math.floor(x + 0.5))


def _is_missing(v: object) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def fmt_m(v: float | None) -> str:
    """Dollars in millions, negatives parenthesised: 5184175733 -> '$5,184'."""
    if _is_missing(v):
        return EM_DASH
    m = float(v) / 1e6           # type: ignore[arg-type]
    s = "$" + f"{round_half_up(abs(m)):,}"
    return f"({s})" if m < 0 else s


def fmt_pct(v: float | None) -> str:
    """Ratio to whole percent: 0.5476 -> '55%'."""
    if _is_missing(v):
        return EM_DASH
    return f"{round_half_up(float(v) * 100)}%"


def fmt_tile(v: float | None) -> str:
    """Headline tile figure in billions: 5184175733 -> '$5.18B'."""
    if _is_missing(v):
        return EM_DASH
    return f"${float(v) / 1e9:.2f}B"


def delta_fmt(
    curr: float | None, comp: float | None, is_pct: bool, has_comp: bool = True
) -> dict[str, str] | None:
    """Period-over-period delta cell: {'text', 'cls'}, or None when no comparison.

    Percent rows go to basis points, dollar rows to a percent change. The
    thresholds (0.5 bps, 0.1%) are the deck's, not a rounding artifact -- a
    delta inside them renders neutral rather than green/red.

    Deviation from the deck, deliberate: when ``curr`` is missing this returns
    an em-dash. The deck's JS would coerce a null ``curr`` to 0 and print a
    confident -100%, which is wrong -- it happens whenever the comparison
    vintage covers a period the forecast does not (or vice versa), which is
    routine now that FY26 Actuals is only 7 months.
    """
    if not has_comp or _is_missing(comp) or _is_missing(curr):
        return None
    curr_f, comp_f = float(curr), float(comp)  # type: ignore[arg-type]

    if is_pct:
        d = (curr_f - comp_f) * 10_000
        sign = "+" if d >= 0 else ""
        cls = "gpos" if d > 0.5 else "gneg" if d < -0.5 else "gflat"
        return {"text": f"{sign}{round_half_up(d)} bps", "cls": cls}

    if comp_f == 0:
        return {"text": EM_DASH, "cls": "gflat"}
    d = (curr_f - comp_f) / abs(comp_f) * 100
    sign = "+" if d >= 0 else ""
    cls = "gpos" if d > 0.1 else "gneg" if d < -0.1 else "gflat"
    return {"text": f"{sign}{round_half_up(d)}%", "cls": cls}


# ---------------------------------------------------------------------------
# Gap registry
# ---------------------------------------------------------------------------
# The kinds a row may be flagged with. What each one means, which rows it hits
# and what would have to change in the source to close it: ISSUES.md section 4.
SPLIT = "SPLIT"
COMBINED = "COMBINED"
PARTIAL = "PARTIAL"
ABSENT = "ABSENT"
HIERARCHY = "HIERARCHY"
UNRECONCILED = "UNRECONCILED"
SIGN = "SIGN"

#: Every kind the registry may use. Guards GAPS against a typo'd kind --
#: tools/validate_vs_deck.py::check_gap_registry asserts membership.
GAP_KINDS: frozenset[str] = frozenset(
    {SPLIT, COMBINED, PARTIAL, ABSENT, HIERARCHY, UNRECONCILED, SIGN}
)

# Keyed by row index. A row may carry more than one kind.
#
# NOTE 2026-09-29: two rows were inserted (Revenue Eliminations at 2, Gross
# Margin Eliminations % at 10), so every index below is shifted from the deck's
# own numbering. Row.deck_idx carries the deck position; this registry keys on
# the app's ROWS position. See ISSUES.md section 0.
#
# Row 4 (Revenue Digital) is worth a word: it currently matches the deck to the
# cent, because Corporate has no revenue, so the residual happens to be Digital
# alone. It is still flagged -- the moment any Corporate revenue appears it will
# be silently absorbed into this row with no other symptom.
#
# Row 2 (Revenue Eliminations) is deliberately UNFLAGGED. It is a direct read of
# the elim segment -- the most trustworthy kind of row there is. The deck has no
# Revenue Eliminations line to tie it to (it folds eliminations into North
# America), so deck_idx is None and the deck gates skip it rather than fail it.
#
# The Gross Margin % rows inherit the same structural limits as the Revenue rows
# they sit under (row 12 is the same residual, row 14 the same combined
# segment). They are not double-flagged with SPLIT/COMBINED because all 8
# already carry UNRECONCILED, which strictly dominates. Rows 10, 12 and 20 are
# the exception: SIGN and HIERARCHY are not dominated, because they withhold the
# figure where UNRECONCILED alone would let it render.
#
# Row 10 (Gross Margin Eliminations %) carries SIGN: the elim segment's revenue
# is NEGATIVE in every cell (SEP26RF: -16.9 / -24.7 / -55.5 / -53.4 / -150.5),
# so a margin over it is sign-inverted and means nothing. The numerator and
# denominator are both real, so the row is is_live -- SIGN is what withholds it.
#
# Row 24 (EBITDA Key Litigation Costs) is worth its own note. It was a candidate
# to ship unflagged, because it ties to the cent for Jul. FC -- but the ROW 22
# gate in tools/validate_vs_deck.py proved that is only true for 5 of the 9
# shared vintages, so it keeps the flag. See ROW22_TIES there, and ISSUES.md 6.2.
GAPS: dict[int, tuple[str, ...]] = {
    4: (SPLIT,),
    6: (COMBINED,),
    # Gross Margin % -- rows 8-15, with 12 carrying the broken residual and 10
    # the negative denominator.
    **{i: (UNRECONCILED,) for i in range(8, 16) if i not in (10, 12)},
    10: (UNRECONCILED, SIGN),
    12: (UNRECONCILED, HIERARCHY),
    # EBITDA -- rows 16-26 -- and EBITDA Margin (27).
    16: (UNRECONCILED,),
    17: (UNRECONCILED,),
    18: (UNRECONCILED, PARTIAL),
    19: (UNRECONCILED,),
    20: (UNRECONCILED, SPLIT, HIERARCHY),
    21: (UNRECONCILED, SPLIT),
    22: (UNRECONCILED,),
    23: (UNRECONCILED, COMBINED),
    24: (UNRECONCILED,),
    25: (UNRECONCILED, ABSENT),
    26: (UNRECONCILED,),
    27: (UNRECONCILED,),
}

#: Rows whose live value cannot be trusted as a like-for-like of the deck.
UNRECONCILED_ROWS: frozenset[int] = frozenset(
    i for i, kinds in GAPS.items() if UNRECONCILED in kinds
)

#: Gap kinds that withhold the figure unconditionally, because the number that
#: would appear is not merely off, it is meaningless.
BLOCKING_KINDS: frozenset[str] = frozenset({HIERARCHY, SIGN})


def blocking_reason(row: "Row") -> str | None:
    """The gap kind that explains why a row renders blank, most specific first.

    Every cost row's tuple leads with UNRECONCILED, whose note is about failing
    to tie to the deck -- which is the wrong answer to "why is this cell empty".
    So prefer a BLOCKING kind, then any structural kind (SPLIT / ABSENT), and
    fall back to UNRECONCILED only when it is all there is.

    Without this, Corporate and TCG both explained themselves as "cost basis
    does not tie" when the real reason is that no such segment exists.

    Nothing in the UI reads this any more -- the app states no reasons on screen
    (ISSUES.md does). tools/validate_vs_deck.py asserts the resolution, so the
    semantics stay honest for whoever needs them next.
    """
    for kind in row.gaps:
        if kind in BLOCKING_KINDS:
            return kind
    for kind in row.gaps:
        if kind != UNRECONCILED:
            return kind
    return row.gaps[0] if row.gaps else None

# ---------------------------------------------------------------------------
# Segment expressions
# ---------------------------------------------------------------------------
Segs = Mapping[str, float]

# One North America definition on the whole page: the source's own
# 'Total - North America Gross' segment, alone. Decided 2026-09-29 by Anoop
# Tiwari (EPM owner) -- EPM cube CARDPLN is the business standard.
#
# Revenue and Gross Margin used to fold Topps Eliminations into North America
# (_na_folded = na + elim) to reproduce the deck's printed 3,953.3. That made
# the page disagree with EPM by exactly the eliminations (FY -150.5), and made
# North America mean two different things in two sections of one page. The fold
# is gone; Eliminations now has its own Revenue and Gross Margin row, as it
# always did under EBITDA, so the block still adds up:
#     na + elim + intl == phys
_na_gross: Callable[[Segs], float] = lambda s: s["na"]
_elim: Callable[[Segs], float] = lambda s: s["elim"]
_intl: Callable[[Segs], float] = lambda s: s["intl"]
_phys: Callable[[Segs], float] = lambda s: s["phys"]
_digital_residual: Callable[[Segs], float] = lambda s: s["exem"] - s["phys"]
_exem: Callable[[Segs], float] = lambda s: s["exem"]
_fanlive: Callable[[Segs], float] = lambda s: s["fanlive"]
_keylit: Callable[[Segs], float] = lambda s: s["keylit"]
_grand_total: Callable[[Segs], float] = lambda s: s["exem"] + s["fanlive"] + s["keylit"]


@dataclass(frozen=True)
class Row:
    """One line item of the statement."""

    idx: int
    #: Position of the counterpart row in reference/deck_jul2026.json, or None
    #: when the deck has no such row. Distinct from idx since 2026-09-29: the
    #: page carries two rows the deck does not (Revenue Eliminations, Gross
    #: Margin Eliminations %), so ROWS position no longer equals deck position.
    #: tools/extract_deck.py regenerates that JSON wholesale, so the mapping
    #: lives here rather than as placeholder rows inserted into the artifact.
    deck_idx: int | None
    section: str
    label: str            # as shown in the statement table
    metric_label: str     # as shown in the Trends metric picker
    row_type: str         # sub | subtotal | total | margin
    is_pct: bool
    num_line: str | None  # key into queries.PL_LINES
    den_line: str | None  # only for is_pct rows
    expr: Callable[[Segs], float] | None

    @property
    def gaps(self) -> tuple[str, ...]:
        return GAPS.get(self.idx, ())

    @property
    def is_live(self) -> bool:
        """True when the row has a derivable expression at all."""
        return self.expr is not None

    @property
    def is_derivable(self) -> bool:
        """True when a figure may be shown at all.

        Distinct from is_live. Five rows must never render: 21 (Corporate) and
        25 (TCG) have no expression, while 12 and 20 (Digital) DO have one -- it
        just evaluates over a residual the source has made nonsense of -- and 10
        (Gross Margin Eliminations %) has both parts but a negative denominator.
        Callers gate placeholders on this rather than on is_live, so a broken
        residual can never reach the screen. See ISSUES.md sections 0 and 4.
        """
        return self.is_live and not (set(self.gaps) & BLOCKING_KINDS)

    @property
    def is_reconciled(self) -> bool:
        """True when the live value is a trustworthy like-for-like of the deck."""
        return self.is_live and UNRECONCILED not in self.gaps


def _rev(idx: int, deck_idx: int | None, label: str, row_type: str, expr) -> Row:
    return Row(idx, deck_idx, "Revenue", label,
               label if row_type != "total" else "Total Revenue",
               row_type, False, "net_revenue", None, expr)


def _gm(idx: int, deck_idx: int | None, label: str, metric_label: str,
        row_type: str, expr) -> Row:
    return Row(idx, deck_idx, "Gross Margin", label, metric_label, row_type,
               True, "gross_margin", "net_revenue", expr)


def _eb(idx: int, deck_idx: int | None, label: str, row_type: str, expr) -> Row:
    return Row(idx, deck_idx, "EBITDA", label,
               label if row_type != "total" else "Total EBITDA",
               row_type, False, "ebitda", None, expr)


#: The statement's 28 rows. The first field is the app's own row index -- the one
#: GAPS, _TILES and the Trends picker key on. The second is the position of the
#: counterpart row in reference/deck_jul2026.json, which has 26 rows and no
#: Eliminations line under Revenue or Gross Margin: those two get None and the
#: deck gates skip them. Never reorder either numbering.
ROWS: tuple[Row, ...] = (
    # -- Revenue (live, reconciled exactly) --------------------------------
    _rev(0,  0,    "North America",            "sub",      _na_gross),
    _rev(1,  1,    "International",            "sub",      _intl),
    _rev(2,  None, "Eliminations",             "sub",      _elim),
    _rev(3,  2,    "Total Physical Cards",     "subtotal", _phys),
    _rev(4,  3,    "Digital",                  "sub",      _digital_residual),
    _rev(5,  4,    "Total ex-Emerging Svcs",   "subtotal", _exem),
    _rev(6,  5,    "Fanatics Live and Collect", "sub",     _fanlive),
    _rev(7,  6,    "Total Revenue",            "total",    _grand_total),
    # -- Gross Margin % (unreconciled) ------------------------------------
    # Each row's basis is the Revenue row directly above it, so the two blocks
    # read as parallel. The deck's table labels carry no '%'; its metric picker
    # does. Row 10 is withheld: eliminations revenue is negative, so a margin
    # over it is sign-inverted and meaningless (gap kind SIGN).
    _gm(8,  7,    "North America",            "North America %",            "sub",      _na_gross),
    _gm(9,  8,    "International",            "International %",            "sub",      _intl),
    _gm(10, None, "Eliminations",             "Eliminations %",             "sub",      _elim),
    _gm(11, 9,    "Total Physical Cards",     "Total Physical Cards %",     "subtotal", _phys),
    _gm(12, 10,   "Digital",                  "Digital %",                  "sub",      _digital_residual),
    _gm(13, 11,   "Total ex-Emerging Svcs",   "Total ex-Emerging Svcs %",   "subtotal", _exem),
    _gm(14, 12,   "Fanatics Live and Collect", "Fanatics Live and Collect %", "sub",    _fanlive),
    _gm(15, 13,   "Total Gross Margin",       "Total Gross Margin %",       "total",    _grand_total),
    # -- EBITDA (unreconciled) --------------------------------------------
    _eb(16, 14,   "North America",            "sub",      _na_gross),
    _eb(17, 15,   "International",            "sub",      _intl),
    _eb(18, 16,   "Eliminations",             "sub",      _elim),
    _eb(19, 17,   "Total Physical Cards",     "subtotal", _phys),
    _eb(20, 18,   "Digital",                  "sub",      _digital_residual),
    # Corporate and TCG have NO expression: the view carries no segment for
    # either, so there is nothing to show and they render as an em-dash.
    _eb(21, 19,   "Corporate",                "sub",      None),
    _eb(22, 20,   "Total ex-Emerging Svcs",   "subtotal", _exem),
    _eb(23, 21,   "Fanatics Live and Collect", "sub",     _fanlive),
    _eb(24, 22,   "Key Litigation Costs",     "sub",      _keylit),
    _eb(25, 23,   "TCG",                      "sub",      None),
    _eb(26, 24,   "Total EBITDA",             "total",    _grand_total),
    # -- EBITDA Margin % (unreconciled) -----------------------------------
    Row(27, 25, "EBITDA Margin", "EBITDA Margin", "EBITDA Margin %", "margin",
        True, "ebitda", "net_revenue", _grand_total),
)

assert len(ROWS) == 28, "26 deck rows plus Revenue and Gross Margin Eliminations"
assert all(r.idx == i for i, r in enumerate(ROWS)), "ROWS must be in index order"
_DECK_IDXS = [r.deck_idx for r in ROWS if r.deck_idx is not None]
assert _DECK_IDXS == list(range(26)), "deck_idx must cover the deck's 26 rows once each"

# ---------------------------------------------------------------------------
# Vintages
# ---------------------------------------------------------------------------
VINTAGE_LABELS: dict[str, str] = {
    "2025A": "2025 Actuals (PY)",
    "2026B": "2026 Budget",
    "2026A": "FY26 Actuals (partial)",
}

#: The FY26 Actuals vintage. Seven months only (Jan-Jul), three quarters with
#: Q3 = Jul alone, no Q4, and a YearTotal that is a 7-month sum. Never a
#: like-for-like full-year comparison; the UI warns whenever it is selected.
PARTIAL_VINTAGE = "2026A"


def vintage_label(key: str) -> str:
    return VINTAGE_LABELS.get(key, key)


def _fc_month_index(key: str) -> int:
    """Calendar position of a '<Mon>. FC' vintage, or -1."""
    if not key.endswith(". FC"):
        return -1
    mon = key[:-4]
    return MONTHS.index(mon) if mon in MONTHS else -1


def order_vintages(keys: Sequence[str]) -> list[str]:
    """Baselines first, then forecast vintages oldest to newest.

    Mirrors the deck's ALL_PERIODS_ORDERED (2025A, 2026B, then Jan..Jul FC) and
    slots the two vintages the deck lacks: FY26 Actuals next to the other
    baselines, Aug. FC at the end of the forecast run.
    """
    base_order = {"2025A": 0, "2026B": 1, PARTIAL_VINTAGE: 2}
    return sorted(
        keys,
        key=lambda k: (0, base_order[k]) if k in base_order else (1, _fc_month_index(k)),
    )


def forecast_options(keys: Sequence[str]) -> list[str]:
    """Forecast dropdown: newest forecast first, FY26 Actuals last.

    Newest-first because the working answer to "what is the current outlook" is
    the latest vintage; the deck defaulted to Jul. FC for the same reason and
    this account now carries Aug. FC.
    """
    fcs = [k for k in keys if k.endswith(". FC")]
    fcs.sort(key=_fc_month_index, reverse=True)
    tail = [k for k in (PARTIAL_VINTAGE,) if k in keys]
    return fcs + tail


def comp_options(keys: Sequence[str], forecast: str) -> list[str]:
    """Comparison dropdown, porting the deck's refreshCompOpts().

    '' is the "None" entry. Order: baselines, then every forecast vintage
    EXCEPT the selected one -- comparing a vintage to itself is the deck's one
    excluded case, and resolve_comp() below reproduces its reset-on-collision.
    """
    out: list[str] = [""]
    out += [k for k in ("2026B", "2025A", PARTIAL_VINTAGE) if k in keys and k != forecast]
    fcs = [k for k in keys if k.endswith(". FC") and k != forecast]
    fcs.sort(key=_fc_month_index, reverse=True)
    return out + fcs


def resolve_comp(comp: str, forecast: str, options: Sequence[str]) -> str:
    """The deck's rule: a comparison that collides with the forecast resets."""
    if comp == forecast or comp not in options:
        return ""
    return comp


# ---------------------------------------------------------------------------
# The cube
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Cube:
    """Every figure the app can show, keyed for O(1) lookup.

    ``segs[(vintage, line, period_key)]`` is the 7-segment dict for one cell;
    every displayed number is an expression over one or two of those dicts.
    """

    segs: dict[tuple[str, str, str], dict[str, float]]
    month_actual: dict[tuple[str, str], bool]
    scenario_label: dict[str, str]
    fiscal_year: dict[str, str]
    months_present: dict[str, tuple[str, ...]]
    quarters_present: dict[str, tuple[str, ...]]
    vintages: tuple[str, ...]

    # -- values ----------------------------------------------------------
    def value(self, vintage: str, row: Row, period_key: str) -> float | None:
        """The figure for one cell, or None when it cannot be derived."""
        if row.expr is None or row.num_line is None:
            return None
        num_segs = self.segs.get((vintage, row.num_line, period_key))
        if num_segs is None:
            return None
        num = row.expr(num_segs)
        if not row.is_pct:
            return num
        if row.den_line is None:
            return None
        den_segs = self.segs.get((vintage, row.den_line, period_key))
        if den_segs is None:
            return None
        den = row.expr(den_segs)
        return None if not den else num / den

    # -- period labelling ------------------------------------------------
    def _yy(self, vintage: str) -> str:
        return self.fiscal_year.get(vintage, "FY26")[2:]

    def _yyyy(self, vintage: str) -> str:
        return "20" + self._yy(vintage)

    def _suffix(self, vintage: str, months: Sequence[str]) -> str:
        """'A' actual, 'B' budget, 'F' forecast.

        A quarter or a year is only 'A' when every month it contains is an
        actual -- which is what reproduces the deck's Q1 26A / Q2 26A / Q3 26F /
        Q4 26F for Jul. FC, and correctly labels older vintages that the deck's
        hardcoded constants got wrong.
        """
        label = self.scenario_label.get(vintage, "FORECAST")
        if label == "ACTUAL":
            return "A"
        if label == "BUDGET":
            return "B"
        flags = [self.month_actual[(vintage, m)] for m in months
                 if (vintage, m) in self.month_actual]
        return "A" if flags and all(flags) else "F"

    def periods(self, vintage: str, grain: str) -> list[tuple[str, str]]:
        """(period_key, label) pairs for one vintage at one grain.

        The annual column is appended to the quarterly and monthly grains, as
        in the deck. Only periods the vintage actually has are listed, so FY26
        Actuals yields 7 months / 3 quarters rather than fabricating a Q4.
        """
        yy, yyyy = self._yy(vintage), self._yyyy(vintage)
        months = self.months_present.get(vintage, ())
        annual = (ANNUAL, f"FY {yyyy}{self._suffix(vintage, months)}")

        if grain == "annual":
            return [annual]
        if grain == "quarterly":
            qs = [
                (q, f"{q} {yy}{self._suffix(vintage, QUARTER_MONTHS[q])}")
                for q in self.quarters_present.get(vintage, ())
            ]
            return qs + [annual]
        ms = [(m, f"{m} {yy}{self._suffix(vintage, (m,))}") for m in months]
        return ms + [annual]

    def is_partial(self, vintage: str) -> bool:
        return len(self.months_present.get(vintage, ())) < 12


#: Internal cube key for queries.COMPENSATION_LINE. Never referenced by a Row --
#: build_cube discards it, after folding it into gross_margin and ebitda only
#: when queries.APPLY_COMPENSATION_ADJUSTMENT is True (it is False by default).
_COMP = "_compensation"


def build_cube(df: pd.DataFrame) -> Cube:
    """Index the master frame for lookup. ~724 rows, so cost is negligible."""
    line_of = {sql_name: key for key, sql_name in queries.PL_LINES.items()}
    line_of[queries.COMPENSATION_LINE] = _COMP
    seg_cols = [f"seg_{k}" for k in queries.SEGMENTS]

    segs: dict[tuple[str, str, str], dict[str, float]] = {}
    month_actual: dict[tuple[str, str], bool] = {}
    scenario_label: dict[str, str] = {}
    fiscal_year: dict[str, str] = {}
    months: dict[str, set[str]] = {}
    quarters: dict[str, set[str]] = {}

    for rec in df.to_dict("records"):
        vintage = rec["vintage_key"]
        line = line_of.get(rec["pl_line"])
        if line is None:
            continue

        ptype = rec["period_type"]
        if ptype == "YEAR":
            pkey = ANNUAL
        elif ptype == "QUARTER":
            pkey = rec["period"]
            quarters.setdefault(vintage, set()).add(pkey)
        else:
            pkey = rec["period"]
            months.setdefault(vintage, set()).add(pkey)
            flag = rec["is_actual_month"]
            if flag is not None and flag is not pd.NA:
                month_actual[(vintage, pkey)] = bool(flag)

        segs[(vintage, line, pkey)] = {
            k: float(rec[c]) for k, c in zip(queries.SEGMENTS, seg_cols)
        }
        scenario_label[vintage] = rec["scenario_label"]
        fiscal_year[vintage] = rec["fiscal_year"]

    _apply_compensation(segs)

    return Cube(
        segs=segs,
        month_actual=month_actual,
        scenario_label=scenario_label,
        fiscal_year=fiscal_year,
        months_present={v: tuple(m for m in MONTHS if m in s) for v, s in months.items()},
        quarters_present={v: tuple(q for q in QUARTERS if q in s) for v, s in quarters.items()},
        vintages=tuple(order_vintages(list(scenario_label))),
    )


def _apply_compensation(segs: dict[tuple[str, str, str], dict[str, float]]) -> None:
    """Optionally undo the source's Compensation double-count, in place.

    GATED BY queries.APPLY_COMPENSATION_ADJUSTMENT, default False (2026-09-29).

    When the flag is False -- the default -- this only DISCARDS the _COMP keys
    and returns, adding nothing. gross_margin and ebitda are then the source's
    own ACX_Gross Margin and ACX_EBITDA, which is what EPM (cube CARDPLN)
    reports and what the business treats as authoritative: Q1 FY26 North America
    EBITDA is $195.32M, not the $244.22M the add-back produced. Finance handles
    the Compensation double-count outside this app, so applying it here
    double-corrects it.

    The keys are removed rather than left in place because build_cube's contract
    is that every key in the returned cube is a reported line; a leftover
    _compensation entry would be a trap for the next reader (and for anything
    that iterates the cube).

    When the flag is True, the original behaviour runs unchanged, as described
    below.

    ------------------------------------------------------------------
    ACX_Cost of Goods Sold is not the sum of its seven mapped children -- it is
    those children PLUS ACX_Compensation. And Compensation is ALSO inside
    ACX_Other SG&A. Since the source computes

        Gross Margin = Net Revenue - Cost of Goods Sold
        EBITDA       = Gross Margin - Marketing - SG&A

    the line is charged twice, so both subtotals understate by exactly that
    amount. Adding it back once to each is the correction.

    Sign: COGS is stored positive and is SUBTRACTED to reach Gross Margin, so
    removing Compensation from COGS is ``+ compensation`` on both subtotals.

    Why this is safe per segment: Compensation satisfies
    ``na + elim + intl == phys`` at 428/428 cells (worst residual $0.0001), so
    correcting each of the seven segments independently keeps every row
    expression coherent -- including ``_digital_residual`` (exem - phys) and
    ``_grand_total`` (exem + fanlive + keylit). Nothing downstream needs to know
    this happened.

    Gated by tools/validate_vs_deck.py::check_compensation, which fails if the
    source ever stops satisfying ``cogs == children + compensation`` -- and which
    is itself skipped while this flag is False.
    """
    comp_keys = [k for k in segs if k[1] == _COMP]

    if not queries.APPLY_COMPENSATION_ADJUSTMENT:
        for key in comp_keys:
            del segs[key]
        return

    for key in comp_keys:
        vintage, _, pkey = key
        comp = segs.pop(key)
        for target in ("gross_margin", "ebitda"):
            dest = segs.get((vintage, target, pkey))
            if dest is None:
                continue
            for seg_key, amount in comp.items():
                dest[seg_key] += amount


# ---------------------------------------------------------------------------
# Deck reference lookup
# ---------------------------------------------------------------------------
def deck_value(
    deck: Mapping[str, list[dict]], vintage: str, deck_idx: int | None,
    period_key: str
) -> float | None:
    """The deck's own figure for a cell, or None when the deck lacks it.

    Takes a DECK position (Row.deck_idx), not a ROWS index -- the two diverged
    on 2026-09-29 when Revenue and Gross Margin gained an Eliminations row that
    the deck has no counterpart for. Those rows pass deck_idx=None and get None
    back, which is the honest answer: there is nothing in the deck to compare.

    The deck also predates Aug. FC and FY26 Actuals, so those legitimately
    return None everywhere.
    """
    if deck_idx is None:
        return None
    rows = deck.get(vintage)
    if not rows or deck_idx >= len(rows):
        return None
    row = rows[deck_idx]
    if period_key == ANNUAL:
        return row.get("annual")
    if period_key in QUARTERS:
        return (row.get("quarterly") or {}).get(period_key)
    if period_key in MONTHS:
        monthly = row.get("monthly") or []
        i = MONTHS.index(period_key)
        return monthly[i] if i < len(monthly) else None
    return None
