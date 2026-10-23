"""The BU P&L pages: North America, International, Digital and Fanatics Collect.

One draft layout for all four, read from the same cube as the consolidated
page -- the BU lines ride in STG_SQL (queries.BU_LINES), so there is one pull
and one cache, and a BU page's Net Revenue, Gross Margin and EBITDA are the
consolidated page's own lines under the consolidated page's own LOB terms
(queries.BU_DEFS). They tie to rows 0/1/3/5, 7/8/10/12 and 14/15/18/21 by
construction; tools/validate_bu.py guards the wiring.

    Revenue              Net Revenue (+ NA: Topps eliminations memo, and the
                         folded figure that is consolidated row 0)
    Cost of Goods Sold   five buckets and Total COGS, each % of Net Revenue
    Gross Margin         $ and %
    Operating Expenses   Marketing and SG&A ex Marketing, $ and % of Net Revenue
    EBITDA               $ and margin

STG only. LEGACY has no account detail, so under PNL_SOURCE=LEGACY nothing here
is offered (AVAILABLE) and the app registers no BU pages.
"""
from __future__ import annotations

from typing import Callable, Mapping

import queries
import table
import transforms as tx

#: False under LEGACY: no BU pages, no drill links, no fallback links.
AVAILABLE: bool = queries.SOURCE == "STG"

BU_KEYS: tuple[str, ...] = ("na", "intl", "digital", "collect")
BU_NAMES: dict[str, str] = {
    "na": "North America",
    "intl": "International",
    "digital": "Digital",
    "collect": "Fanatics Collect",
}
#: st.navigation url_path per page, so /north-america deep-links.
URL_PATHS: dict[str, str] = {
    "na": "north-america",
    "intl": "international",
    "digital": "digital",
    "collect": "collect",
}

assert set(queries.BU_DEFS) == set(BU_KEYS), "queries.BU_DEFS and BU_KEYS disagree"
assert set(table.DRILL.values()) == set(BU_KEYS), "table.DRILL names an unknown BU"

SECTIONS: tuple[str, ...] = ("Revenue", "Cost of Goods Sold", "Gross Margin",
                             "Operating Expenses", "EBITDA")
#: The EBITDA Margin row is a 'margin' row, as on the consolidated page, so it
#: stays visible when EBITDA collapses. Every section has a header.
SECTIONS_WITH_HEADER: tuple[str, ...] = SECTIONS

PCT_OF_REV = "% of Net Revenue"

#: The COGS buckets, in display order: (cube line, label).
_BUCKETS: tuple[tuple[str, str], ...] = (
    ("std_mfg", "Standard Manufacturing"),
    ("roy",     "Royalties"),
    ("mg",      "MG Shortfalls"),
    ("autos",   "Autos & Relics"),
    ("other",   "Other"),
)

#: Structural zeros: buckets a BU has no business carrying. Omitted from its
#: page -- unless the loaded cube says otherwise (see rows()).
#:
#: MG Shortfall was drafted as a structural zero for Digital and Collect too,
#: but the source carries it (2026-10-22: LB_305 $4.5M in 2025 Actuals, $0.4M
#: in Sep 2026 FC; LB_306 $0.85M in 2025 Actuals), so both pages list it.
BU_OMIT: dict[str, frozenset[str]] = {
    "na":      frozenset(),
    "intl":    frozenset(),
    "digital": frozenset({"autos"}),
    "collect": frozenset({"autos"}),
}

#: Which LOBs a BU is, for its Net Revenue hover.
_BASIS: dict[str, str] = {
    "na": ("North America ex Topps eliminations: Physical Collectibles - Domestic "
           "(LB_302) + Manufacturing & Packaging / GCP (LB_304) + GCP "
           "eliminations (LB_394)"),
    "intl": ("Physical Collectibles - International (LB_303) + International "
             "eliminations (LB_392 @ ICP_32002)"),
    "digital": "Digital Collectibles - Domestic (LB_305)",
    "collect": "Fanatics Live (LB_306) + Marketplace / PWCC (LB_307)",
}

_BUCKET_TIPS: dict[str, str] = {
    "Standard Manufacturing": ("ACX_Manufacturing, plus any COGS reported only "
                               "as the parent (GCP eliminations, LB_394)"),
    "Royalties": "ACX_Royalties",
    "MG Shortfalls": "ACX_MG Shortfall",
    "Autos & Relics": "ACX_Autos & Relics",
    "Other": "Freight + Product Development + Obsolescence + Compensation",
    "Total COGS": "The cost of goods sold that Gross Margin is computed from",
}


def _expr(terms: tuple[tuple[int, str], ...]) -> Callable[[tx.Segs], float]:
    return lambda s: sum(sign * s[key] for sign, key in terms)


def _nonzero(cube: tx.Cube, line: str, terms: tuple[tuple[int, str], ...]) -> bool:
    """True when ``line`` under ``terms`` is non-zero in any loaded cell."""
    expr = _expr(terms)
    return any(abs(expr(segs)) >= 0.5 for (_, ln, _), segs in cube.segs.items()
               if ln == line)


