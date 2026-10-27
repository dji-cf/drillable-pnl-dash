"""Drillable P&L -- the Collectibles forecast deck, live against Snowflake.

The consolidated page, ported from FC_Forecast Dashboard_Jul 2026 FC.html:

  Forecast Table     26 P&L rows x up to 42 columns, collapsible sections,
                     vintage comparison, three grains, Excel / CSV export.
  Historical Trends  how the outlook moved, in which months, and which
                     business units moved it -- for one metric.

plus, under the STG source, a P&L page per business unit (bu.py): North
America, International, Digital and Fanatics Collect. Clicking one of those
labels on the consolidated Revenue or EBITDA block opens it.

STRUCTURE. This file is the entrypoint SHELL: page config, header, the data
load, the sidebar and the Forecast / vs. pair, then st.navigation runs the
current page. Those widgets live here, not on a page, because widget state
only survives a page switch for widgets the entrypoint renders. The grain
control is per page and carried across through a plain shadow key; the Trends
tab's widgets are page-local and reset after a visit to a BU page.

Revenue is live and reconciles to the deck (see tools/validate_vs_deck.py). The
19 cost rows carry a cost basis that is corrected for the source's Compensation
double-count but is still short in actual months; they show their live figures
regardless. Four rows the source cannot express at all render as em-dashes. How
far each figure can be trusted is documented in ISSUES.md, not on screen.

Local: .\\run.ps1     (uses this project's .venv -- Streamlit >= 1.57 required
                       for the clickable section headers)
"""
from __future__ import annotations

from typing import Callable, Mapping, Sequence

import streamlit as st

st.set_page_config(
    page_title="Drillable P&L — Collectibles Forecast",
    page_icon="\U0001F4C8",
    layout="wide",
)

import agent_chat                # noqa: E402
import bu                        # noqa: E402
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
#: The header's "(DRAFT)" tag and this line, while the figures are still being
#: validated against EPM. Set to None to drop both once they are final.
DRAFT_NOTICE: str | None = "Numbers under validation. Not final."

#: Plain (non-widget) session key the grain controls share, so the View picked
#: on one page is the View on the next. A widget's own key is dropped when a
#: page that does not render it runs.
GRAIN_SHADOW = "_grain"

style.inject()


def _shell_header(fiscal_year: str | None) -> str:
    fy = f"FY {fiscal_year} &nbsp;·&nbsp; " if fiscal_year else ""
    tag = '<span class="draft">(DRAFT)</span>' if DRAFT_NOTICE else ""
    note = f'<div class="draft-note">{DRAFT_NOTICE}</div>' if DRAFT_NOTICE else ""
    return (
        '<div class="shell-header">'
        f"<h1>Collectibles Forecast Dashboard{tag}</h1>"
        f"{note}"
        f'<div class="sub">{fy}Figures in $M</div>'
        "</div>"
    )


# Filled again once the forecast is chosen: the year is the selected
# forecast's, not a constant.
header = st.empty()
header.markdown(_shell_header(None), unsafe_allow_html=True)
# A BU page puts its breadcrumb and BU links here, above the Forecast / vs.
# pair the shell renders next.
crumbs = st.container()

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
    # Here in the shell, not on a page, so the conversation survives a switch
    # to a BU page and back. A fragment: asking reruns only the chat.
    agent_chat.render()

    st.divider()
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
# Forecast and comparison -- one pair for every page and tab
# ---------------------------------------------------------------------------
# Above the pages so the statement's change column, the Trends bridge and every
# BU page always compare the same two vintages.
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
# The statement view -- shared by the consolidated page and every BU page
# ---------------------------------------------------------------------------
def _keep_grain(key: str) -> None:
    """on_change: a click on any page's View control becomes the shared View."""
    st.session_state[GRAIN_SHADOW] = st.session_state.get(key) or "annual"


def _grain_control(key: str) -> str:
    """The Annual / Quarterly / Monthly control, always seeded from GRAIN_SHADOW.

    The shadow is the one source of truth: the callback above writes it before
    the run a click causes, and every run writes it back into this page's
    widget key, so whatever a page last held cannot outvote the View picked on
    another. A first run adopts a preset widget value (tools/apptest_smoke).
    """
    if GRAIN_SHADOW not in st.session_state:
        st.session_state[GRAIN_SHADOW] = st.session_state.get(key) or "annual"
    st.session_state[key] = st.session_state[GRAIN_SHADOW]
    c3, _ = st.columns([2.2, 3.7], vertical_alignment="bottom")
    with c3:
        grain = st.segmented_control(
            "View",
            options=list(GRAIN_LABELS),
            format_func=lambda g: GRAIN_LABELS[g],
            key=key,
            on_change=_keep_grain,
            args=(key,),
        ) or "annual"
    return grain


