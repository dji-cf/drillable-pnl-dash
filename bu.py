"""The BU P&L pages: North America, International, Digital and Fanatics Collect.

One draft layout for all four, read from the same cube as the consolidated
page -- the BU lines ride in STG_SQL (queries.BU_LINES), so there is one pull
and one cache, and a BU page's Net Revenue, Gross Margin and EBITDA are the
consolidated page's own lines under the consolidated page's own LOB terms
(queries.BU_DEFS). They tie to rows 0/1/3/5, 7/8/10/12 and 14/15/18/21 by
construction; tools/validate_bu.py guards the wiring.

    Revenue              Net Revenue
    Cost of Goods Sold   Total COGS $, then five buckets as % of Net Revenue
    Gross Margin         $ and %
    Operating Expenses   Marketing and SG&A ex Marketing, $ and % of Net Revenue
    EBITDA               $ and margin

North America has its own layout (_na_spec): every $ line as NASE (LB_302,
James's "North America Excl GCP" slide), then GCP (LB_304 + LB_394), then the
NA total that ties to the consolidated rows; every % over Net Sales (incl.
Topps eliminations), as on the slide. See queries.BU_NA_NASE.

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
PCT_OF_NET_SALES = "% of Net Sales"

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
#: Autos & Relics likewise for Digital: the 2026-10-23 load put $0.067M on
#: LB_305 in Sep 2026 Actuals (so Oct 2026 FC), plus FY23/FY24 crumbs.
BU_OMIT: dict[str, frozenset[str]] = {
    "na":      frozenset(),
    "intl":    frozenset(),
    "digital": frozenset(),
    "collect": frozenset({"autos"}),
}

#: Which LOBs a BU is, for its Net Revenue hover. North America's own rows
#: carry their LOBs in _na_tooltips.
_BASIS: dict[str, str] = {
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


def bucket_terms(bu: str) -> tuple[tuple[int, str], ...]:
    """The terms a BU's COGS buckets are over: NASE alone for North America."""
    return queries.BU_NA_NASE if bu == "na" else queries.BU_DEFS[bu]


def shown_buckets(bu: str, cube: tx.Cube | None) -> list[tuple[str, str]]:
    """The buckets a BU's page lists.

    An omitted bucket comes back the moment the cube carries an amount for it:
    dropping it then would make the buckets on screen stop summing to Total
    COGS, silently. tools/validate_bu.py separately fails while any omitted
    bucket is non-zero, so the config gets fixed rather than relied on.
    """
    terms = bucket_terms(bu)
    return [(line, label) for line, label in _BUCKETS
            if line not in BU_OMIT[bu]
            or (cube is not None and _nonzero(cube, line, terms))]


#: North America's row labels (James's slide wording). Validators and tiles
#: look rows up by these.
NA_GROSS_REV = "Gross Revenue (NASE)"
NA_TOPPS = "Topps eliminations"
NA_NASE_NET_SALES = "Net Sales (NASE)"
NA_GCP_REV = "GCP (net of eliminations)"
NA_NET_SALES = "Net Sales"
NA_NASE_COGS = "COGS (NASE)"
NA_GCP = "GCP"
NA_GCP_SGA = "GCP SG&A"
NA_TOTAL_COGS = "Total COGS"
NA_NASE_GP = "Gross Profit (NASE)"
NA_GP = "Gross Profit"
NA_GP_PCT = "Gross Profit %"
NA_NASE_SGA = "SG&A (NASE)"
NA_NASE_EBITDA = "EBITDA (NASE)"
NA_NASE_MARGIN = "EBITDA Margin (NASE)"


