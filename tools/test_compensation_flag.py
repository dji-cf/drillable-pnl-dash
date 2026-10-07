"""Assert the cube reports the source's own ACX_ values, as EPM CARDPLN does.

Dev-only harness, deliberately NOT in snowflake.yml::artifacts. Same convention
as tools/validate_vs_deck.py: connects with snowflake.connector directly so it
runs without a Streamlit context.

    .venv\\Scripts\\python.exe tools\\test_compensation_flag.py

This is the regression gate for the 2026-09-29 change that set
queries.APPLY_COMPENSATION_ADJUSTMENT = False. The symptom it exists to catch is
the one that prompted the change: the app showed Q1 FY26 North America EBITDA as
$244.22M where EPM (cube CARDPLN, LOB 'Total - North America Gross', account
ACX_EBITDA, CO_31000, all other dimensions Total) reports $195.32M -- the
difference being ACX_Compensation being added back on top.

Four gates:

  ANCHOR       Q1 FY26 JUL26RF North America EBITDA, against whichever
               definition the active SOURCE is built on. Source-dependent on
               purpose -- see the two anchor constants below.
  NO ADD-BACK  every (vintage, line, period, segment) cell in the cube equals the
               matching seg_* column of queries.MASTER_SQL. The general form of
               ANCHOR, and what actually proves nothing is added anywhere.
  NO LEFTOVER  no _compensation keys survive in the cube.
  FLAG ON      setting the flag True restores the add-back at exactly the
               Compensation amount -- so this documents the old behaviour rather
               than deleting it. LEGACY ONLY: STG derives Gross Margin and
               EBITDA from account lines and never passes an ACX_ subtotal
               through, so there is no add-back to restore and no
               ACX_Compensation cell to restore it from.

The source side is taken from MASTER_SQL's own output rather than from a second
query. That is deliberate: MASTER_SQL already applies the vintage filter and
derives vintage_key, and an independent re-derivation here got it wrong -- it
keyed '*RF' scenarios on the month alone, so the FY27/FY28 rows of a scenario
overwrote its FY26 rows and every 'source' figure downstream was nonsense.
Reading the same frame build_cube reads makes this a test of build_cube, which is
what changed, rather than a test of a hand-copied filter.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import snowflake.connector  # noqa: E402

import queries  # noqa: E402
import transforms as tx  # noqa: E402

TOLERANCE = 0.0001
#: STG anchor tolerance. The decks print $M to one decimal place, so the anchor
#: can only be asserted to 0.1M -- unlike the LEGACY anchor, which is an exact
#: figure read out of EPM and is therefore held to $0.0001.
TOLERANCE_STG = 0.1e6
CONN_NAME = os.getenv("SNOWFLAKE_DEFAULT_CONNECTION_NAME", "HIDR_PROD")

#: The cell from the bug report, in both of its definitions. Which one applies
#: depends on queries.SOURCE, because Finance changed the definition underneath
#: this test on 2026-09-30 and BOTH numbers are correct for their own source.
ANCHOR_VINTAGE = "Jul. FC"
ANCHOR_SEGMENT = "na"
ANCHOR_PERIOD = "Q1"

#: LEGACY: the EPM CARDPLN figure at Total Cost Center (LOB
#: 'Total - North America Gross', account ACX_EBITDA, CO_31000, all other
#: dimensions Total), which was the business standard when the 2026-09-29
#: APPLY_COMPENSATION_ADJUSTMENT = False change was made. Still the right gate
#: for LEGACY, which passes the source's own ACX_ subtotals straight through.
ANCHOR_EBITDA = 195.3216765600e6

#: STG: 286.1M. Finance replaced the Total-Cost-Center definition on 2026-09-30
#: (Anoop: use Megan Coleman's sheet logic), which is what the STG row map and
#: the derived Gross Margin / EBITDA in queries.py implement. Corroborated three
#: ways: the HTML deck gives Jul FC Q1 NA EBITDA 286.1; the 2026-07 deck p.9
#: gives 286; and the 2026-09 deck p.7 gives 286 for Q1 26A. The ~+90.74M step
#: up from the LEGACY anchor is the KNOWN cost-centre double-count gap, not a
#: regression -- do not "fix" either number to make them agree.
ANCHOR_EBITDA_STG = 286.1e6


def _fetch(sql: str) -> pd.DataFrame:
    conn = snowflake.connector.connect(connection_name=CONN_NAME)
    try:
        conn.cursor().execute("USE SECONDARY ROLES NONE")
        df = conn.cursor().execute(sql).fetch_pandas_all()
    finally:
        conn.close()
    df.columns = [c.lower() for c in df.columns]
    return df


def _source_lookup(master: pd.DataFrame) -> dict[tuple[str, str, str, str], float]:
    """(vintage_key, line, period_key, segment) -> the source figure.

    Keyed exactly the way build_cube keys its cube, and read from the same frame,
    so any difference is build_cube's arithmetic and not a keying artifact.
    """
    line_of = {sql_name: key for key, sql_name in queries.PL_LINES.items()}
    line_of[queries.COMPENSATION_LINE] = tx._COMP

    out: dict[tuple[str, str, str, str], float] = {}
    for rec in master.to_dict("records"):
        line = line_of.get(rec["pl_line"])
        if line is None:
            continue
        pkey = tx.ANNUAL if rec["period_type"] == "YEAR" else rec["period"]
        for seg in queries.SEGMENTS:
            out[(rec["vintage_key"], line, pkey, seg)] = float(rec[f"seg_{seg}"])
    return out


def _anchor_for_source() -> tuple[float, float, str]:
    """(expected, tolerance, provenance label) for the active source."""
    if queries.SOURCE == "STG":
        return (ANCHOR_EBITDA_STG, TOLERANCE_STG,
                "HTML deck / 2026-07 deck p.9, Megan's sheet logic")
    return (ANCHOR_EBITDA, TOLERANCE, "EPM CARDPLN Total Cost Center")


def check_anchor(cube: tx.Cube) -> list[str]:
    """The exact cell from the bug report, against the active source's figure."""
    want, tol, label = _anchor_for_source()
    row = tx.ROWS[14]                      # EBITDA / North America
    got = cube.value(ANCHOR_VINTAGE, row, ANCHOR_PERIOD)
    if got is None:
        return [f"{ANCHOR_VINTAGE} {ANCHOR_PERIOD} NA EBITDA is None"]
    if abs(got - want) > tol:
        return [
            f"{ANCHOR_VINTAGE} {ANCHOR_PERIOD} North America EBITDA = "
            f"{got / 1e6:,.10f}M, expected {want / 1e6:,.10f}M "
            f"({label}), off by {(got - want) / 1e6:+,.10f}M"
        ]
    return []


