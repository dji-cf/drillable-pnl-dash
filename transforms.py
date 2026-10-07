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
import re
from dataclasses import dataclass, replace
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

#: Year-to-date period keys are 'YTD:<last month>', e.g. 'YTD:Aug' = Jan..Aug.
#: The month range lives IN the key so a comparison vintage read with the
#: forecast's period keys is summed over exactly the forecast's months.
YTD_PREFIX = "YTD:"


def ytd_key(last_month: str) -> str:
    return f"{YTD_PREFIX}{last_month}"


def ytd_months(period_key: str) -> tuple[str, ...]:
    """'YTD:Aug' -> ('Jan', ..., 'Aug')."""
    last = period_key[len(YTD_PREFIX):]
    return MONTHS[: MONTHS.index(last) + 1]


def is_ytd(period_key: str) -> bool:
    return period_key.startswith(YTD_PREFIX)


GRAINS: tuple[str, ...] = ("annual", "quarterly", "monthly")

SECTIONS: tuple[str, ...] = ("Revenue", "Gross Margin", "EBITDA", "EBITDA Margin")
# The deck prints no section header for the single-row margin section
# (source JS line 357).
SECTIONS_WITH_HEADER: tuple[str, ...] = ("Revenue", "Gross Margin", "EBITDA")

# ---------------------------------------------------------------------------
# Deck colors
# ---------------------------------------------------------------------------
# The deck keyed PERIOD_COLORS on literal vintage names ('2025A', 'Jul. FC').
# The same colors are now assigned by KIND and as-of month -- see
# vintage_color() -- so a new year's vintages are colored with no edit.
# Actuals and Budgets alternate shade by year parity, so two adjacent years
# plotted together stay distinguishable.
_ACTUAL_COLORS: tuple[str, str] = ("#7a9ab8", "#56708c")
_BUDGET_COLORS: tuple[str, str] = ("#a0b4c8", "#c3cfdc")
#: Forecast colors by as-of month. Jan-Aug are the deck's own; Sep-Dec extend
#: its ramp into the violet Aug started.
_FC_MONTH_COLORS: tuple[str, ...] = (
    "#93c5fd", "#60a5fa", "#3b82f6", "#1d4ed8", "#1e3a8a", "#172554",
    "#0b1220", "#4c1d95", "#6d28d9", "#7c3aed", "#8b5cf6", "#a78bfa",
)
FALLBACK_COLOR = "#4d7ab8"

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


#: How the change column reads on dollar rows: a percent change ("pct", the
#: deck's only mode) or the gross difference in $M ("usd"). Percent rows are
#: basis points in BOTH modes -- a "% change of a margin" is not a quantity
#: anyone quotes, and a margin has no dollar difference.
DELTA_MODES: tuple[str, ...] = ("pct", "usd")
#: The toggle's button text, in DELTA_MODES order.
DELTA_MODE_LABELS: dict[str, str] = {"pct": "%", "usd": "$"}


def delta_value(
    curr: float | None, comp: float | None, is_pct: bool, mode: str = "pct"
) -> float | None:
    """The raw change behind a delta cell, in the unit the cell shows.

    Percent rows: basis points. Dollar rows: the fractional change (0.42 for
    +42%) in "pct" mode, the dollar difference in "usd" mode. None when either
    side is missing, or for a percent change against zero.
    """
    if _is_missing(comp) or _is_missing(curr):
        return None
    curr_f, comp_f = float(curr), float(comp)  # type: ignore[arg-type]
    if is_pct:
        return (curr_f - comp_f) * 10_000
    if mode == "usd":
        return curr_f - comp_f
    if comp_f == 0:
        return None
    return (curr_f - comp_f) / abs(comp_f)


