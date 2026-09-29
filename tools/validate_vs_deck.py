"""Assert the live figures reproduce the source deck where we claim they do.

Dev-only harness, deliberately NOT in snowflake.yml::artifacts.

    .venv\\Scripts\\python.exe tools\\validate_vs_deck.py

Connects with snowflake.connector directly rather than through data.py, so it
runs without a Streamlit context. Uses the same connections.toml entry the app
defaults to (HIDR_PROD -- role POWER_ANALYST_ORACLE_PROD), then drops secondary
roles, so this doubles as the owner's-rights check: if MASTER_SQL needs a
privilege the deployed app will not have, it fails here. That matters more since
the app moved off the view onto the base table.

Nine gates:

  REVENUE      every live Revenue cell within $0.05M of the deck, across the 9
               shared vintages x every period x 7 deck rows. Compared through
               REVENUE_UNITS, because the page now splits the deck's single
               North America row into North America gross + Eliminations, so
               that one unit sums two app rows. Aug. FC and FY26 Actuals are
               skipped -- they postdate the deck.
  ADDITIVITY   North America + Eliminations + International - Total Physical
               Cards == 0, per vintage per period.
  FORMATTERS   fmt_m / fmt_pct / delta_fmt against values read off the deck.
  GAP REGISTRY the registry's own invariants, including that the two broken
               residual rows and Gross Margin Eliminations % can never render.
  BASE vs VIEW the base table this app now reads reproduces the view it used to
               read, for the three reported lines. Guards the source swap.
  COMPENSATION ACX_Cost of Goods Sold == its 7 mapped children + ACX_Compensation.
               This identity is the whole justification for the correction in
               transforms._apply_compensation; if the source stops satisfying it,
               the correction becomes wrong and this fails loudly. SKIPPED while
               queries.APPLY_COMPENSATION_ADJUSTMENT is False (the default since
               2026-09-29) -- with no add-back there is nothing to justify.
  COMP ADDITIV ACX_Compensation satisfies na + elim + intl == phys, which is what
               makes it safe to correct each segment independently.
  ROW 22       EBITDA Key Litigation Costs ties to the deck in exactly the
               vintages ROW22_TIES says it does -- asserted in BOTH directions,
               so a regression and an improvement are equally loud. This is the
               gate that stopped row 22 shipping unflagged.

What is deliberately NOT gated: Gross Margin and EBITDA against the deck. They
do not tie in actual months and that is documented, not asserted -- see
transforms.py's module docstring and tools/gap_analysis.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Import the app's own modules, so this validates what ships rather than a copy.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import snowflake.connector  # noqa: E402

import queries  # noqa: E402
import transforms as tx  # noqa: E402

TOLERANCE_DOLLARS = 50_000.0        # $0.05M, per cell
ANNUAL_NOTE_THRESHOLD = 1.00        # report annual drift above a dollar
CONN_NAME = os.getenv("SNOWFLAKE_DEFAULT_CONNECTION_NAME", "HIDR_PROD")
DECK_JSON = Path(__file__).resolve().parent.parent / "reference" / "deck_jul2026.json"

# ---------------------------------------------------------------------------
# Documented drift between the view and the deck
# ---------------------------------------------------------------------------
# The deck is a point-in-time export (Jul 2026). The view is live and has been
# restated since. Where that restatement is a pure WITHIN-YEAR REALLOCATION --
# months move value between each other but no annual total changes -- the live
# app is more correct than the deck and the difference is expected.
#
# Listing a (vintage, deck row) here permits per-cell sub-annual differences for
# it. It does NOT weaken the two real gates, which still apply to every row:
#   * the annual figure must tie (ANNUAL), and
#   * sub-annual differences must sum to the annual difference (REALLOCATION),
# so a genuine level change cannot hide behind an entry in this table.
#
# Keyed by DECK row position, not by the app's ROWS index. Those were the same
# number until 2026-09-29, when the page gained two rows the deck has not; deck
# positions are the stable key, so this table did not have to be renumbered.
KNOWN_REALLOCATIONS: dict[tuple[str, int], str] = {
    ("2025A", 0): "FY25 restated: Apr/May/Jun value reallocated between North "
                  "America and International (+6,179,159.04 / +4,830,806.60 / "
                  "-11,009,965.64, summing to 0). Every quarter and the annual "
                  "still tie exactly.",
    ("2025A", 1): "FY25 restated: the offsetting side of the North America "
                  "Apr/May/Jun reallocation. Quarters and annual tie exactly.",
    ("2025A", 3): "FY25 restated: H1 ex-Emerging Services reallocated across "
                  "Jan-Jun, shifting $1,648,251.86 from Q1 into Q2. Q3, Q4 and "
                  "the annual tie exactly.",
    ("2025A", 4): "FY25 restated: the ex-Emerging Services subtotal carrying "
                  "the same H1 reallocation as Digital.",
}

# 2026 Budget carries a constant -$484.07 in North America that propagates into
# Total Physical Cards, Total ex-Emerging Svcs and Total Revenue at every grain.
# That is 1.3e-7 of a $3.6B budget -- a restatement crumb, far below materiality,
# but recorded rather than rounded away. Anything larger fails.
KNOWN_ANNUAL_DRIFT_CAP = 1_000.0

# ---------------------------------------------------------------------------
# Documented COGS mis-tagging
# ---------------------------------------------------------------------------
# The COMPENSATION gate below asserts
#     ACX_Cost of Goods Sold == its 7 mapped children + ACX_Compensation
# which holds at 100% of cells for na / elim / intl / phys / fanlive / total.
#
# It does NOT hold for 16 cells, every one of them 2025A sub-annual, where the
# Key Litigation segment carries COGS detail that belongs to ex-Emerging
# Services. They come in exactly offsetting pairs (Jun: exem -44.38M /
# keylit +44.38M; Q2: -11.54M / +11.54M; ...), so the company total --
# exem + fanlive + keylit -- is unaffected, and no FY26 vintage is touched.
#
# Listing a (vintage, period_type, period) here permits the pair. The gate still
# requires that the two residuals CANCEL and that no third segment is involved,
# so a genuine one-sided error cannot hide behind an entry in this table.
_MISTAG_NOTE = (
    "FY25 only: Key Litigation carries ex-Emerging Services COGS detail. The "
    "two residuals offset exactly, so exem + fanlive + keylit is unaffected."
)
KNOWN_COGS_MISTAG: dict[tuple[str, str, str], str] = {
    **{("2025A", "MONTH", m): _MISTAG_NOTE
       for m in ("Jan", "Feb", "Mar", "Apr", "May", "Jun")},
    **{("2025A", "QUARTER", q): _MISTAG_NOTE for q in ("Q1", "Q2")},
}

#: Vintages in which row 22 (EBITDA Key Litigation Costs) ties to the deck at
#: every grain. Measured, not assumed -- see check_row22.
#:
#: This is the reason row 22 keeps its UNRECONCILED flag. It ties to the cent for
#: Jul. FC, which made it look like the one reconciled cost row, but:
#:   * 2025A ties annually (+$0.26) and differs sub-annually, worst -$19.0M in
#:     Jun -- the FY25 Key Litigation Compensation that KNOWN_COGS_MISTAG covers.
#:   * The deck's Jan/Feb/Mar FC columns carry the 2026 BUDGET figure for this
#:     line (-$33,432,594) while those refreshes had already moved it. The deck
#:     is stale there rather than the source being wrong, but the ANNUAL does not
#:     tie, so it fails the bar KNOWN_REALLOCATIONS sets for excusal.
#:
#: Every one of those differences is PRE-EXISTING: verified against a cube built
#: with the Compensation rows dropped, the correction introduces none of them.
ROW22_TIES: frozenset[str] = frozenset(
    {"2026B", "Apr. FC", "May. FC", "Jun. FC", "Jul. FC"}
)

#: Cost rows permitted to report is_reconciled. Empty, and the ROW 22 gate is
#: why -- kept as a named constant so the invariant below reads as a policy
#: rather than a bare `False`, and so unflagging a row later is a one-line edit
#: with a gate already watching it.
RECONCILED_COST_ROWS: frozenset[int] = frozenset()

_COGS_KIDS: tuple[str, ...] = (
    "ACX_Manufacturing", "ACX_Royalties", "ACX_Net Freight Expense",
    "ACX_Product Development", "ACX_Autos & Relics", "ACX_MG Shortfall",
    "ACX_Obsolescence",
)


def _quoted(names) -> str:
    return ", ".join(f"'{n}'" for n in names)


# The gate SQL reuses queries.py's own private expressions on purpose: a gate
# that re-derived the vintage key or the filter would be testing a copy, not the
# statement the app actually runs.
_RAW_CTE = f"""
raw AS (
  SELECT
     {queries._FORECAST_ASOF.strip()} AS FORECAST_ASOF_DATE,
      SCENARIO_LABEL, FISCAL_YEAR, PERIOD, PERIOD_TYPE, LOB_SEGMENT, PL_LINE,
      AMOUNT
  FROM {queries.BASE}
),
f AS (
  SELECT
     {queries._VINTAGE_KEY.strip()} AS vintage_key,
      PERIOD, PERIOD_TYPE, LOB_SEGMENT, PL_LINE, AMOUNT
  FROM raw
  WHERE ({queries._VINTAGE_FILTER.strip()})
)"""

#: Cells where the COGS subtotal is not its children plus Compensation.
COMPOSITION_SQL = f"""
WITH {_RAW_CTE},
p AS (
  SELECT vintage_key, PERIOD_TYPE, PERIOD, LOB_SEGMENT,
      ZEROIFNULL(SUM(IFF(PL_LINE = 'ACX_Cost of Goods Sold', AMOUNT, NULL))) AS cogs,
      ZEROIFNULL(SUM(IFF(PL_LINE = '{queries.COMPENSATION_LINE}', AMOUNT, NULL))) AS comp,
      ZEROIFNULL(SUM(IFF(PL_LINE IN ({_quoted(_COGS_KIDS)}), AMOUNT, NULL))) AS kids
  FROM f
  GROUP BY 1, 2, 3, 4
)
SELECT vintage_key, PERIOD_TYPE, PERIOD, LOB_SEGMENT,
       cogs - kids - comp AS residual
