"""Is the Compensation correction a calculated value, or a plug fitted to the deck?

Dev-only, throwaway. Answers one question: does ACX_Compensation's OWN magnitude
independently equal the live-vs-deck EBITDA gap, or was the adjustment sized to
close it?

A plug is defined as (deck - live), so it ties everywhere by construction. A
calculated value has a magnitude nobody chose, so it can only tie where the
hypothesis it encodes is actually true -- and must leave a residual elsewhere.
Run against Jul. FC at month grain, which separates actual from forecast months.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import data  # noqa: E402

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
GRAND_TOTAL = ["seg_exem", "seg_fanlive", "seg_keylit"]
VINTAGE = "Jul 2026 FC"
#: The same vintage as reference/deck_jul2026.json keys it (the deck's own name).
DECK_VINTAGE = "Jul. FC"
#: The deck rows the source can express -- ex-Emerging + Collect + Key Lit.
#: Deliberately NOT row 24, which includes TCG (no segment exists for it).
DECK_ROWS = (20, 21, 22)

DECK_JSON = Path(__file__).resolve().parent.parent / "reference" / "deck_jul2026.json"


def main() -> int:
    # __wrapped__ bypasses @st.cache_data outside a Streamlit runtime.
    df, _ = data.load_master.__wrapped__()
    deck = json.loads(DECK_JSON.read_text(encoding="utf-8"))

    sub = df[(df.vintage_key == VINTAGE) & (df.period_type == "MONTH")]

    def live(line: str, month: str) -> float:
        r = sub[(sub.pl_line == line) & (sub.period == month)]
        return float(r[GRAND_TOTAL].sum(axis=1).iloc[0]) if len(r) else float("nan")

    def deck_val(month: str) -> float:
        i = MONTHS.index(month)
        total = 0.0
        for row in DECK_ROWS:
            monthly = deck[DECK_VINTAGE][row].get("monthly") or []
            if i < len(monthly) and monthly[i] is not None:
                total += float(monthly[i])
        return total

    hdr = (f"{'Mon':<5}{'actual':<8}{'raw EBITDA':>13}{'Comp':>11}"
           f"{'gap BEFORE':>13}{'gap AFTER':>12}")
    print(hdr)
    print("-" * len(hdr))

    totals = [0.0, 0.0, 0.0, 0.0]
    fc_after = act_after = 0.0

    for month in MONTHS:
        raw = live("ACX_EBITDA", month)
        comp = live("ACX_Compensation", month)
        dk = deck_val(month)
        before, after = raw - dk, raw + comp - dk

        flag = sub[(sub.pl_line == "ACX_EBITDA") & (sub.period == month)]["is_actual_month"]
        is_act = bool(flag.iloc[0]) if len(flag) else False

        print(f"{month:<5}{('yes' if is_act else 'no'):<8}{raw/1e6:>13,.1f}"
              f"{comp/1e6:>11,.1f}{before/1e6:>13,.1f}{after/1e6:>12,.1f}")

        for j, v in enumerate((raw, comp, before, after)):
            totals[j] += v
        if is_act:
            act_after += after
        else:
            fc_after += after

    print("-" * len(hdr))
    print(f"{'YEAR':<5}{'':<8}{totals[0]/1e6:>13,.1f}{totals[1]/1e6:>11,.1f}"
          f"{totals[2]/1e6:>13,.1f}{totals[3]/1e6:>12,.1f}")
    print()
    print(f"residual after correction, FORECAST months: {fc_after/1e6:>+10,.1f}M")
    print(f"residual after correction, ACTUAL months:   {act_after/1e6:>+10,.1f}M")
    print()
    if abs(fc_after) < 1e6 and abs(act_after) > 1e7:
        print("=> CALCULATED. Ties forecast months on its own magnitude and leaves")
        print("   a large actual-month residual. A plug would zero both.")
    else:
        print("=> inconclusive under these thresholds; inspect the columns above.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