def delta_fmt(
    curr: float | None,
    comp: float | None,
    is_pct: bool,
    has_comp: bool = True,
    mode: str = "pct",
    usd_suffix: str = "",
) -> dict[str, str] | None:
    """Change cell: {'text', 'cls'}, or None when no comparison.

    Percent rows go to basis points; dollar rows to a percent change ("pct")
    or to the difference in $M ("usd", formatted like fmt_m: '+$12', '($5)').
    ``usd_suffix`` goes inside the figure ('+$120M', '($5M)') for the tiles.
    The pct-mode thresholds (0.5 bps, 0.1%) are the deck's, not a rounding
    artifact -- a delta inside them renders neutral rather than green/red. A
    usd delta is neutral when it rounds to $0M.

    Deviation from the deck, deliberate: when ``curr`` is missing this returns
    an em-dash. The deck's JS would coerce a null ``curr`` to 0 and print a
    confident -100%, which is wrong -- it happens whenever the comparison
    vintage covers a period the forecast does not (or vice versa).
    """
    if not has_comp or _is_missing(comp) or _is_missing(curr):
        return None
    d = delta_value(curr, comp, is_pct, mode)

    if is_pct:
        assert d is not None
        sign = "+" if d >= 0 else ""
        cls = "gpos" if d > 0.5 else "gneg" if d < -0.5 else "gflat"
        return {"text": f"{sign}{round_half_up(d)} bps", "cls": cls}

    if mode == "usd":
        assert d is not None
        m = d / 1e6
        r = round_half_up(abs(m))
        if r == 0:
            return {"text": f"$0{usd_suffix}", "cls": "gflat"}
        if m > 0:
            return {"text": f"+${r:,}{usd_suffix}", "cls": "gpos"}
        return {"text": f"(${r:,}{usd_suffix})", "cls": "gneg"}

    if d is None:                   # a percent change against zero
        return {"text": EM_DASH, "cls": "gflat"}
    d *= 100
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

#: Every kind the registry may use. Guards GAPS against a typo'd kind --
#: tools/validate_vs_deck.py::check_gap_registry asserts membership.
GAP_KINDS: frozenset[str] = frozenset(
    {SPLIT, COMBINED, PARTIAL, ABSENT, HIERARCHY, UNRECONCILED}
)

# Keyed by row index. A row may carry more than one kind.
#
# Row 3 (Revenue Digital) is worth a word: it currently matches the deck to the
# cent, because Corporate has no revenue, so the residual happens to be Digital
# alone. It is still flagged -- the moment any Corporate revenue appears it will
# be silently absorbed into this row with no other symptom.
#
# The Gross Margin % rows inherit the same structural limits as the Revenue rows
# they sit under (row 10 is the same residual, row 12 the same combined
# segment). They are not double-flagged with SPLIT/COMBINED because all 7
# already carry UNRECONCILED, which strictly dominates. Rows 10 and 18 are the
# exception: HIERARCHY is not dominated, because it withholds the figure where
# UNRECONCILED alone would let it render.
#
# Row 22 (EBITDA Key Litigation Costs) is worth its own note. It was a candidate
# to ship unflagged, because it ties to the cent for Jul. FC -- but the ROW 22
# gate in tools/validate_vs_deck.py proved that is only true for 5 of the 9
# shared vintages, so it keeps the flag. See ROW22_TIES there, and ISSUES.md 6.2.
GAPS: dict[int, tuple[str, ...]] = {
    3: (SPLIT,),
    5: (COMBINED,),
    # Gross Margin % -- rows 7-13, with 10 carrying the broken residual.
    **{i: (UNRECONCILED,) for i in range(7, 14) if i != 10},
    10: (UNRECONCILED, HIERARCHY),
    # EBITDA -- rows 14-24 -- and EBITDA Margin (25).
    14: (UNRECONCILED,),
    15: (UNRECONCILED,),
    16: (UNRECONCILED, PARTIAL),
    17: (UNRECONCILED,),
    18: (UNRECONCILED, SPLIT, HIERARCHY),
    19: (UNRECONCILED, SPLIT),
    20: (UNRECONCILED,),
    21: (UNRECONCILED, COMBINED),
    22: (UNRECONCILED,),
    23: (UNRECONCILED, ABSENT),
    24: (UNRECONCILED,),
    25: (UNRECONCILED,),
}

#: Rows whose live value cannot be trusted as a like-for-like of the deck.
UNRECONCILED_ROWS: frozenset[int] = frozenset(
    i for i, kinds in GAPS.items() if UNRECONCILED in kinds
)

