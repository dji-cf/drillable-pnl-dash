"""Excel and CSV downloads of the statement, exactly as the grid lays it out.

Same columns as table.build_statement -- both read cube.periods(forecast,
grain), so the comparison | current | change blocks, the YTD column and the
greyed same-actuals cells line up one for one -- but carrying RAW figures
rather than the grid's rounded strings, so a download can be summed and
re-cut. All 26 rows are written regardless of which sections are collapsed:
collapse is a view state, not a filter.

Units, per cell:
  * dollar rows       $M (float, unrounded)
  * margin rows       ratio (0.548), formatted as a percent in Excel
  * change, $ rows    ratio in "pct" mode, $M in "usd" mode
  * change, margins   basis points, in either mode
Cells the grid shows as an em-dash -- a non-derivable row, a missing period,
a greyed same-actuals change -- are left blank.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

import pandas as pd

import transforms as tx

GRAIN_TITLES: dict[str, str] = {
    "annual": "Annual",
    "quarterly": "Quarterly",
    "monthly": "Monthly",
}

_VALUE, _CHANGE = "value", "change"


@dataclass(frozen=True)
class _Col:
    block: str          # group header, e.g. 'Sep 2026 FC' / 'Change vs. Aug 2026 FC'
    period: str         # period header, e.g. 'Jan 26A'
    kind: str           # _VALUE | _CHANGE
    vintage: str        # whose figure a _VALUE column carries
    period_key: str
    dimmed: bool        # a greyed same-actuals change column


def _columns(cube: tx.Cube, *, forecast: str, comp: str, grain: str) -> list[_Col]:
    periods = cube.periods(forecast, grain)
    cols: list[_Col] = []
    if comp:
        cols += [_Col(tx.vintage_label(comp), lbl, _VALUE, comp, pk, False)
                 for pk, lbl in periods]
    cols += [_Col(tx.vintage_label(forecast), lbl, _VALUE, forecast, pk, False)
             for pk, lbl in periods]
    if comp:
        cols += [_Col(tx.change_label(comp), lbl, _CHANGE, forecast, pk,
                      cube.same_actuals(forecast, comp, pk))
                 for pk, lbl in periods]
    return cols


def _cell(
    cube: tx.Cube, row: tx.Row, col: _Col, *, forecast: str, comp: str, delta_mode: str
) -> float | None:
    if not row.is_derivable:
        return None
    if col.kind == _VALUE:
        v = cube.value(col.vintage, row, col.period_key)
        if v is None:
            return None
        return v if row.is_pct else v / 1e6
    if col.dimmed:
        return None
    d = tx.delta_value(
        cube.value(forecast, row, col.period_key),
        cube.value(comp, row, col.period_key),
        row.is_pct,
        delta_mode,
    )
    if d is None:
        return None
    return d / 1e6 if (delta_mode == "usd" and not row.is_pct) else d


def _unit(row: tx.Row) -> str:
    return "ratio" if row.is_pct else "$M"


def _change_unit(row: tx.Row, delta_mode: str) -> str:
    if row.is_pct:
        return "bps"
    return "$M" if delta_mode == "usd" else "ratio"


def statement_frame(
    cube: tx.Cube, *, forecast: str, comp: str, grain: str, delta_mode: str = "pct"
) -> pd.DataFrame:
    """One row per statement line, one column per grid column, raw figures.

    Leading columns Section / Line Item / Unit (and Change unit, with a
    comparison); data columns are named '<block> | <period>'.
    """
    cols = _columns(cube, forecast=forecast, comp=comp, grain=grain)
    records = []
    for row in tx.ROWS:
        rec: dict[str, object] = {
            "Section": row.section,
            "Line Item": row.label,
            "Unit": _unit(row),
        }
        if comp:
            rec["Change unit"] = _change_unit(row, delta_mode)
        for col in cols:
            rec[f"{col.block} | {col.period}"] = _cell(
                cube, row, col, forecast=forecast, comp=comp, delta_mode=delta_mode
            )
        records.append(rec)
    return pd.DataFrame.from_records(records)


def title(*, forecast: str, comp: str, grain: str) -> str:
    vs = f" vs. {tx.vintage_label(comp)}" if comp else ""
    return (f"Collectibles Forecast — {tx.vintage_label(forecast)}{vs} "
            f"— {GRAIN_TITLES.get(grain, grain)}")


def filename(*, forecast: str, comp: str, grain: str, ext: str) -> str:
    """'pnl_sep-2026-fc_vs_aug-2026-fc_monthly.xlsx'."""
    def slug(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    vs = f"_vs_{slug(tx.vintage_label(comp))}" if comp else ""
    return f"pnl_{slug(tx.vintage_label(forecast))}{vs}_{grain}.{ext}"


def to_csv(
    cube: tx.Cube, *, forecast: str, comp: str, grain: str, delta_mode: str = "pct"
) -> bytes:
    frame = statement_frame(cube, forecast=forecast, comp=comp, grain=grain,
                            delta_mode=delta_mode)
    # utf-8-sig: the BOM is what makes Excel, opening the CSV directly, decode
    # it as UTF-8 rather than the local code page.
    return frame.to_csv(index=False).encode("utf-8-sig")


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------
_NUM_FORMATS: dict[str, str] = {
    "usd": "#,##0.0;(#,##0.0)",
    "pct": "0.0%",
    "chg_pct": "+0.0%;-0.0%;0.0%",
    "chg_usd": "+#,##0.0;(#,##0.0);0.0",
    "chg_bps": '+#,##0" bps";-#,##0" bps";0" bps"',
}

_HEADER_FILL = {"comp": "#2d4a6e", "curr": "#1a3560", "change": "#1e3a4a"}
_HEADER_FONT = {"comp": "#a8c0dd", "curr": "#e0eaf7", "change": "#7dd3c8"}


def _num_format_key(row: tx.Row, col: _Col, delta_mode: str) -> str:
    if col.kind == _VALUE:
        return "pct" if row.is_pct else "usd"
    if row.is_pct:
        return "chg_bps"
    return "chg_usd" if delta_mode == "usd" else "chg_pct"


def to_xlsx(
    cube: tx.Cube,
    *,
    forecast: str,
    comp: str,
    grain: str,
    delta_mode: str = "pct",
    pulled_at: datetime | None = None,
) -> bytes:
    """A formatted workbook: title, two-tier header, frozen labels and header."""
    import xlsxwriter   # imported here so a missing wheel only breaks the download

    cols = _columns(cube, forecast=forecast, comp=comp, grain=grain)
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    ws = wb.add_worksheet("Statement")

    base = {"font_name": "Calibri", "font_size": 10}
    cache: dict[tuple, object] = {}

    def fmt(**props):
        key = tuple(sorted(props.items()))
        if key not in cache:
            cache[key] = wb.add_format({**base, **props})
        return cache[key]

    # -- title ----------------------------------------------------------
    ws.write(0, 0, title(forecast=forecast, comp=comp, grain=grain),
             fmt(bold=True, font_size=13, font_color="#1a2b4a"))
    change_note = ""
    if comp:
        change_note = (" · Change in $M (margins in bps)" if delta_mode == "usd"
                       else " · Change in % (margins in bps)")
    pulled = f" · Data pulled {pulled_at:%Y-%m-%d %H:%M} UTC" if pulled_at else ""
    ws.write(1, 0, f"Figures in $M; margins in %{change_note}{pulled}",
             fmt(italic=True, font_color="#6b7fa3"))

    # -- two-tier header ------------------------------------------------
    top, sub, first = 3, 4, 5
    lead = ("Section", "Line Item")
    hdr = dict(bold=True, font_color="#ffffff", bg_color="#1a2b4a",
               border=1, border_color="#2d4a7a", valign="vcenter")
    for c, text in enumerate(lead):
        ws.merge_range(top, c, sub, c, text, fmt(**hdr))

    def block_style(col: _Col) -> str:
        if col.kind == _CHANGE:
            return "change"
        return "comp" if comp and col.vintage == comp else "curr"

    c0 = len(lead)
    i = 0
    while i < len(cols):
        j = i
        while j + 1 < len(cols) and cols[j + 1].block == cols[i].block:
            j += 1
        style = block_style(cols[i])
        f = fmt(bold=True, align="center", bg_color=_HEADER_FILL[style],
                font_color=_HEADER_FONT[style], border=1, border_color="#1a2b4a")
        if j > i:
            ws.merge_range(top, c0 + i, top, c0 + j, cols[i].block, f)
        else:
            ws.write(top, c0 + i, cols[i].block, f)
        i = j + 1

    for k, col in enumerate(cols):
        style = block_style(col)
        ws.write(sub, c0 + k, col.period, fmt(
            bold=True, align="right", bg_color=_HEADER_FILL[style],
            font_color=_HEADER_FONT[style], italic=col.period_key == tx.ANNUAL
            or tx.is_ytd(col.period_key), border=1, border_color="#1a2b4a"))

    # -- body -----------------------------------------------------------
    for r, row in enumerate(tx.ROWS):
        emphasis = row.row_type in ("total", "subtotal", "margin")
        fill = {"total": "#e8edf7", "margin": "#e4eaf8",
                "subtotal": "#f5f7fc"}.get(row.row_type)
        row_props: dict[str, object] = {"bold": emphasis}
        if fill:
            row_props["bg_color"] = fill
        if row.row_type in ("total", "margin"):
            row_props.update(top=1, top_color="#b8c5d8")

        ws.write(first + r, 0, row.section, fmt(font_color="#6b7fa3", **row_props))
        indent = 2 if row.row_type == "sub" else 1 if row.row_type == "subtotal" else 0
        ws.write(first + r, 1, row.label,
                 fmt(indent=indent, font_color="#1a2b4a", **row_props))

        for k, col in enumerate(cols):
            v = _cell(cube, row, col, forecast=forecast, comp=comp, delta_mode=delta_mode)
            props = dict(row_props, num_format=_NUM_FORMATS[_num_format_key(row, col, delta_mode)])
            if col.dimmed:
                props.update(bg_color="#f3f4f6")
            if v is None:
                ws.write_blank(first + r, c0 + k, None, fmt(**props))
            else:
                ws.write_number(first + r, c0 + k, v, fmt(**props))

    # -- layout ---------------------------------------------------------
    ws.set_column(0, 0, 14)
    ws.set_column(1, 1, 26)
    ws.set_column(c0, c0 + max(len(cols) - 1, 0), 12)
    ws.freeze_panes(first, c0)
    ws.set_landscape()
    ws.fit_to_pages(1, 0)

    wb.close()
    return buf.getvalue()


def downloads(
    cube: tx.Cube,
    *,
    forecast: str,
    comp: str,
    grain: str,
    delta_mode: str,
    pulled_at: datetime | None,
) -> Sequence[tuple[str, bytes, str, str]]:
    """(label, data, file name, mime) for each download button, in order."""
    kw = dict(forecast=forecast, comp=comp, grain=grain)
    return (
        ("Download Excel",
         to_xlsx(cube, delta_mode=delta_mode, pulled_at=pulled_at, **kw),
         filename(ext="xlsx", **kw),
         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("Download CSV",
         to_csv(cube, delta_mode=delta_mode, **kw),
         filename(ext="csv", **kw),
         "text/csv"),
    )
