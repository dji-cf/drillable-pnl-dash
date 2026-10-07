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
import export  # noqa: E402
import queries  # noqa: E402
import style  # noqa: E402
import table  # noqa: E402
import transforms as tx  # noqa: E402

CONN_NAME = os.getenv("SNOWFLAKE_DEFAULT_CONNECTION_NAME", "HIDR_PROD")

#: Data columns at each grain, with and without a comparison. Periods are the
#: sub-periods plus the always-appended FY column -- plus a YTD column when the
#: forecast is part-way through its year; a comparison triples them
#: (comparison | current | change).
EXPECTED_PERIODS = {"annual": 1, "quarterly": 5, "monthly": 13}

#: The relabel reverted in e61c93f. Must not come back on screen.
STALE_LABELS: tuple[str, ...] = ("Fanatics Live and Collect", "Period-over-Period",
                                 "(PY)", "(partial)")


def _fc(cube: tx.Cube, mon: str, year: int = 2026) -> str | None:
    """The key of a given month's forecast, or None when the cube lacks it."""
    key = f"{mon} {year} FC"
    return key if key in cube.vintages else None


def _newest_fc(cube: tx.Cube) -> str:
    return tx.forecast_options(cube)[0]


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
    df["forecast_asof_date"] = pd.to_datetime(df["forecast_asof_date"], errors="coerce")
    return df


def body_rows(html: str) -> list[str]:
    body = html.split("<tbody>", 1)[1].rsplit("</tbody>", 1)[0]
    return [m for m in re.findall(r"<tr\b.*?</tr>", body, flags=re.S)]


#: Markup the old diagnostic view produced. None of it may survive anywhere.
DEAD_MARKUP: tuple[str, ...] = ("gap-badge", "var-badge", "diag-row",
                                "tile-note", "tile gapped", "footnotes")


def check_grid(cube: tx.Cube) -> list[str]:
    problems: list[str] = []
    forecast = _newest_fc(cube)
    budget = f"{cube.year(forecast)}B"
    comp_choice = budget if budget in cube.vintages else ""
    has_ytd = cube.ytd_period(forecast) is not None
    if not has_ytd:
        problems.append(f"{forecast}: no YTD column, but it is part-way through its year")

    for grain, n_periods in EXPECTED_PERIODS.items():
        for comp in ("", comp_choice):
            collapsed = {s: False for s in tx.SECTIONS_WITH_HEADER}
            html = table.build_statement(
                cube,
                forecast=forecast, comp=comp, grain=grain,
                collapsed=collapsed,
            )
            tag = f"{grain}/{'comp' if comp else 'solo'}"

            want_data = (n_periods + has_ytd) * (3 if comp else 1)
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

            # Section names live in their own sticky cell so they pin while the
            # figures scroll (a full-width colspan cell cannot).
            for r in hdr_rows:
                if '<td class="lbl">' not in r or 'class="sec-fill"' not in r:
                    problems.append(f"{tag}: section header without a sticky label cell")
                    break

            if comp and tx.change_label(comp) not in html:
                problems.append(f"{tag}: change header {tx.change_label(comp)!r} missing")
            for stale in STALE_LABELS:
                if stale in html:
                    problems.append(f"{tag}: stale label {stale!r} rendered")
            if has_ytd and "ytd-col" not in html:
                problems.append(f"{tag}: YTD column header missing")

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

    # The frozen label column must be opaque, or scrolled figures show through.
    if "background: inherit" in style.TABLE_CSS:
        problems.append("TABLE_CSS: td.lbl background is 'inherit' (transparent rows)")

    return problems


