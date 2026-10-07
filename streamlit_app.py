"""Drillable P&L -- the Collectibles forecast deck, live against Snowflake.

Two pages, ported from FC_Forecast Dashboard_Jul 2026 FC.html:

  Forecast Table     26 P&L rows x up to 42 columns, collapsible sections,
                     vintage comparison, three grains, Excel / CSV export.
  Historical Trends  how the outlook moved, in which months, and which
                     business units moved it -- for one metric.

Revenue is live and reconciles to the deck (see tools/validate_vs_deck.py). The
19 cost rows carry a cost basis that is corrected for the source's Compensation
double-count but is still short in actual months; they show their live figures
regardless. Four rows the source cannot express at all render as em-dashes. How
far each figure can be trusted is documented in ISSUES.md, not on screen.

Local: .\\run.ps1     (uses this project's .venv -- Streamlit >= 1.57 required
                       for the clickable section headers)
"""
from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="Drillable P&L — Collectibles Forecast (DRAFT)",
    page_icon="\U0001F4C8",
    layout="wide",
)

import charts                    # noqa: E402
import data                      # noqa: E402
import export                    # noqa: E402
import interactive               # noqa: E402
import style                     # noqa: E402
import table                     # noqa: E402
import transforms as tx          # noqa: E402

GRAIN_LABELS: dict[str, str] = {
    "annual": "Annual",
    "quarterly": "Quarterly",
    "monthly": "Monthly",
}
NONE_LABEL = "— None —"

style.inject()


def _shell_header(fiscal_year: str | None) -> str:
    fy = f"FY {fiscal_year} &nbsp;·&nbsp; " if fiscal_year else ""
    return (
        '<div class="shell-header">'
        '<h1>Collectibles Forecast Dashboard <span class="draft">(DRAFT)</span></h1>'
        '<div class="draft-note">Numbers under validation. Not final.</div>'
        f'<div class="sub">{fy}Figures in $M</div>'
        "</div>"
    )


