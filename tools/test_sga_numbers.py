"""Read-only tie-out of the SG&A tab (sga.py) against docs/fleet/cfd-sga-retie.md.

Runs sga.SQL (a SELECT) through the same connection as the app and checks:
- LB_302 / SEP26RF / FY26: template 402,433,283.86, Key Litigation
  2,778,538.51, Oracle total 405,211,822.37, check 0.00, Not mapped 0.00;
- LB_302 / 2027B-09.28 / FY27: Oracle total 483,119,838.51;
- Not mapped per LOB, 2027B-09.28 FY27, vs the retie report section 4.

    python tools/test_sga_numbers.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sga  # noqa: E402

FY = sga.FY
NOT_MAPPED_FY27 = {
    "LB_301": 0.0, "LB_302": 188_000.00, "LB_303": 34_561_724.22,
    "LB_304": 0.0, "LB_305": 9_827_811.41, "LB_306": 84_972_355.48,
    "LB_307": 43_024_723.29, "LB_308": 16_898_596.53,
}


def main() -> None:
    df = sga.load()
    problems: list[str] = []

    def check(label: str, got: float, want: float) -> None:
        ok = abs(got - want) < 0.005
        print(f"{label:<55} {got:>18,.2f}  want {want:>18,.2f}  {'ok' if ok else 'MISMATCH'}")
        if not ok:
            problems.append(label)

    r = sga.report(df, "LB_302", "SEP26RF", "FY26")
    print(f"rows in table: {len(r)} (52 Will + 6 subtotals + Pre-Allocations + "
          f"Not mapped + total + {sga.KEY_LIT} + check)")
    if len(r) != 63:
        problems.append(f"table has {len(r)} rows, not 63")
    order = [x for x in r.index if x in sga.TEMPLATE_ORDER]
    print(f"52 lines in template order: {order == list(sga.TEMPLATE_ORDER)}")
    if order != list(sga.TEMPLATE_ORDER):
        problems.append("lines are not in template order")
    pre, first, last = sga.PRE_ALLOC
    idx = list(r.index)
    pos_ok = idx[idx.index(pre) - 1] == "Benefits" and idx[idx.index(pre) + 1] == "Allocated Compensation"
    print(f"{pre!r} between Benefits and Allocated Compensation: {pos_ok}")
    if not pos_ok:
        problems.append(f"{pre} is not between Benefits and Allocated Compensation")
    check(f"subtotal {pre} (lines 1-4)", r.loc[pre, FY],
          r.loc[list(sga.TEMPLATE_ORDER[first - 1:last]), FY].sum())
    for name, first, last in sga.SUBTOTALS:
        want = r.loc[list(sga.TEMPLATE_ORDER[first - 1:last]), FY].sum()
        check(f"subtotal {name}", r.loc[name, FY], want)
    subs = sum(r.loc[n, FY] for n, _, _ in sga.SUBTOTALS) + r.loc["Marketing", FY]
    check("6 subtotals + Marketing + Not mapped = template total",
          subs + r.loc[sga.NOT_MAPPED, FY], r.loc[sga.TOTAL, FY])
    check("LB_302 SEP26RF FY26 template total", r.loc[sga.TOTAL, FY], 402_433_283.86)
    check("LB_302 SEP26RF FY26 Key Litigation", r.loc[sga.KEY_LIT, FY], 2_778_538.51)
    check("LB_302 SEP26RF FY26 Oracle total",
          sga.oracle_total(df, "LB_302", "SEP26RF", "FY26"), 405_211_822.37)
    check("LB_302 SEP26RF FY26 check row (FY)", r.loc[sga.CHECK, FY], 0.0)
    worst = r.loc[sga.CHECK, list(sga.MONTHS)].abs().max()
    check("LB_302 SEP26RF FY26 check row (worst month, abs)", worst, 0.0)
    check("LB_302 SEP26RF FY26 Not mapped", r.loc[sga.NOT_MAPPED, FY], 0.0)
    check("LB_302 2027B-09.28 FY27 Oracle total",
          sga.oracle_total(df, "LB_302", "2027B-09.28", "FY27"), 483_119_838.51)

    print("\nNot mapped, 2027B-09.28 FY27, vs cfd-sga-retie section 4:")
    for lob, want in NOT_MAPPED_FY27.items():
        rr = sga.report(df, lob, "2027B-09.28", "FY27")
        check(f"{lob} Not mapped", rr.loc[sga.NOT_MAPPED, FY], want)
        print(f"{'':<4}{lob} check row FY = {rr.loc[sga.CHECK, FY]:,.2f}")

    if problems:
        print("\nPROBLEMS:", *problems, sep="\n  ")
        raise SystemExit(1)
    print("\nOK -- sga.py ties")


def apptest() -> None:
    """The SG&A tab body alone in AppTest (no Income Statement deps needed)."""
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_string(
        f"import sys; sys.path.insert(0, {str(ROOT)!r})\nimport sga\nsga.render()\n",
        default_timeout=300).run()
    err = "; ".join(str(e.value) for e in at.exception)
    rows = list(at.dataframe[0].value.index) if at.dataframe else []
    print(f"\nAppTest sga.render(): exception={err or 'none'}, rows={len(rows)}, "
          f"total row shown={sga.TOTAL in rows}, {sga.KEY_LIT!r} shown={sga.KEY_LIT in rows}")
    print("first 8 rows:", rows[:8])
    print("subtotal rows:", [(rows.index(n), n) for n, _, _ in sga.SUBTOTALS if n in rows])
    print("last 4 rows:", rows[-4:])
    print("pickers:", [(s.label, s.value) for s in at.selectbox])
    if err or sga.TOTAL not in rows or sga.KEY_LIT not in rows:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
    apptest()