def check_change(cube: tx.Cube) -> list[str]:
    """Greying, $ mode and the change header against the live cube."""
    problems: list[str] = []
    fcs = tx.forecast_options(cube)
    forecast, prior = fcs[0], fcs[1]
    derivable = sum(1 for r in tx.ROWS if r.is_derivable)

    for grain in tx.GRAINS:
        periods = cube.periods(forecast, grain)
        n_same = sum(cube.same_actuals(forecast, prior, pk) for pk, _ in periods)
        html = table.build_statement(cube, forecast=forecast, comp=prior, grain=grain,
                                     collapsed={})
        if html.count(" gact") != n_same * derivable:
            problems.append(f"{grain} vs {prior}: {html.count(' gact')} greyed cells, "
                            f"want {n_same} periods x {derivable} rows")
        # A greyed column must really be zero: closed months are byte-identical
        # across snapshots (ISSUES.md section 3). If the source ever restates
        # them, greying would hide a real change -- so fail loudly here.
        for pk, lbl in periods:
            if not cube.same_actuals(forecast, prior, pk):
                continue
            for row in tx.ROWS:
                a, b = cube.value(forecast, row, pk), cube.value(prior, row, pk)
                if a is None or b is None:
                    continue
                if abs(a - b) > (1e-9 if row.is_pct else 1.0):
                    problems.append(f"{lbl} {row.section}/{row.label}: greyed but "
                                    f"{forecast} - {prior} = {a - b:,.2f}")
                    break

    monthly = table.build_statement(cube, forecast=forecast, comp=prior, grain="monthly",
                                    collapsed={})
    if not (0 < monthly.count("ph-act") < len(cube.periods(forecast, "monthly"))):
        problems.append(f"monthly vs {prior}: {monthly.count('ph-act')} greyed period "
                        f"headers -- expected some, not all")

    budget = f"{cube.year(forecast)}B"
    if budget in cube.vintages:
        html = table.build_statement(cube, forecast=forecast, comp=budget,
                                     grain="monthly", collapsed={})
        if "gact" in html:
            problems.append("vs. Budget: a change cell was greyed")
    prior_year = f"{int(cube.year(forecast)) - 1}A"
    if prior_year in cube.vintages:
        html = table.build_statement(cube, forecast=forecast, comp=prior_year,
                                     grain="monthly", collapsed={})
        if "gact" in html:
            problems.append("vs. prior-year Actuals: a change cell was greyed")

    usd = table.build_statement(cube, forecast=forecast, comp=prior, grain="annual",
                                collapsed={}, delta_mode="usd")
    cells = re.findall(r'<td class="gc (?!gact)[^"]*">(.*?)</td>', usd)
    bad = [c for c in cells
           if not re.fullmatch(r"\+\$[\d,]+|\(\$[\d,]+\)|\$0|[+-]?\d+ bps|"
                               + tx.EM_DASH, c)]
    if bad:
        problems.append(f"usd mode: unexpected change cells {bad[:5]}")
    if not any(c.startswith(("+$", "($")) for c in cells):
        problems.append("usd mode: no dollar change cell rendered")

    # The % / $ toggle lives in the change header, marks the active mode, goes
    # away with the change block, and renders disabled on the static path.
    for mode in tx.DELTA_MODES:
        html = table.build_statement(cube, forecast=forecast, comp=prior,
                                     grain="annual", collapsed={}, delta_mode=mode)
        header = re.search(r'<th class="grp-growth"[^>]*>(.*?)</th>', html, flags=re.S)
        if not header or 'class="dmode"' not in header.group(1):
            problems.append(f"{mode}: toggle missing from the change header")
            continue
        on = re.findall(r'data-mode="(\w+)" class="on"', header.group(1))
        if on != [mode]:
            problems.append(f"{mode}: active toggle button {on}")
    solo = table.build_statement(cube, forecast=forecast, comp="", grain="annual",
                                 collapsed={})
    if "dmode" in solo:
        problems.append("toggle rendered with no comparison")
    static = table.build_statement(cube, forecast=forecast, comp=prior, grain="annual",
                                   collapsed={}, toggle_enabled=False)
    if static.count(" disabled>") != len(tx.DELTA_MODES):
        problems.append("static grid: toggle buttons not disabled")
    return problems


def check_ytd(cube: tx.Cube) -> list[str]:
    """YTD:Dec must equal the source's own YEAR row: month additivity."""
    problems: list[str] = []
    checked = 0
    for v in cube.vintages:
        if not cube.is_complete(v):
            continue
        for row in tx.ROWS:
            a = cube.value(v, row, tx.ytd_key("Dec"))
            b = cube.value(v, row, tx.ANNUAL)
            if a is None or b is None:
                continue
            checked += 1
            if abs(a - b) > (1e-9 if row.is_pct else 1.0):
                problems.append(f"{v} {row.section}/{row.label}: YTD:Dec {a:,.2f} "
                                f"!= FY {b:,.2f}")
    if not checked:
        problems.append("no complete vintage to check YTD additivity against")
    return problems