FROM p
WHERE ABS(cogs - kids - comp) > 1
ORDER BY vintage_key, PERIOD_TYPE, PERIOD, LOB_SEGMENT
"""

#: Cells where Compensation is not additive across the segment hierarchy.
COMP_ADDITIVITY_SQL = f"""
WITH {_RAW_CTE},
p AS (
  SELECT vintage_key, PERIOD_TYPE, PERIOD,
      ZEROIFNULL(SUM(IFF(LOB_SEGMENT = '{queries.SEGMENTS["na"]}',   AMOUNT, NULL))) AS na,
      ZEROIFNULL(SUM(IFF(LOB_SEGMENT = '{queries.SEGMENTS["elim"]}', AMOUNT, NULL))) AS elim,
      ZEROIFNULL(SUM(IFF(LOB_SEGMENT = '{queries.SEGMENTS["intl"]}', AMOUNT, NULL))) AS intl,
      ZEROIFNULL(SUM(IFF(LOB_SEGMENT = '{queries.SEGMENTS["phys"]}', AMOUNT, NULL))) AS phys
  FROM f
  WHERE PL_LINE = '{queries.COMPENSATION_LINE}'
  GROUP BY 1, 2, 3
)
SELECT vintage_key, PERIOD_TYPE, PERIOD, na + elim + intl - phys AS residual
FROM p
WHERE ABS(na + elim + intl - phys) > 1
ORDER BY vintage_key, PERIOD_TYPE, PERIOD
"""

#: Row-count / distinct-cell / sum parity between the base table and the view.
PARITY_SQL = f"""
WITH {_RAW_CTE},
bf AS (
  SELECT * FROM f WHERE PL_LINE IN ({_quoted(queries.PL_LINES.values())})
),
vf AS (
  SELECT
     {queries._VINTAGE_KEY.strip()} AS vintage_key,
      PERIOD, PERIOD_TYPE, LOB_SEGMENT, PL_LINE, AMOUNT
  FROM {queries.VIEW}
  WHERE PL_LINE IN ({_quoted(queries.PL_LINES.values())})
    AND ({queries._VINTAGE_FILTER.strip()})
)
SELECT 'base' AS src, COUNT(*) AS n_rows,
       COUNT(DISTINCT vintage_key || '|' || PERIOD || '|' || PERIOD_TYPE
                      || '|' || PL_LINE || '|' || LOB_SEGMENT) AS n_cells,
       ROUND(SUM(AMOUNT), 4) AS total
