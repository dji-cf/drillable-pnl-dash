"""Historical Trends charts, in Altair.

Ports the deck's hand-rolled SVG charting (source JS lines 583-775) to Altair:
one bar per vintage in Annual mode, grouped bars in Quarterly/Monthly mode with
one bar per selected sub-period. The deck's three color maps (PERIOD_COLORS,
QTR_SUB_COLORS, MONTH_SUB_COLORS) come across unchanged, as do its value labels
and its zero rule.

Two deliberate improvements over the original:

* Tooltips, which the hand-rolled SVG had no way to offer.
* A fixed bug. The deck reads ``def.is_pct`` at source line 585, but its
  ROW_DEFS entries define ``isPct`` -- so ``isPct`` was always undefined there
  and every percent metric (all 7 Gross Margin rows and EBITDA Margin) was
  plotted and labelled on the dollar scale. Here the row's real is_pct drives
  both.
"""
from __future__ import annotations

from typing import Sequence

import altair as alt
import pandas as pd

import transforms as tx

_HEIGHT = 380


def _scale(value: float | None, is_pct: bool) -> float | None:
    """Dollars to millions, ratios to whole percent -- the deck's chart units."""
    if value is None:
        return None
    return value * 100 if is_pct else value / 1e6


def bar_label(scaled: float, is_pct: bool) -> str:
    """Value label above a bar, in the deck's format (source lines 691-692)."""
    if is_pct:
        return f"{tx.round_half_up(scaled)}%"
    if abs(scaled) >= 1000:
        return f"${scaled / 1000:.1f}B"
    return f"${tx.round_half_up(scaled):,}"


def _axis_title(is_pct: bool) -> str:
    return "%" if is_pct else "$M"


def _titles(row: tx.Row, subtitle: str) -> alt.TitleParams:
    return alt.TitleParams(
        text=f"{row.section} — {row.metric_label}",
        subtitle=subtitle,
        anchor="start",
        fontSize=14,
        subtitleFontSize=12,
        subtitleColor="#6b7fa3",
        color="#1a2b4a",
    )


def _zero_rule(df: pd.DataFrame) -> alt.Chart | None:
    """A solid line at zero, drawn only when the data actually crosses it."""
    if df.empty or df["value"].min() >= 0:
        return None
    return (
        alt.Chart(pd.DataFrame({"zero": [0.0]}))
        .mark_rule(color="#b0bcd4", strokeWidth=1.5)
        .encode(y=alt.Y("zero:Q"))
    )


def _empty(message: str) -> alt.Chart:
    return (
        alt.Chart(pd.DataFrame({"t": [message]}))
        .mark_text(color="#9aaccc", fontSize=13)
        .encode(text=alt.Text("t:N"))
        .properties(height=_HEIGHT)
    )


def annual_chart(
    cube: tx.Cube, row: tx.Row, vintages: Sequence[str]
) -> alt.LayerChart | alt.Chart:
    """One bar per vintage on the annual figure, colored by the deck's period map."""
    records = []
    for v in vintages:
        scaled = _scale(cube.value(v, row, tx.ANNUAL), row.is_pct)
        if scaled is None:
            continue
        records.append({
            "vintage": tx.vintage_label(v),
            "key": v,
            "value": scaled,
            "label": bar_label(scaled, row.is_pct),
        })
    if not records:
        return _empty("No data for this metric")

    df = pd.DataFrame(records)
    order = [r["vintage"] for r in records]
    colors = [tx.PERIOD_COLORS.get(r["key"], "#4d7ab8") for r in records]
    unit = _axis_title(row.is_pct)

    base = alt.Chart(df).encode(
        x=alt.X("vintage:N", sort=order, title=None,
                axis=alt.Axis(labelAngle=0, labelFontWeight="bold")),
        y=alt.Y("value:Q", title=unit,
                axis=alt.Axis(grid=True, gridDash=[4, 3], gridColor="#e8edf5")),
    )
    bars = base.mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2).encode(
        color=alt.Color("vintage:N", sort=order,
                        scale=alt.Scale(domain=order, range=colors), legend=None),
        tooltip=[alt.Tooltip("vintage:N", title="Vintage"),
                 alt.Tooltip("label:N", title=row.metric_label)],
    )
    text = base.mark_text(dy=-7, fontSize=11, fontWeight="bold",
                          color="#1a2b4a").encode(text=alt.Text("label:N"))

    layers = [bars, text]
    rule = _zero_rule(df)
    if rule is not None:
        layers.insert(0, rule)
    return (
        alt.layer(*layers)
        .properties(height=_HEIGHT, title=_titles(row, f"Annual (FY) · {unit}"))
    )


