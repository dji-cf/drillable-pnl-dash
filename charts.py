"""Historical Trends charts, in Altair.

Three charts, in the order the tab shows them:

  outlook_chart  Outlook across forecasts. One period (FY or a quarter) across
                 the year's Budget and forecasts in as-of order, with that
                 Budget and the prior year's Actuals as flat references.
  months_chart   Monthly values by forecast. Jan-Dec, one line per chosen
                 vintage. The lines coincide through the selected forecast's
                 actual months (red points) and part where it re-phased.
  bridge_chart   Change by business unit. A waterfall from the comparison to
                 the forecast, one bar per business unit (transforms.bridge).

These replace the deck's per-vintage bar charts (source JS lines 583-775) on
purpose: those showed what each vintage said, not how or why it moved. One fix
from that port still holds. The deck read ``def.is_pct`` where its ROW_DEFS
define ``isPct``, so every margin was plotted on the dollar scale; here the
row's real is_pct drives the scale and the labels.

Figures read as the statement does -- $M with commas, negatives in parentheses
(transforms.fmt_m), changes as transforms.delta_fmt prints them -- except that
margins carry one decimal, since their moves are tenths of a point.
"""
from __future__ import annotations

from typing import Sequence

import altair as alt
import pandas as pd

import transforms as tx

_HEIGHT = 340
_INK = "#1a2b4a"
_MUTED = "#6b7fa3"
#: Streamlit's chart theme paints the background with the page color (#f0f2f5,
#: .streamlit/config.toml), so these are set against that, not white.
_GRID = "#d3dae5"
#: The axis baselines, heavier than the grid so the plot's floor reads first.
_AXIS_LINE = {"domain": True, "domainColor": _MUTED, "domainWidth": 1.5}
#: Bridge steps, as the statement's change cells color them (gpos / gneg).
_UP, _DOWN, _FLAT = "#16a34a", "#dc2626", "#b0bcd4"
#: A month a vintage holds as actuals, on the month chart's points.
_ACTUAL = "#dc2626"

# ---------------------------------------------------------------------------
# Colors by role
# ---------------------------------------------------------------------------
# A vintage is colored by the part it plays against the selected forecast, not
# by which vintage it is. transforms.vintage_color() steps its forecast ramp by
# as-of month, so neighbouring forecasts -- exactly the pair these charts
# compare -- are too close to tell apart: OKLab dE 12.8 for Aug/Sep FC, 11.4 for
# Jun/Jul FC, against a floor of 15.
#
# Measured for this set (OKLab dE x100, normal vision; deutan / protan / tritan
# simulations agree to within a few points): forecast-comparison 23.7,
# forecast-budget 18.9, forecast-prior year 28.8, comparison-budget 17.7. The one
# pair under 15 is budget-other (13.7); the budget's dash and the direct labels
# tell those apart.
ROLE_COLORS: dict[str, str] = {
    "forecast":   "#4d7ab8",
    "budget":     "#a3adbd",
    "prior_year": "#1a2b4a",
    "comparison": "#b5822a",
    "other":      "#d3d8e0",
}
_ROLE_WIDTH: dict[str, float] = {
    "forecast": 3, "budget": 2, "prior_year": 2, "comparison": 2, "other": 1.5,
}
#: Reference series are dashed; gridlines are not (solid hairlines).
_DASHED: frozenset[str] = frozenset({"budget", "prior_year"})
_DASH = [5, 4]


def role(cube: tx.Cube, vintage: str, forecast: str, comp: str) -> str:
    """The first role that applies: forecast, its year's Budget, the prior
    year's Actuals, the comparison, anything else."""
    if vintage == forecast:
        return "forecast"
    if vintage == tx.year_budget(cube, forecast):
        return "budget"
    if vintage == tx.prior_year_actuals(cube, forecast):
        return "prior_year"
    if vintage == comp:
        return "comparison"
    return "other"


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------
def _scale(value: float | None, is_pct: bool) -> float | None:
    """Dollars to millions, ratios to whole percent -- the charts' units."""
    if value is None:
        return None
    return value * 100 if is_pct else value / 1e6


def fmt_value(raw: float, is_pct: bool) -> str:
    """'$5,184' / '($12)' as in the statement; margins to one decimal, '55.3%'."""
    return f"{raw * 100:.1f}%" if is_pct else tx.fmt_m(raw)


