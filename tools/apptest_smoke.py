"""Headless end-to-end run of the app via Streamlit's AppTest harness.

Executes streamlit_app.py the way the server would -- real session_state, real
widget wiring, real Snowflake fetch -- and asserts no exception escapes, across
every combination of grain x comparison, plus the partial-year vintage and a
sweep of all 26 Trends metrics.

    .venv\\Scripts\\python.exe tools\\apptest_smoke.py

WHAT THIS DOES NOT COVER. AppTest does not execute custom components, so the
Component v2 shadow-DOM render and the section-header CLICK path are out of
scope here; tools/smoke_render.py checks the HTML those produce, but the click
round-trip itself needs a browser. Everything else -- imports, page config,
session_state discipline, widget construction, the data load, both tabs, all
builders -- runs for real.
"""
from __future__ import annotations

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


def main() -> None:
    problems: list[str] = []

    # -- baseline ---------------------------------------------------------
    at = run()
    if at.exception:
        print("BASELINE FAILED:", describe(at))
        raise SystemExit(1)

    vintages = [v for v in ss(at, "t_checks", set())]
    print(f"baseline ok · default forecast={ss(at, 'fc_sel')!r} "
          f"comp={ss(at, 'comp_sel')!r} "
          f"grain={ss(at, 'grain')!r} "
          f"trends checks={sorted(vintages)}")

    if ss(at, "fc_sel") != "Aug. FC":
        problems.append(
            f"default forecast is {ss(at, 'fc_sel')!r}, expected "
            f"'Aug. FC' (newest vintage)"
        )
    if not at.error:
        pass
    else:
        problems.append(f"error box on baseline: {[e.value for e in at.error]}")

    # -- grain x comparison ----------------------------------------------
    combos = 0
    for grain in ("annual", "quarterly", "monthly"):
        for comp in ("", "2026B", "Jul. FC"):
            combos += 1
            at = run(fc_sel="Aug. FC", comp_sel=comp, grain=grain)
            if at.exception:
                problems.append(f"{grain}/{comp or 'none'}: {describe(at)}")
    print(f"grain x comparison: {combos} combinations run")

    # -- partial-year vintage must warn, as forecast and as comparison ---
    at = run(fc_sel=tx.PARTIAL_VINTAGE, comp_sel="", grain="quarterly")
    if at.exception:
        problems.append(f"partial as forecast: {describe(at)}")
    else:
        warns = " ".join(w.value for w in at.warning)
        if "7-month partial" not in warns:
            problems.append(f"partial-as-forecast warning missing; saw: {warns!r}")
        if "no Q4" not in warns:
            problems.append("partial-as-forecast warning does not mention no Q4")

    at = run(fc_sel="Aug. FC", comp_sel=tx.PARTIAL_VINTAGE, grain="monthly")
    if at.exception:
        problems.append(f"partial as comparison: {describe(at)}")
    else:
        warns = " ".join(w.value for w in at.warning)
        if "7-month partial" not in warns:
            problems.append("partial-as-comparison warning missing")

    # -- comparison collision resets to None (the deck's refreshCompOpts) ---
    at = run(fc_sel="Jul. FC", comp_sel="Jul. FC")
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
    at = run(fc_sel="Jul. FC", comp_sel="2026B")
    if ss(at, "comp_sel") != "2026B":
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
        at = run(t_metric=idx, t_grain="annual")
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

    # -- Trends sub-period floor ----------------------------------------
    for grain in ("quarterly", "monthly"):
        at = run(t_grain=grain, t_subs=[])
        if at.exception:
            problems.append(f"trends {grain} with empty subs: {describe(at)}")
        elif not ss(at, "t_subs"):
            problems.append(f"trends {grain}: sub-period selection emptied out")
    # A stale selection from the other grain must not survive.
    at = run(t_grain="quarterly", t_subs=["Jan", "Feb"])
    if at.exception:
        problems.append(f"trends stale subs: {describe(at)}")
    elif set(ss(at, "t_subs", [])) - set(tx.QUARTERS):
        problems.append(
            f"trends quarterly kept month sub-periods: "
            f"{ss(at, 't_subs')}"
        )
    else:
        print(f"sub-period guard ok · stale months -> "
              f"{ss(at, 't_subs')}")

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