FROM bf
UNION ALL
SELECT 'view', COUNT(*),
       COUNT(DISTINCT vintage_key || '|' || PERIOD || '|' || PERIOD_TYPE
                      || '|' || PL_LINE || '|' || LOB_SEGMENT),
       ROUND(SUM(AMOUNT), 4)
FROM vf
"""


def _fetch_sql(sql: str) -> pd.DataFrame:
    """Run one statement under the deployed app's identity."""
    conn = snowflake.connector.connect(connection_name=CONN_NAME)
    try:
        cur = conn.cursor()
        # Mirror the deployed app: SiS runs owner's-rights with no secondary
        # roles, so a query that only works via inherited roles must fail here.
        cur.execute("USE SECONDARY ROLES NONE")
        cur.execute(sql)
        df = cur.fetch_pandas_all()
    finally:
        conn.close()
    df.columns = [c.lower() for c in df.columns]
    return df


def fetch() -> pd.DataFrame:
    df = _fetch_sql(queries.MASTER_SQL)
    for col in [f"seg_{k}" for k in queries.SEGMENTS]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["is_actual_month"] = df["is_actual_month"].astype("boolean")
    return df


#: Revenue comparison units: (label, deck row position, app ROWS index/indices).
#:
#: One unit per deck Revenue row. All but the first are a single app row, and the
#: first is why this table exists: since 2026-09-29 the page shows 'North
#: America' as the source's gross segment and gives Eliminations its own row,
#: while the deck prints ONE folded North America figure (na + elim). So the
#: deck's row 0 is compared against the SUM of app rows 0 and 2.
#:
#: This keeps North America inside the hard annual gate rather than dropping it.
#: The fold that used to live in transforms._na_folded now lives here, where it
#: belongs -- it is a statement about the deck, not about the business.
REVENUE_UNITS: tuple[tuple[str, int, tuple[int, ...]], ...] = (
    ("North America + Eliminations", 0, (0, 2)),
    ("International",                1, (1,)),
    ("Total Physical Cards",         2, (3,)),
    ("Digital",                      3, (4,)),
    ("Total ex-Emerging Svcs",       4, (5,)),
    ("Fanatics Live and Collect",    5, (6,)),
    ("Total Revenue",                6, (7,)),
)