def _change(curr: float | None, prev: float | None, is_pct: bool) -> str:
    """'+$46 (+1%)' for a dollar row, '+12 bps' for a margin."""
    if curr is None or prev is None:
        return tx.EM_DASH
    if is_pct:
        return tx.delta_fmt(curr, prev, True)["text"]  # type: ignore[index]
    usd = tx.delta_fmt(curr, prev, False, mode="usd")["text"]  # type: ignore[index]
    pct = tx.delta_fmt(curr, prev, False, mode="pct")["text"]  # type: ignore[index]
    return f"{usd} ({pct})"


def period_label(period: str) -> str:
    return "FY" if period == tx.ANNUAL else period


def _short_label(key: str) -> str:
    """'Budget', 'Sep FC' -- the outlook axis, whose subtitle carries the year."""
    parts = tx.vintage_parts(key)
    if parts is None:
        return key
    kind, _, month = parts
    if kind == tx.BUDGET:
        return "Budget"
    if kind == tx.FORECAST:
        return f"{tx.MONTHS[month - 1]} FC"
    return tx.vintage_label(key)


def _axis_title(is_pct: bool) -> str:
    return "%" if is_pct else "$M"


def _titles(row: tx.Row, subtitle: str) -> alt.TitleParams:
    return alt.TitleParams(
        text=f"{row.section} — {row.metric_label}",
        subtitle=subtitle,
        anchor="start",
        fontSize=14,
        subtitleFontSize=12,
        subtitleColor=_MUTED,
        color=_INK,
        offset=8,  # Streamlit's theme leaves 26px between subtitle and plot
    )


def _y_axis() -> alt.Axis:
    # minExtent: one label gutter on every chart, so the three stacked plots
    # start at the same x whether their labels read '600' or '5,500'.
    return alt.Axis(grid=True, gridColor=_GRID, ticks=False, minExtent=36,
                    labelColor=_MUTED, titleColor=_MUTED, **_AXIS_LINE)


def _quiet(chart: alt.Chart | alt.LayerChart) -> alt.Chart | alt.LayerChart:
    """No tooltip unless a layer encodes one.

    Streamlit's chart theme sets ``mark.tooltip`` for every mark, so labels,
    rules and bands popped their raw encoded fields ('x', 'top', 'label_y').
    The chart's own config is merged over the theme, so null wins.
    """
    return chart.configure_mark(tooltip=None)


def _zero_rule(lo: float, hi: float) -> alt.Chart | None:
    """A solid line at zero, drawn only when the figures cross it."""
    if not lo < 0 < hi:
        return None
    return (
        alt.Chart(pd.DataFrame({"zero": [0.0]}))
        .mark_rule(color="#b0bcd4", strokeWidth=1.5)
        .encode(y=alt.Y("zero:Q"))
    )


def _dodge(values: Sequence[float], gap: float) -> list[float]:
    """Push stacked labels apart so no two sit closer than ``gap``, in order."""
    out = list(values)
    order = sorted(range(len(out)), key=lambda i: out[i])
    for a, b in zip(order, order[1:]):
        if out[b] - out[a] < gap:
            out[b] = out[a] + gap
    return out


def _empty(message: str) -> alt.Chart:
    return _quiet(
        alt.Chart(pd.DataFrame({"t": [message]}))
        .mark_text(color="#9aaccc", fontSize=13)
        .encode(text=alt.Text("t:N"))
        .properties(height=_HEIGHT)
    )


