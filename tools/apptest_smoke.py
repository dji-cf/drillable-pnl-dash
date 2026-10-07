"""Headless end-to-end run of the app via Streamlit's AppTest harness.

Executes streamlit_app.py the way the server would -- real session_state, real
widget wiring, real Snowflake fetch -- and asserts no exception escapes, across
every combination of grain x comparison x change mode, the prior-year toggle,
a stale selection, the downloads, a sweep of all 26 Trends metrics, and the
Trends period, line picker and bridge messages.

    .venv\\Scripts\\python.exe tools\\apptest_smoke.py

WHAT THIS DOES NOT COVER. AppTest does not execute custom components, so the
Component v2 shadow-DOM render and the section-header CLICK path are out of
scope here; tools/smoke_render.py checks the HTML those produce, but the click
round-trip itself needs a browser. Everything else -- imports, page config,
session_state discipline, widget construction, the data load, both tabs, all
builders -- runs for real.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

import transforms as tx  # noqa: E402

APP = ROOT / "streamlit_app.py"
TIMEOUT = 180


def run(**state) -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=TIMEOUT)
    for k, v in state.items():
        at.session_state[k] = v
    return at.run()


def ss(at: AppTest, key: str, default=None):
    """AppTest's SafeSessionState has no .get(), so read defensively."""
    try:
        return at.session_state[key]
    except (KeyError, AttributeError):
        return default


def describe(at: AppTest) -> str:
    return "; ".join(f"{e.value}" for e in at.exception) or "no exception"


def options(at: AppTest, key: str) -> list[str]:
    """A selectbox's options as KEYS. Forecast keys are their own labels; the
    comparison box formats Actuals/Budget, so map those back."""
    out = []
    for label in at.selectbox(key=key).options:
        if label.endswith(" Actuals"):
            label = label.split()[0] + "A"
        elif label.endswith(" Budget"):
            label = label.split()[0] + "B"
        out.append(label)
    return out