def check_export(cube: tx.Cube) -> list[str]:
    """The download carries the grid's columns, raw, and opens as a workbook."""
    problems: list[str] = []
    fcs = tx.forecast_options(cube)
    forecast, prior = fcs[0], fcs[1]
    for grain in tx.GRAINS:
        for comp in ("", prior):
            for mode in tx.DELTA_MODES:
                frame = export.statement_frame(cube, forecast=forecast, comp=comp,
                                               grain=grain, delta_mode=mode)
                n_lead = 4 if comp else 3
                want = len(cube.periods(forecast, grain)) * (3 if comp else 1)
                if frame.shape != (len(tx.ROWS), n_lead + want):
                    problems.append(f"export {grain}/{comp or 'solo'}/{mode}: "
                                    f"shape {frame.shape}")
    frame = export.statement_frame(cube, forecast=forecast, comp=prior, grain="annual")
    rev = tx.ROWS[6]
    col = f"{tx.vintage_label(forecast)} | {cube.periods(forecast, 'annual')[-1][1]}"
    got = frame.loc[6, col]
    want = cube.value(forecast, rev, tx.ANNUAL) / 1e6
    if abs(got - want) > 1e-9:
        problems.append(f"export: {col} Total Revenue {got} != {want}")
    xlsx = export.to_xlsx(cube, forecast=forecast, comp=prior, grain="monthly")
    if not xlsx.startswith(b"PK"):
        problems.append("export: xlsx payload is not a zip/OOXML file")
    try:
        import openpyxl  # optional: only to prove the workbook re-opens
    except ImportError:
        pass
    else:
        import io
        wb = openpyxl.load_workbook(io.BytesIO(xlsx))
        if wb.active.freeze_panes != "C6":
            problems.append(f"export: freeze panes {wb.active.freeze_panes}")
    csv = export.to_csv(cube, forecast=forecast, comp=prior, grain="monthly")
    if tx.change_label(prior).encode() not in csv:
        problems.append("export: csv lacks the change block")
    return problems


def check_tiles(cube: tx.Cube) -> list[str]:
    problems: list[str] = []
    forecast = _fc(cube, "Jul") or _newest_fc(cube)
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
        problems.append("tiles: Jul 2026 FC revenue tile is not $5.18B")
    usd = table.build_tiles(cube, forecast=forecast, comp="2026B", delta_mode="usd")
    if not re.search(r"vs\. 2026 Budget: (\+\$[\d,]+M|\(\$[\d,]+M\))", usd):
        problems.append("tiles: usd-mode revenue delta is not '+$NM' / '($NM)'")
    return problems