def _unit_live(cube: tx.Cube, vintage: str, idxs: tuple[int, ...],
               pk: str) -> float | None:
    """The app's figure for a comparison unit, or None if any part is missing."""
    total = 0.0
    for i in idxs:
        v = cube.value(vintage, tx.ROWS[i], pk)
        if v is None:
            return None
        total += v
    return total


def _shared_vintages(cube: tx.Cube, deck: dict) -> list[str]:
    """Vintages present in both. Aug. FC and FY26 Actuals postdate the deck."""
    return [v for v in cube.vintages if v in deck]


def check_revenue_annual(cube: tx.Cube, deck: dict) -> tuple[int, list[str], list[str]]:
    """HARD GATE: the annual figure must tie for every Revenue row.

    This is the gate that matters. A reallocation between months leaves the
    annual untouched; a genuine level change cannot.
    """
    failures: list[str] = []
    notes: list[str] = []
    checked = 0

    for vintage in _shared_vintages(cube, deck):
        for label, didx, idxs in REVENUE_UNITS:
            live = _unit_live(cube, vintage, idxs, tx.ANNUAL)
            want = tx.deck_value(deck, vintage, didx, tx.ANNUAL)
            if want is None or live is None:
                continue
            checked += 1
            diff = live - want
            if abs(diff) > KNOWN_ANNUAL_DRIFT_CAP:
                failures.append(
                    f"{vintage} deck{didx} ({label}) annual: "
                    f"live {live:,.2f} vs deck {want:,.2f} (diff {diff:,.2f})"
                )
            elif abs(diff) > ANNUAL_NOTE_THRESHOLD:
                notes.append(
                    f"{vintage} deck{didx} ({label}) annual drift "
                    f"{diff:,.2f} (within the ${KNOWN_ANNUAL_DRIFT_CAP:,.0f} cap)"
                )
    return checked, failures, notes


def check_revenue_reallocation(cube: tx.Cube, deck: dict) -> tuple[int, list[str]]:
    """HARD GATE: sub-annual drift must sum to the annual drift.

    If the 12 monthly differences (and the 4 quarterly differences) add up to
    the annual difference, then whatever changed is a reallocation across
    periods, not value appearing or disappearing. This is what makes it safe to
    tolerate the per-cell differences in KNOWN_REALLOCATIONS.
    """
    failures: list[str] = []
    checked = 0

    for vintage in _shared_vintages(cube, deck):
        for label, didx, idxs in REVENUE_UNITS:
            a_live = _unit_live(cube, vintage, idxs, tx.ANNUAL)
            a_deck = tx.deck_value(deck, vintage, didx, tx.ANNUAL)
            if a_live is None or a_deck is None:
                continue
            annual_diff = a_live - a_deck

            for grain_name, keys in (("monthly", tx.MONTHS), ("quarterly", tx.QUARTERS)):
                total = 0.0
                seen = 0
                for pk in keys:
                    lv = _unit_live(cube, vintage, idxs, pk)
                    dv = tx.deck_value(deck, vintage, didx, pk)
                    if lv is None or dv is None:
                        continue
                    total += lv - dv
                    seen += 1
                if seen == 0:
                    continue
                checked += 1
                # $1 absorbs float noise across a dozen billion-scale addends.
                if abs(total - annual_diff) > 1.0:
                    failures.append(
                        f"{vintage} deck{didx} ({label}): {grain_name} "
                        f"differences sum to {total:,.2f} but the annual "
                        f"difference is {annual_diff:,.2f} -- that is a level "
                        f"change, not a reallocation"
                    )
    return checked, failures


