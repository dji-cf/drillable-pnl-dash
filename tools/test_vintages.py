"""Offline checks of the vintage rules -- labels, ordering, retirement, YTD.

No Snowflake. Builds a cube from a synthetic frame shaped like MASTER_SQL's
output, at two points in time, so the year-boundary behaviour can be asserted
today rather than discovered in January:

  OCT 2026   2025A complete, 2026A partial (Jan-Aug), 2026B, an FY25 forecast,
             and the Aug/Sep 2026 FCs.
  JAN 2027   2026A now complete, 2027B landed, the first FY27 forecast either
             absent (the gap week) or present.

    .venv\\Scripts\\python.exe tools\\test_vintages.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

import queries  # noqa: E402
import table  # noqa: E402
import transforms as tx  # noqa: E402

#: (key, scenario_label, fiscal_year, months present, months actual)
Vintage = tuple[str, str, str, int, int]


def _frame(vintages: list[Vintage]) -> pd.DataFrame:
    """MASTER_SQL-shaped rows. Every segment of month m is worth m * $1M, so a
    YTD is a triangular number and an annual total is 78 (x $1M)."""
    recs = []
    for key, label, fy, n_months, n_actual in vintages:
        months = tx.MONTHS[:n_months]
        for line in queries.PL_LINES.values():
            def rec(ptype: str, period: str, amount: float, actual) -> dict:
                r = {"vintage_key": key, "scenario_label": label, "fiscal_year": fy,
                     "period": period, "period_type": ptype, "pl_line": line,
                     "is_actual_month": actual}
                r.update({f"seg_{k}": amount for k in queries.SEGMENTS})
                return r
            for i, m in enumerate(months, start=1):
                recs.append(rec("MONTH", m, i * 1e6, i <= n_actual))
            for q, qm in tx.QUARTER_MONTHS.items():
                present = [tx.MONTHS.index(m) + 1 for m in qm if m in months]
                if present:
                    recs.append(rec("QUARTER", q, sum(present) * 1e6, None))
            recs.append(rec("YEAR", "YearTotal",
                            sum(range(1, n_months + 1)) * 1e6, None))
    df = pd.DataFrame(recs)
    df["is_actual_month"] = df["is_actual_month"].astype("boolean")
    return df


OCT_2026: list[Vintage] = [
    ("2025A", "ACTUAL", "FY25", 12, 12),
    ("2026A", "ACTUAL", "FY26", 8, 8),
    ("2026B", "BUDGET", "FY26", 12, 0),
    ("Dec 2025 FC", "FORECAST", "FY25", 12, 11),
    ("Aug 2026 FC", "FORECAST", "FY26", 12, 7),
    ("Sep 2026 FC", "FORECAST", "FY26", 12, 8),
]

JAN_2027_NO_FC: list[Vintage] = [
    ("2025A", "ACTUAL", "FY25", 12, 12),
    ("2026A", "ACTUAL", "FY26", 12, 12),
    ("2026B", "BUDGET", "FY26", 12, 0),
    ("2027B", "BUDGET", "FY27", 12, 0),
    ("Sep 2026 FC", "FORECAST", "FY26", 12, 8),
    ("Dec 2026 FC", "FORECAST", "FY26", 12, 11),
]

JAN_2027 = JAN_2027_NO_FC + [("Jan 2027 FC", "FORECAST", "FY27", 12, 0),
                             ("Feb 2027 FC", "FORECAST", "FY27", 12, 1)]

#: 2027B lands while FY26 actuals are still open (Jan-Nov closed).
DEC_2026_EARLY_BUDGET: list[Vintage] = [
    ("2025A", "ACTUAL", "FY25", 12, 12),
    ("2026A", "ACTUAL", "FY26", 11, 11),
    ("2026B", "BUDGET", "FY26", 12, 0),
    ("2027B", "BUDGET", "FY27", 12, 0),
    ("Nov 2026 FC", "FORECAST", "FY26", 12, 10),
    ("Dec 2026 FC", "FORECAST", "FY26", 12, 11),
]


def check(problems: list[str], cond: bool, msg: str) -> None:
    if not cond:
        problems.append(msg)


def check_labels() -> list[str]:
    p: list[str] = []
    for key, want in (("2025A", "2025 Actuals"), ("2026B", "2026 Budget"),
                      ("2031A", "2031 Actuals"), ("Sep 2026 FC", "Sep 2026 FC"),
                      ("Jan 2027 FC", "Jan 2027 FC")):
        check(p, tx.vintage_label(key) == want,
              f"vintage_label({key!r}) = {tx.vintage_label(key)!r}, want {want!r}")
    for key in ("2025A", "2026A", "2026B"):
        check(p, "(PY)" not in tx.vintage_label(key) and "partial" not in
              tx.vintage_label(key).lower(), f"{key} label carries a relative qualifier")
    check(p, tx.change_label("Aug 2026 FC") == "Change vs. Aug 2026 FC",
          f"change_label: {tx.change_label('Aug 2026 FC')!r}")
    check(p, tx.change_label("2025A") == "Change vs. 2025 Actuals",
          f"change_label: {tx.change_label('2025A')!r}")
    check(p, tx.vintage_parts("Jul. FC") is None, "old key format still parses")
    check(p, tx.vintage_label("Jul. FC") == "Jul. FC", "unknown key not passed through")
    check(p, tx.vintage_color("Sep 2026 FC") == tx.vintage_color("Sep 2027 FC"),
          "forecast color should follow as-of month")
    check(p, tx.vintage_color("2025A") != tx.vintage_color("2026A"),
          "adjacent Actuals years share a color")
    return p


def check_ordering() -> list[str]:
    p: list[str] = []
    keys = ["Jan 2027 FC", "2026B", "Dec 2026 FC", "2027B", "2025A", "Sep 2026 FC",
            "2026A"]
    got = tx.order_vintages(keys)
    want = ["2025A", "2026A", "2026B", "2027B", "Sep 2026 FC", "Dec 2026 FC",
            "Jan 2027 FC"]
    check(p, got == want, f"order_vintages: {got}")
    check(p, tx.order_vintages(["x", "2025A", "y"]) == ["2025A", "x", "y"],
          "unknown keys should sort last, in input order")
    return p


def check_oct_2026() -> list[str]:
    p: list[str] = []
    cube = tx.build_cube(_frame(OCT_2026))

    check(p, cube.final_years == frozenset({"FY25"}), f"final_years {cube.final_years}")
    check(p, cube.is_retired("Dec 2025 FC"), "FY25 forecast not retired")
    check(p, not cube.is_retired("2025A"), "Actuals must never retire")
    check(p, not cube.is_retired("2026B"), "open-year Budget retired")

    vis = cube.visible()
    check(p, "2026A" not in vis, "partial-year Actuals offered")
    check(p, "Dec 2025 FC" not in vis, "retired forecast offered by default")
    check(p, "Dec 2025 FC" in cube.visible(include_retired=True), "toggle does not restore")
    check(p, "2026A" not in cube.visible(include_retired=True),
          "toggle restored partial Actuals")

    fc = tx.forecast_options(cube)
    check(p, fc == ["Sep 2026 FC", "Aug 2026 FC"], f"forecast_options {fc}")
    check(p, tx.forecast_options(cube, True) == ["Sep 2026 FC", "Aug 2026 FC",
                                                 "Dec 2025 FC"],
          f"forecast_options(retired) {tx.forecast_options(cube, True)}")
    comp = tx.comp_options(cube, "Sep 2026 FC")
    check(p, comp == ["", "2026B", "2025A", "Aug 2026 FC"], f"comp_options {comp}")

    # YTD column, every grain, just before FY.
    for grain, n in (("annual", 2), ("quarterly", 6), ("monthly", 14)):
        periods = cube.periods("Sep 2026 FC", grain)
        check(p, len(periods) == n, f"{grain}: {len(periods)} periods, want {n}")
        check(p, periods[-2] == ("YTD:Aug", "YTD Aug 26A"),
              f"{grain}: YTD column {periods[-2]}")
    check(p, cube.ytd_period("2026B") is None, "Budget got a YTD column")
    check(p, cube.ytd_period("2025A") is None, "complete Actuals got a YTD column")

    rev = tx.ROWS[6]                                   # Total Revenue
    n_terms = len(queries.STG_ROW_MAP[(rev.section, rev.label)]) \
        if queries.SOURCE == "STG" else 3
    want_ytd = sum(range(1, 9)) * 1e6 * n_terms        # Jan..Aug
    got_ytd = cube.value("Sep 2026 FC", rev, "YTD:Aug")
    check(p, got_ytd is not None and abs(got_ytd - want_ytd) < 1e-6,
          f"YTD revenue {got_ytd} != {want_ytd}")
    check(p, cube.value("2026B", rev, "YTD:Aug") == got_ytd,
          "comparison YTD not summed over the forecast's months")
    full = cube.value("2025A", rev, "YTD:Dec")
    check(p, full == cube.value("2025A", rev, tx.ANNUAL), "YTD:Dec != annual")
    margin = next(r for r in tx.ROWS if r.is_pct)
    check(p, cube.value("Sep 2026 FC", margin, "YTD:Aug") is not None,
          "margin YTD missing")

    # Greying: same year's actuals on both sides only.
    for pk, want in (("Jul", True), ("Aug", False), ("Q2", True), ("Q3", False),
                     ("YTD:Aug", False), (tx.ANNUAL, False)):
        got = cube.same_actuals("Sep 2026 FC", "Aug 2026 FC", pk)
        check(p, got == want, f"same_actuals(Sep FC, Aug FC, {pk}) = {got}")
    check(p, not cube.same_actuals("Sep 2026 FC", "2026B", "Jan"), "Budget greyed")
    check(p, not cube.same_actuals("Sep 2026 FC", "2025A", "Jan"), "prior year greyed")

    html = table.build_statement(cube, forecast="Sep 2026 FC", comp="Aug 2026 FC",
                                 grain="monthly", collapsed={})
    check(p, "Change vs. Aug 2026 FC" in html, "change header missing")
    check(p, "Period-over-Period" not in html, "old change header still rendered")
    # Jan-Jul greyed on every derivable row (a LEGACY placeholder row keeps its
    # plain em-dash: it has no figure on either side to be "the same").
    want = 7 * sum(1 for r in tx.ROWS if r.is_derivable)
    check(p, html.count("gact") == want,
          f"{html.count('gact')} greyed cells, want {want}")
    check(p, html.count("ph-act") == 7, f"{html.count('ph-act')} greyed headers")
    html_b = table.build_statement(cube, forecast="Sep 2026 FC", comp="2026B",
                                   grain="monthly", collapsed={})
    check(p, "gact" not in html_b, "vs. Budget greyed a cell")

    # The % / $ toggle sits in the change header and marks the active mode.
    check(p, 'Change vs. Aug 2026 FC<span class="dmode"' in html,
          "toggle not in the change header")
    check(p, 'data-mode="pct" class="on"' in html, "pct not marked active")
    usd = table.build_statement(cube, forecast="Sep 2026 FC", comp="Aug 2026 FC",
                                grain="annual", collapsed={}, delta_mode="usd")
    check(p, 'data-mode="usd" class="on"' in usd and 'data-mode="pct" class="on"'
          not in usd, "usd not marked active")
    solo = table.build_statement(cube, forecast="Sep 2026 FC", comp="",
                                 grain="annual", collapsed={})
    check(p, "dmode" not in solo, "toggle rendered with no comparison")
    return p


def check_jan_2027() -> list[str]:
    p: list[str] = []
    gap = tx.build_cube(_frame(JAN_2027_NO_FC))
    check(p, gap.final_years == frozenset({"FY25", "FY26"}), f"{gap.final_years}")
    for v in ("2026B", "Sep 2026 FC", "Dec 2026 FC"):
        check(p, gap.is_retired(v), f"{v} not retired once FY26 is final")
    check(p, "2026A" in gap.visible(), "completed FY26 Actuals not offered")
    check(p, tx.forecast_options(gap) == ["2027B"],
          f"gap-week fallback {tx.forecast_options(gap)}")

    cube = tx.build_cube(_frame(JAN_2027))
    fc = tx.forecast_options(cube)
    check(p, fc == ["Feb 2027 FC", "Jan 2027 FC"], f"forecast_options {fc}")
    comp = tx.comp_options(cube, "Feb 2027 FC")
    check(p, comp == ["", "2027B", "2026A", "2025A", "Jan 2027 FC"],
          f"comp_options {comp}")
    check(p, cube.year("Feb 2027 FC") == "2027", "header year")
    check(p, cube.periods("Feb 2027 FC", "annual")[0] == ("YTD:Jan", "YTD Jan 27A"),
          f"{cube.periods('Feb 2027 FC', 'annual')}")
    check(p, cube.ytd_period("Jan 2027 FC") is None, "no closed month, still a YTD")
    # Prior-year comparison is a real variance, never greyed.
    check(p, not cube.same_actuals("Feb 2027 FC", "2026A", "Jan"), "PY greyed")
    return p


def check_newest_budget() -> list[str]:
    p: list[str] = []
    cube = tx.build_cube(_frame(DEC_2026_EARLY_BUDGET))
    check(p, "FY26" not in cube.final_years, "FY26 should still be open")
    check(p, cube.newest_budget == "2027B", f"newest_budget {cube.newest_budget}")
    vis = cube.visible()
    check(p, "2027B" in vis and "2026B" not in vis,
          f"only the newest Budget should be offered: {vis}")
    check(p, "2026B" in cube.visible(include_retired=True), "toggle does not restore 2026B")
    comp = tx.comp_options(cube, "Dec 2026 FC")
    check(p, [k for k in comp if k.endswith("B")] == ["2027B"], f"comp_options {comp}")
    oct_cube = tx.build_cube(_frame(OCT_2026))
    check(p, "2026B" in oct_cube.visible(), "single Budget hidden")
    return p


def check_delta_modes() -> list[str]:
    p: list[str] = []
    cases = [
        ((142e6, 100e6, False, True, "pct"), "+42%", "gpos"),
        ((142e6, 100e6, False, True, "usd"), "+$42", "gpos"),
        ((95e6, 100e6, False, True, "usd"), "($5)", "gneg"),
        ((100.3e6, 100e6, False, True, "usd"), "$0", "gflat"),
        ((100e6, 0.0, False, True, "usd"), "+$100", "gpos"),
        ((100e6, 0.0, False, True, "pct"), tx.EM_DASH, "gflat"),
        ((0.5476, 0.4617, True, True, "usd"), "+859 bps", "gpos"),
        ((0.5476, 0.4617, True, True, "pct"), "+859 bps", "gpos"),
    ]
    for args, text, cls in cases:
        got = tx.delta_fmt(*args)
        check(p, got == {"text": text, "cls": cls}, f"delta_fmt{args} = {got}")
    tile = tx.delta_fmt(-120e6, 0.0, False, mode="usd", usd_suffix="M")
    check(p, tile and tile["text"] == "($120M)", f"tile usd {tile}")
    check(p, tx.delta_value(142.0, 100.0, False) == 0.42, "delta_value pct")
    check(p, tx.delta_value(142.0, 100.0, False, "usd") == 42.0, "delta_value usd")
    return p


def check_trends() -> list[str]:
    """The vintage rules behind the Trends charts, and the bridge arithmetic."""
    p: list[str] = []
    cube = tx.build_cube(_frame(OCT_2026))
    fc = "Sep 2026 FC"

    got = tx.outlook_vintages(cube, fc)
    check(p, got == ["2026B", "Aug 2026 FC", "Sep 2026 FC"], f"outlook_vintages {got}")
    check(p, tx.outlook_vintages(cube, "Aug 2026 FC") == got,
          "an older forecast truncated the year")
    check(p, tx.outlook_vintages(cube, "Dec 2025 FC", True) == ["Dec 2025 FC"],
          f"FY25 outlook {tx.outlook_vintages(cube, 'Dec 2025 FC', True)}")
    check(p, tx.prior_forecast(cube, fc) == "Aug 2026 FC", "prior_forecast")
    check(p, tx.prior_forecast(cube, "Aug 2026 FC") is None,
          "first forecast of the year has a prior")
    check(p, tx.year_budget(cube, fc) == "2026B", "year_budget")
    check(p, tx.year_budget(cube, "Dec 2025 FC") is None, "FY25 has no budget here")
    check(p, tx.prior_year_actuals(cube, fc) == "2025A", "prior_year_actuals")
    check(p, tx.prior_year_actuals(cube, "Dec 2025 FC") is None,
          "2024A is not in the cube")
    check(p, tx.default_lines(cube, fc, "") == ["2026B", "Aug 2026 FC", fc],
          f"default_lines, no comp {tx.default_lines(cube, fc, '')}")
    check(p, tx.default_lines(cube, fc, "2025A") == ["2025A", "2026B", fc],
          f"default_lines vs PY {tx.default_lines(cube, fc, '2025A')}")
    check(p, tx.default_lines(cube, fc, "2026B") == ["2026B", fc],
          f"default_lines vs Budget {tx.default_lines(cube, fc, '2026B')}")

    gap = tx.build_cube(_frame(JAN_2027_NO_FC))
    check(p, tx.default_lines(gap, "2027B", "") == ["2027B"],
          f"gap-week default_lines {tx.default_lines(gap, '2027B', '')}")
    check(p, tx.outlook_vintages(gap, "2027B") == ["2027B"], "gap-week outlook")
    check(p, tx.prior_year_actuals(gap, "2027B") == "2026A", "gap-week PY")

    # start + every step == end, for every dollar total and subtotal, at every
    # period the charts offer, against each kind of comparison.
    for comp in ("Aug 2026 FC", "2026B", "2025A"):
        for row in tx.ROWS:
            if row.is_pct or row.row_type == "sub" or not row.is_derivable:
                continue
            for period in tx.TREND_PERIODS:
                b = tx.bridge(cube, row, fc, comp, period)
                if b is None:
                    p.append(f"bridge row{row.idx} vs {comp} {period}: None")
                    continue
                gap_m = abs(b.start + sum(s.delta for s in b.steps) - b.end) / 1e6
                check(p, gap_m < 0.5,
                      f"bridge row{row.idx} vs {comp} {period} misses by ${gap_m:.2f}M")
                check(p, b.parent is row, f"bridge row{row.idx} parent {b.parent.idx}")
                check(p, not any(s.highlight for s in b.steps),
                      f"bridge row{row.idx}: a total highlighted a step")
    check(p, tx.bridge(cube, tx.ROWS[6], fc, "", tx.ANNUAL) is None, "bridge with no comp")
    check(p, tx.bridge(cube, tx.ROWS[13], fc, "2026B", tx.ANNUAL) is None,
          "bridge of a % row")
    sub = tx.bridge(cube, tx.ROWS[0], fc, "2026B", tx.ANNUAL)    # Revenue NA
    check(p, sub is not None and sub.parent.idx == 6, "a detail row bridges its total")
    check(p, sub is not None and [s.label for s in sub.steps if s.highlight]
          == ["North America"], "the detail row is not the highlighted step")
    phys = tx.bridge(cube, tx.ROWS[17], fc, "2026B", tx.ANNUAL)  # EBITDA Total Phys
    check(p, phys is not None and [s.label for s in phys.steps][:3]
          == ["North America", "International", "Eliminations"],
          f"Total Physical EBITDA children {phys and [s.label for s in phys.steps]}")
    return p


def main() -> None:
    suites = (
        ("LABELS", check_labels()),
        ("ORDERING", check_ordering()),
        ("OCT 2026", check_oct_2026()),
        ("JAN 2027", check_jan_2027()),
        ("NEWEST BUDGET", check_newest_budget()),
        ("DELTA MODES", check_delta_modes()),
        ("TRENDS", check_trends()),
    )
    failed = False
    for name, problems in suites:
        print(f"{name:<12} {'FAIL' if problems else 'pass'}")
        for msg in problems:
            print(f"  {msg}")
        failed |= bool(problems)
    print("\n" + ("FAILED" if failed else "ALL VINTAGE CHECKS PASS"))
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
