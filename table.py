"""Build the statement grid and the KPI tiles as HTML.

The grid is a two-tier header over up to 42 columns (12 months + YTD + FY, x
comparison + current + change), which is why the label column is sticky -- and
opaque, so figures scrolled under it do not show through -- and the whole table
lives in a horizontal scroller. Structure is ported from the deck's
renderHead()/renderBody() (source JS lines 322-397) so the CSS in style.py --
also ported -- lands on the same elements.

The grid HTML is handed to interactive.py, which mounts it inside a Component v2
shadow DOM. The tiles are ordinary page markup.
"""
from __future__ import annotations

import html
from typing import Mapping, Sequence

import transforms as tx

CARET_OPEN = "&#9660;"      # ▼
CARET_CLOSED = "&#9654;"    # ▶
ACT_TIP = "Actual in both vintages: no change"
MODE_TIP = "Show the change as a % or as $M. Margin rows are always in bps."

_ROW_CLASS = {
    "margin": "row-margin",
    "total": "row-total",
    "subtotal": "row-subtotal",
    "sub": "row-sub",
}


def _esc(s: object) -> str:
    return html.escape(str(s), quote=True)


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
def _mode_toggle(delta_mode: str, enabled: bool) -> str:
    """The % / $ switch that sits in the change block's header.

    Clicks are picked up by interactive._JS (a 'mode' trigger), so the buttons
    only do anything inside the component. On the static fallback they render
    disabled rather than looking clickable and doing nothing.
    """
    disabled = "" if enabled else " disabled"
    buttons = []
    for mode in tx.DELTA_MODES:
        on = ' class="on"' if mode == delta_mode else ""
        buttons.append(
            f'<button type="button" data-mode="{mode}"{on}{disabled}>'
            f"{_esc(tx.DELTA_MODE_LABELS[mode])}</button>"
        )
    return f'<span class="dmode" title="{_esc(MODE_TIP)}">{"".join(buttons)}</span>'


def _head(
    periods: Sequence[tuple[str, str]],
    forecast: str,
    comp: str,
    dimmed: Sequence[bool],
    delta_mode: str,
    toggle_enabled: bool,
) -> str:
    n = len(periods)
    # The label column header spans both tiers (the deck renders its text
    # transparent, so it reads as a solid block).
    r1 = ['<tr class="group-row"><th class="lbl-th" rowspan="2">Line Item</th>']
    if comp:
        r1.append(f'<th class="grp-comp" colspan="{n}">{_esc(tx.vintage_label(comp))}</th>')
        r1.append(f'<th class="grp-curr" colspan="{n}">{_esc(tx.vintage_label(forecast))}</th>')
        r1.append(
            f'<th class="grp-growth" colspan="{n}">{_esc(tx.change_label(comp))}'
            f"{_mode_toggle(delta_mode, toggle_enabled)}</th>"
        )
    else:
        r1.append(f'<th class="grp-solo" colspan="{n}">{_esc(tx.vintage_label(forecast))}</th>')
    r1.append("</tr>")

    def tier(cls: str, dim: Sequence[bool] = ()) -> str:
        cells = []
        for i, (pk, label) in enumerate(periods):
            extra = " pf" if i == 0 else ""
            if pk == tx.ANNUAL:
                extra += " fy-col"
            elif tx.is_ytd(pk):
                extra += " ytd-col"
            if dim and dim[i]:
                extra += " ph-act"
            cells.append(f'<th class="{cls}{extra}">{_esc(label)}</th>')
        return "".join(cells)

    r2 = ['<tr class="period-row">']
    if comp:
        r2.append(tier("ph-comp"))
        r2.append(tier("ph-curr"))
        r2.append(tier("ph-growth", dimmed))
    else:
        r2.append(tier("ph-solo"))
    r2.append("</tr>")

    return f"<thead>{''.join(r1)}{''.join(r2)}</thead>"