def grouped_chart(
    cube: tx.Cube,
    row: tx.Row,
    vintages: Sequence[str],
    subs: Sequence[str],
    grain: str,
) -> alt.LayerChart | alt.Chart:
    """Grouped bars: a group per vintage, a bar per selected sub-period."""
    sub_colors = tx.QTR_SUB_COLORS if grain == "quarterly" else tx.MONTH_SUB_COLORS

    records = []
    for v in vintages:
        for sub in subs:
            scaled = _scale(cube.value(v, row, sub), row.is_pct)
            if scaled is None:
                continue
            records.append({
                "vintage": tx.vintage_label(v),
                "sub": sub,
                "value": scaled,
                "label": bar_label(scaled, row.is_pct),
            })
    if not records:
        return _empty("No data for this metric and period")

    df = pd.DataFrame(records)
    order = [tx.vintage_label(v) for v in vintages
             if tx.vintage_label(v) in set(df["vintage"])]
    used_subs = [s for s in subs if s in set(df["sub"])]
    unit = _axis_title(row.is_pct)

    base = alt.Chart(df).encode(
        x=alt.X("vintage:N", sort=order, title=None,
                axis=alt.Axis(labelAngle=0, labelFontWeight="bold")),
        xOffset=alt.XOffset("sub:N", sort=used_subs),
        y=alt.Y("value:Q", title=unit,
                axis=alt.Axis(grid=True, gridDash=[4, 3], gridColor="#e8edf5")),
    )
    bars = base.mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2).encode(
        color=alt.Color(
            "sub:N",
            sort=used_subs,
            scale=alt.Scale(domain=used_subs,
                            range=[sub_colors.get(s, "#4d7ab8") for s in used_subs]),
            # The deck only draws a legend when more than one sub-period is on.
            legend=(alt.Legend(title=None, orient="bottom")
                    if len(used_subs) > 1 else None),
        ),
        tooltip=[alt.Tooltip("vintage:N", title="Vintage"),
                 alt.Tooltip("sub:N", title="Period"),
                 alt.Tooltip("label:N", title=row.metric_label)],
    )
    # The deck suppresses value labels when bars get narrow (barW < 18px);
    # approximate that with the bar count, which is what drives the width.
    layers: list[alt.Chart] = [bars]
    if len(order) * len(used_subs) <= 24:
        layers.append(
            base.mark_text(dy=-7, fontSize=10, fontWeight="bold", color="#1a2b4a")
            .encode(text=alt.Text("label:N"))
        )
    rule = _zero_rule(df)
    if rule is not None:
        layers.insert(0, rule)

    subtitle = f"{', '.join(used_subs)} · {unit}"
    return alt.layer(*layers).properties(height=_HEIGHT, title=_titles(row, subtitle))


def build(
    cube: tx.Cube,
    row: tx.Row,
    vintages: Sequence[str],
    grain: str,
    subs: Sequence[str],
) -> alt.LayerChart | alt.Chart:
    """Dispatch to the annual or grouped form, mirroring the deck's renderChart."""
    if not vintages:
        return _empty("Select at least one period to display")
    if grain == "annual":
        return annual_chart(cube, row, vintages)
    if not subs:
        return _empty("Select at least one period")
    return grouped_chart(cube, row, vintages, subs, grain)