def check_revenue_cells(cube: tx.Cube, deck: dict) -> tuple[int, list[str], list[str]]:
    """Per-cell parity, excusing only the documented reallocations."""
    failures: list[str] = []
    excused: list[str] = []
    checked = 0

    for vintage in _shared_vintages(cube, deck):
        period_keys: list[str] = []
        for grain in tx.GRAINS:
            for pk, _ in cube.periods(vintage, grain):
                if pk not in period_keys:
                    period_keys.append(pk)

        for label, didx, idxs in REVENUE_UNITS:
            hits: list[str] = []
            for pk in period_keys:
                live = _unit_live(cube, vintage, idxs, pk)
                want = tx.deck_value(deck, vintage, didx, pk)
                if want is None:
                    continue
                checked += 1
                if live is None:
                    hits.append(f"{pk}: live is None, deck {want:,.2f}")
                elif abs(live - want) > TOLERANCE_DOLLARS:
                    hits.append(f"{pk}: {live - want:+,.2f}")
            if not hits:
                continue
            key = (vintage, didx)
            if key in KNOWN_REALLOCATIONS:
                excused.append(
                    f"{vintage} deck{didx} ({label}): {len(hits)} cells "
                    f"[{', '.join(hits)}]"
                )
            else:
                failures.append(
                    f"{vintage} deck{didx} ({label}): {', '.join(hits)}"
                )
    return checked, failures, excused


def check_additivity(cube: tx.Cube) -> tuple[int, list[str]]:
    """NA + Eliminations + International - Total Physical Cards must be 0.

    Before 2026-09-29 this was NA(folded) + International, because North America
    carried the eliminations. Now Eliminations is its own row, so the identity is
    stated in three terms -- which is how the source rolls it up, and the reason
    splitting the row is safe.
    """
    failures: list[str] = []
    checked = 0
    na, intl, elim, phys = tx.ROWS[0], tx.ROWS[1], tx.ROWS[2], tx.ROWS[3]

    for vintage in cube.vintages:
        keys = {pk for grain in tx.GRAINS for pk, _ in cube.periods(vintage, grain)}
        for pk in sorted(keys):
            a = cube.value(vintage, na, pk)
            b = cube.value(vintage, intl, pk)
            e = cube.value(vintage, elim, pk)
            c = cube.value(vintage, phys, pk)
            if None in (a, b, e, c):
                continue
            checked += 1
            resid = a + b + e - c        # type: ignore[operator]
            if abs(resid) > 1.0:         # $1, generous against float noise
                failures.append(f"{vintage} {pk}: residual {resid:,.4f}")
    return checked, failures


def check_formatters() -> list[str]:
    """Character parity against figures read off the deck / screenshot."""
    cases: list[tuple[str, object, str]] = [
        # fmt_m -- Jul. FC total revenue and the Topps eliminations line
        ("fmt_m", tx.fmt_m(5_184_175_733.30), "$5,184"),
        ("fmt_m", tx.fmt_m(-121_464_675.93), "($121)"),
        ("fmt_m", tx.fmt_m(457_957_083.0), "$458"),
        ("fmt_m", tx.fmt_m(None), tx.EM_DASH),
        ("fmt_m", tx.fmt_m(0.0), "$0"),
        # fmt_pct -- Jul. FC total gross margin and EBITDA margin
        ("fmt_pct", tx.fmt_pct(0.5476226635245023), "55%"),
        ("fmt_pct", tx.fmt_pct(0.3821458717945473), "38%"),
        ("fmt_pct", tx.fmt_pct(None), tx.EM_DASH),
        # JS Math.round semantics: half rounds toward +Infinity, both signs.
        ("fmt_pct", tx.fmt_pct(0.005), "1%"),
        ("fmt_pct", tx.fmt_pct(-0.025), "-2%"),
        # delta_fmt -- dollar rows to percent, pct rows to bps
        ("delta_fmt", (tx.delta_fmt(142.0, 100.0, False) or {}).get("text"), "+42%"),
        ("delta_fmt", (tx.delta_fmt(142.0, 100.0, False) or {}).get("cls"), "gpos"),
        ("delta_fmt", (tx.delta_fmt(0.5476, 0.4617, True) or {}).get("text"), "+859 bps"),
        ("delta_fmt", (tx.delta_fmt(0.4617, 0.5476, True) or {}).get("text"), "-859 bps"),
        ("delta_fmt", (tx.delta_fmt(100.0, 0.0, False) or {}).get("text"), tx.EM_DASH),
        ("delta_fmt", tx.delta_fmt(100.0, 100.0, False, has_comp=False), None),
        ("delta_fmt", tx.delta_fmt(None, 100.0, False), None),
        ("delta_fmt", tx.delta_fmt(100.0, None, False), None),
    ]
    return [
        f"{name}: got {got!r}, want {want!r}"
        for name, got, want in cases
        if got != want
    ]