def check_no_addback(cube: tx.Cube, src: dict) -> tuple[int, list[str]]:
    """Every cube cell equals the source line it claims to be."""
    failures: list[str] = []
    checked = 0
    for (vintage, line, pkey), segs in sorted(cube.segs.items()):
        for seg, live in sorted(segs.items()):
            want = src.get((vintage, line, pkey, seg))
            if want is None:
                failures.append(f"{vintage} {line} {pkey} {seg}: no source cell")
                continue
            checked += 1
            if abs(live - want) > TOLERANCE:
                failures.append(
                    f"{vintage} {line} {pkey} {seg}: cube {live / 1e6:,.6f}M vs "
                    f"source {want / 1e6:,.6f}M "
                    f"({(live - want) / 1e6:+,.6f}M)"
                )
    return checked, failures


def check_no_leftover(cube: tx.Cube) -> list[str]:
    """No _compensation keys survive, whatever the flag says."""
    leftover = sorted(k for k in cube.segs if k[1] == tx._COMP)
    if leftover:
        return [
            f"{len(leftover)} _compensation key(s) left in the cube, "
            f"first: {leftover[0]}"
        ]
    return []


def check_flag_on_restores_addback(master: pd.DataFrame, src: dict) -> list[str]:
    """With the flag True, the add-back reappears at exactly Compensation.

    Documents the old behaviour instead of deleting it, and proves the flag is
    the only thing standing between the two.
    """
    original = queries.APPLY_COMPENSATION_ADJUSTMENT
    queries.APPLY_COMPENSATION_ADJUSTMENT = True
    try:
        cube = tx.build_cube(master)
    finally:
        queries.APPLY_COMPENSATION_ADJUSTMENT = original

    got = cube.value(ANCHOR_VINTAGE, tx.ROWS[14], ANCHOR_PERIOD)
    comp = src.get((ANCHOR_VINTAGE, tx._COMP, ANCHOR_PERIOD, ANCHOR_SEGMENT))
    if got is None or comp is None:
        return ["flag-on check could not resolve the anchor cell"]

    want = ANCHOR_EBITDA + comp
    if abs(got - want) > TOLERANCE:
        return [
            f"flag ON: expected {want / 1e6:,.6f}M "
            f"(source {ANCHOR_EBITDA / 1e6:,.6f}M + Compensation "
            f"{comp / 1e6:,.6f}M), got {got / 1e6:,.6f}M"
        ]
    return check_no_leftover(cube)


