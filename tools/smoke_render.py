"""Render smoke test: exercise every builder without a browser.

Catches the class of bug a visual check tends to miss -- a malformed Vega-Lite
spec, a wrong column count, a placeholder row that leaks a live figure -- and
does it for every combination of grain x comparison.

The placeholder checks run BOTH ways off transforms.Row.is_derivable, never off
hardcoded row indices: a row that cannot be derived must print no figure, and a
row that can must print one. The second direction is what guards the removal of
the old diagnostic toggle -- every cost row now shows its live value.

    .venv\\Scripts\\python.exe tools\\smoke_render.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import snowflake.connector  # noqa: E402

import charts  # noqa: E402
import queries  # noqa: E402
import table  # noqa: E402
import transforms as tx  # noqa: E402

CONN_NAME = os.getenv("SNOWFLAKE_DEFAULT_CONNECTION_NAME", "HIDR_PROD")

#: Data columns at each grain, with and without a comparison. Periods are the
#: sub-periods plus the always-appended FY column; a comparison triples them
#: (comparison | current | delta).
EXPECTED_PERIODS = {"annual": 1, "quarterly": 5, "monthly": 13}


def fetch() -> pd.DataFrame:
    conn = snowflake.connector.connect(connection_name=CONN_NAME)
    try:
        cur = conn.cursor()
        cur.execute("USE SECONDARY ROLES NONE")
        cur.execute(queries.MASTER_SQL)
        df = cur.fetch_pandas_all()
    finally:
        conn.close()
    df.columns = [c.lower() for c in df.columns]
    for col in [f"seg_{k}" for k in queries.SEGMENTS]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["is_actual_month"] = df["is_actual_month"].astype("boolean")
    return df


def body_rows(html: str) -> list[str]:
    body = html.split("<tbody>", 1)[1].rsplit("</tbody>", 1)[0]
    return [m for m in re.findall(r"<tr\b.*?</tr>", body, flags=re.S)]


#: Markup the old diagnostic view produced. None of it may survive anywhere.
DEAD_MARKUP: tuple[str, ...] = ("gap-badge", "var-badge", "diag-row",
                                "tile-note", "tile gapped", "footnotes")


def check_grid(cube: tx.Cube) -> list[str]:
    problems: list[str] = []
    forecast = "Jul. FC" if "Jul. FC" in cube.vintages else cube.vintages[-1]
    comp_choice = "2026B" if "2026B" in cube.vintages else ""

    for grain, n_periods in EXPECTED_PERIODS.items():
        for comp in ("", comp_choice):
            collapsed = {s: False for s in tx.SECTIONS_WITH_HEADER}
            html = table.build_statement(
                cube,
                forecast=forecast, comp=comp, grain=grain,
                collapsed=collapsed,
            )
            tag = f"{grain}/{'comp' if comp else 'solo'}"

            want_data = n_periods * (3 if comp else 1)
            want_cells = want_data + 1          # + the sticky label column

            rows = body_rows(html)
            data_rows = [r for r in rows if "section-hdr" not in r]
            if len(data_rows) != 26:
                problems.append(f"{tag}: {len(data_rows)} data rows, expected 26")
            hdr_rows = [r for r in rows if "section-hdr" in r]
            if len(hdr_rows) != 3:
                problems.append(f"{tag}: {len(hdr_rows)} section headers, expected 3")

            for r in data_rows[:1] + data_rows[-1:]:
                n = len(re.findall(r"<td\b", r))
                if n != want_cells:
                    problems.append(
                        f"{tag}: row has {n} cells, expected {want_cells}"
                    )

            n_period_th = len(re.findall(r'<th class="ph-', html))
            if n_period_th != want_data:
                problems.append(
                    f"{tag}: {n_period_th} period headers, expected {want_data}"
                )

            for dead in DEAD_MARKUP:
                if dead in html:
                    problems.append(f"{tag}: '{dead}' is still rendered")

            if 'class="lbl"' not in data_rows[0]:
                problems.append(f"{tag}: first data row has no sticky label cell")

            # Placeholder discipline, both directions, derived from the registry
            # rather than hardcoded so it keeps covering the right rows if GAPS
            # changes. Currently the withheld four are 19/23 (no expression) and
            # 10/18 (expression over a broken residual).
            #
            # Tested against the em-dash rather than a leading-character class:
            # fmt_m parenthesises negatives, so rows 21 and 22 render '($33)'
            # and a `[$\-0-9]` probe reads them as blank.
            for idx, r_row in enumerate(tx.ROWS):
                cells = re.findall(
                    r'<td class="curr-cell[^"]*">(.*?)</td>', data_rows[idx]
                )
                if not cells:
                    problems.append(f"{tag}: row{idx} has no current-period cells")
                    continue
                figures = [c for c in cells if c != tx.EM_DASH]
                if r_row.is_derivable and not figures:
                    problems.append(
                        f"{tag}: row{idx} ({r_row.label}) is derivable but "
                        f"prints no figure in any period"
                    )
                elif not r_row.is_derivable and figures:
                    problems.append(
                        f"{tag}: row{idx} ({r_row.label}) shows {figures[:3]} "
                        f"but cannot be derived"
                    )

    # Collapse actually hides the detail rows, and only the detail rows.
    collapsed = {s: True for s in tx.SECTIONS_WITH_HEADER}
    html = table.build_statement(
        cube, forecast=forecast, comp="", grain="annual", collapsed=collapsed,
    )
    rows = [r for r in body_rows(html) if "section-hdr" not in r]
    hidden = [r for r in rows if "collapsed" in r]
    expected_hidden = sum(
        1 for r in tx.ROWS
        if r.row_type == "sub" and r.section in tx.SECTIONS_WITH_HEADER
    )
    if len(hidden) != expected_hidden:
        problems.append(
            f"collapse-all: {len(hidden)} hidden rows, expected {expected_hidden}"
        )
    for r in rows:
        if "collapsed" in r and ("row-total" in r or "row-subtotal" in r):
            problems.append("collapse-all: a subtotal/total row was hidden")
    if "&#9654;" not in html:
        problems.append("collapse-all: closed caret not rendered")

    return problems


def check_tiles(cube: tx.Cube) -> list[str]:
    problems: list[str] = []
    forecast = "Jul. FC" if "Jul. FC" in cube.vintages else cube.vintages[-1]
    html = table.build_tiles(cube, forecast=forecast, comp="2026B")
    if html.count('class="tile') < 3:
        problems.append("tiles: fewer than 3 tiles")
    # All three tile rows are derivable, so none may read as a muted dash --
    # Total EBITDA and EBITDA Margin used to, until the toggle was removed.
    if html.count("tile-val muted") != 0:
        problems.append(
            f"tiles: expected no muted tiles, got {html.count('tile-val muted')}"
        )
    for dead in DEAD_MARKUP:
        if dead in html:
            problems.append(f"tiles: '{dead}' is still rendered")
    if "$5.18B" not in html:
        problems.append("tiles: Jul. FC revenue tile is not $5.18B")
    return problems


def check_charts(cube: tx.Cube) -> list[str]:
    """Every metric x grain must produce a valid Vega-Lite spec."""
    problems: list[str] = []
    vintages = [v for v in ("2025A", "2026B", "Jul. FC") if v in cube.vintages]

    cases = [
        ("annual", []),
        ("quarterly", ["Q1"]),
        ("quarterly", list(tx.QUARTERS)),
        ("monthly", ["Jan"]),
        ("monthly", list(tx.MONTHS)),
    ]
    for row in tx.ROWS:
        for grain, subs in cases:
            try:
                spec = charts.build(cube, row, vintages, grain, subs).to_dict()
            except Exception as exc:  # noqa: BLE001
                problems.append(
                    f"row{row.idx} ({row.metric_label}) {grain}: {type(exc).__name__}: {exc}"
                )
                continue
            if not isinstance(spec, dict) or not spec:
                problems.append(f"row{row.idx} {grain}: empty spec")

    # Degenerate inputs must not raise.
    for grain, subs in (("annual", []), ("monthly", ["Jan"])):
        try:
            charts.build(cube, tx.ROWS[6], [], grain, subs).to_dict()
        except Exception as exc:  # noqa: BLE001
            problems.append(f"no-vintages {grain}: {type(exc).__name__}: {exc}")
    try:
        charts.build(cube, tx.ROWS[6], vintages, "monthly", []).to_dict()
    except Exception as exc:  # noqa: BLE001
        problems.append(f"no-subs monthly: {type(exc).__name__}: {exc}")

    # The deck's is_pct bug: a percent metric must be labelled '%', not '$'.
    pct_spec = charts.build(cube, tx.ROWS[13], vintages, "annual", []).to_dict()
    if '%' not in str(pct_spec.get("layer", pct_spec)):
        problems.append("row13 (Total Gross Margin %) is not labelled as a percent")
    if charts.bar_label(54.76, True) != "55%":
        problems.append(f"bar_label pct: {charts.bar_label(54.76, True)!r} != '55%'")
    if charts.bar_label(5184.0, False) != "$5.2B":
        problems.append(f"bar_label $B: {charts.bar_label(5184.0, False)!r} != '$5.2B'")
    if charts.bar_label(458.0, False) != "$458":
        problems.append(f"bar_label $M: {charts.bar_label(458.0, False)!r} != '$458'")
    return problems


def check_periods(cube: tx.Cube) -> list[str]:
    """Period labels must reproduce the deck for Jul. FC and be honest elsewhere."""
    problems: list[str] = []

    if "Jul. FC" in cube.vintages:
        want_months = ["Jan 26A", "Feb 26A", "Mar 26A", "Apr 26A", "May 26A",
                       "Jun 26A", "Jul 26F", "Aug 26F", "Sep 26F", "Oct 26F",
                       "Nov 26F", "Dec 26F"]
        got = [lbl for pk, lbl in cube.periods("Jul. FC", "monthly")
               if pk != tx.ANNUAL]
        if got != want_months:
            problems.append(f"Jul. FC month labels {got} != deck MONTH_LBL")

        want_q = ["Q1 26A", "Q2 26A", "Q3 26F", "Q4 26F"]
        got_q = [lbl for pk, lbl in cube.periods("Jul. FC", "quarterly")
                 if pk != tx.ANNUAL]
        if got_q != want_q:
            problems.append(f"Jul. FC quarter labels {got_q} != deck Q_LBL")

        annual = cube.periods("Jul. FC", "annual")[0][1]
        if annual != "FY 2026F":
            problems.append(f"Jul. FC annual label {annual!r} != 'FY 2026F'")

    # The correction: Jan. FC must NOT claim Jan-Jun are actuals.
    if "Jan. FC" in cube.vintages:
        labels = [lbl for pk, lbl in cube.periods("Jan. FC", "monthly")
                  if pk != tx.ANNUAL]
        actuals = [l for l in labels if l.endswith("A")]
        if len(actuals) != 0:
            problems.append(
                f"Jan. FC shows {len(actuals)} actual months ({actuals}); "
                f"as-of 2026-01-31 means none are"
            )

    # The partial year must not fabricate periods.
    if tx.PARTIAL_VINTAGE in cube.vintages:
        months = cube.months_present[tx.PARTIAL_VINTAGE]
        quarters = cube.quarters_present[tx.PARTIAL_VINTAGE]
        if len(months) != 7:
            problems.append(f"{tx.PARTIAL_VINTAGE}: {len(months)} months, expected 7")
        if list(quarters) != ["Q1", "Q2", "Q3"]:
            problems.append(f"{tx.PARTIAL_VINTAGE}: quarters {list(quarters)}")
        if not cube.is_partial(tx.PARTIAL_VINTAGE):
            problems.append(f"{tx.PARTIAL_VINTAGE} not reported as partial")
    return problems


def check_dropdowns(cube: tx.Cube) -> list[str]:
    problems: list[str] = []
    fc = tx.forecast_options(cube.vintages)
    if fc[0] != "Aug. FC":
        problems.append(f"forecast options start with {fc[0]!r}, expected 'Aug. FC'")
    if fc[-1] != tx.PARTIAL_VINTAGE:
        problems.append(f"forecast options end with {fc[-1]!r}")

    comp = tx.comp_options(cube.vintages, "Jul. FC")
    if comp[0] != "":
        problems.append("comparison options must start with the None entry")
    if "Jul. FC" in comp:
        problems.append("comparison options include the selected forecast")
    if tx.resolve_comp("Jul. FC", "Jul. FC", comp) != "":
        problems.append("resolve_comp did not reset on collision")
    if tx.resolve_comp("2026B", "Jul. FC", comp) != "2026B":
        problems.append("resolve_comp dropped a valid comparison")
    return problems


def main() -> None:
    df = fetch()
    cube = tx.build_cube(df)
    print(f"connection {CONN_NAME} · {len(df):,} rows · {len(cube.vintages)} vintages")

    suites = (
        ("PERIOD LABELS", check_periods(cube)),
        ("DROPDOWNS", check_dropdowns(cube)),
        ("GRID", check_grid(cube)),
        ("TILES", check_tiles(cube)),
        ("CHARTS", check_charts(cube)),
    )
    failed = False
    for name, problems in suites:
        print(f"{name:<14} {'FAIL' if problems else 'pass'}")
        for p in problems[:15]:
            print(f"  {p}")
        if len(problems) > 15:
            print(f"  ... and {len(problems) - 15} more")
        failed |= bool(problems)

    print("\n" + ("FAILED" if failed else "ALL RENDER CHECKS PASS"))
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
