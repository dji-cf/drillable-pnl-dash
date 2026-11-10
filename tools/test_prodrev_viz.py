"""Pure tests for prodrev_viz (no streamlit, no Snowflake, no app file).

Run: python3 tools/test_prodrev_viz.py
"""
from __future__ import annotations

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import prodrev_viz as viz  # noqa: E402

EDGES = (10e6, 25e6, 35e6, 50e6)


def _df(rows):
    return pd.DataFrame(rows, columns=["coa", "fiscal_year", "period_date", "net_rev"]).assign(
        period_date=lambda d: pd.to_datetime(d["period_date"]))


def test_prefix_rule():
    assert viz.license_from_coa("NFL2418") == "NFL"
    assert viz.license_from_coa("wwe2601") == "WWE"
    for c in ("10003", "UNKNOWN", "PD02624", "", None):
        assert viz.license_from_coa(c) == viz.OTHER, c


def test_bar_pct_excludes_other():
    df = _df([("NBA2601", "FY26", "2026-01-01", 60.0),
              ("NFL2601", "FY26", "2026-02-01", 40.0),
              ("10003", "FY26", "2026-03-01", 100.0)])
    s = viz.quarter_summary(df).iloc[0]
    assert (s["total"], s["release"], s["other"]) == (200.0, 100.0, 100.0)
    b = viz.bar_frame(df, "license", EDGES).set_index("segment")
    assert abs(b.loc["NBA", "pct"] - 0.60) < 1e-12  # 60 / 100 release, not / 200
    assert abs(b.loc["Other", "pct"] - 0.50) < 1e-12
    assert b.loc["Other", "stack"] == 0 and b.loc["Other", "y0"] == 0  # bottom block
    assert b["net_rev"].sum() == 200.0  # bar = quarter total incl. Other


def test_chip_pct():
    df = _df([("NBA2601", "FY26", "2026-01-01", 25.0),
              ("NBA2601", "FY26", "2026-04-01", 75.0)])
    s = viz.quarter_summary(df).set_index("quarter")
    assert s.loc["Q1'26", "chip_pct"] == 0.25 and s.loc["Q2'26", "chip_pct"] == 0.75


def test_tier_edges():
    assert viz.tier_labels(EDGES) == ["<10M", "10-25M", "25-35M", "35-50M", "Tentpole"]
    cases = {9_999_999.99: "<10M", 10e6: "10-25M", 24.9e6: "10-25M", 25e6: "25-35M",
             35e6: "35-50M", 49.99e6: "35-50M", 50e6: "Tentpole", -5e6: "<10M"}
    for amt, want in cases.items():
        assert viz.size_tier(amt, EDGES) == want, (amt, want)


def test_peak_quarter_count():
    df = _df([("WWE2601", "FY26", "2026-01-01", 5.0),
              ("WWE2601", "FY26", "2026-04-01", 9.0),   # peak Q2
              ("WWE2602", "FY26", "2026-04-01", 3.0),   # peak Q2
              ("NBA2601", "FY26", "2026-01-01", 7.0),
              ("NBA2601", "FY26", "2026-07-01", 7.0),   # tie -> earlier (Q1)
              ("10003", "FY26", "2026-01-01", 50.0)])   # Other: never counted
    c = viz.release_counts(df).set_index(["quarter", "coa_license"])["releases"].to_dict()
    assert c == {("Q2'26", "WWE"): 2, ("Q1'26", "NBA"): 1}, c
    b = viz.bar_frame(df, "license", EDGES)
    assert "WWE 100.0% · 2" in b["label"].tolist()


def test_tier_view_pct():
    df = _df([("NBA2601", "FY26", "2026-01-01", 60e6),
              ("NFL2601", "FY26", "2026-01-01", 20e6),
              ("10003", "FY26", "2026-01-01", 20e6)])
    b = viz.bar_frame(df, "tier", EDGES).set_index("segment")
    assert abs(b.loc["Tentpole", "pct"] - 0.75) < 1e-12
    assert abs(b.loc["10-25M", "pct"] - 0.25) < 1e-12


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"{len(tests)} passed")
