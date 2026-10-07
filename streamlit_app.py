"""Drillable P&L -- the Collectibles forecast deck, live against Snowflake.

Two pages, ported from FC_Forecast Dashboard_Jul 2026 FC.html:

  Forecast Table     26 P&L rows x up to 39 columns, collapsible sections,
                     vintage comparison, three grains.
  Historical Trends  one metric across vintages, Annual / Quarterly / Monthly.

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

st.markdown(
    '<div class="shell-header">'
    '<h1>Collectibles Forecast Dashboard <span class="draft">(DRAFT)</span></h1>'
    '<div class="draft-note">Numbers under validation. Not final.</div>'
    '<div class="sub">FY 2026 &nbsp;·&nbsp; Figures in $M'
    "</div>"
    "</div>",
    unsafe_allow_html=True,
)

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
    st.caption(f"{len(cube.vintages)} vintages: {', '.join(cube.vintages)}")

# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
tab_table, tab_trends = st.tabs(["Forecast Table", "Historical Trends"])

# ══ Forecast Table ═════════════════════════════════════════════════════════
with tab_table:
    fc_opts = tx.forecast_options(cube.vintages)
    if not fc_opts:
        fc_opts = list(cube.vintages)
    if "fc_sel" not in st.session_state:
        st.session_state.fc_sel = fc_opts[0]

    c1, c2, c3 = st.columns([1.3, 1.6, 2.2], vertical_alignment="bottom")

    with c1:
        forecast = st.selectbox(
            "Forecast", fc_opts, key="fc_sel", format_func=tx.vintage_label
        )

    comp_opts = tx.comp_options(cube.vintages, forecast)
    if "comp_sel" not in st.session_state:
        # First load only: default to the vintage immediately before the
        # selected forecast, which is the deck's opening pairing (Jul. FC vs
        # Jun. FC).
        prior = [o for o in comp_opts if o.endswith(". FC")]
        st.session_state["comp_sel"] = prior[0] if prior else ""
    else:
        # Thereafter the deck's refreshCompOpts() rule applies: a comparison
        # that collides with the newly chosen forecast resets to None. It resets
        # rather than sliding to a neighbouring vintage -- quietly comparing
        # against a different vintage than the user picked would be worse than
        # clearing it. Rewriting the key before the widget renders is also what
        # keeps Streamlit from raising on a value no longer in the option list.
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

    with c3:
        grain = st.segmented_control(
            "View",
            options=list(GRAIN_LABELS),
            format_func=lambda g: GRAIN_LABELS[g],
            default="annual",
            key="grain",
        ) or "annual"

    for vintage, role in ((forecast, "forecast"), (comp, "comparison")):
        if vintage and cube.is_partial(vintage):
            months = len(cube.months_present.get(vintage, ()))
            quarters = ", ".join(cube.quarters_present.get(vintage, ()))
            st.warning(
                f"**{tx.vintage_label(vintage)}** is selected as the {role} and "
                f"is a **{months}-month partial year**: {quarters} only (no Q4), "
                f"and its FY total is a {months}-month sum. It is not a "
                f"like-for-like comparison against a full-year vintage."
            )

    st.markdown(
        table.build_tiles(cube, forecast=forecast, comp=comp),
        unsafe_allow_html=True,
    )

    if "collapsed" not in st.session_state:
        st.session_state.collapsed = {s: False for s in tx.SECTIONS_WITH_HEADER}

    grid = table.build_statement(
        cube,
        forecast=forecast, comp=comp, grain=grain,
        collapsed=st.session_state.collapsed,
    )
    clicked = interactive.statement(grid, key="statement")

    # Checked AFTER the render: the component-registration case only becomes
    # known once we have tried to mount it.
    reason = interactive.unavailable_reason()
    if reason:
        st.info(reason)

    if clicked and clicked in st.session_state.collapsed:
        st.session_state.collapsed[clicked] = not st.session_state.collapsed[clicked]
        # The grid above was already rendered from the pre-click state, so the
        # new state needs a fresh run to show. `clicked` is transient, so this
        # cannot loop.
        st.rerun()

# ══ Historical Trends ══════════════════════════════════════════════════════
with tab_trends:
    side, main = st.columns([1, 3.4], gap="medium")

    with side:
        st.markdown("**Time Period**")
        t_grain = st.selectbox(
            "Time period",
            list(GRAIN_LABELS),
            format_func=lambda g: GRAIN_LABELS[g],
            key="t_grain",
            label_visibility="collapsed",
        )

        sub_items: list[str] = []
        if t_grain == "quarterly":
            sub_items = list(tx.QUARTERS)
        elif t_grain == "monthly":
            sub_items = list(tx.MONTHS)

        subs: list[str] = []
        if sub_items:
            # Porting the deck's buildSub(): keep whatever is still valid after a
            # grain change, else fall back to the first item, and never allow the
            # selection to empty out.
            kept = [s for s in st.session_state.get("t_subs", []) if s in sub_items]
            if not kept:
                kept = [sub_items[0]]
            st.session_state.t_subs = kept

            def _keep_one_selected() -> None:
                if not st.session_state.get("t_subs"):
                    st.session_state["t_subs"] = st.session_state.get(
                        "subs_prev", [sub_items[0]]
                    )
                else:
                    st.session_state["subs_prev"] = list(st.session_state["t_subs"])

            subs = st.segmented_control(
                "Sub-periods",
                options=sub_items,
                selection_mode="multi",
                key="t_subs",
                on_change=_keep_one_selected,
                label_visibility="collapsed",
            ) or kept

        st.markdown("**Metric**")

        def _metric_label(idx: int) -> str:
            row = tx.ROWS[idx]
            return f"{row.section} — {row.metric_label}"

        metric_idx = st.selectbox(
            "Metric",
            list(range(len(tx.ROWS))),
            index=6,                     # Total Revenue, the deck's default
            format_func=_metric_label,
            key="t_metric",
            label_visibility="collapsed",
        )
        row = tx.ROWS[metric_idx]

        st.markdown("**Periods to Display**")
        if "t_checks" not in st.session_state:
            newest = next((v for v in reversed(cube.vintages)
                           if v.endswith(". FC")), None)
            st.session_state.t_checks = {
                v for v in ("2025A", "2026B", newest) if v and v in cube.vintages
            }

        selected_vintages: list[str] = []
        for v in cube.vintages:
            swatch, box = st.columns([1, 9], vertical_alignment="center")
            with swatch:
                st.markdown(
                    f'<div style="width:12px;height:12px;border-radius:3px;'
                    f'background:{tx.PERIOD_COLORS.get(v, "#4d7ab8")};'
                    f'margin-top:6px"></div>',
                    unsafe_allow_html=True,
                )
            with box:
                if st.checkbox(
                    tx.vintage_label(v),
                    value=v in st.session_state.t_checks,
                    key=f"chk_{v}",
                ):
                    selected_vintages.append(v)
        st.session_state.t_checks = set(selected_vintages)

    with main:
        # Gated on is_derivable, not is_live: rows 10 and 18 DO have an
        # expression, it just evaluates over a residual the source has broken,
        # and plotting it would show a 108.5% gross margin. See ISSUES.md.
        if not row.is_derivable:
            st.info(
                f"**{row.section} — {row.metric_label}** is not available "
                f"from the source."
            )
        else:
            st.altair_chart(
                charts.build(cube, row, selected_vintages, t_grain, subs),
                width="stretch",
            )
