"""AppTest: the BU page COGS drill ties to its Total COGS row.

Sets session_state "cogs_drill_na" = True (the state a click on "Total COGS"
sets), runs the North America page for Sep 2026 FC (SEP26RF, FY26) at annual
grain with no comparison, and checks:
  * the detail table renders the COGS child lines, ACX_Compensation included;
  * its $M column sums to the grid's "Total COGS" for the same vintage
    (tolerance 0.05 $M);
  * the "Close" control clears the state.

AppTest records the grid component (it checks the data-cogs markup) but does
not run its JS, so the click itself is NOT exercised here: browser check.

    .venv/bin/python tools/test_cogs_drill.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import bu  # noqa: E402
import data  # noqa: E402
import queries  # noqa: E402
import transforms as tx  # noqa: E402
from apptest_smoke import goto, run, ss  # noqa: E402

VINTAGE = "Sep 2026 FC"
TOL = 0.05
CHILDREN = ("Manufacturing", "Royalties", "Net Freight Expense", "Product Development",
            "Autos & Relics", "MG Shortfall", "Obsolescence", "ACX_Compensation")


def total_cogs() -> float:
    """NA "Total COGS", full year of VINTAGE, from the app's own cube ($M).

    The grid prints whole $M, too coarse for the 0.05 tolerance, so this reads
    the same cube the page renders from: load_master -> build_cube -> bu.rows.
    """
    df, _ = data.load_master()
    cube = tx.build_cube(df)
    row = next(r for r in bu.rows("na", cube) if (r.section, r.label) == bu.TOTAL_COGS)
    return float(cube.value(VINTAGE, row, tx.ANNUAL)) / 1e6  # cube holds $


def grid_has_cogs_link(at) -> bool:
    """The grid markup puts data-cogs on the Total COGS label (click target)."""
    blobs = [str(getattr(e.proto, "json", "")) for e in at.get("bidi_component")]
    blobs += [str(getattr(e.proto, "body", "")) for e in at.get("html")]
    return any(re.search(r'data-cogs=\\*"na\\*"[^>]*>Total COGS<', b) for b in blobs)


def main() -> None:
    problems: list[str] = []
    at = run(fc_sel=VINTAGE, comp_sel="", grain_na="annual")
    at.session_state["cogs_drill_na"] = True
    at = goto(at, bu.URL_PATHS["na"])
    if at.exception:
        raise SystemExit(f"FAILED: {[e.value for e in at.exception]}")
    if ss(at, "fc_sel") != VINTAGE:
        raise SystemExit(f"FAILED: fc_sel is {ss(at, 'fc_sel')!r}, wanted {VINTAGE!r}")
    if at.error:
        problems.append(f"error box: {[e.value for e in at.error]}")

    frames = [d.value for d in at.dataframe if "COGS line" in d.value.columns]
    if not frames:
        raise SystemExit("FAILED: no COGS detail table on the NA page")
    df = frames[0]
    print(df.to_string(index=False))
    for line in CHILDREN:
        if line not in set(df["COGS line"]):
            problems.append(f"child line {line!r} missing from the detail")

    if not grid_has_cogs_link(at):
        problems.append("grid markup has no data-cogs on the Total COGS label")

    # Unrounded detail from the same loader the page calls (cache hit), so the
    # 0.1 rounding of the table rows does not eat the tolerance.
    raw = data.load_cogs_drill(VINTAGE, "FY26", queries.bu_base_lobs("na"))
    exact, shown, grid = float(raw["amount_mm"].sum()), float(df["$M"].sum()), total_cogs()
    print(f"detail sum {exact:,.3f} (table rows {shown:,.1f}) vs Total COGS {grid:,.3f}")
    if abs(exact - grid) > TOL:
        problems.append(f"detail sums to {exact:,.3f}, Total COGS is {grid:,.3f}")
    if abs(shown - exact) > 0.05 * len(df):
        problems.append(f"table rows sum {shown:,.1f} drift from {exact:,.3f}")

    # Close clears the state and the table.
    at = at.button(key="cogs_close_na").click().run()
    if ss(at, "cogs_drill_na") is not False:
        problems.append("Close did not clear cogs_drill_na")
    if any("COGS line" in d.value.columns for d in at.dataframe):
        problems.append("detail table still shown after Close")

    if problems:
        print("FAIL\n  " + "\n  ".join(problems))
        raise SystemExit(1)
    print("PASS")


if __name__ == "__main__":
    main()
