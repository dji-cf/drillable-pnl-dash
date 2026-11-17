"""Pure pandas tests for license_revenue_core (no Streamlit, no Snowflake).

Run: python3 tools/test_license_revenue.py
"""
from __future__ import annotations

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import license_revenue_core as core  # noqa: E402

SCEN = ("Rolling Forecast", "Working", "FY27")


def _rows():
    rows = []
    spec = {("LB_302", "NFL"): 10.0, ("LB_302", "NBA"): 20.0,
            ("LB_303", "NFL"): 5.0, ("LB_305", "NFL"): 100.0, ("Total LOB", "NFL"): 9999.0}
    for (lob, lg), q in spec.items():
        for i, p in enumerate(core.QUARTERS, 1):
            amt = q * i
            rows.append(dict(scenario_label="FORECAST", lob=lob, lob_label="x", category="Sports",
                             league=lg, scenario=SCEN[0], version=SCEN[1], fiscal_year=SCEN[2],
                             period=p, period_type="QUARTER", amount=amt, hedge=-1.0, unhedged=amt + 1))
        rows.append(dict(scenario_label="FORECAST", lob=lob, lob_label="x", category="Sports",
                         league=lg, scenario=SCEN[0], version=SCEN[1], fiscal_year=SCEN[2],
                         period="YearTotal", period_type="YEAR", amount=q * 10, hedge=-4.0,
                         unhedged=q * 10 + 4))
    return pd.DataFrame(rows)


def test_quarters_pivot():
    t = core.license_table(core.select(_rows(), "North America", SCEN, "Hedged"))
    nba = t[t["License"] == "NBA"].iloc[0]
    assert [nba[q] for q in core.QUARTERS] == [20, 40, 60, 80]
    assert nba["FY"] == 200
    assert t["License"].tolist() == ["NBA", "NFL", "Total"]


def test_total_row_is_sum():
    t = core.license_table(core.select(_rows(), "Global (NA+Intl)", SCEN, "Hedged"))
    body, tot = t.iloc[:-1], t.iloc[-1]
    assert tot["License"] == "Total"
    for c in core.QUARTERS + ["FY"]:
        assert tot[c] == body[c].sum()
    assert tot["FY"] == 100 + 200 + 50


def test_hedge_pick():
    df = _rows()
    h = core.region_split(core.select(df, "North America", SCEN, "Hedged")).sum()
    u = core.region_split(core.select(df, "North America", SCEN, "Un-hedged")).sum()
    assert h == 300 and u == 308


def test_digital_excluded_from_global():
    split = core.region_split(core.select(_rows(), "Global (NA+Intl)", SCEN, "Hedged"))
    assert "Digital" not in split.index and split.sum() == 350
    allin = core.region_split(core.select(_rows(), "All incl. Digital", SCEN, "Hedged"))
    assert allin["Digital"] == 1000


def test_total_lob_never_summed():
    df = _rows()
    for region in core.REGION_CHOICES:
        sel = core.select(df, region, SCEN, "Hedged")
        assert core.TOTAL_LOB not in sel["lob"].unique()
        assert sel["value"].max() < 9999
    assert core.TOTAL_LOB not in [c for v in core.REGION_CHOICES.values() for c in v]


def test_default_scenario_fallback():
    assert core.default_scenario(_rows()) == core.FALLBACK_SCENARIO


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                fails += 1
                print(f"FAIL {name}: {e!r}")
    sys.exit(1 if fails else 0)