def main() -> None:
    problems: list[str] = []

    # -- baseline ---------------------------------------------------------
    at = run()
    if at.exception:
        print("BASELINE FAILED:", describe(at))
        raise SystemExit(1)

    print(f"baseline ok · default forecast={ss(at, 'fc_sel')!r} "
          f"comp={ss(at, 'comp_sel')!r} "
          f"grain={ss(at, 'grain')!r} "
          f"trends lines={ss(at, 't_lines')}")
    n_charts = len(at.get("vega_lite_chart"))
    if n_charts != 3:
        problems.append(f"baseline renders {n_charts} Trends charts, expected 3")

    fc_opts = options(at, "fc_sel")
    newest = max(fc_opts, key=lambda k: tx.vintage_parts(k)[1:])
    if ss(at, "fc_sel") != newest or fc_opts[0] != newest:
        problems.append(
            f"default forecast is {ss(at, 'fc_sel')!r}, expected {newest!r} "
            f"(newest forecast)"
        )
    if at.error:
        problems.append(f"error box on baseline: {[e.value for e in at.error]}")
    if at.warning:
        problems.append(f"warning on baseline: {[w.value for w in at.warning]}")
    downloads = at.get("download_button")
    if len(downloads) != 2:
        problems.append(f"{len(downloads)} download buttons, expected 2")
    # The % / $ switch lives in the table's change header now, not above it.
    group_keys = [getattr(g, "key", None) for g in at.button_group]
    if "grain" not in group_keys:
        problems.append(f"View control missing; button groups {group_keys}")
    if "delta_mode" in group_keys:
        problems.append("a 'Change' control is still rendered above the grid")

    forecast, prior = fc_opts[0], fc_opts[1]
    budget = f"{tx.vintage_parts(forecast)[1]}B"
    prior_year = f"{tx.vintage_parts(forecast)[1] - 1}A"
    comp_opts = options(at, "comp_sel")
    for want in (budget, prior_year, prior):
        if want not in comp_opts:
            problems.append(f"{want!r} missing from comparison options {comp_opts}")
    for v in comp_opts + fc_opts:
        if v.endswith("A") and v[:4] == str(tx.vintage_parts(forecast)[1]):
            problems.append(f"partial-year Actuals {v!r} is offered")

    # -- grain x comparison x change mode -------------------------------
    combos = 0
    for grain in ("annual", "quarterly", "monthly"):
        for comp in ("", budget, prior):
            for mode in ("pct", "usd"):
                combos += 1
                at = run(fc_sel=forecast, comp_sel=comp, grain=grain, delta_mode=mode)
                if at.exception:
                    problems.append(f"{grain}/{comp or 'none'}/{mode}: {describe(at)}")
    print(f"grain x comparison x mode: {combos} combinations run")

    # delta_mode is plain session state (the in-table toggle writes it); the
    # tiles must follow it.
    at = run(fc_sel=forecast, comp_sel=budget, delta_mode="usd")
    tiles = " ".join(m.value for m in at.markdown if "tile-delta" in m.value)
    if not re.search(r"\+\$[\d,]+M|\(\$[\d,]+M\)", tiles):
        problems.append("delta_mode='usd' did not reach the tiles")
    at = run(fc_sel=forecast, comp_sel=budget, delta_mode="bogus")
    if at.exception or ss(at, "delta_mode") != "pct":
        problems.append(f"unknown delta_mode not reset: {ss(at, 'delta_mode')!r}")

    # -- prior-year toggle and stale selections ---------------------------
    at = run(show_retired=True)
    shown = options(at, "fc_sel")
    retired = [v for v in shown if v not in fc_opts]
    if at.exception:
        problems.append(f"show_retired: {describe(at)}")
    elif not retired:
        problems.append("show_retired brought back no forecast")
    else:
        print(f"prior-year toggle ok · +{len(retired)} forecasts: {', '.join(retired)}")
        # Selected while shown, then hidden: must fall back, not raise.
        at = run(show_retired=False, fc_sel=retired[0])
        if at.exception:
            problems.append(f"hidden forecast selected: {describe(at)}")
        elif ss(at, "fc_sel") != forecast:
            problems.append(f"hidden forecast not reset: fc_sel={ss(at, 'fc_sel')!r}")

    # A partial Actuals key -- no longer an option -- must reset, not raise.
    at = run(fc_sel=f"{tx.vintage_parts(forecast)[1]}A")
    if at.exception:
        problems.append(f"stale partial-Actuals selection: {describe(at)}")
    elif ss(at, "fc_sel") != forecast:
        problems.append(f"stale selection not reset: fc_sel={ss(at, 'fc_sel')!r}")
    else:
        print(f"stale selection reset ok · fc_sel -> {forecast!r}")

    # -- comparison collision resets to None (the deck's refreshCompOpts) ---
    at = run(fc_sel=prior, comp_sel=prior)
    if at.exception:
        problems.append(f"self-comparison: {describe(at)}")
    elif ss(at, "comp_sel") != "":
        problems.append(
            f"collision should reset the comparison to None, got "
            f"{ss(at, 'comp_sel')!r}"
        )
    else:
        print("collision reset ok · comp_sel -> '' (None)")

    # A valid comparison must survive a forecast change untouched.
    at = run(fc_sel=prior, comp_sel=budget)
    if ss(at, "comp_sel") != budget:
        problems.append(
            f"valid comparison was dropped: {ss(at, 'comp_sel')!r}"
        )

    # -- every Trends metric ---------------------------------------------
    # Only the rows that cannot be derived at all are withheld: 19/23 have no
    # expression, 10/18 have one over a residual the source has broken. The 19
    # unreconciled cost rows must now PLOT -- that is what changed when the
    # diagnostic toggle went away, so both directions are asserted.
    expected_withheld = sum(1 for r in tx.ROWS if not r.is_derivable)
    withheld = 0
    for idx in range(len(tx.ROWS)):
        at = run(t_metric=idx)
        if at.exception:
            problems.append(
                f"trends metric {idx} ({tx.ROWS[idx].metric_label}): "
                f"{describe(at)}"
            )
            continue
        infos = " ".join(i.value for i in at.info)
        said_unavailable = "is not available from the source" in infos
        if tx.ROWS[idx].is_derivable and said_unavailable:
            problems.append(
                f"trends metric {idx} ({tx.ROWS[idx].metric_label}) is "
                f"derivable but was withheld"
            )
        elif not tx.ROWS[idx].is_derivable:
            if said_unavailable:
                withheld += 1
            else:
                problems.append(
                    f"trends metric {idx} ({tx.ROWS[idx].metric_label}) cannot "
                    f"be derived but was plotted anyway"
                )
    print(f"trends metrics: {len(tx.ROWS)} runs · {withheld} correctly withheld")
    if withheld != expected_withheld:
        problems.append(
            f"{withheld} metrics withheld, expected {expected_withheld}"
        )

    # -- Trends: period, line picker, bridge messages ---------------------
    def infos(at: AppTest) -> str:
        return " ".join(i.value for i in at.info)

    for period in tx.TREND_PERIODS:
        at = run(t_period=period)
        if at.exception:
            problems.append(f"trends period {period}: {describe(at)}")
    print(f"trends periods: {len(tx.TREND_PERIODS)} runs")

    # Opening lines: that year's Budget, the comparison (the prior FC), the
    # forecast -- in tx.order_vintages order, which puts the Budget first.
    want = [budget, prior, forecast]
    at = run()
    if ss(at, "t_lines") != want:
        problems.append(f"default lines {ss(at, 't_lines')}, expected {want}")

    # An emptied picker stays empty (no silent refill) and does not raise.
    at = run(t_lines=[], t_lines_for=(forecast, prior))
    if at.exception:
        problems.append(f"trends with no lines: {describe(at)}")
    elif ss(at, "t_lines") != []:
        problems.append(f"emptied line picker was refilled: {ss(at, 't_lines')}")

    # A hidden vintage left in the picker is dropped, not raised on.
    if retired:
        at = run(show_retired=False, t_lines=[retired[0], forecast],
                 t_lines_for=(forecast, prior))
        if at.exception:
            problems.append(f"stale trends line: {describe(at)}")
        elif ss(at, "t_lines") != [forecast]:
            problems.append(f"stale trends line kept: {ss(at, 't_lines')}")

    # A new Forecast / vs. pair starts the lines over from its default.
    at = run(fc_sel=prior, comp_sel=budget, t_lines=[forecast],
             t_lines_for=(forecast, prior))
    if at.exception:
        problems.append(f"trends forecast change: {describe(at)}")
    elif ss(at, "t_lines") != [budget, prior]:
        problems.append(f"lines not reset on forecast change: {ss(at, 't_lines')}")
    else:
        print(f"line picker ok · reset to {ss(at, 't_lines')} on a new pair")

    # The bridge explains itself rather than drawing nothing.
    for state, msg in (({"comp_sel": ""}, "Choose a comparison"),
                       ({"t_metric": 13}, "breaks a $ line"),
                       ({"t_period": "Q1"}, "is actuals in both")):
        at = run(**state)
        if at.exception:
            problems.append(f"trends {state}: {describe(at)}")
        elif msg not in infos(at):
            problems.append(f"trends {state}: no {msg!r} message ({infos(at)!r})")
    print("bridge messages ok")

    # -- collapse state round-trips through session_state ---------------
    at = run(collapsed={s: True for s in tx.SECTIONS_WITH_HEADER})
    if at.exception:
        problems.append(f"all sections collapsed: {describe(at)}")

    print()
    if problems:
        print("PROBLEMS:", *problems, sep="\n  ")
        print("\nFAILED")
        raise SystemExit(1)
    print("ALL APPTEST CHECKS PASS")


if __name__ == "__main__":
    main()