def _statement_view(
    *,
    grain_key: str,
    collapsed_key: str,
    grid_key: str,
    rows: Sequence[tx.Row] = tx.ROWS,
    sections: Sequence[str] = tx.SECTIONS_WITH_HEADER,
    tooltips: Mapping[tuple[str, str], str] = tx.ROW_TOOLTIPS,
    tiles: Sequence[tuple[str, tx.Row]] | None = None,
    money: Callable[[float | None], str] = tx.fmt_tile,
    subject: str = export.CONSOLIDATED,
    drill: Mapping[tuple[str, str], str] | None = None,
) -> tuple[str, str] | None:
    """Tiles, downloads and the statement grid. Returns a 'drill' click, if any.

    Section and mode clicks are handled here; a drill click is returned for the
    caller to switch page on.
    """
    grain = _grain_control(grain_key)

    # % or $ on the change column. Set by the toggle in that column's header
    # (a 'mode' click from interactive.statement, handled below), so it is
    # plain session state rather than a widget value -- shared by every page.
    delta_mode = st.session_state.get("delta_mode", "pct")
    if delta_mode not in tx.DELTA_MODES:
        delta_mode = st.session_state.delta_mode = "pct"

    st.markdown(
        table.build_tiles(cube, forecast=forecast, comp=comp, delta_mode=delta_mode,
                          tiles=tiles, money=money),
        unsafe_allow_html=True,
    )

    # Built from the same periods as the grid (export.py), every row whatever
    # is collapsed. ~26 x 42 cells, so rebuilding per run is free.
    _, *dl_cols = st.columns([6, 1.1, 1.1], vertical_alignment="bottom")
    for col, (label, payload, fname, mime) in zip(dl_cols, export.downloads(
        cube, forecast=forecast, comp=comp, grain=grain,
        delta_mode=delta_mode, pulled_at=pulled_at, rows=rows, subject=subject,
    )):
        with col:
            st.download_button(
                label, payload, file_name=fname, mime=mime,
                icon=":material/download:", on_click="ignore", width="stretch",
            )

    if collapsed_key not in st.session_state:
        st.session_state[collapsed_key] = {s: False for s in sections}
    collapsed = st.session_state[collapsed_key]

    live = interactive.interactive_available()
    grid = table.build_statement(
        cube,
        forecast=forecast, comp=comp, grain=grain,
        collapsed=collapsed,
        delta_mode=delta_mode,
        toggle_enabled=live,
        rows=rows, sections=sections, tooltips=tooltips,
        # Only where the click can land: on the static path the labels would
        # look like links and do nothing.
        drill=drill if live else None,
    )
    clicked = interactive.statement(grid, key=grid_key)

    # Checked AFTER the render: the component-registration case only becomes
    # known once we have tried to mount it.
    reason = interactive.unavailable_reason()
    if reason:
        st.info(reason)
        if drill:
            # Drilling still works without the component, from these links.
            _bu_links(None)

    changed = False
    if clicked:
        kind, value = clicked
        if kind == "toggle" and value in collapsed:
            collapsed[value] = not collapsed[value]
            changed = True
        elif kind == "mode" and value in tx.DELTA_MODES and value != delta_mode:
            st.session_state.delta_mode = value
            changed = True
        elif kind == "drill":
            return clicked
    if changed:
        # The grid -- and for a mode click the tiles and downloads above it --
        # were already rendered from the pre-click state, so the new state
        # needs a fresh run to show. `clicked` is transient, so this cannot
        # loop.
        st.rerun()
    return None


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
def consolidated_page() -> None:
    tab_table, tab_trends = st.tabs(["Forecast Table", "Historical Trends"])

    # ══ Forecast Table ═════════════════════════════════════════════════════
    with tab_table:
        clicked = _statement_view(
            grain_key="grain", collapsed_key="collapsed", grid_key="statement",
            drill=table.DRILL if bu.AVAILABLE else None,
        )
        if clicked and clicked[1] in BU_PAGES:
            st.switch_page(BU_PAGES[clicked[1]])

    # ══ Historical Trends ══════════════════════════════════════════════════
    # Three charts: the outlook across forecasts, monthly values by forecast,
    # and the change by business unit. All read the Forecast / vs. pair above.
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
                # A new Forecast / vs. pair starts the lines over from its
                # default (that year's Budget, the comparison, the forecast).
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


def _bu_links(current: str | None) -> None:
    """One link per BU page, the current one disabled.

    Links rather than a segmented control: they hold no widget state that
    could outlive a page switch and send a drill to the wrong BU.
    """
    cols = st.columns([1] * len(bu.BU_KEYS) + [2.4])
    for col, key in zip(cols, bu.BU_KEYS):
        with col:
            st.page_link(BU_PAGES[key], label=bu.BU_NAMES[key],
                         disabled=key == current)


def bu_page(key: str) -> None:
    """One BU's P&L: tiles, downloads and the statement, no Trends tab."""
    with crumbs:
        back, here = st.columns([1.3, 6], vertical_alignment="center")
        with back:
            st.page_link(CONSOLIDATED, label="Consolidated",
                         icon=":material/arrow_back:")
        with here:
            st.markdown(f"› **{bu.subject(key)}**")
        _bu_links(key)

    rows = bu.rows(key, cube)
    # A per-page widget key: one key shared by the four BU pages is a different
    # widget on each, which opens with no value and would reset the View.
    _statement_view(
        grain_key=f"grain_{key}", collapsed_key=f"collapsed_{key}",
        grid_key=f"statement_{key}",
        rows=rows, sections=bu.SECTIONS_WITH_HEADER, tooltips=bu.tooltips(key),
        tiles=bu.tiles(rows), money=tx.fmt_tile_m, subject=bu.subject(key),
    )


# Named wrappers, one per page: st.Page needs a distinct callable per page.
def north_america_page() -> None:
    bu_page("na")


def international_page() -> None:
    bu_page("intl")


def digital_page() -> None:
    bu_page("digital")


def collect_page() -> None:
    bu_page("collect")


CONSOLIDATED = st.Page(consolidated_page, title="Consolidated", default=True)
_BU_FUNCS = {"na": north_america_page, "intl": international_page,
             "digital": digital_page, "collect": collect_page}
#: Empty under LEGACY: no BU pages are registered at all.
BU_PAGES: dict[str, st.Page] = {
    key: st.Page(_BU_FUNCS[key], title=bu.subject(key), url_path=bu.URL_PATHS[key])
    for key in bu.BU_KEYS
} if bu.AVAILABLE else {}

st.navigation([CONSOLIDATED, *BU_PAGES.values()], position="hidden").run()