# ---------------------------------------------------------------------------
# 1. Outlook across forecasts
# ---------------------------------------------------------------------------
def outlook_chart(
    cube: tx.Cube,
    row: tx.Row,
    forecast: str,
    comp: str,
    period: str,
    include_retired: bool = False,
) -> alt.LayerChart | alt.Chart:
    """The year's Budget then each forecast, as one line, against the Budget and
    the prior year's Actuals as flat references."""
    keys = tx.outlook_vintages(cube, forecast, include_retired)
    budget = tx.year_budget(cube, forecast)
    budget_raw = cube.value(budget, row, period) if budget else None

    records = []
    prev: float | None = None
    for v in keys:
        raw = cube.value(v, row, period)
        if raw is None:
            continue
        records.append({
            "x": _short_label(v),
            "vintage": tx.vintage_label(v),
            "value": _scale(raw, row.is_pct),
            "text": fmt_value(raw, row.is_pct),
            "vs_prev": _change(raw, prev, row.is_pct),
            "vs_budget": tx.EM_DASH if v == budget else _change(raw, budget_raw, row.is_pct),
            "selected": v == forecast,
            # Value labels on the first point and the selected one only.
            "labelled": v == forecast or not records,
            "ring": bool(comp) and v == comp,
        })
        prev = raw
    if not records:
        return _empty("No data for this metric and period")

    refs = []
    for key, name_role in ((budget, "budget"),
                           (tx.prior_year_actuals(cube, forecast), "prior_year")):
        if not key or key == forecast:
            continue
        raw = cube.value(key, row, period)
        if raw is None:
            continue
        name = "Budget" if name_role == "budget" else tx.vintage_label(key)
        refs.append({"value": _scale(raw, row.is_pct),
                     "text": f"{name} {fmt_value(raw, row.is_pct)}",
                     "color": ROLE_COLORS[name_role]})

    df = pd.DataFrame(records)
    unit = _axis_title(row.is_pct)
    values = list(df["value"]) + [r["value"] for r in refs]
    lo, hi = min(values), max(values)

    x = alt.X("x:N", sort=list(df["x"]), title=None,
              axis=alt.Axis(labelAngle=0, labelFontWeight="bold", labelColor=_INK,
                            ticks=False, **_AXIS_LINE))
    y = alt.Y("value:Q", title=unit, scale=alt.Scale(zero=False), axis=_y_axis())
    base = alt.Chart(df).encode(x=x, y=y)
    tooltip = [
        alt.Tooltip("vintage:N", title="Vintage"),
        alt.Tooltip("text:N", title=row.metric_label),
        alt.Tooltip("vs_prev:N", title="vs. previous"),
        alt.Tooltip("vs_budget:N", title="vs. Budget"),
    ]

    layers: list[alt.Chart] = []
    if refs:
        rdf = pd.DataFrame(refs)
        # Keyed in a legend below the plot, as the month chart's lines are, not
        # labelled off its right edge: the plot then spans the same width as
        # the charts beneath it.
        layers.append(
            alt.Chart(rdf).mark_rule(strokeDash=_DASH, strokeWidth=1.5)
            .encode(y="value:Q", color=alt.Color(
                "text:N", sort=list(rdf["text"]),
                scale=alt.Scale(domain=list(rdf["text"]), range=list(rdf["color"])),
                legend=alt.Legend(title=None, orient="bottom", symbolType="stroke",
                                  symbolDash=_DASH, symbolStrokeWidth=2,
                                  labelColor=_INK),
            ))
        )
    rule = _zero_rule(lo, hi)
    if rule is not None:
        layers.insert(0, rule)

    layers += [
        base.mark_line(color=ROLE_COLORS["forecast"], strokeWidth=2),
        base.mark_point(filled=True, opacity=1, color=ROLE_COLORS["forecast"]).encode(
            size=alt.condition(alt.datum.selected, alt.value(160), alt.value(64)),
            tooltip=tooltip,
        ),
        base.transform_filter(alt.datum.labelled)
        .mark_text(dy=-15, fontSize=12, fontWeight="bold", color=_INK)
        .encode(text="text:N"),
    ]
    if comp and df["ring"].any():
        layers.append(
            base.transform_filter(alt.datum.ring)
            .mark_point(filled=False, size=360, strokeWidth=2,
                        color=ROLE_COLORS[role(cube, comp, forecast, comp)])
            .encode(tooltip=tooltip)
        )

    subtitle = f"{period_label(period)} {cube.year(forecast)} · {unit}"
    return _quiet(alt.layer(*layers).properties(height=_HEIGHT,
                                                title=_titles(row, subtitle)))