def check_parity() -> tuple[str, list[str]]:
    """HARD GATE: the base table reproduces the view for the three reported lines.

    queries.py reads CARDPLN_PL_BY_LOB directly because the view's INNER JOIN to
    CARDPLN_PL_ACCOUNT_LAYOUT drops ACX_Compensation. That swap is only safe
    while the two agree on everything else.
    """
    df = _fetch_sql(PARITY_SQL).set_index("src")
    failures: list[str] = []
    for col in ("n_rows", "n_cells", "total"):
        base, view = df.at["base", col], df.at["view", col]
        if base != view:
            failures.append(f"{col}: base {base!r} vs view {view!r}")
    if df.at["base", "n_rows"] != df.at["base", "n_cells"]:
        failures.append(
            f"base table is not unique per cell: {df.at['base', 'n_rows']} rows "
            f"vs {df.at['base', 'n_cells']} distinct cells -- MASTER_SQL would "
            f"double-count"
        )
    summary = (f"{df.at['base', 'n_rows']:,} rows / "
               f"{df.at['base', 'n_cells']:,} cells")
    return summary, failures


def check_compensation() -> tuple[int, list[str], list[str]]:
    """HARD GATE: COGS == its 7 mapped children + ACX_Compensation.

    SKIPPED while queries.APPLY_COMPENSATION_ADJUSTMENT is False (the default
    since 2026-09-29). This identity is the entire justification for
    transforms._apply_compensation; with the add-back disabled there is nothing
    for it to justify, and the source is free to break it without affecting a
    single displayed figure. Flip the flag back to True and this gate returns.

    When the adjustment IS applied: if the source ever stops satisfying the
    identity -- because the layout gained the missing lines, or Compensation
    moved -- then adding Compensation back becomes wrong, and this is where we
    find out.

    Violations are excused only as documented offsetting pairs: both exem and
    keylit must appear for the same period and their residuals must cancel.
    """
    if not queries.APPLY_COMPENSATION_ADJUSTMENT:
        return 0, [], []

    df = _fetch_sql(COMPOSITION_SQL)
    failures: list[str] = []
    excused: list[str] = []

    exem, keylit = queries.SEGMENTS["exem"], queries.SEGMENTS["keylit"]
    for key, grp in df.groupby(["vintage_key", "period_type", "period"], sort=True):
        vintage, ptype, period = key
        where = f"{vintage} {ptype} {period}"
        segs = dict(zip(grp["lob_segment"], grp["residual"].astype(float)))

        if key not in KNOWN_COGS_MISTAG:
            failures.append(
                f"{where}: COGS != children + Compensation for "
                + ", ".join(f"{s} ({r:+,.2f})" for s, r in sorted(segs.items()))
            )
            continue

        # Documented -- but only as a cancelling exem/keylit pair.
        if set(segs) != {exem, keylit}:
            failures.append(
                f"{where}: documented mis-tag must involve exactly ex-Emerging "
                f"and Key Litigation, got {sorted(segs)}"
            )
        elif abs(segs[exem] + segs[keylit]) > 1.0:
            failures.append(
                f"{where}: mis-tagged residuals do not cancel "
                f"({segs[exem]:+,.2f} and {segs[keylit]:+,.2f} sum to "
                f"{segs[exem] + segs[keylit]:+,.2f}) -- that is a real error, "
                f"not a mis-tag"
            )
        else:
            excused.append(f"{where}: {segs[exem]:+,.2f} / {segs[keylit]:+,.2f}")

    return len(df), failures, excused


def check_comp_additivity() -> list[str]:
    """HARD GATE: Compensation satisfies na + elim + intl == phys.

    _apply_compensation corrects all seven segments independently. That is only
    coherent -- for the folded North America row, for the exem-minus-phys
    residual, for the grand total -- if Compensation rolls up the same way every
    other line does.
    """
    df = _fetch_sql(COMP_ADDITIVITY_SQL)
    return [
        f"{r.vintage_key} {r.period_type} {r.period}: na+elim+intl-phys = "
        f"{float(r.residual):+,.2f}"
        for r in df.itertuples()
    ]