def shown_buckets(bu: str, cube: tx.Cube | None) -> list[tuple[str, str]]:
    """The buckets a BU's page lists.

    An omitted bucket comes back the moment the cube carries an amount for it:
    dropping it then would make the buckets on screen stop summing to Total
    COGS, silently. tools/validate_bu.py separately fails while any omitted
    bucket is non-zero, so the config gets fixed rather than relied on.
    """
    terms = queries.BU_DEFS[bu]
    return [(line, label) for line, label in _BUCKETS
            if line not in BU_OMIT[bu]
            or (cube is not None and _nonzero(cube, line, terms))]


def rows(bu: str, cube: tx.Cube | None = None) -> tuple[tx.Row, ...]:
    """The BU page's statement rows. ``cube`` drives the BU_OMIT guard."""
    terms = queries.BU_DEFS[bu]
    name = BU_NAMES[bu]
    expr = _expr(terms)
    spec: list[tuple] = []     # (section, label, row_type, is_pct, num, den, expr, cost)

    def add(section, label, row_type, num, *, pct=False, cost=False, e=expr):
        spec.append((section, label, row_type, pct, num,
                     "net_revenue" if pct else None, e, cost))

    add("Revenue", "Net Revenue", "subtotal", "net_revenue")
    if bu == "na":
        add("Revenue", "Topps eliminations", "sub", "net_revenue",
            e=_expr(queries.BU_NA_TOPPS))
        add("Revenue", "North America incl. eliminations", "sub", "net_revenue",
            e=_expr(queries.BU_NA_INCL_ELIMS))
    for line, label in shown_buckets(bu, cube):
        add("Cost of Goods Sold", label, "ratio", line, pct=True, cost=True)
    add("Cost of Goods Sold", "Total COGS", "subtotal", "cogs", pct=True, cost=True)
    add("Gross Margin", "Gross Margin", "subtotal", "gross_margin")
    add("Gross Margin", "Gross Margin %", "ratio", "gross_margin", pct=True)
    add("Operating Expenses", "Marketing", "sub", "mkt", cost=True)
    add("Operating Expenses", PCT_OF_REV, "ratio", "mkt", pct=True, cost=True)
    add("Operating Expenses", "SG&A", "sub", "sga", cost=True)
    add("Operating Expenses", PCT_OF_REV, "ratio", "sga", pct=True, cost=True)
    add("EBITDA", "EBITDA", "total", "ebitda")
    add("EBITDA", "EBITDA Margin", "margin", "ebitda", pct=True)

    return tuple(
        tx.Row(i, section, label, f"{name} \u2014 {label}", row_type, pct, num, den,
               e, cost)
        for i, (section, label, row_type, pct, num, den, e, cost) in enumerate(spec)
    )


def tooltips(bu: str) -> Mapping[tuple[str, str], str]:
    """Hover text on the BU page's labels, keyed (section, label)."""
    sga = "SG&A excluding Marketing"
    if bu == "na":
        sga += ("; also excludes the NASE Key Litigation cost, which the "
                "consolidated page shows under Key Litigation Costs")
    tips: dict[tuple[str, str], str] = {
        ("Revenue", "Net Revenue"): _BASIS[bu],
        ("Operating Expenses", "Marketing"): "Marketing (AC_60001)",
        ("Operating Expenses", "SG&A"): sga,
        ("Operating Expenses", PCT_OF_REV): f"As a share of {BU_NAMES[bu]} Net Revenue",
        ("EBITDA", "EBITDA"): f"Equals the consolidated EBITDA {BU_NAMES[bu]} row",
        **{("Cost of Goods Sold", label): f"{label}: {tip} -- as % of Net Revenue"
           for label, tip in _BUCKET_TIPS.items()},
    }
    if bu == "na":
        tips[("Revenue", "Topps eliminations")] = (
            "In consolidated North America revenue, but outside the North "
            "America Gross Margin and EBITDA basis")
        tips[("Revenue", "North America incl. eliminations")] = (
            "Equals the consolidated Revenue North America row")
    return tips


#: The tiles, by row label.
_TILE_LABELS: tuple[tuple[str, str], ...] = (
    ("Net Revenue", "Net Revenue"),
    ("Gross Margin %", "Gross Margin %"),
    ("EBITDA", "EBITDA"),
    ("EBITDA Margin", "EBITDA Margin"),
)


def tiles(bu_rows: tuple[tx.Row, ...]) -> list[tuple[str, tx.Row]]:
    """(label, Row) pairs for table.build_tiles. Format with tx.fmt_tile_m."""
    by_label = {r.label: r for r in bu_rows}
    return [(tile, by_label[label]) for tile, label in _TILE_LABELS]


def subject(bu: str) -> str:
    """Page title and download subject: 'North America P&L'."""
    return f"{BU_NAMES[bu]} P&L"