def check_charts(cube: tx.Cube) -> list[str]:
    """Every metric x period must produce a valid Vega-Lite spec from all three
    Trends charts, and the bridge must add up to the statement's own change."""
    problems: list[str] = []
    forecast = _newest_fc(cube)
    prior = tx.prior_forecast(cube, forecast) or ""
    lines = tx.default_lines(cube, forecast, prior)

    def spec(name: str, build) -> dict | None:
        try:
            out = build().to_dict()
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{name}: {type(exc).__name__}: {exc}")
            return None
        if not isinstance(out, dict) or not out:
            problems.append(f"{name}: empty spec")
        return out

    for row in tx.ROWS:
        for period in (tx.ANNUAL, "Q1", "Q4"):
            spec(f"outlook row{row.idx} {period}", lambda: charts.outlook_chart(
                cube, row, forecast, prior, period))
            spec(f"bridge row{row.idx} {period}", lambda: charts.bridge_chart(
                cube, row, forecast, prior, period))
        spec(f"months row{row.idx}", lambda: charts.months_chart(
            cube, row, lines, forecast, prior))

    # Degenerate inputs must not raise.
    rev = tx.ROWS[6]
    spec("months, no lines", lambda: charts.months_chart(cube, rev, [], forecast, prior))
    spec("bridge, no comparison", lambda: charts.bridge_chart(
        cube, rev, forecast, "", tx.ANNUAL))
    spec("outlook, no comparison", lambda: charts.outlook_chart(
        cube, rev, forecast, "", tx.ANNUAL))
    budget = tx.year_budget(cube, forecast)
    if budget:
        spec("outlook, Budget as the forecast", lambda: charts.outlook_chart(
            cube, rev, budget, "", tx.ANNUAL))
        spec("months, Budget as the forecast", lambda: charts.months_chart(
            cube, rev, [budget], budget, ""))

    # The deck's is_pct bug: a percent metric must be labelled '%', not '$'.
    pct = spec("outlook row13", lambda: charts.outlook_chart(
        cube, tx.ROWS[13], forecast, prior, tx.ANNUAL)) or {}
    if "'title': '%'" not in str(pct.get("layer", pct)):
        problems.append("row13 (Total Gross Margin %) is not labelled as a percent")
    if charts.fmt_value(0.5476, True) != "54.8%":
        problems.append(f"fmt_value pct: {charts.fmt_value(0.5476, True)!r} != '54.8%'")
    if charts.fmt_value(-12.4e6, False) != "($12)":
        problems.append(f"fmt_value $: {charts.fmt_value(-12.4e6, False)!r} != '($12)'")

    # The bridge runs from the comparison's figure to the forecast's, and its
    # ends are the figures the statement prints a change for.
    if prior:
        html = table.build_statement(cube, forecast=forecast, comp=prior, grain="annual",
                                     collapsed={}, delta_mode="usd")
        for idx in (6, 24):
            row = tx.ROWS[idx]
            b = tx.bridge(cube, row, forecast, prior, tx.ANNUAL)
            if b is None:
                problems.append(f"bridge row{idx}: None for {forecast} vs {prior}")
                continue
            miss = abs(b.start + sum(st.delta for st in b.steps) - b.end) / 1e6
            if miss >= 0.5:
                problems.append(f"bridge row{idx}: steps miss the forecast by ${miss:.2f}M")
            text = tx.delta_fmt(b.end, b.start, False, mode="usd")["text"]
            cells = re.findall(r'<td class="gc [^"]*">([^<]*)</td>',
                               body_rows(html)[_body_index(row)])
            if not cells or cells[-1] != text:
                problems.append(f"bridge row{idx}: change {text!r}, table says {cells[-1:]}")
            labels = [st.label for st in b.steps]
            if queries.SOURCE == "STG" and idx == 24 and tx.OTHER_LABEL in labels:
                problems.append(f"STG Total EBITDA bridge has an Other step: {labels}")
    else:
        problems.append(f"no prior forecast for {forecast}; bridge checks skipped")
    return problems


def _body_index(row: tx.Row) -> int:
    """Index of a row's <tr> among body_rows(): section headers sit before it."""
    headers = sum(1 for s in tx.SECTIONS_WITH_HEADER
                  if any(r.section == s and r.idx <= row.idx for r in tx.ROWS))
    return row.idx + headers