#: Gap kinds that withhold the figure unconditionally, because the number that
#: would appear is not merely off, it is meaningless.
BLOCKING_KINDS: frozenset[str] = frozenset({HIERARCHY})


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

# Revenue / Gross Margin basis. The deck folds Topps Eliminations into North
# America revenue (4,074.8 - 121.5 = 3,953.3, its exact printed value), so we
# do too -- flagged with a footnote in the UI rather than silently.
_na_folded: Callable[[Segs], float] = lambda s: s["na"] + s["elim"]
_intl: Callable[[Segs], float] = lambda s: s["intl"]
_phys: Callable[[Segs], float] = lambda s: s["phys"]
_digital_residual: Callable[[Segs], float] = lambda s: s["exem"] - s["phys"]
_exem: Callable[[Segs], float] = lambda s: s["exem"]
_fanlive: Callable[[Segs], float] = lambda s: s["fanlive"]
_keylit: Callable[[Segs], float] = lambda s: s["keylit"]
_grand_total: Callable[[Segs], float] = lambda s: s["exem"] + s["fanlive"] + s["keylit"]
# EBITDA keeps North America and Eliminations apart -- unlike Revenue, the deck
# gives Eliminations its own EBITDA row, so folding would double-count.
_na_gross: Callable[[Segs], float] = lambda s: s["na"]
_elim: Callable[[Segs], float] = lambda s: s["elim"]