def check_row22(cube: tx.Cube, deck: dict) -> tuple[int, list[str]]:
    """TWO-WAY GATE on the one cost row that comes closest to tying.

    Row 22 (EBITDA Key Litigation Costs) ties in ROW22_TIES and differs in the
    rest. Both directions are asserted, so we hear about it either way:

      * a vintage in ROW22_TIES that stops tying is a regression -- most likely
        _apply_compensation starting to move a row it currently does not;
      * a vintage outside it that starts tying means the source improved and the
        UNRECONCILED flag on row 22 could be dropped.

    The specific risk for the first case: Key Litigation has zero Compensation at
    YEAR grain in every vintage, but 2025A carries non-zero amounts at MONTH and
    QUARTER grain (Jan +0.27M ... Jun -6.34M, summing to zero -- which is exactly
    why the annual figure is clean). So the correction can move this row
    sub-annually even where it cannot move it annually.
    """
    row = tx.ROWS[24]                # deck row 22, EBITDA Key Litigation Costs
    failures: list[str] = []
    checked = 0

    for vintage in _shared_vintages(cube, deck):
        period_keys: list[str] = []
        for grain in tx.GRAINS:
            for pk, _ in cube.periods(vintage, grain):
                if pk not in period_keys:
                    period_keys.append(pk)

        worst, where = 0.0, ""
        for pk in period_keys:
            want = tx.deck_value(deck, vintage, row.deck_idx, pk)
            if want is None:
                continue
            checked += 1
            live = cube.value(vintage, row, pk)
            if live is None:
                failures.append(f"{vintage} {pk}: live is None, deck {want:,.2f}")
                continue
            if abs(live - want) > worst:
                worst, where = abs(live - want), pk

        ties = worst <= TOLERANCE_DOLLARS
        expected = vintage in ROW22_TIES
        if expected and not ties:
            failures.append(
                f"{vintage}: row22 was tying and no longer does -- worst "
                f"{worst:,.2f} at {where}. Check _apply_compensation."
            )
        elif ties and not expected:
            failures.append(
                f"{vintage}: row22 now TIES (worst {worst:,.2f}) but is not in "
                f"ROW22_TIES. The source improved -- re-check whether row 22 "
                f"can drop its UNRECONCILED flag."
            )
    return checked, failures


def check_gap_registry() -> list[str]:
    """The registry's own invariants, so a later edit cannot drift silently."""
    problems: list[str] = []

    flagged = sorted(tx.GAPS)
    if len(flagged) != 22:
        problems.append(f"{len(flagged)} flagged rows, expected 22: {flagged}")

    if len(tx.UNRECONCILED_ROWS) != 20:
        problems.append(
            f"{len(tx.UNRECONCILED_ROWS)} unreconciled rows, expected 20"
        )

    # Every Revenue row must be reconciled; a cost row may only claim to be if it
    # is on the allowlist, and the ROW 22 gate has to back that up.
    for row in tx.ROWS:
        if row.section == "Revenue" and not row.is_reconciled:
            problems.append(f"row{row.idx} ({row.label}) is Revenue but not reconciled")
        if (row.section != "Revenue" and row.is_reconciled
                and row.idx not in RECONCILED_COST_ROWS):
            problems.append(f"row{row.idx} ({row.label}) is a cost row but reconciled")
    for idx in RECONCILED_COST_ROWS:
        if not tx.ROWS[idx].is_reconciled:
            problems.append(
                f"row{idx} is on the reconciled-cost allowlist but is flagged"
            )

    for idx, kinds in tx.GAPS.items():
        for kind in kinds:
            if kind not in tx.GAP_KINDS:
                problems.append(f"row{idx}: unknown gap kind {kind!r}")

    # A row that can never render must say why, or it renders blank unexplained.
    for row in tx.ROWS:
        if not row.is_derivable and not row.gaps:
            problems.append(f"row{row.idx} ({row.label}) cannot render and has no gap")

    # The broken-residual rows must be withheld unconditionally: a 108.5% gross
    # margin must not be reachable by flipping the diagnostic toggle.
    if tx.HIERARCHY not in tx.BLOCKING_KINDS:
        problems.append("HIERARCHY must be in BLOCKING_KINDS")
    for idx in (12, 20):
        row = tx.ROWS[idx]
        if tx.HIERARCHY not in row.gaps:
            problems.append(f"row{idx} ({row.label}) must carry HIERARCHY")
        if row.is_derivable:
            problems.append(
                f"row{idx} ({row.label}) is derivable -- the broken residual "
                f"would render"
            )
        if tx.blocking_reason(row) != tx.HIERARCHY:
            problems.append(f"row{idx} explains itself as {tx.blocking_reason(row)!r}")

    # Gross Margin Eliminations % must be withheld too: eliminations revenue is
    # negative, so the margin over it is sign-inverted and means nothing.
    if tx.SIGN not in tx.BLOCKING_KINDS:
        problems.append("SIGN must be in BLOCKING_KINDS")
    elim_gm = tx.ROWS[10]
    if tx.SIGN not in elim_gm.gaps:
        problems.append(f"row10 ({elim_gm.label} %) must carry SIGN")
    if elim_gm.is_derivable:
        problems.append(
            "row10 (Gross Margin Eliminations %) is derivable -- a margin over "
            "negative revenue would render"
        )
    if tx.blocking_reason(elim_gm) != tx.SIGN:
        problems.append(
            f"row10 explains itself as {tx.blocking_reason(elim_gm)!r}"
        )

    return problems