def check_periods(cube: tx.Cube) -> list[str]:
    """Period labels must reproduce the deck for Jul FC and be honest elsewhere."""
    problems: list[str] = []

    def sub_periods(vintage: str, grain: str) -> list[str]:
        return [lbl for pk, lbl in cube.periods(vintage, grain)
                if pk != tx.ANNUAL and not tx.is_ytd(pk)]

    jul = _fc(cube, "Jul")
    if jul:
        want_months = ["Jan 26A", "Feb 26A", "Mar 26A", "Apr 26A", "May 26A",
                       "Jun 26A", "Jul 26F", "Aug 26F", "Sep 26F", "Oct 26F",
                       "Nov 26F", "Dec 26F"]
        got = sub_periods(jul, "monthly")
        if got != want_months:
            problems.append(f"{jul} month labels {got} != deck MONTH_LBL")

        want_q = ["Q1 26A", "Q2 26A", "Q3 26F", "Q4 26F"]
        got_q = sub_periods(jul, "quarterly")
        if got_q != want_q:
            problems.append(f"{jul} quarter labels {got_q} != deck Q_LBL")

        annual = cube.periods(jul, "annual")
        if annual != [("YTD:Jun", "YTD Jun 26A"), (tx.ANNUAL, "FY 2026F")]:
            problems.append(f"{jul} annual periods {annual}")

    # The correction: the Jan FC must NOT claim Jan-Jun are actuals.
    jan = _fc(cube, "Jan")
    if jan:
        actuals = [l for l in sub_periods(jan, "monthly") if l.endswith("A")]
        if actuals:
            problems.append(
                f"{jan} shows {len(actuals)} actual months ({actuals}); "
                f"as-of 2026-01-31 means none are"
            )
        if cube.ytd_period(jan) is not None:
            problems.append(f"{jan} has a YTD column but no closed month")

    # A partial Actuals year must not fabricate periods -- and is not offered.
    for v in cube.vintages:
        if cube.scenario_label[v] != "ACTUAL" or cube.is_complete(v):
            continue
        months = cube.months_present[v]
        if list(months) != list(tx.MONTHS[: len(months)]):
            problems.append(f"{v}: months {list(months)} are not a Jan-anchored run")
        if "Q4" in cube.quarters_present.get(v, ()) and len(months) < 10:
            problems.append(f"{v}: Q4 fabricated from {len(months)} months")
    return problems


def check_dropdowns(cube: tx.Cube, df: pd.DataFrame) -> list[str]:
    problems: list[str] = []
    fc = tx.forecast_options(cube)
    # Independent of the key parser: the newest as-of date in the raw frame.
    asof = df.loc[df["scenario_label"] == "FORECAST", "forecast_asof_date"].max()
    newest = f"{asof:%b %Y} FC"
    if fc[0] != newest:
        problems.append(f"forecast options start with {fc[0]!r}, expected {newest!r}")
    if any(cube.scenario_label[v] != "FORECAST" for v in fc):
        problems.append(f"non-forecast in forecast options: {fc}")

    offered = set(fc) | set(tx.comp_options(cube, fc[0]))
    for v in cube.vintages:
        if cube.scenario_label[v] == "ACTUAL" and not cube.is_complete(v) and v in offered:
            problems.append(f"partial-year Actuals {v} is offered")
        if cube.is_retired(v) and v in offered:
            problems.append(f"retired {v} is offered by default")
    retired = [v for v in cube.vintages if cube.is_retired(v)]
    if retired and not set(retired) <= set(tx.forecast_options(cube, True)) | set(
            tx.comp_options(cube, fc[0], True)):
        problems.append("show-retired does not bring the retired vintages back")
    if any(not cube.fiscal_year[v] in cube.final_years for v in retired):
        problems.append("a vintage retired for a year whose actuals are not final")

    labels = [tx.vintage_label(v) for v in cube.vintages]
    for stale in STALE_LABELS:
        if any(stale in l for l in labels):
            problems.append(f"stale qualifier {stale!r} in vintage labels {labels}")

    jul = _fc(cube, "Jul") or fc[0]
    comp = tx.comp_options(cube, jul)
    if comp[0] != "":
        problems.append("comparison options must start with the None entry")
    if jul in comp:
        problems.append("comparison options include the selected forecast")
    if tx.resolve_comp(jul, jul, comp) != "":
        problems.append("resolve_comp did not reset on collision")
    if tx.resolve_comp("2026B", jul, comp) != "2026B":
        problems.append("resolve_comp dropped a valid comparison")
    return problems


def main() -> None:
    df = fetch()
    cube = tx.build_cube(df)
    print(f"connection {CONN_NAME} · {len(df):,} rows · {len(cube.vintages)} vintages")

    suites = (
        ("PERIOD LABELS", check_periods(cube)),
        ("DROPDOWNS", check_dropdowns(cube, df)),
        ("GRID", check_grid(cube)),
        ("CHANGE", check_change(cube)),
        ("YTD", check_ytd(cube)),
        ("EXPORT", check_export(cube)),
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
