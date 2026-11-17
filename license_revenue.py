"""(DRAFT) Revenue by License (Global) -- standalone app license_revenue_dash (LICENSE_REVENUE_DASH).

Revenue per license (league) x region x quarter from ONE source, Vivek's
FCT_EPM.CARDPLN_PL_BY_LEAGUE_V (James Dillon / Megan Coleman, 2026-11-17).
All shaping lives in license_revenue_core (pure pandas, tested).
"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

import data
import license_revenue_core as core
from license_revenue_core import LEAGUE_VIEW, REGIONS  # noqa: F401  (task constants)

_LOBS = ", ".join(f"'{c}'" for c in REGIONS)
SQL = f"""
SELECT scenario_label, lob, lob_label, category, product_group, league, scenario, version, fiscal_year,
       period, period_type, amount, hedge, unhedged
FROM {LEAGUE_VIEW}
WHERE pl_line = 'ACX_Net Revenue'
  AND currency = 'USD_Reporting'
  AND lob IN ({_LOBS})
  AND period_type IN ('QUARTER', 'YEAR')
"""


def load() -> pd.DataFrame:
    return data._q(SQL)


def _m(x: float) -> str:
    return f"${x / 1e6:,.1f}M"


def render() -> None:
    st.subheader("Revenue by License (Global)")
    df = load()
    if df.empty:
        st.info(f"No rows returned from {LEAGUE_VIEW}.")
        return

    c1, c2, c3 = st.columns([2, 2, 1])
    region = c1.radio("Region", list(core.REGION_CHOICES), horizontal=True,
                      index=list(core.REGION_CHOICES).index(core.DEFAULT_REGION), key="licrev_region")
    opts = core.scenario_options(df)
    label = c2.selectbox("Scenario", [o[0] for o in opts], index=0, key="licrev_scenario")
    scen = dict(opts)[label]
    hedge = c3.radio("Hedge", list(core.HEDGE_CHOICES), index=0, key="licrev_hedge")
    if core.default_scenario(df) != core.PREFERRED_SCENARIO:
        st.caption(core.SCENARIO_PENDING)
    st.caption(f"Pricing go-get With/Without: {core.P2_PRICING_GOGET}")

    sel = core.select(df, region, scen, hedge)
    if sel.empty:
        st.info("No rows for this selection.")
        return
    split = core.region_split(sel)
    parts = " | ".join(f"{r} {_m(v)}" for r, v in split.items())
    st.markdown(f"**{label}, {hedge}, {region}: {_m(split.sum())}**  ({parts})")

    if scen[2] != "FY27":
        st.info(f"Budget artifact targets are FY27; not compared to {label}.")
    elif region == core.DEFAULT_REGION and hedge == "Hedged":
        gaps = core.megan_gaps(split)
        if any(abs(g["gap_pct"]) > core.GAP_WARN_PCT for g in gaps):
            st.warning("View vs Megan's artifact (FY27 hedged, ex Digital): " + "; ".join(
                f"{g['region']} view ${g['view_m']:,.1f}M vs Megan ${g['megan_m']:,.1f}M "
                f"({g['gap_m']:+,.1f}M, {g['gap_pct']:+.1%})" for g in gaps))

    bars = core.quarter_frame(sel)
    bars["value_m"] = bars["value"] / 1e6
    order = core.license_table(sel)["License"].tolist()[:-1]
    chart = alt.Chart(bars).mark_bar().encode(
        x=alt.X("period:N", sort=core.QUARTERS, title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("value_m:Q", title="Net Revenue $M"),
        color=alt.Color("league:N", sort=order, title="License", scale=alt.Scale(scheme="tableau20")),
        order=alt.Order("value_m:Q", sort="descending"),
        tooltip=[alt.Tooltip("league:N", title="License"), alt.Tooltip("period:N", title="Quarter"),
                 alt.Tooltip("value_m:Q", format=",.1f", title="$M"),
                 alt.Tooltip("share:Q", format=".1%", title="Share of quarter")])
    st.altair_chart(chart.properties(height=520), width="stretch")
    st.caption("Source: FCT_EPM.CARDPLN_PL_BY_LEAGUE_V (CardPlan, league level). Release detail "
               "(e.g. MLB Chrome) is NA only, in the Product Revenue (NA) tab.")
    st.caption("Sports - Other (PG_10000) is the sports total in CardPlan. It is shown only when "
               "no league split exists.")
    st.caption(f"International release-level detail: {core.P1_INTL_RELEASES}")

    tbl = core.license_table(sel)
    show = tbl.copy()
    for c in core.QUARTERS + ["FY"]:
        show[c] = (show[c] / 1e6).round(1)
    show.loc[show["License"].isin(core.OTHER_LIKE), "Category"] += f" ({core.P3_OTHER})"
    st.dataframe(show, hide_index=True, width="stretch",
                 column_config={c: st.column_config.NumberColumn(f"{c} $M", format="%,.1f")
                                for c in core.QUARTERS + ["FY"]})
    st.download_button("Download CSV ($)", tbl.to_csv(index=False).encode(),
                       file_name="revenue_by_license.csv", mime="text/csv", key="licrev_csv")