# Filled again once the forecast is chosen: the year is the selected
# forecast's, not a constant.
header = st.empty()
header.markdown(_shell_header(None), unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
# load_master() lets its exceptions out on purpose (see data.py): a cached
# loader that returned an empty frame would memoize that empty for two hours
# and render a convincing but false "no data" dashboard.
try:
    master, pulled_at = data.load_master()
except Exception as exc:  # noqa: BLE001 -- surface anything, then offer a retry
    st.error(f"Could not load the P&L cube from Snowflake.\n\n`{exc}`")
    if st.button("Retry", type="primary"):
        data.load_master.clear()
        st.rerun()
    st.stop()

cube = tx.build_cube(master)

if not cube.vintages:
    st.warning("The query returned no vintages. Nothing to show.")
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.caption(f"Data pulled {pulled_at:%Y-%m-%d %H:%M} UTC · {len(master):,} rows")
    st.caption(f"{len(cube.vintages)} vintages: "
               f"{', '.join(tx.vintage_label(v) for v in cube.vintages)}")
    # Once a year's actuals are final its forecasts and budget are history, so
    # they are hidden by default (Cube.is_retired). Offered only when there is
    # something to bring back.
    retired = [v for v in cube.vintages if cube.is_retired(v)]
    show_retired = False
    if retired:
        closed = ", ".join(sorted({cube.fiscal_year[v] for v in retired}))
        show_retired = st.checkbox(
            "Show prior-year forecasts & budgets",
            key="show_retired",
            help=f"Forecasts and budgets for years whose actuals are final "
                 f"({closed}) are hidden by default. "
                 f"{len(retired)} hidden: "
                 f"{', '.join(tx.vintage_label(v) for v in retired)}.",
        )

# ---------------------------------------------------------------------------
# Forecast and comparison -- one pair for both tabs
# ---------------------------------------------------------------------------
# Above the tabs so the statement's change column and the Trends bridge always
# compare the same two vintages.
fc_opts = tx.forecast_options(cube, show_retired)
# Also covers a selection that has just stopped being offered (the prior-year
# toggle switched off under it) -- a session_state value outside the options
# would otherwise make the selectbox raise.
if st.session_state.get("fc_sel") not in fc_opts:
    st.session_state.fc_sel = fc_opts[0]

c1, c2, _ = st.columns([1.3, 1.6, 3.1], vertical_alignment="bottom")

with c1:
    forecast = st.selectbox(
        "Forecast", fc_opts, key="fc_sel", format_func=tx.vintage_label
    )

header.markdown(_shell_header(cube.year(forecast)), unsafe_allow_html=True)

comp_opts = tx.comp_options(cube, forecast, show_retired)
if "comp_sel" not in st.session_state:
    # First load only: default to the forecast immediately before the selected
    # one, which is the deck's opening pairing (Jul. FC vs Jun. FC).
    prior = [o for o in comp_opts if cube.scenario_label.get(o) == "FORECAST"]
    st.session_state["comp_sel"] = prior[0] if prior else ""
else:
    # Thereafter the deck's refreshCompOpts() rule applies: a comparison that
    # collides with the newly chosen forecast resets to None. It resets rather
    # than sliding to a neighbouring vintage -- quietly comparing against a
    # different vintage than the user picked would be worse than clearing it.
    # Rewriting the key before the widget renders is also what keeps Streamlit
    # from raising on a value no longer in the option list.
    st.session_state["comp_sel"] = tx.resolve_comp(
        st.session_state["comp_sel"], forecast, comp_opts
    )

with c2:
    comp = st.selectbox(
        "vs.",
        comp_opts,
        key="comp_sel",
        format_func=lambda k: NONE_LABEL if k == "" else tx.vintage_label(k),
    )

# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
tab_table, tab_trends = st.tabs(["Forecast Table", "Historical Trends"])

# ══ Forecast Table ═════════════════════════════════════════════════════════
with tab_table:
    c3, _ = st.columns([2.2, 3.7], vertical_alignment="bottom")

    with c3:
        grain = st.segmented_control(
            "View",
            options=list(GRAIN_LABELS),
            format_func=lambda g: GRAIN_LABELS[g],
            default="annual",
            key="grain",
        ) or "annual"

    # % or $ on the change column. Set by the toggle in that column's header
    # (a 'mode' click from interactive.statement, handled below), so it is
    # plain session state rather than a widget value.
    delta_mode = st.session_state.get("delta_mode", "pct")
    if delta_mode not in tx.DELTA_MODES:
        delta_mode = st.session_state.delta_mode = "pct"

    st.markdown(
        table.build_tiles(cube, forecast=forecast, comp=comp, delta_mode=delta_mode),
        unsafe_allow_html=True,
    )

    # Built from the same periods as the grid (export.py), all 26 rows
    # whatever is collapsed. ~26 x 42 cells, so rebuilding per run is free.
    _, *dl_cols = st.columns([6, 1.1, 1.1], vertical_alignment="bottom")
    for col, (label, payload, fname, mime) in zip(dl_cols, export.downloads(
        cube, forecast=forecast, comp=comp, grain=grain,
        delta_mode=delta_mode, pulled_at=pulled_at,
    )):
        with col:
            st.download_button(
                label, payload, file_name=fname, mime=mime,
                icon=":material/download:", on_click="ignore", width="stretch",
            )

    if "collapsed" not in st.session_state:
        st.session_state.collapsed = {s: False for s in tx.SECTIONS_WITH_HEADER}

    grid = table.build_statement(
        cube,
        forecast=forecast, comp=comp, grain=grain,
        collapsed=st.session_state.collapsed,
        delta_mode=delta_mode,
        toggle_enabled=interactive.interactive_available(),
    )
    clicked = interactive.statement(grid, key="statement")

    # Checked AFTER the render: the component-registration case only becomes
    # known once we have tried to mount it.
    reason = interactive.unavailable_reason()
    if reason:
        st.info(reason)

    changed = False
    if clicked:
        kind, value = clicked
        if kind == "toggle" and value in st.session_state.collapsed:
            st.session_state.collapsed[value] = not st.session_state.collapsed[value]
            changed = True
        elif kind == "mode" and value in tx.DELTA_MODES and value != delta_mode:
            st.session_state.delta_mode = value
            changed = True
    if changed:
        # The grid -- and for a mode click the tiles and downloads above it --
        # were already rendered from the pre-click state, so the new state
        # needs a fresh run to show. `clicked` is transient, so this cannot
        # loop.
        st.rerun()

# ══ Historical Trends ══════════════════════════════════════════════════════
# Three charts: the outlook across forecasts, monthly values by forecast, and the
# change by business unit. All read the Forecast / vs. pair above.
with tab_trends:
    m1, m2, _ = st.columns([2.2, 1.0, 2.6], vertical_alignment="bottom")

    with m1:
        def _metric_label(idx: int) -> str:
            row = tx.ROWS[idx]
            return f"{row.section} — {row.metric_label}"

        metric_idx = st.selectbox(
            "Metric",
            list(range(len(tx.ROWS))),
            index=6,                     # Total Revenue, the deck's default
            format_func=_metric_label,
            key="t_metric",
        )
    with m2:
        t_period = st.selectbox(
            "Period",
            list(tx.TREND_PERIODS),
            format_func=charts.period_label,
            key="t_period",
            help="For the outlook and the bridge. The month view always "
                 "spans Jan–Dec.",
        )
    row = tx.ROWS[metric_idx]

    # Gated on is_derivable, not is_live: rows 10 and 18 DO have an
    # expression, it just evaluates over a residual the source has broken,
    # and plotting it would show a 108.5% gross margin. See ISSUES.md.
    if not row.is_derivable:
        st.info(
            f"**{row.section} — {row.metric_label}** is not available "
            f"from the source."
        )
    else:
        st.markdown("#### Outlook across forecasts")
        st.altair_chart(
            charts.outlook_chart(cube, row, forecast, comp, t_period, show_retired),
            width="stretch",
        )

        st.markdown("#### Monthly values by forecast")
        line_opts = list(cube.visible(show_retired))
        if ("t_lines" not in st.session_state
                or st.session_state.get("t_lines_for") != (forecast, comp)):
            # A new Forecast / vs. pair starts the lines over from its default
            # (that year's Budget, the comparison, the forecast).
            st.session_state.t_lines = tx.default_lines(
                cube, forecast, comp, show_retired
            )
            st.session_state.t_lines_for = (forecast, comp)
        else:
            # Same guard as fc_sel: drop what is no longer offered.
            st.session_state.t_lines = [
                v for v in st.session_state.t_lines if v in line_opts
            ]
        lines = st.multiselect(
            "Lines", line_opts, key="t_lines", format_func=tx.vintage_label
        )
        st.altair_chart(
            charts.months_chart(cube, row, tx.order_vintages(lines), forecast, comp),
            width="stretch",
        )

        st.markdown("#### Change by business unit")
        if not comp:
            st.info("Choose a comparison in **vs.** above to see what drove "
                    "the change.")
        elif row.is_pct:
            st.info("The bridge breaks a $ line into its business units. Pick "
                    "a Revenue or EBITDA line.")
        elif cube.same_actuals(forecast, comp, t_period):
            st.info(f"{charts.period_label(t_period)} is actuals in both "
                    f"{tx.vintage_label(comp)} and {tx.vintage_label(forecast)}, "
                    f"so nothing moved.")
        else:
            st.altair_chart(
                charts.bridge_chart(cube, row, forecast, comp, t_period),
                width="stretch",
            )