def _na_spec(add, cube: tx.Cube | None) -> None:
    """North America: NASE, then GCP, then the NA total, on every $ line.

    NASE % rows are over NASE Net Sales (the slide's denominator); NA-total %
    rows over NA Net Sales, i.e. consolidated row 0. Marketing has no GCP line:
    GCP carries none, which tools/validate_bu.py gates.
    """
    nase, gcp = _expr(queries.BU_NA_NASE), _expr(queries.BU_NA_GCP)
    nase_ns = _expr(queries.BU_NA_NASE_NET_SALES)
    na_ns = _expr(queries.BU_NA_INCL_ELIMS)

    add("Revenue", NA_GROSS_REV, "sub", "net_revenue", e=nase)
    add("Revenue", NA_TOPPS, "sub", "net_revenue", e=_expr(queries.BU_NA_TOPPS))
    add("Revenue", NA_NASE_NET_SALES, "sub", "net_revenue", e=nase_ns)
    add("Revenue", NA_GCP_REV, "sub", "net_revenue", e=gcp)
    add("Revenue", NA_NET_SALES, "subtotal", "net_revenue", e=na_ns)

    add("Cost of Goods Sold", NA_NASE_COGS, "sub", "cogs", cost=True, e=nase)
    for line, label in shown_buckets("na", cube):
        add("Cost of Goods Sold", label, "ratio", line, pct=True, cost=True,
            e=nase, d=nase_ns)
    add("Cost of Goods Sold", NA_GCP, "sub", "cogs", cost=True, e=gcp)
    add("Cost of Goods Sold", NA_TOTAL_COGS, "subtotal", "cogs", cost=True)

    add("Gross Margin", NA_NASE_GP, "sub", "gross_margin", e=nase)
    add("Gross Margin", NA_GCP, "sub", "gross_margin", e=gcp)
    add("Gross Margin", NA_GP, "subtotal", "gross_margin")
    add("Gross Margin", NA_GP_PCT, "ratio", "gross_margin", pct=True, d=na_ns)

    add("Operating Expenses", "Marketing", "sub", "mkt", cost=True)
    add("Operating Expenses", PCT_OF_NET_SALES, "ratio", "mkt", pct=True, cost=True,
        d=na_ns)
    add("Operating Expenses", NA_NASE_SGA, "sub", "sga", cost=True, e=nase)
    add("Operating Expenses", PCT_OF_NET_SALES, "ratio", "sga", pct=True, cost=True,
        e=nase, d=nase_ns)
    add("Operating Expenses", NA_GCP_SGA, "sub", "sga", cost=True, e=gcp)
    add("Operating Expenses", "SG&A", "sub", "sga", cost=True)

    add("EBITDA", NA_NASE_EBITDA, "sub", "ebitda", e=nase)
    add("EBITDA", NA_NASE_MARGIN, "ratio", "ebitda", pct=True, e=nase, d=nase_ns)
    add("EBITDA", NA_GCP, "sub", "ebitda", e=gcp)
    add("EBITDA", "EBITDA", "total", "ebitda")
    add("EBITDA", "EBITDA Margin", "margin", "ebitda", pct=True, d=na_ns)


def rows(bu: str, cube: tx.Cube | None = None) -> tuple[tx.Row, ...]:
    """The BU page's statement rows. ``cube`` drives the BU_OMIT guard."""
    terms = queries.BU_DEFS[bu]
    name = BU_NAMES[bu]
    expr = _expr(terms)
    spec: list[tuple] = []  # (section, label, row_type, is_pct, num, den, expr, cost, den_expr)

    def add(section, label, row_type, num, *, pct=False, cost=False, e=expr, d=None):
        spec.append((section, label, row_type, pct, num,
                     "net_revenue" if pct else None, e, cost, d))

    if bu == "na":
        _na_spec(add, cube)
    else:
        add("Revenue", "Net Revenue", "subtotal", "net_revenue")
        add("Cost of Goods Sold", "Total COGS", "subtotal", "cogs", cost=True)
        for line, label in shown_buckets(bu, cube):
            add("Cost of Goods Sold", label, "ratio", line, pct=True, cost=True)
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
               e, cost, d)
        for i, (section, label, row_type, pct, num, den, e, cost, d) in enumerate(spec)
    )