# ---------------------------------------------------------------------------
# 2. Monthly values by forecast
# ---------------------------------------------------------------------------
def months_chart(
    cube: tx.Cube,
    row: tx.Row,
    vintages: Sequence[str],
    forecast: str,
    comp: str,
) -> alt.LayerChart | alt.Chart:
    """Jan-Dec, one line per vintage, actual months as red points."""
    if not vintages:
        return _empty("Pick at least one line")

    records = []
    for v in vintages:
        r = role(cube, v, forecast, comp)
        for i, m in enumerate(tx.MONTHS, start=1):
            raw = cube.value(v, row, m)
            if raw is None:
                continue
            records.append({
                "m": i, "month": m, "vintage": tx.vintage_label(v), "role": r,
                "value": _scale(raw, row.is_pct), "text": fmt_value(raw, row.is_pct),
                "dash": "dashed" if r in _DASHED else "solid",
                "actual": bool(cube.month_actual.get((v, m))),
            })
    if not records:
        return _empty("No monthly data for this metric")

    df = pd.DataFrame(records)
    present = set(df["vintage"])
    names = [tx.vintage_label(v) for v in vintages if tx.vintage_label(v) in present]
    roles = {tx.vintage_label(v): role(cube, v, forecast, comp) for v in vintages}
    unit = _axis_title(row.is_pct)
    lo, hi = float(df["value"].min()), float(df["value"].max())

    x = alt.X("m:Q", title=None, scale=alt.Scale(domain=[0.5, 12.5], nice=False),
              axis=alt.Axis(values=list(range(1, 13)), grid=False, ticks=False,
                            labelColor=_INK, labelFontWeight="bold",
                            labelExpr=f"{list(tx.MONTHS)}[datum.value - 1]",
                            **_AXIS_LINE))
    y = alt.Y("value:Q", title=unit, scale=alt.Scale(zero=False), axis=_y_axis())
    color = alt.Color(
        "vintage:N", sort=names,
        scale=alt.Scale(domain=names, range=[ROLE_COLORS[roles[n]] for n in names]),
        legend=alt.Legend(title=None, orient="bottom", symbolType="stroke",
                          symbolStrokeWidth=3, labelColor=_INK),
    )
    lines = alt.Chart(df).encode(
        x=x, y=y, color=color,
        strokeWidth=alt.StrokeWidth(
            "role:N", legend=None,
            scale=alt.Scale(domain=list(_ROLE_WIDTH), range=list(_ROLE_WIDTH.values())),
        ),
        strokeDash=alt.StrokeDash(
            "dash:N", legend=None,
            scale=alt.Scale(domain=["solid", "dashed"], range=[[1, 0], _DASH]),
        ),
    )

    layers: list[alt.Chart] = []
    rule = _zero_rule(lo, hi)
    if rule is not None:
        layers.append(rule)

    # The forecast is drawn last, so it sits on top where the lines coincide.
    pointed = ["forecast", "comparison"]
    layers += [
        lines.transform_filter(alt.datum.role != "forecast").mark_line(),
        lines.transform_filter(alt.datum.role == "forecast").mark_line(),
        lines.transform_filter(alt.FieldOneOfPredicate(field="role", oneOf=pointed))
        .mark_point(filled=True, size=50, opacity=1),
    ]

    # Crosshair: the nearest month, every line's value in one tooltip. Pivoted
    # here rather than with transform_pivot, whose default op (sum) turned the
    # formatted figures into NaN.
    nearest = alt.selection_point(nearest=True, on="pointerover", fields=["m"],
                                  empty=False, clear="pointerout")
    wide = (df.pivot(index=["m", "month"], columns="vintage", values="text")
            .reindex(columns=names).fillna(tx.EM_DASH).reset_index())
    wide.columns.name = None
    layers.append(
        lines.mark_point(filled=True, size=70)
        .encode(opacity=alt.condition(nearest, alt.value(1), alt.value(0)))
    )

    # The months each pointed line holds as actuals, in red over its own point
    # (and over the hover point, which then rings it). Every forecast of a year
    # shares its closed months, so the lines coincide there by construction.
    act = df[df["role"].isin(pointed) & df["actual"]]
    if not act.empty:
        layers.append(
            alt.Chart(act).transform_calculate(kind="'Actual month'")
            .mark_point(filled=True, size=50, opacity=1)
            .encode(x=x, y=y, fill=alt.Fill(
                "kind:N",
                scale=alt.Scale(domain=["Actual month"], range=[_ACTUAL]),
                legend=alt.Legend(title=None, orient="bottom", labelColor=_INK),
            ))
        )

    layers.append(
        alt.Chart(wide)
        .mark_rule(color="#9aaccc", strokeWidth=1)
        .encode(
            x="m:Q",
            opacity=alt.condition(nearest, alt.value(0.8), alt.value(0)),
            tooltip=[alt.Tooltip("month:N", title="Month")]
            + [alt.Tooltip(field=n, type="nominal") for n in names],
        )
        .add_params(nearest)
    )

    # Direct labels at each line's last month, when there are few enough lines
    # to read them; the legend carries identity either way.
    labelled = len(names) <= 4
    if labelled:
        ends = df.loc[df.groupby("vintage")["m"].idxmax()].copy()
        ends["label_y"] = _dodge(list(ends["value"]), 0.07 * ((hi - lo) or abs(hi) or 1))
        layers.append(
            alt.Chart(ends)
            .mark_text(align="left", baseline="middle", dx=8, fontSize=11,
                       fontWeight="bold", color=_MUTED)
            .encode(x="m:Q", y="label_y:Q", text="vintage:N")
        )

    # No right padding for the labels: Streamlit sizes the chart with autosize
    # "fit", which already makes room for marks past the plot's edge.
    return _quiet(alt.layer(*layers).properties(
        height=_HEIGHT, title=_titles(row, f"Monthly · {unit}"),
    ))