def main() -> None:
    if not DECK_JSON.exists():
        raise SystemExit("run tools/extract_deck.py first")
    import json

    deck = json.loads(DECK_JSON.read_text(encoding="utf-8"))

    print(f"connection: {CONN_NAME}")
    df = fetch()
    cube = tx.build_cube(df)
    print(f"fetched {len(df):,} rows / {len(cube.vintages)} vintages: "
          f"{', '.join(cube.vintages)}")

    failed = False

    fmt_problems = check_formatters()
    print(f"\nFORMATTERS  {'FAIL' if fmt_problems else 'pass'}")
    for p in fmt_problems:
        print(f"  {p}")
    failed |= bool(fmt_problems)

    gap_problems = check_gap_registry()
    print(f"GAP REGISTRY {'FAIL' if gap_problems else 'pass'}"
          f"  ({len(tx.GAPS)} flagged, {len(tx.UNRECONCILED_ROWS)} unreconciled)")
    for p in gap_problems:
        print(f"  {p}")
    failed |= bool(gap_problems)

    summary, parity_problems = check_parity()
    print(f"BASE vs VIEW {'FAIL' if parity_problems else 'pass'}  ({summary})")
    for p in parity_problems:
        print(f"  {p}")
    failed |= bool(parity_problems)

    n, comp_problems, comp_excused = check_compensation()
    if not queries.APPLY_COMPENSATION_ADJUSTMENT:
        print("COMPENSATION pass  (compensation adjustment disabled - skipped)")
    else:
        print(f"COMPENSATION {'FAIL' if comp_problems else 'pass'}"
              f"  ({n} cell(s) breaking COGS == children + Compensation)")
        for p in comp_problems[:20]:
            print(f"  {p}")
    failed |= bool(comp_problems)

    add_comp_problems = check_comp_additivity()
    print(f"COMP ADDITIV {'FAIL' if add_comp_problems else 'pass'}")
    for p in add_comp_problems[:20]:
        print(f"  {p}")
    failed |= bool(add_comp_problems)

    n, row22_problems = check_row22(cube, deck)
    print(f"ROW 22       {'FAIL' if row22_problems else 'pass'}  ({n:,} cells, "
          f"all grains)")
    for p in row22_problems[:20]:
        print(f"  {p}")
    failed |= bool(row22_problems)

    n, add_problems = check_additivity(cube)
    print(f"ADDITIVITY  {'FAIL' if add_problems else 'pass'}  ({n:,} cells)")
    for p in add_problems[:20]:
        print(f"  {p}")
    failed |= bool(add_problems)

    n, ann_problems, ann_notes = check_revenue_annual(cube, deck)
    print(f"REV ANNUAL  {'FAIL' if ann_problems else 'pass'}  ({n:,} row-years)")
    for p in ann_problems:
        print(f"  {p}")
    for p in ann_notes:
        print(f"  note: {p}")
    failed |= bool(ann_problems)

    n, realloc_problems = check_revenue_reallocation(cube, deck)
    print(f"REALLOCATION {'FAIL' if realloc_problems else 'pass'}  ({n:,} row-grains)")
    for p in realloc_problems:
        print(f"  {p}")
    failed |= bool(realloc_problems)

    n, cell_problems, excused = check_revenue_cells(cube, deck)
    print(f"REV CELLS   {'FAIL' if cell_problems else 'pass'}  ({n:,} cells vs deck)")
    for p in cell_problems[:20]:
        print(f"  {p}")
    if len(cell_problems) > 20:
        print(f"  ... and {len(cell_problems) - 20} more")
    failed |= bool(cell_problems)

    if excused:
        print(f"\n  {len(excused)} documented reallocation(s), annual unaffected:")
        for e in excused:
            print(f"    {e}")
            print(f"      why: {KNOWN_REALLOCATIONS[_key_of(e)]}")

    if comp_excused:
        print(f"\n  {len(comp_excused)} documented COGS mis-tag pair(s), "
              f"company total unaffected:")
        for e in comp_excused:
            print(f"    {e}")
        print(f"      why: {_MISTAG_NOTE}")

    print("\n" + ("FAILED" if failed else "ALL GATES PASS"))
    raise SystemExit(1 if failed else 0)


def _key_of(excused_line: str) -> tuple[str, int]:
    """Recover the (vintage, deck_idx) key from an excused-line string."""
    vintage, rest = excused_line.split(" deck", 1)
    return vintage, int(rest.split(" ", 1)[0].rstrip(":"))


if __name__ == "__main__":
    main()