@dataclass(frozen=True)
class Row:
    """One line item of the statement."""

    idx: int
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

        Distinct from is_live. Four rows must never render: 19 (Corporate) and
        23 (TCG) have no expression, while 10 and 18 (Digital) DO have one -- it
        just evaluates over a residual the source has made nonsense of. Callers
        gate placeholders on this rather than on is_live, so a broken residual
        can never reach the screen. See ISSUES.md section 4, HIERARCHY.
        """
        return self.is_live and not (set(self.gaps) & BLOCKING_KINDS)

    @property
    def is_reconciled(self) -> bool:
        """True when the live value is a trustworthy like-for-like of the deck."""
        return self.is_live and UNRECONCILED not in self.gaps


def _rev(idx: int, label: str, row_type: str, expr) -> Row:
    return Row(idx, "Revenue", label, label if row_type != "total" else "Total Revenue",
               row_type, False, "net_revenue", None, expr)


def _gm(idx: int, label: str, metric_label: str, row_type: str, expr) -> Row:
    return Row(idx, "Gross Margin", label, metric_label, row_type, True,
               "gross_margin", "net_revenue", expr)


def _eb(idx: int, label: str, row_type: str, expr) -> Row:
    return Row(idx, "EBITDA", label, label if row_type != "total" else "Total EBITDA",
               row_type, False, "ebitda", None, expr)


#: The deck's 26 rows, in deck order. Index IS the deck's row index -- the
#: reference JSON keys on it, so never reorder.
ROWS: tuple[Row, ...] = (
    # -- Revenue (live, reconciled exactly) --------------------------------
    _rev(0, "North America",          "sub",      _na_folded),
    _rev(1, "International",          "sub",      _intl),
    _rev(2, "Total Physical Cards",   "subtotal", _phys),
    _rev(3, "Digital",                "sub",      _digital_residual),
    _rev(4, "Total ex-Emerging Svcs", "subtotal", _exem),
    _rev(5, "Fanatics Collect",       "sub",      _fanlive),
    _rev(6, "Total Revenue",          "total",    _grand_total),
    # -- Gross Margin % (unreconciled) ------------------------------------
    # Each row's basis is the Revenue row directly above it, so the two blocks
    # read as parallel. The deck's table labels carry no '%'; its metric picker
    # does.
    _gm(7,  "North America",          "North America %",          "sub",      _na_folded),
    _gm(8,  "International",          "International %",          "sub",      _intl),
    _gm(9,  "Total Physical Cards",   "Total Physical Cards %",   "subtotal", _phys),
    _gm(10, "Digital",                "Digital %",                "sub",      _digital_residual),
    _gm(11, "Total ex-Emerging Svcs", "Total ex-Emerging Svcs %", "subtotal", _exem),
    _gm(12, "Fanatics Collect",       "Fanatics Collect %",       "sub",      _fanlive),
    _gm(13, "Total Gross Margin",     "Total Gross Margin %",     "total",    _grand_total),
    # -- EBITDA (unreconciled) --------------------------------------------
    _eb(14, "North America",          "sub",      _na_gross),
    _eb(15, "International",          "sub",      _intl),
    _eb(16, "Eliminations",           "sub",      _elim),
    _eb(17, "Total Physical Cards",   "subtotal", _phys),
    _eb(18, "Digital",                "sub",      _digital_residual),
    # Corporate and TCG have NO expression: the view carries no segment for
    # either, so there is nothing to show and they render as an em-dash.
    _eb(19, "Corporate",              "sub",      None),
    _eb(20, "Total ex-Emerging Svcs", "subtotal", _exem),
    _eb(21, "Fanatics Collect",       "sub",      _fanlive),
    _eb(22, "Key Litigation Costs",   "sub",      _keylit),
    _eb(23, "TCG",                    "sub",      None),
    _eb(24, "Total EBITDA",           "total",    _grand_total),
    # -- EBITDA Margin % (unreconciled) -----------------------------------
    Row(25, "EBITDA Margin", "EBITDA Margin", "EBITDA Margin %", "margin",
        True, "ebitda", "net_revenue", _grand_total),
)

assert len(ROWS) == 26, "the deck has 26 rows"
assert all(r.idx == i for i, r in enumerate(ROWS)), "ROWS must be in index order"

#: Hover text on the statement's row labels, keyed (section, label).
ROW_TOOLTIPS: dict[tuple[str, str], str] = {
    **{(sec, "North America"): (
        "North America Gross Margins exclude eliminations; "
        "Total Gross Margin includes eliminations.")
       for sec in ("Revenue", "Gross Margin", "EBITDA")},
    **{(sec, "Fanatics Collect"): "Fanatics Live (LB_306) + Marketplace / PWCC (LB_307)"
       for sec in ("Revenue", "Gross Margin", "EBITDA")},
}

# ---------------------------------------------------------------------------
# STG source
# ---------------------------------------------------------------------------
# Same 26 rows, same labels, same order -- only the expressions change, and they
# come from queries.STG_ROW_MAP, so no LOB grouping lives in this file. Every
# row is derivable and none is a structural gap any more: Digital, Corporate and
# TCG have real LOBs in STG. So the legacy gap registry, which describes the
# legacy table's limits, does not apply and is cleared.
if queries.SOURCE == "STG":
    def _terms_expr(terms: tuple[tuple[int, str], ...]) -> Callable[[Segs], float]:
        return lambda s: sum(sign * s[key] for sign, key in terms)

    _missing = [(r.section, r.label) for r in ROWS
                if (r.section, r.label) not in queries.STG_ROW_MAP]
    assert not _missing, f"STG_ROW_MAP has no entry for {_missing}"

    ROWS = tuple(
        replace(r, expr=_terms_expr(queries.STG_ROW_MAP[(r.section, r.label)]))
        for r in ROWS
    )
    GAPS = {}
    UNRECONCILED_ROWS = frozenset()

# ---------------------------------------------------------------------------
# Vintages
# ---------------------------------------------------------------------------
# Keys come from queries._VINTAGE_KEY and always carry their year:
#   '2025A'        Actuals, FY25
#   '2026B'        Budget, FY26
#   'Sep 2026 FC'  the forecast as of Sep 2026 (read at FY26)
# Labels, ordering and colors are all derived from the key and which vintages
# are OFFERED from the data (Cube.visible), so nothing below names a year.
ACTUAL, BUDGET, FORECAST = "A", "B", "F"

_BASE_KEY = re.compile(r"^(\d{4})([AB])$")
_FC_KEY = re.compile(r"^([A-Z][a-z]{2}) (\d{4}) FC$")
_KIND_RANK = {ACTUAL: 0, BUDGET: 1, FORECAST: 2}


def vintage_parts(key: str) -> tuple[str, int, int] | None:
    """(kind, year, as-of month 1-12 -- 0 for Actuals/Budget), or None.

    The one parser of the keys queries._VINTAGE_KEY emits. None for anything
    else, so a dev tool carrying its own key format (tools/gap_analysis.py)
    degrades to input order rather than raising.
    """
    m = _BASE_KEY.match(key)
    if m:
        return m.group(2), int(m.group(1)), 0
    m = _FC_KEY.match(key)
    if m and m.group(1) in MONTHS:
        return FORECAST, int(m.group(2)), MONTHS.index(m.group(1)) + 1
    return None


def vintage_label(key: str) -> str:
    """'2025A' -> '2025 Actuals', '2026B' -> '2026 Budget'.

    A forecast key ('Sep 2026 FC') is already its own label. No "(PY)" or
    "(partial)" qualifiers: both are relative to today and go stale on their
    own -- prior-year-ness is the comparison the user picked, and partial
    actuals are not offered at all (see Cube.visible).
    """
    parts = vintage_parts(key)
    if parts is None:
        return key
    kind, year, _ = parts
    if kind == ACTUAL:
        return f"{year} Actuals"
    if kind == BUDGET:
        return f"{year} Budget"
    return key


def change_label(comp: str) -> str:
    """Header for the change block, e.g. 'Change vs. Aug 2026 FC'."""
    return f"Change vs. {vintage_label(comp)}"


def vintage_color(key: str) -> str:
    """Chart / swatch color: by kind, and by as-of month for forecasts."""
    parts = vintage_parts(key)
    if parts is None:
        return FALLBACK_COLOR
    kind, year, month = parts
    if kind == ACTUAL:
        return _ACTUAL_COLORS[year % 2]
    if kind == BUDGET:
        return _BUDGET_COLORS[year % 2]
    return _FC_MONTH_COLORS[month - 1]


def _sort_key(key: str) -> tuple[int, int, int]:
    parts = vintage_parts(key)
    if parts is None:
        return (len(_KIND_RANK), 0, 0)
    kind, year, month = parts
    return (_KIND_RANK[kind], year, month)


def order_vintages(keys: Sequence[str]) -> list[str]:
    """Actuals, then Budgets, then forecasts -- each oldest to newest.

    The deck's ALL_PERIODS_ORDERED (2025A, 2026B, then Jan..Jul FC), carried
    across years: Dec 2026 FC sorts before Jan 2027 FC. Stable, so unparseable
    keys keep their input order at the end.
    """
    return sorted(keys, key=_sort_key)


def _newest_first(keys: Sequence[str]) -> list[str]:
    return sorted(keys, key=_sort_key, reverse=True)


def forecast_options(cube: "Cube", include_retired: bool = False) -> list[str]:
    """Forecast dropdown: the offered forecasts, newest first.

    Newest-first because the working answer to "what is the current outlook" is
    the latest vintage; the deck defaulted to its newest (Jul. FC) for the same
    reason. If no forecast is offered -- early in a year, after the prior year's
    are retired and before the first new one lands -- fall back to the open
    year's Budget, then to every vintage, so the page always has something.
    """
    visible = cube.visible(include_retired)
    for label in ("FORECAST", "BUDGET"):
        keys = [k for k in visible if cube.scenario_label.get(k) == label]
        if keys:
            return _newest_first(keys)
    return _newest_first(visible or cube.vintages)


def comp_options(cube: "Cube", forecast: str, include_retired: bool = False) -> list[str]:
    """Comparison dropdown, porting the deck's refreshCompOpts().

    '' is the "None" entry. Then Budgets, complete Actuals, and forecasts, each
    newest first, EXCEPT the selected forecast -- comparing a vintage to itself
    is the deck's one excluded case, and resolve_comp() below reproduces its
    reset-on-collision.
    """
    visible = [k for k in cube.visible(include_retired) if k != forecast]
    out: list[str] = [""]
    for label in ("BUDGET", "ACTUAL", "FORECAST"):
        out += _newest_first([k for k in visible if cube.scenario_label.get(k) == label])
    return out


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
    def _segs(self, vintage: str, line: str, period_key: str) -> dict[str, float] | None:
        """The segment dict for one cell; a YTD key sums its months.

        Summed BEFORE the row expression is applied, so a percent row's YTD is
        the ratio of the summed numerator and denominator, not a mean of
        monthly ratios. Any missing month makes the whole YTD missing rather
        than quietly short.
        """
        if not is_ytd(period_key):
            return self.segs.get((vintage, line, period_key))
        total: dict[str, float] = {}
        for month in ytd_months(period_key):
            month_segs = self.segs.get((vintage, line, month))
            if month_segs is None:
                return None
            for k, v in month_segs.items():
                total[k] = total.get(k, 0.0) + v
        return total

    def value(self, vintage: str, row: Row, period_key: str) -> float | None:
        """The figure for one cell, or None when it cannot be derived."""
        if row.expr is None or row.num_line is None:
            return None
        num_segs = self._segs(vintage, row.num_line, period_key)
        if num_segs is None:
            return None
        num = row.expr(num_segs)
        if not row.is_pct:
            return num
        if row.den_line is None:
            return None
        den_segs = self._segs(vintage, row.den_line, period_key)
        if den_segs is None:
            return None
        den = row.expr(den_segs)
        return None if not den else num / den

    # -- which vintages the page offers ----------------------------------
    def is_complete(self, vintage: str) -> bool:
        """All 12 months present. False only for an in-progress Actuals year."""
        return len(self.months_present.get(vintage, ())) == len(MONTHS)

    @property
    def final_years(self) -> frozenset[str]:
        """Fiscal years whose actuals are final: the ACTUAL vintage has 12 months."""
        return frozenset(
            self.fiscal_year[v] for v in self.vintages
            if self.scenario_label.get(v) == "ACTUAL" and self.is_complete(v)
        )

    def is_retired(self, vintage: str) -> bool:
        """A Budget or forecast for a year whose actuals are final.

        Once a year has closed, its forecasts and budget are history: the
        Actuals are the answer. They stay in the cube and come back with the
        sidebar's "show prior-year" toggle, but are not offered by default.
        """
        return (self.scenario_label.get(vintage) in ("BUDGET", "FORECAST")
                and self.fiscal_year.get(vintage) in self.final_years)

    def visible(self, include_retired: bool = False) -> tuple[str, ...]:
        """The vintages the dropdowns and the Trends checklist offer.

        Never a partial-year Actuals vintage: it is a strict subset of the
        newest forecast (its closed months are that forecast's actual months),
        and its FY total is an n-month sum that reads as a full year. The YTD
        column carries what it was used for. An Actuals year appears once all
        12 months are in, which is when it becomes the prior-year comparison.
        """
        return tuple(
            v for v in self.vintages
            if (self.scenario_label.get(v) != "ACTUAL" or self.is_complete(v))
            and (include_retired or not self.is_retired(v))
        )

    # -- actual vs forecast ----------------------------------------------
    def months_of(self, vintage: str, period_key: str) -> tuple[str, ...]:
        """The calendar months a period key covers for one vintage."""
        if period_key == ANNUAL:
            return self.months_present.get(vintage, ())
        if period_key in QUARTER_MONTHS:
            return QUARTER_MONTHS[period_key]
        if is_ytd(period_key):
            return ytd_months(period_key)
        return (period_key,)

    def is_actual(self, vintage: str, period_key: str) -> bool:
        return self._suffix(vintage, self.months_of(vintage, period_key)) == "A"

    def same_actuals(self, a: str, b: str, period_key: str) -> bool:
        """Both vintages report this period as the same year's actuals.

        Then the change between them is zero by construction -- an RF
        snapshot's closed months are the Actual scenario's, byte for byte
        (ISSUES.md section 3) -- so the change cell is greyed rather than
        printing '+0%'. Different years (vs. prior-year Actuals) or a Budget
        side (never actual) are real variances and are not greyed.
        """
        return (self.fiscal_year.get(a) == self.fiscal_year.get(b)
                and self.is_actual(a, period_key)
                and self.is_actual(b, period_key))

    # -- period labelling ------------------------------------------------
    def _yy(self, vintage: str) -> str:
        return self.fiscal_year[vintage][2:]

    def _yyyy(self, vintage: str) -> str:
        return "20" + self._yy(vintage)

    def year(self, vintage: str) -> str:
        """'2026' -- the fiscal year a vintage is read at."""
        return self._yyyy(vintage)

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

    def ytd_period(self, vintage: str) -> tuple[str, str] | None:
        """('YTD:Aug', 'YTD Aug 26A') for a vintage part-way through its year.

        Jan through the last closed month. None when nothing is closed yet
        (Jan FC), when everything is (a full Actuals year -- YTD would be FY), or
        for a Budget, which has no actual months. Also None if the closed months
        are not a Jan-anchored run, which _IS_ACTUAL_MONTH cannot produce but a
        YTD label would then misdescribe.
        """
        closed = [m for m in self.months_present.get(vintage, ())
                  if self.month_actual.get((vintage, m))]
        if not closed or len(closed) == len(MONTHS):
            return None
        if tuple(closed) != MONTHS[: len(closed)]:
            return None
        key = ytd_key(closed[-1])
        return key, f"YTD {closed[-1]} {self._yy(vintage)}{self._suffix(vintage, closed)}"

    def periods(self, vintage: str, grain: str) -> list[tuple[str, str]]:
        """(period_key, label) pairs for one vintage at one grain.

        The annual column is appended to the quarterly and monthly grains, as
        in the deck, and a YTD column (see ytd_period) sits just before it at
        every grain. Only periods the vintage actually has are listed, so a
        partial Actuals year yields its closed months rather than fabricating
        a Q4.
        """
        yy, yyyy = self._yy(vintage), self._yyyy(vintage)
        months = self.months_present.get(vintage, ())
        tail = [(ANNUAL, f"FY {yyyy}{self._suffix(vintage, months)}")]
        ytd = self.ytd_period(vintage)
        if ytd is not None:
            tail.insert(0, ytd)

        if grain == "annual":
            return tail
        if grain == "quarterly":
            qs = [
                (q, f"{q} {yy}{self._suffix(vintage, QUARTER_MONTHS[q])}")
                for q in self.quarters_present.get(vintage, ())
            ]
            return qs + tail
        ms = [(m, f"{m} {yy}{self._suffix(vintage, (m,))}") for m in months]
        return ms + tail


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
# Trends
# ---------------------------------------------------------------------------
# What the Historical Trends charts read, kept here rather than in charts.py so
# the vintage rules and the bridge arithmetic can be asserted offline
# (tools/test_vintages.py).

#: The periods the outlook and bridge charts read: the FY total or one quarter.
#: The month chart always spans Jan-Dec.
TREND_PERIODS: tuple[str, ...] = (ANNUAL,) + QUARTERS


def year_budget(cube: Cube, vintage: str) -> str | None:
    """The Budget of a vintage's fiscal year ('2026B'), when the cube has it."""
    key = f"{cube.year(vintage)}B"
    return key if cube.scenario_label.get(key) == "BUDGET" else None


def prior_year_actuals(cube: Cube, vintage: str) -> str | None:
    """The year before's Actuals ('2025A' for FY26), once all 12 months are in."""
    key = f"{int(cube.year(vintage)) - 1}A"
    if cube.scenario_label.get(key) != "ACTUAL" or not cube.is_complete(key):
        return None
    return key


def outlook_vintages(cube: Cube, forecast: str, include_retired: bool = False) -> list[str]:
    """The outlook chart's x-axis: the year's Budget, then its forecasts by as-of.

    Only the selected forecast's own fiscal year, and every offered forecast of
    it -- not just those up to the selection, so picking an older forecast shows
    where it sits in the year rather than truncating the year.
    """
    fy = cube.fiscal_year[forecast]
    keys = [v for v in cube.visible(include_retired)
            if cube.fiscal_year[v] == fy
            and cube.scenario_label.get(v) in ("BUDGET", "FORECAST")]
    if forecast not in keys:
        keys.append(forecast)
    return order_vintages(keys)


def prior_forecast(cube: Cube, forecast: str, include_retired: bool = False) -> str | None:
    """The forecast just before this one in the same year; None for the first."""
    line = [v for v in outlook_vintages(cube, forecast, include_retired)
            if cube.scenario_label.get(v) == "FORECAST"]
    i = line.index(forecast) if forecast in line else 0
    return line[i - 1] if i > 0 else None


def default_lines(
    cube: Cube, forecast: str, comp: str, include_retired: bool = False
) -> list[str]:
    """The month chart's opening lines: the year's Budget, the comparison, and
    the forecast. With no comparison, the forecast just before stands in for it.
    """
    other = comp or prior_forecast(cube, forecast, include_retired)
    offered = set(cube.visible(include_retired))
    keys = {k for k in (year_budget(cube, forecast), other, forecast) if k}
    return order_vintages([k for k in keys if k in offered])


@dataclass(frozen=True)
class BridgeStep:
    """One bar of the bridge: a row's value in the comparison and the forecast."""

    label: str
    comp: float
    curr: float
    highlight: bool = False

    @property
    def delta(self) -> float:
        return self.curr - self.comp


@dataclass(frozen=True)
class Bridge:
    """``start`` + every step's delta == ``end`` (to within the dropped residual)."""

    parent: Row
    start: float
    end: float
    steps: tuple[BridgeStep, ...]


#: The residual step: whatever of the parent no row above it breaks out.
#: Corporate and TCG revenue, which have no Revenue rows; under LEGACY also the
#: EBITDA rows it cannot derive (18, 19, 23).
OTHER_LABEL = "Other"


def bridge(cube: Cube, row: Row, forecast: str, comp: str, period: str) -> Bridge | None:
    """The comparison-to-forecast bridge of a dollar row, by business unit.

    A total or subtotal is broken into the derivable detail rows above it in
    its section (Total Physical EBITDA = North America + International +
    Eliminations). A detail row is shown inside its section's total, with its
    own bar highlighted. Whatever the detail rows leave out becomes one
    OTHER_LABEL step -- included only when its change rounds to a non-zero $M --
    so the bars always run from the comparison's figure to the forecast's.

    Steps stay in deck order, not sorted by size, so a business unit keeps its
    place from one selection to the next.

    None when there is nothing to bridge: no comparison, a percent row (a
    margin's change does not split into additive pieces), a row that cannot be
    derived, or a parent figure missing on either side.
    """
    if not comp or row.is_pct or not row.is_derivable:
        return None
    if row.row_type == "sub":
        parent = next(r for r in ROWS if r.section == row.section and r.row_type == "total")
    else:
        parent = row
    start, end = cube.value(comp, parent, period), cube.value(forecast, parent, period)
    if start is None or end is None:
        return None

    steps: list[BridgeStep] = []
    rest_comp, rest_curr = start, end
    for child in ROWS:
        if (child.section != parent.section or child.row_type != "sub"
                or child.idx > parent.idx or not child.is_derivable):
            continue
        was, now = cube.value(comp, child, period), cube.value(forecast, child, period)
        if was is None or now is None:
            continue
        steps.append(BridgeStep(child.label, was, now, highlight=child.idx == row.idx))
        rest_comp -= was
        rest_curr -= now
    if round_half_up(abs(rest_curr - rest_comp) / 1e6):
        steps.append(BridgeStep(OTHER_LABEL, rest_comp, rest_curr))
    return Bridge(parent, start, end, tuple(steps))


# ---------------------------------------------------------------------------
# Deck reference lookup
# ---------------------------------------------------------------------------
def deck_value(
    deck: Mapping[str, list[dict]], vintage: str, row_idx: int, period_key: str
) -> float | None:
    """The deck's own figure for a cell, or None when the deck lacks it.

    The deck predates the Aug 2026 FC and later vintages, so those
    legitimately return None everywhere.
    """
    rows = deck.get(vintage)
    if not rows or row_idx >= len(rows):
        return None
    row = rows[row_idx]
    if period_key == ANNUAL:
        return row.get("annual")
    if period_key in QUARTERS:
        return (row.get("quarterly") or {}).get(period_key)
    if period_key in MONTHS:
        monthly = row.get("monthly") or []
        i = MONTHS.index(period_key)
        return monthly[i] if i < len(monthly) else None
    return None
