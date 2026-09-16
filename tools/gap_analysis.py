"""Reconciliation diagnostic: the deck's Gross Margin / EBITDA vs the view's.

Revenue ties to the cent. Gross Margin and EBITDA do not. This script isolates
why, and how much of the gap is explainable.

    .venv\\Scripts\\python.exe tools\\gap_analysis.py

Reads the BASE table (ORACLE_DATA_PROD.FCT_EPM.CARDPLN_PL_BY_LOB) rather than
the view, because the view inner-joins CARDPLN_PL_ACCOUNT_LAYOUT and that join
silently drops 19 of the base table's 42 PL_LINEs -- including the one that
turns out to matter.

Five checks:

  COGS COMPOSITION   is ACX_Cost of Goods Sold == its 7 mapped children?
                     (no -- it is the 7 children PLUS ACX_Compensation)
  SUBTOTAL CHAIN     do the view's own subtotals tie to their inputs?
  SUPERSET           is ex. Emerging Services >= Physical Cards on every line?
                     (it must be -- Physical is a subset -- but it is not)
  BRIDGE             the deck-vs-view gap per vintage, before and after
                     removing Compensation from COGS
  UNEXPLAINED        what is left once every identified cause is corrected
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import snowflake.connector

import transforms as tx

CONN = os.getenv("SNOWFLAKE_DEFAULT_CONNECTION_NAME", "HIDR_PROD")
DECK = json.loads(
    (Path(__file__).resolve().parent.parent / "reference" / "deck_jul2026.json")
    .read_text(encoding="utf-8")
)
BASE = "ORACLE_DATA_PROD.FCT_EPM.CARDPLN_PL_BY_LOB"
M = 1e6

SEGS = {
    "na": "Total - North America Gross",
    "elim": "Total - Topps Eliminations",
    "intl": "Total - International incl Elims",
    "phys": "Total - Physical Cards",
    "exem": "Total - ex. Emerging Services",
    "fanlive": "Total - Fanatics Live and Collect",
    "keylit": "Total - Key Litigation",
}

COGS_KIDS = ["ACX_Manufacturing", "ACX_Royalties", "ACX_Net Freight Expense",
             "ACX_Product Development", "ACX_Autos & Relics",
             "ACX_MG Shortfall", "ACX_Obsolescence"]

# Vintage key derived exactly as queries.py does, but off the base table (which
# has SCENARIO, not FORECAST_ASOF_DATE -- the view derives the date from it).
SQL = f"""
SELECT
    CASE
      WHEN SCENARIO_LABEL = 'ACTUAL' THEN '20' || SUBSTR(FISCAL_YEAR, 3, 2) || 'A'
      WHEN SCENARIO_LABEL = 'BUDGET' THEN '20' || SUBSTR(FISCAL_YEAR, 3, 2) || 'B'
      ELSE INITCAP(LEFT(SCENARIO, 3)) || '. FC'
    END                    AS vintage,
    PERIOD_TYPE            AS ptype,
    PERIOD                 AS period,
    PL_LINE                AS line,
{chr(10).join(f"    ZEROIFNULL(SUM(IFF(LOB_SEGMENT = '{v}', AMOUNT, NULL))) AS {k}," for k, v in SEGS.items())}
    0 AS _pad
FROM {BASE}
WHERE (   (SCENARIO_LABEL = 'ACTUAL'   AND FISCAL_YEAR IN ('FY25','FY26'))
       OR (SCENARIO_LABEL = 'BUDGET'   AND FISCAL_YEAR = 'FY26')
       OR (SCENARIO_LABEL = 'FORECAST' AND FISCAL_YEAR = 'FY26'
           AND SCENARIO RLIKE '^[A-Z]{{3}}26RF$'))
