"""Extract the source deck's DATA literal into reference/deck_jul2026.json.

Dev-only. Run once (or whenever the deck is re-exported). Neither this script
nor the JSON it writes is deployed -- the app stopped reading the deck when the
variance-vs-deck badges were removed.

    .venv\\Scripts\\python.exe tools\\extract_deck.py

Why a separate file rather than a Python literal: the deck carries ~102 KB of
numbers on a single line (line 233 of the HTML). Inlining that into a module
would dominate every diff and every review of the app's actual logic.

The JSON is the reference for two dev harnesses:
  1. tools/validate_vs_deck.py, which asserts the live Revenue rows reproduce
     the deck cell for cell, and
  2. tools/gap_analysis.py, which measures how far the unreconciled cost rows
     sit from it.

Shape written (unchanged from the deck):

    {"<vintage>": [ {section, label, row_type, is_pct,
                     annual: float|null,
                     quarterly: {Q1..Q4: float|null},
                     monthly: [12 x float|null]}, ... x26 ], ... x9}
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SRC = Path(r"c:\Users\dji\Downloads\FC_Forecast Dashboard_Jul 2026 FC.html")
OUT = Path(__file__).resolve().parent.parent / "reference" / "deck_jul2026.json"

# The deck's own row inventory, from ROW_DEFS in the source JS (lines 443-470).
# Asserting against it catches a re-export that reorders or renames rows, which
# would silently misalign every row index the app keys on.
EXPECTED_SECTIONS = {
    "Revenue": 7,
    "Gross Margin": 7,
    "EBITDA": 11,
    "EBITDA Margin": 1,
}
EXPECTED_ROWS = 26
QUARTERS = ("Q1", "Q2", "Q3", "Q4")


def extract(html: str) -> dict:
    """Pull the `const DATA = {...};` object literal out of the deck's script."""
    m = re.search(r"const\s+DATA\s*=\s*", html)
    if m is None:
        raise SystemExit("could not find `const DATA =` in the deck HTML")
    start = html.index("{", m.end())

    # Brace-match rather than regex to the end of line: the literal is one line
    # today, but a re-export that pretty-prints it would break a line-based cut.
    # No strings in this literal contain braces, so a plain depth count is safe.
    depth = 0
    for i in range(start, len(html)):
        c = html[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return json.loads(html[start : i + 1])
    raise SystemExit("unbalanced braces in the DATA literal")


def validate(data: dict) -> None:
    """Fail loudly on any shape drift, rather than shipping a misaligned file."""
    problems: list[str] = []

    for vintage, rows in data.items():
        if len(rows) != EXPECTED_ROWS:
            problems.append(f"{vintage}: {len(rows)} rows, expected {EXPECTED_ROWS}")
            continue

        counts: dict[str, int] = {}
        for ri, row in enumerate(rows):
            missing = {"section", "label", "row_type", "is_pct", "annual",
                       "quarterly", "monthly"} - set(row)
            if missing:
                problems.append(f"{vintage}[{ri}]: missing keys {sorted(missing)}")
                continue
            counts[row["section"]] = counts.get(row["section"], 0) + 1
            if len(row["monthly"]) != 12:
                problems.append(
                    f"{vintage}[{ri}]: {len(row['monthly'])} monthly values, expected 12"
                )
            if tuple(row["quarterly"]) != QUARTERS:
                problems.append(
                    f"{vintage}[{ri}]: quarterly keys {list(row['quarterly'])}"
                )
        if counts != EXPECTED_SECTIONS:
            problems.append(f"{vintage}: section counts {counts} != {EXPECTED_SECTIONS}")

    # Row identity must be shared across vintages -- the app indexes rows by
    # position and assumes DATA[a][i] and DATA[b][i] are the same line item.
    #
    # Deliberately excludes `label`. The deck is internally inconsistent there:
    # row 25 is "EBITDA Margin %" under Jul./Jun./May. FC and "EBITDA Margin"
    # under the other six vintages. It does not matter, because the deck's own
    # renderBody() overrides the displayed label for that section (source JS
    # line 365) and our port likewise takes labels from transforms.ROWS. This
    # JSON is consumed for NUMBERS only, so a label difference is not drift
    # worth failing on -- it is reported below instead.
    vintages = list(data)
    if vintages:
        def spine_of(v: str) -> list[tuple]:
            return [(r["section"], r["row_type"], r["is_pct"]) for r in data[v]]

        spine = spine_of(vintages[0])
        for v in vintages[1:]:
            other = spine_of(v)
            if other != spine:
                diff = next(
                    (i for i, (a, b) in enumerate(zip(spine, other)) if a != b), None
                )
                problems.append(
                    f"{v}: row spine differs from {vintages[0]} at index {diff}"
                )

        label_variants: dict[int, set[str]] = {}
        for ri in range(EXPECTED_ROWS):
            labels = {data[v][ri]["label"] for v in vintages}
            if len(labels) > 1:
                label_variants[ri] = labels
        for ri, labels in label_variants.items():
            print(
                f"note: row {ri} label varies across vintages {sorted(labels)} "
                "-- ignored, labels come from transforms.ROWS",
                file=sys.stderr,
            )

    if problems:
        print("DECK SHAPE PROBLEMS:", *problems, sep="\n  ", file=sys.stderr)
        raise SystemExit(1)


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"source deck not found: {SRC}")

    data = extract(SRC.read_text(encoding="utf-8"))
    validate(data)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Compact on purpose: this file is machine-read, and indenting 102 KB of
    # floats would triple it for no reader's benefit.
    OUT.write_text(
        json.dumps(data, separators=(",", ":"), sort_keys=False), encoding="utf-8"
    )

    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
    print(f"vintages ({len(data)}): {', '.join(data)}")
    print(f"rows per vintage: {len(next(iter(data.values())))}")
    # Spot value the plan's reconciliation quotes, so a re-export that shifts
    # units or row order is obvious here rather than three steps later.
    jul = data.get("Jul. FC")
    if jul:
        print(f"Jul. FC total revenue (row 6, annual): {jul[6]['annual']:,.2f}")
        print(f"Jul. FC total EBITDA  (row 24, annual): {jul[24]['annual']:,.2f}")
        print(f"Jul. FC EBITDA margin (row 25, annual): {jul[25]['annual']:.4f}")


if __name__ == "__main__":
    main()