# ---------------------------------------------------------------------------
# 3. Change by business unit
# ---------------------------------------------------------------------------
def bridge_chart(
    cube: tx.Cube,
    row: tx.Row,
    forecast: str,
    comp: str,
    period: str,
) -> alt.LayerChart | alt.Chart:
    """Waterfall from the comparison's figure to the forecast's, by business unit.

    The axis does not start at zero -- business-unit moves are a few $M against
    totals in the $B -- so the two end bars rise from the axis floor, and the
    subtitle says so.
    """
    b = tx.bridge(cube, row, forecast, comp, period)
    if b is None:
        return _empty("No bridge for this metric and comparison")

    def end_bar(vintage: str, raw: float) -> dict:
        return {
            "x": tx.vintage_label(vintage), "lo": None, "hi": raw / 1e6,
            "text": tx.fmt_m(raw), "fill": ROLE_COLORS[role(cube, vintage, forecast, comp)],
            "opacity": 1.0, "was": tx.EM_DASH, "now": tx.fmt_m(raw), "change": tx.EM_DASH,
        }

    focus = any(s.highlight for s in b.steps)
    bars = [end_bar(comp, b.start)]
    running = b.start
    for s in b.steps:
        d = tx.delta_fmt(s.curr, s.comp, False, mode="usd") or {"text": tx.EM_DASH, "cls": "gflat"}
        bars.append({
            "x": s.label, "lo": running / 1e6, "hi": (running + s.delta) / 1e6,
            "text": d["text"],
            "fill": _UP if d["cls"] == "gpos" else _DOWN if d["cls"] == "gneg" else _FLAT,
            "opacity": 1.0 if s.highlight or not focus else 0.35,
            "was": tx.fmt_m(s.comp), "now": tx.fmt_m(s.curr),
            "change": _change(s.curr, s.comp, False),
        })
        running += s.delta
    bars.append(end_bar(forecast, b.end))

    levels = [v for bar in bars for v in (bar["lo"], bar["hi"]) if v is not None]
    lo, hi = min(levels), max(levels)
    pad = max(0.25 * (hi - lo), 0.02 * abs(b.end / 1e6), 1.0)
    floor, ceiling = lo - pad, hi + pad
    for bar in bars:
        if bar["lo"] is None:
            bar["lo"] = floor
        bar["top"] = max(bar["lo"], bar["hi"])

    df = pd.DataFrame(bars)
    scale = alt.Scale(domain=[floor, ceiling], nice=False, zero=False)
    x = alt.X("x:N", sort=list(df["x"]), title=None,
              axis=alt.Axis(labelAngle=0, ticks=False,
                            labelColor=_INK, labelFontWeight="bold",
                            labelExpr="length(datum.label) > 12 "
                                      "? split(datum.label, ' ') : datum.label",
                            **_AXIS_LINE))
    layers: list[alt.Chart] = [
        alt.Chart(df).mark_bar(clip=True, cornerRadius=2).encode(
            x=x,
            y=alt.Y("lo:Q", title="$M", scale=scale, axis=_y_axis()),
            y2="hi:Q",
            color=alt.Color("fill:N", scale=None),
            opacity=alt.Opacity("opacity:Q", scale=None),
            tooltip=[
                alt.Tooltip("x:N", title=b.parent.metric_label),
                alt.Tooltip("was:N", title=tx.vintage_label(comp)),
                alt.Tooltip("now:N", title=tx.vintage_label(forecast)),
                alt.Tooltip("change:N", title="Change"),
            ],
        ),
        alt.Chart(df).mark_text(baseline="bottom", dy=-5, fontSize=11,
                                fontWeight="bold", color=_INK)
        .encode(x=x, y=alt.Y("top:Q", scale=scale), text="text:N"),
    ]
    rule = _zero_rule(floor, ceiling)
    if rule is not None:
        layers.insert(0, rule)

    subtitle = (f"{tx.vintage_label(comp)} → {tx.vintage_label(forecast)} · "
                f"{period_label(period)} {cube.year(forecast)} · $M · "
                f"axis does not start at $0")
    return _quiet(alt.layer(*layers).properties(height=_HEIGHT,
                                                title=_titles(b.parent, subtitle)))