GROUP BY 1, 2, 3, 4
"""


def fetch() -> pd.DataFrame:
    conn = snowflake.connector.connect(connection_name=CONN)
    try:
        cur = conn.cursor()
        cur.execute("USE SECONDARY ROLES NONE")
        cur.execute(SQL)
        df = cur.fetch_pandas_all()
    finally:
        conn.close()
    df.columns = [c.lower() for c in df.columns]
    for k in SEGS:
        df[k] = pd.to_numeric(df[k], errors="coerce").astype(float).fillna(0.0)
    df["total"] = df.exem + df.fanlive + df.keylit      # the app's _grand_total
    return df


def pivot(df: pd.DataFrame) -> pd.DataFrame:
    """(vintage, ptype, period) x line -> value, for one segment column."""
    return df.set_index(["vintage", "ptype", "period", "line"])


def main() -> None:
    df = fetch()
    print(f"connection: {CONN}")
    print(f"fetched {len(df):,} line-cells, {df.line.nunique()} distinct PL_LINEs, "
          f"{df.vintage.nunique()} vintages\n")

    segcols = list(SEGS) + ["total"]
    wide = df.pivot_table(index=["vintage", "ptype", "period"], columns="line",
                          values=segcols, aggfunc="sum", fill_value=0.0)

    def col(line: str, seg: str) -> pd.Series:
        return wide[(seg, line)] if (seg, line) in wide.columns else pd.Series(
            0.0, index=wide.index)

    # ------------------------------------------------------ 1. COGS composition
    print("=" * 92)
    print("1. COGS COMPOSITION -- does ACX_Cost of Goods Sold equal its 7 mapped children?")
    print("=" * 92)
    print(f"{'segment':<10} {'cells':>7} {'kids==subtotal':>15} {'kids+Comp==subtotal':>21} "
          f"{'max resid $':>13}")
    print("-" * 92)
    for seg in segcols:
        subtotal = col("ACX_Cost of Goods Sold", seg)
        kids = sum(col(k, seg) for k in COGS_KIDS)
        comp = col("ACX_Compensation", seg)
        r1, r2 = (kids - subtotal).abs(), (kids + comp - subtotal).abs()
        print(f"{seg:<10} {len(subtotal):>7,} {f'{(r1 < 1).mean()*100:.1f}%':>15} "
              f"{f'{(r2 < 1).mean()*100:.1f}%':>21} {r2.max():>13,.2f}")
    print("\n  => COGS = 7 mapped children + ACX_Compensation. ACX_Compensation is one")
    print("     of the 19 PL_LINEs the view's inner join to CARDPLN_PL_ACCOUNT_LAYOUT")
    print("     drops, so it is invisible in the view yet inside its COGS subtotal.")

    # -------------------------------------------------------- 2. subtotal chain
    print("\n" + "=" * 92)
    print("2. SUBTOTAL CHAIN -- are the view's own subtotals internally consistent?")
    print("=" * 92)
    checks = {
        "NetRev = GrossSales + GrossToNet":
            col("ACX_Gross Sales", "total") + col("ACX_Gross to Net", "total")
            - col("ACX_Net Revenue", "total"),
        "GM = NetRev - COGS":
            col("ACX_Net Revenue", "total") - col("ACX_Cost of Goods Sold", "total")
            - col("ACX_Gross Margin", "total"),
        "CM = GM - Marketing":
            col("ACX_Gross Margin", "total") - col("ACX_Marketing", "total")
            - col("ACX_Contribution Margin", "total"),
        "EBITDA = CM - SG&A":
            col("ACX_Contribution Margin", "total") - col("ACX_SG&A", "total")
            - col("ACX_EBITDA", "total"),
        "SG&A = Other SG&A":
            col("ACX_Other SG&A", "total") - col("ACX_SG&A", "total"),
    }
    for name, resid in checks.items():
        print(f"  {'ok ' if resid.abs().max() < 1 else 'FAIL'} {name:<40} "
              f"max |resid| {resid.abs().max():>14,.2f}")
    print("\n  => the chain ties. The view is self-consistent; the question is whether")
    print("     Compensation belongs in COGS at all.")

    # ------------------------------------------------------------- 3. superset
    print("\n" + "=" * 92)
    print("3. SUPERSET -- 'ex. Emerging Services' must be >= 'Physical Cards' on every")
    print("   cost line (Physical is a subset). Violations = the app's Digital residual")
    print("   goes negative.")
    print("=" * 92)
    print(f"{'line':<28} {'viol cells':>11} {'of':>7} {'worst exem-phys $':>19}")
    print("-" * 92)
    any_viol = False
    for line in sorted(df.line.unique()):
        resid = col(line, "exem") - col(line, "phys")
        # A cost line is stored positive, so a subset overshooting its superset
        # shows up as a negative residual.
        viol = resid < -1.0
        if viol.any():
            any_viol = True
            print(f"{line:<28} {viol.sum():>11,} {len(resid):>7,} {resid.min():>19,.2f}")
    if not any_viol:
        print("  (none)")
    print("\n  => Physical Cards exceeds its own superset. The 'Digital' residual the")
    print("     app derives (exem - phys) is therefore not a real segment.")

    # --------------------------------------------------------------- 4. bridge
    print("\n" + "=" * 92)
    print("4. BRIDGE -- annual, company total, $M. 'live+C' moves Compensation out of")
    print("   COGS (raising GM; EBITDA is unchanged by a COGS->opex reclass).")
    print("=" * 92)
    hdr = (f"{'vintage':>9} | {'rev gap':>8} | {'GM deck':>8} {'GM live':>8} "
           f"{'GM live+C':>9} {'GM resid':>9} | {'EB deck*':>9} {'EB live':>8} "
           f"{'EB resid':>9}")
    print(hdr)
    print("-" * len(hdr))
    rows = []
    for vintage in tx.order_vintages([v for v in df.vintage.unique() if v in DECK]):
        key = (vintage, "YEAR", "YearTotal")
        if key not in wide.index:
            key = next((k for k in wide.index if k[0] == vintage and k[1] == "YEAR"), None)
            if key is None:
                continue

        def v(line: str, seg: str = "total") -> float:
            return float(col(line, seg).loc[key])

        rev_deck = tx.deck_value(DECK, vintage, 6, tx.ANNUAL) or 0.0
        gm_deck = (tx.deck_value(DECK, vintage, 13, tx.ANNUAL) or 0.0) * rev_deck
        # Deck row 24 includes TCG, which the app's exem+fanlive+keylit cannot.
        # Compare like for like: rows 20 + 21 + 22.
        eb_deck = sum(tx.deck_value(DECK, vintage, i, tx.ANNUAL) or 0.0
                      for i in (20, 21, 22))

        rev, gm, eb = v("ACX_Net Revenue"), v("ACX_Gross Margin"), v("ACX_EBITDA")
        comp = v("ACX_Compensation")
        gm_c = gm + comp

        print(f"{vintage:>9} | {(rev-rev_deck)/M:8,.1f} | {gm_deck/M:8,.1f} "
              f"{gm/M:8,.1f} {gm_c/M:9,.1f} {(gm_c-gm_deck)/M:9,.1f} | "
              f"{eb_deck/M:9,.1f} {eb/M:8,.1f} {(eb-eb_deck)/M:9,.1f}")
        rows.append({"vintage": vintage, "rev": rev, "comp": comp,
                     "gm": gm, "gm_deck": gm_deck, "eb": eb, "eb_deck": eb_deck,
                     "mkt": v("ACX_Marketing"), "sga": v("ACX_SG&A")})
    print("  * EB deck = deck rows 20+21+22 (ex-Emerging + Fanatics Collect + Key Lit),")
    print("    the like-for-like of the app's exem+fanlive+keylit. Excludes TCG.")

    # ---------------------------------------------------------- 5. unexplained
    print("\n" + "=" * 92)
    print("5. UNEXPLAINED -- how much of each gap Compensation accounts for")
    print("=" * 92)
    hdr2 = (f"{'vintage':>9} | {'GM gap':>9} {'Comp':>9} {'explained':>10} "
            f"{'left':>9} | {'EB gap':>9} {'Comp':>9} {'left':>9}")
    print(hdr2)
    print("-" * len(hdr2))
    for r in rows:
        gm_gap = r["gm"] - r["gm_deck"]
        eb_gap = r["eb"] - r["eb_deck"]
        pct = r["comp"] / abs(gm_gap) * 100 if gm_gap else 0.0
        print(f"{r['vintage']:>9} | {gm_gap/M:9,.1f} {r['comp']/M:9,.1f} "
              f"{pct:9.0f}% {(gm_gap + r['comp'])/M:9,.1f} | "
              f"{eb_gap/M:9,.1f} {r['comp']/M:9,.1f} {(eb_gap + r['comp'])/M:9,.1f}")

    print("\n  GM  gap: Compensation explains most of it; a residual remains.")
    print("  EB  gap: a COGS->opex reclass does NOT change EBITDA, so if Compensation")
    print("           is genuinely opex the EBITDA gap is entirely unexplained; if it")
    print("           is double-counted (in COGS *and* inside Other SG&A) it explains")
    print("           the amount shown, and the 'left' column is what remains.")

    # ------------------------------------------- 6. actual months vs forecast
    # The residual in (5) grows monotonically with the number of ACTUAL months a
    # vintage contains (2026B, all budget, is the smallest; 2025A, all actual, is
    # the largest). If that is the driver, the gap should sit in Jan-Jun of
    # Jul. FC and vanish in Jul-Dec.
    print("\n" + "=" * 92)
    print("6. ACTUAL vs FORECAST MONTHS -- Jul. FC monthly, $M. Compensation already")
    print("   removed from COGS. Jan-Jun are actuals, Jul-Dec are forecast.")
    print("=" * 92)
    hdr3 = (f"{'month':<6} {'kind':<9} | {'GM deck':>9} {'GM live+C':>10} {'GM resid':>9} "
            f"| {'EB deck*':>9} {'EB live+C':>10} {'EB resid':>9}")
    print(hdr3)
    print("-" * len(hdr3))
    agg = {"actual": [0.0, 0.0], "forecast": [0.0, 0.0]}
    for i, mon in enumerate(tx.MONTHS):
        key = ("Jul. FC", "MONTH", mon)
        if key not in wide.index:
            continue

        def v(line: str) -> float:
            return float(col(line, "total").loc[key])

        rev_deck = tx.deck_value(DECK, "Jul. FC", 6, mon) or 0.0
        gm_deck = (tx.deck_value(DECK, "Jul. FC", 13, mon) or 0.0) * rev_deck
        eb_deck = sum(tx.deck_value(DECK, "Jul. FC", r, mon) or 0.0
                      for r in (20, 21, 22))
        gm_c = v("ACX_Gross Margin") + v("ACX_Compensation")
        eb_c = v("ACX_EBITDA") + v("ACX_Compensation")
        kind = "actual" if i < 6 else "forecast"
        agg[kind][0] += gm_c - gm_deck
        agg[kind][1] += eb_c - eb_deck
        print(f"{mon:<6} {kind:<9} | {gm_deck/M:9,.1f} {gm_c/M:10,.1f} "
              f"{(gm_c-gm_deck)/M:9,.1f} | {eb_deck/M:9,.1f} {eb_c/M:10,.1f} "
              f"{(eb_c-eb_deck)/M:9,.1f}")
    print("-" * len(hdr3))
    for kind, (g, e) in agg.items():
        print(f"{kind:<16} subtotal residual:  GM {g/M:>10,.1f}     EB {e/M:>10,.1f}")
    print("  * EB deck = deck rows 20+21+22.")


if __name__ == "__main__":
    main()