def _na_tooltips() -> dict[tuple[str, str], str]:
    nase = "NASE: Physical Collectibles - Domestic (LB_302), excl. GCP"
    gcp = ("GCP: GC Packaging, the card printer -- LB_304 gross plus LB_394, "
           "which eliminates its sales to Topps")
    ns = "Net Sales (incl. Topps eliminations)"
    keylit = ("Excludes the NASE Key Litigation cost, which the consolidated page "
              "shows under Key Litigation Costs")
    tips = {
        ("Revenue", NA_GROSS_REV): nase,
        ("Revenue", NA_TOPPS): "Topps eliminations (Total - Topps Eliminations)",
        ("Revenue", NA_NASE_NET_SALES): "NASE gross revenue less the Topps eliminations",
        ("Revenue", NA_GCP_REV): gcp + ". Nets to about zero on revenue",
        ("Revenue", NA_NET_SALES): ("NASE + GCP, incl. Topps eliminations. Equals the "
                                    "consolidated Revenue North America row"),
        ("Cost of Goods Sold", NA_NASE_COGS): nase,
        ("Cost of Goods Sold", NA_GCP): gcp,
        ("Cost of Goods Sold", NA_TOTAL_COGS): "NASE + GCP: the COGS Gross Profit is computed from",
        ("Gross Margin", NA_NASE_GP): nase,
        ("Gross Margin", NA_GCP): gcp,
        ("Gross Margin", NA_GP): "NASE + GCP",
        ("Gross Margin", NA_GP_PCT): (
            f"Gross Profit over {ns}. The consolidated North America Gross Margin % "
            "is over revenue ex Topps eliminations, so it reads lower"),
        ("Operating Expenses", "Marketing"): "Marketing (AC_60001). GCP carries none",
        ("Operating Expenses", PCT_OF_NET_SALES): f"As a share of {ns}",
        ("Operating Expenses", NA_NASE_SGA): f"{nase}. SG&A excluding Marketing. {keylit}",
        ("Operating Expenses", NA_GCP_SGA): gcp,
        ("Operating Expenses", "SG&A"): f"NASE + GCP. SG&A excluding Marketing. {keylit}",
        ("EBITDA", NA_NASE_EBITDA): nase + " -- James's North America Excl GCP basis",
        ("EBITDA", NA_NASE_MARGIN): f"EBITDA (NASE) over NASE {ns}",
        ("EBITDA", NA_GCP): gcp,
        ("EBITDA", "EBITDA"): "NASE + GCP. Equals the consolidated EBITDA North America row",
        ("EBITDA", "EBITDA Margin"): f"EBITDA over {ns}",
    }
    tips.update({("Cost of Goods Sold", label): f"{label}: {tip} -- NASE, as % of NASE {ns}"
                 for label, tip in _BUCKET_TIPS.items() if label != "Total COGS"})
    tips[("Cost of Goods Sold", "Standard Manufacturing")] = (
        f"Standard Manufacturing: ACX_Manufacturing -- NASE, as % of NASE {ns}")
    return tips


def tooltips(bu: str) -> Mapping[tuple[str, str], str]:
    """Hover text on the BU page's labels, keyed (section, label)."""
    if bu == "na":
        return _na_tooltips()
    sga = "SG&A excluding Marketing"
    tips: dict[tuple[str, str], str] = {
        ("Revenue", "Net Revenue"): _BASIS[bu],
        ("Operating Expenses", "Marketing"): "Marketing (AC_60001)",
        ("Operating Expenses", "SG&A"): sga,
        ("Operating Expenses", PCT_OF_REV): f"As a share of {BU_NAMES[bu]} Net Revenue",
        ("EBITDA", "EBITDA"): f"Equals the consolidated EBITDA {BU_NAMES[bu]} row",
        **{("Cost of Goods Sold", label): f"{label}: {tip} -- as % of Net Revenue"
           for label, tip in _BUCKET_TIPS.items()},
    }
    tips[("Cost of Goods Sold", "Total COGS")] = _BUCKET_TIPS["Total COGS"]
    return tips


#: The tiles, by row label: (tile title, row label).
_TILE_LABELS: tuple[tuple[str, str], ...] = (
    ("Net Revenue", "Net Revenue"),
    ("Gross Margin %", "Gross Margin %"),
    ("EBITDA", "EBITDA"),
    ("EBITDA Margin", "EBITDA Margin"),
)
#: North America's: the NA totals, under the slide's names.
_NA_TILE_LABELS: tuple[tuple[str, str], ...] = (
    ("Net Sales", NA_NET_SALES),
    ("Gross Profit %", NA_GP_PCT),
    ("EBITDA", "EBITDA"),
    ("EBITDA Margin", "EBITDA Margin"),
)


def tiles(bu_rows: tuple[tx.Row, ...]) -> list[tuple[str, tx.Row]]:
    """(label, Row) pairs for table.build_tiles. Format with tx.fmt_tile_m."""
    by_label = {r.label: r for r in bu_rows}
    labels = _NA_TILE_LABELS if NA_NET_SALES in by_label else _TILE_LABELS
    return [(tile, by_label[label]) for tile, label in labels]


def subject(bu: str) -> str:
    """Page title and download subject: 'North America P&L'."""
    return f"{BU_NAMES[bu]} P&L"
