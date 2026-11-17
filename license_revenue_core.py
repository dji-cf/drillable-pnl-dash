"""(DRAFT) Revenue by License (Global) -- pure pandas, no Streamlit, no Snowflake.

Shapes the rows of FCT_EPM.CARDPLN_PL_BY_LEAGUE_V (see license_revenue.SQL) into
the tab's summary, chart frame and table. Kept apart from license_revenue.py so
tools/test_license_revenue.py can test it without a Snowflake login.
"""
from __future__ import annotations

import pandas as pd

PENDING = "PENDING"

LEAGUE_VIEW = "ORACLE_DATA_PROD.FCT_EPM.CARDPLN_PL_BY_LEAGUE_V"
REGIONS = {"LB_302": "North America", "LB_303": "International", "LB_305": "Digital"}
# 'Total LOB' is larger than LB_302+LB_303+LB_305 in most scenarios (STEP 1,
# docs/fleet/cfd-license-global.md), so it is never loaded or summed.
TOTAL_LOB = "Total LOB"

REGION_CHOICES = {
    "Global (NA+Intl)": ["LB_302", "LB_303"],
    "North America": ["LB_302"],
    "International": ["LB_303"],
    "Digital": ["LB_305"],
    "All incl. Digital": ["LB_302", "LB_303", "LB_305"],
}
DEFAULT_REGION = "Global (NA+Intl)"

HEDGE_CHOICES = {"Hedged": "amount", "Un-hedged": "unhedged"}
QUARTERS = ["Q1", "Q2", "Q3", "Q4"]

# Scenario default. The task asks for "FY27 Budget" (Plan_2027 / Final), but the
# view has no Plan_2027 rows (STEP 1c, 2026-11-17). Until it lands, the default
# falls back to the FY27 Rolling Forecast (Working) -- the only FY27 scenario
# with an NA league split. One constant each, easy to change.
PREFERRED_SCENARIO = ("Plan_2027", "Final", "FY27")
FALLBACK_SCENARIO = ("Rolling Forecast", "Working", "FY27")
SCENARIO_PENDING = (f"{PENDING} - Vivek Srinivasan: Plan_2027 (FY27 Budget) is not in "
                    "CARDPLN_PL_BY_LEAGUE_V yet; showing the FY27 Rolling Forecast (Working) instead.")

# Megan Coleman's artifact, FY27 hedged, ex Digital, $M (James fwd 2026-11-17).
MEGAN_TARGETS_M = {"North America": 3976.0, "International": 1182.0}
GAP_WARN_PCT = 0.01

P1_INTL_RELEASES = (f"{PENDING} - Megan Coleman / Vivek Srinivasan: International release-level "
                    "data is not in Snowflake (Excel only).")
P2_PRICING_GOGET = f"{PENDING} - Vivek Srinivasan: no Snowflake source found for pricing go-get."
# Leagues that look like non-release buckets; listed under their own name.
OTHER_LIKE = ("Sports - Other", "Entertainment - Other")
P3_OTHER = f"{PENDING} - Megan Coleman: group into Other?"

_KIND = {"BUDGET": "Budget", "ACTUAL": "Actual", "FORECAST": "Forecast"}


def scenario_label(scenario_label: str, scenario: str, version: str, fiscal_year: str) -> str:
    kind = _KIND.get(str(scenario_label).upper(), str(scenario_label))
    if scenario == "Rolling Forecast":
        return f"{fiscal_year} Rolling Forecast ({version})"
    return f"{fiscal_year} {kind} ({scenario}, {version})"


def scenario_options(df: pd.DataFrame) -> list[tuple[str, tuple[str, str, str]]]:
    """[(label, (scenario, version, fiscal_year))], default first, then newest FY."""
    keys = (df[["scenario_label", "scenario", "version", "fiscal_year"]]
            .drop_duplicates().sort_values(["fiscal_year", "scenario"], ascending=[False, True]))
    opts = [(scenario_label(*r), (r[1], r[2], r[3])) for r in keys.itertuples(index=False)]
    default = default_scenario(df)
    return sorted(opts, key=lambda o: o[1] != default)


def default_scenario(df: pd.DataFrame) -> tuple[str, str, str]:
    have = set(map(tuple, df[["scenario", "version", "fiscal_year"]].drop_duplicates().values))
    return PREFERRED_SCENARIO if PREFERRED_SCENARIO in have else FALLBACK_SCENARIO


def select(df: pd.DataFrame, region: str, scen: tuple[str, str, str], hedge: str) -> pd.DataFrame:
    """Rows of one region choice x scenario, with a ``value`` column for the hedge pick."""
    s, v, fy = scen
    out = df[(df["lob"].isin(REGION_CHOICES[region])) & (df["lob"] != TOTAL_LOB)
             & (df["scenario"] == s) & (df["version"] == v) & (df["fiscal_year"] == fy)].copy()
    out["value"] = out[HEDGE_CHOICES[hedge]].astype(float)
    return out


def region_split(sel: pd.DataFrame) -> pd.Series:
    """FY $ per region name (YEAR rows)."""
    yr = sel[sel["period_type"] == "YEAR"]
    return yr.groupby(yr["lob"].map(REGIONS))["value"].sum()


def quarter_frame(sel: pd.DataFrame) -> pd.DataFrame:
    """license x quarter $ with share of the quarter, for the stacked bar."""
    q = sel[sel["period_type"] == "QUARTER"]
    g = q.groupby(["period", "league"], as_index=False)["value"].sum()
    g["share"] = g["value"] / g.groupby("period")["value"].transform("sum")
    return g


def license_table(sel: pd.DataFrame) -> pd.DataFrame:
    """License, Category, Q1..Q4, FY ($), sorted by FY desc, Total row last."""
    q = sel[sel["period_type"] == "QUARTER"]
    piv = q.pivot_table(index="league", columns="period", values="value", aggfunc="sum")
    piv = piv.reindex(columns=QUARTERS)
    fy = sel[sel["period_type"] == "YEAR"].groupby("league")["value"].sum()
    piv["FY"] = fy.reindex(piv.index)
    cat = sel.drop_duplicates("league").set_index("league")["category"]
    piv.insert(0, "Category", cat.reindex(piv.index))
    piv = piv.sort_values("FY", ascending=False).reset_index().rename(columns={"league": "License"})
    total = {"License": "Total", "Category": ""}
    total.update({c: piv[c].sum() for c in QUARTERS + ["FY"]})
    return pd.concat([piv, pd.DataFrame([total])], ignore_index=True)


def megan_gaps(split: pd.Series) -> list[dict]:
    """View vs Megan per region ($M, %). Only regions Megan has a target for."""
    rows = []
    for reg, tgt in MEGAN_TARGETS_M.items():
        if reg not in split.index:  # no rows: skip, never show a $0 stand-in
            continue
        view_m = float(split[reg]) / 1e6
        rows.append({"region": reg, "view_m": view_m, "megan_m": tgt,
                     "gap_m": view_m - tgt, "gap_pct": (view_m - tgt) / tgt})
    return rows