def main() -> None:
    failed = False
    print(f"connection: {CONN_NAME}   source: {queries.SOURCE}")
    print(f"APPLY_COMPENSATION_ADJUSTMENT = "
          f"{queries.APPLY_COMPENSATION_ADJUSTMENT}\n")

    if queries.APPLY_COMPENSATION_ADJUSTMENT:
        print("NOTE: the flag is True, so the add-back is ACTIVE. The ANCHOR and")
        print("      NO ADD-BACK gates below assert the flag-OFF contract and are")
        print("      expected to fail. Set it back to False to gate the shipped")
        print("      behaviour.\n")

    master = _fetch(queries.MASTER_SQL)
    src = _source_lookup(master)
    cube = tx.build_cube(master)
    print(f"master frame: {len(master):,} rows\n")

    anchor_problems = check_anchor(cube)
    _want, _tol, _label = _anchor_for_source()
    print(f"ANCHOR       {'FAIL' if anchor_problems else 'pass'}  "
          f"(Q1 FY26 Jul. FC North America EBITDA == "
          f"{_want / 1e6:,.4f}M +/- {_tol / 1e6:g}M, {_label})")
    for p in anchor_problems:
        print(f"  {p}")
    failed |= bool(anchor_problems)

    n, addback_problems = check_no_addback(cube, src)
    print(f"NO ADD-BACK  {'FAIL' if addback_problems else 'pass'}  "
          f"({n:,} cells vs source)")
    for p in addback_problems[:20]:
        print(f"  {p}")
    if len(addback_problems) > 20:
        print(f"  ... and {len(addback_problems) - 20} more")
    failed |= bool(addback_problems)

    leftover_problems = check_no_leftover(cube)
    print(f"NO LEFTOVER  {'FAIL' if leftover_problems else 'pass'}  "
          f"(no _compensation keys in the cube)")
    for p in leftover_problems:
        print(f"  {p}")
    failed |= bool(leftover_problems)

    # LEGACY-only. STG computes EBITDA from account lines and carries no
    # ACX_Compensation cell, so there is no add-back to restore and the gate
    # has nothing to assert -- skipping is the correct result, not a pass.
    if queries.SOURCE == "LEGACY":
        flag_problems = check_flag_on_restores_addback(master, src)
        print(f"FLAG ON      {'FAIL' if flag_problems else 'pass'}  "
              f"(True restores the add-back exactly)")
        for p in flag_problems:
            print(f"  {p}")
        failed |= bool(flag_problems)
    else:
        print("FLAG ON      skip  (LEGACY only: STG derives EBITDA from account "
              "lines and never passes ACX_Compensation through)")

    print("\nFAILED" if failed else "\nALL PASS")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