# ---------------------------------------------------------------------------
# Body
# ---------------------------------------------------------------------------
def _body(
    cube: tx.Cube,
    periods: Sequence[tuple[str, str]],
    *,
    forecast: str,
    comp: str,
    collapsed: Mapping[str, bool],
    dimmed: Sequence[bool],
    delta_mode: str,
) -> str:
    n = len(periods)
    total_cols = 1 + n * (3 if comp else 1)
    out: list[str] = ["<tbody>"]
    current_section: str | None = None

    for row in tx.ROWS:
        section = row.section

        if section != current_section:
            current_section = section
            if section in tx.SECTIONS_WITH_HEADER:
                caret = CARET_CLOSED if collapsed.get(section) else CARET_OPEN
                # The name sits in its own sticky label cell, with a filler
                # spanning the rest. A single cell spanning the full width is
                # as wide as the scroll area, so `sticky` has no room to pin it
                # and the section name scrolled away with the figures.
                out.append(
                    f'<tr class="section-hdr" data-sec="{_esc(section)}">'
                    f'<td class="lbl">'
                    f'<span class="sarr">{caret}</span>{_esc(section)}</td>'
                    f'<td class="sec-fill" colspan="{total_cols - 1}"></td></tr>'
                )

        # Only detail rows collapse; subtotals and totals stay visible, as in
        # the deck. Rendered with the class rather than skipped so the ported
        # `tr.collapsed{display:none}` rule stays the single control.
        hidden = bool(collapsed.get(section)) and row.row_type == "sub"
        # The only rows that show dashes rather than figures are the four the
        # source cannot express: 19/23 have no expression, 10/18 have one over a
        # residual the source has broken. See ISSUES.md section 4.
        placeholder = not row.is_derivable

        classes = [_ROW_CLASS[row.row_type]]
        if hidden:
            classes.append("collapsed")
        if placeholder:
            classes.append("gap-row")

        out.append(f'<tr class="{" ".join(classes)}" data-sec="{_esc(section)}">')
        tip = tx.ROW_TOOLTIPS.get((row.section, row.label))
        title = f' title="{_esc(tip)}"' if tip else ""
        out.append(f'<td class="lbl"{title}>{_esc(row.label)}</td>')

        fmt = tx.fmt_pct if row.is_pct else tx.fmt_m

        def cells(vintage: str, cls: str) -> None:
            for i, (pk, _) in enumerate(periods):
                pf = " pf" if i == 0 else ""
                text = tx.EM_DASH if placeholder else fmt(cube.value(vintage, row, pk))
                out.append(f'<td class="{cls}{pf}">{text}</td>')

        if comp:
            cells(comp, "comp-cell")
        cells(forecast, "curr-cell")

        if comp:
            for i, (pk, _) in enumerate(periods):
                pf = " pf" if i == 0 else ""
                if placeholder:
                    out.append(f'<td class="gc gflat{pf}">{tx.EM_DASH}</td>')
                    continue
                if dimmed[i]:
                    out.append(
                        f'<td class="gc gact{pf}" title="{ACT_TIP}">{tx.EM_DASH}</td>'
                    )
                    continue
                delta = tx.delta_fmt(
                    cube.value(forecast, row, pk),
                    cube.value(comp, row, pk),
                    row.is_pct,
                    mode=delta_mode,
                )
                if delta is None:
                    out.append(f'<td class="gc gflat{pf}">{tx.EM_DASH}</td>')
                else:
                    out.append(
                        f'<td class="gc {delta["cls"]}{pf}">{_esc(delta["text"])}</td>'
                    )

        out.append("</tr>")

    out.append("</tbody>")
    return "".join(out)


def build_statement(
    cube: tx.Cube,
    *,
    forecast: str,
    comp: str,
    grain: str,
    collapsed: Mapping[str, bool],
    delta_mode: str = "pct",
    toggle_enabled: bool = True,
) -> str:
    """The full statement table, ready to mount in the component.

    Period columns come from the SELECTED FORECAST vintage, as in the deck --
    the comparison is read with those same period keys, so a comparison vintage
    covering fewer periods simply yields em-dashes in the columns it lacks
    rather than reshaping the grid, and its YTD is summed over the forecast's
    months. export.py reads the same periods, so a download matches the grid.

    A change column is greyed where both vintages hold that period as the same
    year's actuals (Cube.same_actuals): the change is zero by construction.

    With a comparison, the change header carries the % / $ toggle; pass
    ``toggle_enabled=False`` when the grid will render static (no component to
    receive the click).
    """
    periods = cube.periods(forecast, grain)
    dimmed = [bool(comp) and cube.same_actuals(forecast, comp, pk) for pk, _ in periods]
    head = _head(periods, forecast, comp, dimmed, delta_mode, toggle_enabled)
    body = _body(
        cube, periods,
        forecast=forecast, comp=comp, collapsed=collapsed,
        dimmed=dimmed, delta_mode=delta_mode,
    )
    return f'<div class="table-wrap"><table>{head}{body}</table></div>'


# ---------------------------------------------------------------------------
# KPI tiles
# ---------------------------------------------------------------------------
_TILES: tuple[tuple[str, int], ...] = (
    ("Total Revenue", 6),
    ("Total EBITDA", 24),
    ("EBITDA Margin", 25),
)


def build_tiles(
    cube: tx.Cube, *, forecast: str, comp: str, delta_mode: str = "pct"
) -> str:
    """The three headline tiles, on the annual figure.

    Total EBITDA and EBITDA Margin come from a cost basis that is corrected for
    the source's Compensation double-count but is still short in actual months.
    They show that figure anyway; ISSUES.md records by how much it misses. The
    muted branch below is for a tile whose row cannot be derived at all -- none
    of the current three, but _TILES is meant to be editable.
    """
    out = ['<div class="tiles-row">']
    for label, idx in _TILES:
        row = tx.ROWS[idx]
        placeholder = not row.is_derivable

        value = cube.value(forecast, row, tx.ANNUAL)
        if placeholder:
            val_html = f'<div class="tile-val muted">{tx.EM_DASH}</div>'
        elif row.is_pct:
            val_html = f'<div class="tile-val">{tx.fmt_pct(value)}</div>'
        else:
            val_html = f'<div class="tile-val">{tx.fmt_tile(value)}</div>'

        delta_html = '<div class="tile-delta"></div>'
        if comp and not placeholder:
            delta = tx.delta_fmt(value, cube.value(comp, row, tx.ANNUAL), row.is_pct,
                                 mode=delta_mode, usd_suffix="M")
            if delta:
                cls = ("pos" if delta["cls"] == "gpos"
                       else "neg" if delta["cls"] == "gneg" else "")
                delta_html = (
                    f'<div class="tile-delta {cls}">vs. {_esc(tx.vintage_label(comp))}: '
                    f'{_esc(delta["text"])}</div>'
                )

        out.append(
            f'<div class="tile">'
            f'<div class="tile-lbl">{_esc(label)}</div>'
            f"{val_html}{delta_html}</div>"
        )
    out.append("</div>")
    return "".join(out)
