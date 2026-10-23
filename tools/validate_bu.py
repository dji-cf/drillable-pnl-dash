"""Tie-out gates for the BU P&L pages. Exits non-zero on any failure.

    .venv\\Scripts\\python.exe tools\\validate_bu.py            # live: pull + gate
    .venv\\Scripts\\python.exe tools\\validate_bu.py --offline  # re-gate the last pull

Live mode runs three statements on ONE connection (one SSO login), under the
deployed app's identity (USE SECONDARY ROLES NONE): queries.MASTER_SQL, a
COGS parent/children census, and the reference bucket query. The master frame
is pickled so --offline re-runs every cube gate without Snowflake.

IDENTITIES -- per vintage x period x segment column, i.e. for every LOB and
every carve-out column separately. These are what the new SQL can get wrong:
    std_mfg + roy + mg + autos + other == cogs
    net_revenue - cogs                 == gross_margin
    gross_margin - mkt - sga           == ebitda   (also proves carve-out sign/scope)
TIES -- BU rows to consolidated rows, every vintage x period key. They hold by
construction now, so they guard bu.py's wiring rather than the SQL.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

import bu  # noqa: E402
import queries  # noqa: E402
import transforms as tx  # noqa: E402

CONN_NAME = os.getenv("SNOWFLAKE_DEFAULT_CONNECTION_NAME", "HIDR_PROD")
PICKLE = Path(tempfile.gettempdir()) / "drillable_pnl_golden" / "master_bu.pkl"
TOL = 1.0                     # dollars
PCT_TOL = 1e-9

#: The user's reference: LB_302, SEP26RF, FY27, $M, Other EXCLUDING Compensation.
REFERENCE_FY27 = {"std_mfg": 550.3, "roy": 995.5, "mg": 4.8, "autos": 332.5,
                  "other_ex_comp": 143.4}
REFERENCE_TOTAL_FY27 = 2026.5

_CARVE = ("pisa301", "pisa302", "tcgcc")
_BUCKET_LINES = ("std_mfg", "roy", "mg", "autos", "other")

_FILTER = f"""
      CHANNEL = 'Total Channel' AND PLAN_ELEMENT = 'Total_Budget'
  AND VERSION = 'Final' AND CURRENCY = 'USD_Reporting'
  AND ENTITY = '{queries.STG_ENTITY}'
  AND (   (LOB <> 'LB_392' AND INTERCOMPANY = '{queries.STG_ICP_TOTAL}')
       OR (LOB =  'LB_392' AND INTERCOMPANY = '{queries.STG_ICP_INTL_ELIMS}'))"""

_CHILDREN = ", ".join(f"'{a}'" for a in queries._STG_COGS_ACCOUNTS)

#: Where the COGS parent stands alone (no children) and where it disagrees with
#: its children, by LOB, across every scenario and period in the table.
CENSUS_SQL = f"""
WITH s AS (
  SELECT LOB, SCENARIO, FISCAL_YEAR, PERIOD, PERIOD_TYPE,
         SUM(IFF(ACCOUNT = 'AC_50000' AND COST_CENTER = 'CC_10000', AMOUNT, NULL)) AS parent,
         SUM(IFF(ACCOUNT IN ({_CHILDREN}) AND COST_CENTER = 'CC_10000', AMOUNT, NULL)) AS children
  FROM {queries.STG}
  WHERE {_FILTER.strip()}
  GROUP BY 1, 2, 3, 4, 5
)
SELECT LOB,
       COUNT_IF(parent IS NOT NULL AND children IS NULL AND parent <> 0)          AS parent_only,
       COUNT_IF(parent IS NOT NULL AND children IS NOT NULL
                AND ABS(parent - children) > 1)                                     AS mismatch
FROM s GROUP BY LOB ORDER BY LOB
"""

#: The bucket rules written out directly against the table, LB_302, SEP26RF,
#: annual, at FY27 (the user's figures) and FY26 (what the page shows).
REFERENCE_SQL = f"""
SELECT FISCAL_YEAR,
  SUM(IFF(ACCOUNT = 'ACX_Manufacturing', AMOUNT, 0)) / 1e6                    AS std_mfg,
  SUM(IFF(ACCOUNT = 'ACX_Royalties', AMOUNT, 0)) / 1e6                        AS roy,
  SUM(IFF(ACCOUNT = 'ACX_MG Shortfall', AMOUNT, 0)) / 1e6                     AS mg,
  SUM(IFF(ACCOUNT = 'ACX_Autos & Relics', AMOUNT, 0)) / 1e6                   AS autos,
  SUM(IFF(ACCOUNT IN ('ACX_Net Freight Expense', 'ACX_Product Development',
                      'ACX_Obsolescence'), AMOUNT, 0)) / 1e6                  AS other_ex_comp,
  SUM(IFF(ACCOUNT = 'ACX_Compensation', AMOUNT, 0)) / 1e6                     AS comp
FROM {queries.STG}
WHERE {_FILTER.strip()}
  AND LOB = 'LB_302' AND SCENARIO = 'SEP26RF' AND PERIOD_TYPE = 'YEAR'
  AND COST_CENTER = 'CC_10000' AND FISCAL_YEAR IN ('FY26', 'FY27')
GROUP BY FISCAL_YEAR ORDER BY FISCAL_YEAR
"""


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.lower() for c in df.columns]
    for col in [f"seg_{k}" for k in queries.SEGMENTS]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["is_actual_month"] = df["is_actual_month"].astype("boolean")
    df["forecast_asof_date"] = pd.to_datetime(df["forecast_asof_date"], errors="coerce")
    return df


def fetch_live() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    import snowflake.connector

    conn = snowflake.connector.connect(connection_name=CONN_NAME)
    try:
        cur = conn.cursor()
        cur.execute("USE SECONDARY ROLES NONE")
        out = []
        for sql in (queries.MASTER_SQL, CENSUS_SQL, REFERENCE_SQL):
            cur.execute(sql)
            df = cur.fetch_pandas_all()
            df.columns = [c.lower() for c in df.columns]
            out.append(df)
    finally:
        conn.close()
    master = _normalise(out[0])
    PICKLE.parent.mkdir(parents=True, exist_ok=True)
    master.to_pickle(PICKLE)
    return master, out[1], out[2]


# ---------------------------------------------------------------------------
# Cube gates
# ---------------------------------------------------------------------------
def check_identities(cube: tx.Cube) -> tuple[int, list[str]]:
    fails: list[str] = []
    n = 0
    for (v, line, pk), rev in cube.segs.items():
        if line != "net_revenue":
            continue
        get = {ln: cube.segs.get((v, ln, pk)) for ln in
               ("cogs", "gross_margin", "ebitda", "mkt", "sga", *_BUCKET_LINES)}
        missing = [ln for ln, s in get.items() if s is None]
        if missing:
            fails.append(f"{v} {pk}: lines missing from the cube: {missing}")
            continue
        for col in queries.SEGMENTS:
            n += 1
            buckets = sum(get[b][col] for b in _BUCKET_LINES)
            if abs(buckets - get["cogs"][col]) > TOL:
                fails.append(f"BUCKETS {v} {pk} {col}: {buckets:,.2f} != cogs "
                             f"{get['cogs'][col]:,.2f}")
            if abs(rev[col] - get["cogs"][col] - get["gross_margin"][col]) > TOL:
                fails.append(f"GM {v} {pk} {col}: rev - cogs != gross_margin")
            eb = get["gross_margin"][col] - get["mkt"][col] - get["sga"][col]
            if abs(eb - get["ebitda"][col]) > TOL:
                fails.append(f"EBITDA {v} {pk} {col}: gm - mkt - sga {eb:,.2f} != "
                             f"ebitda {get['ebitda'][col]:,.2f}")
    return n, fails


def check_carveouts(cube: tx.Cube) -> tuple[int, list[str]]:
    """Zero off the ebitda / sga lines; on sga, the exact negation of ebitda."""
    fails: list[str] = []
    n = 0
    for (v, line, pk), segs in cube.segs.items():
        for c in _CARVE:
            n += 1
            if line == "sga":
                eb = cube.segs[(v, "ebitda", pk)][c]
                if abs(segs[c] + eb) > TOL:
                    fails.append(f"{v} {pk} {c}: sga {segs[c]:,.2f} is not -ebitda {eb:,.2f}")
            elif line != "ebitda" and abs(segs[c]) > TOL:
                fails.append(f"{v} {pk} {line} {c}: {segs[c]:,.2f}, expected 0")
    return n, fails


def _row(section: str, label: str) -> tx.Row:
    return next(r for r in tx.ROWS if (r.section, r.label) == (section, label))


def _bu_row(rows: tuple[tx.Row, ...], label: str) -> tx.Row:
    return next(r for r in rows if r.label == label)


def _keys(cube: tx.Cube, v: str) -> list[str]:
    return sorted({pk for g in tx.GRAINS for pk, _ in cube.periods(v, g)})


def check_ties(cube: tx.Cube) -> tuple[int, list[str]]:
    fails: list[str] = []
    n = 0
    for key in bu.BU_KEYS:
        name = bu.BU_NAMES[key]
        rows = bu.rows(key, cube)
        pairs = [
            (_bu_row(rows, "Gross Margin %"), _row("Gross Margin", name)),
            (_bu_row(rows, "EBITDA"), _row("EBITDA", name)),
        ]
        if key == "na":
            pairs.append((_bu_row(rows, "North America incl. eliminations"),
                          _row("Revenue", name)))
        else:
            pairs.append((_bu_row(rows, "Net Revenue"), _row("Revenue", name)))
        for v in cube.vintages:
            for pk in _keys(cube, v):
                for b, m in pairs:
                    x, y = cube.value(v, b, pk), cube.value(v, m, pk)
                    if x is None and y is None:
                        continue
                    n += 1
                    tol = PCT_TOL if b.is_pct else TOL
                    if x is None or y is None or abs(x - y) > tol:
                        fails.append(f"{name} {b.label} {v} {pk}: {x} != main "
                                     f"{m.section}/{m.label} {y}")
                if key == "na":
                    rev = cube.value(v, _bu_row(rows, "Net Revenue"), pk)
                    topps = cube.value(v, _bu_row(rows, "Topps eliminations"), pk)
                    main = cube.value(v, _row("Revenue", name), pk)
                    if None not in (rev, topps, main):
                        n += 1
                        if abs(rev + topps - main) > TOL:
                            fails.append(f"NA {v} {pk}: Net Revenue + Topps memo "
                                         f"{(rev + topps) / 1e6:,.2f} != row 0 "
                                         f"{main / 1e6:,.2f}")
                # The buckets on screen sum to Total COGS (the BU_OMIT guard).
                buckets = [r for r in rows if r.section == "Cost of Goods Sold"
                           and r.label != "Total COGS"]
                total = _bu_row(rows, "Total COGS")
                t = cube.value(v, total, pk)
                parts = [cube.value(v, r, pk) for r in buckets]
                if t is not None and None not in parts:
                    n += 1
                    if abs(sum(parts) - t) > 1e-9:
                        fails.append(f"{name} {v} {pk}: COGS % rows sum "
                                     f"{sum(parts):.6f} != Total COGS {t:.6f}")
    return n, fails


def check_omit(cube: tx.Cube) -> tuple[int, list[str]]:
    fails: list[str] = []
    n = 0
    for key, lines in bu.BU_OMIT.items():
        for line in lines:
            n += 1
            if bu._nonzero(cube, line, queries.BU_DEFS[key]):
                fails.append(f"{bu.BU_NAMES[key]}: omitted bucket {line!r} is non-zero "
                             f"in the loaded cube (the page shows it anyway)")
    return n, fails


def warn_marketing(cube: tx.Cube) -> list[str]:
    """Marketing above the SG&A parent, i.e. negative SG&A ex Marketing."""
    base = [k for k in queries.SEGMENTS if k not in _CARVE]
    out = []
    for (v, line, pk), segs in cube.segs.items():
        if line != "sga":
            continue
        for k in base:
            if segs[k] < -TOL:
                out.append(f"{v} {pk} {k}: SG&A ex Marketing {segs[k] / 1e6:,.2f}M")
    return out


def check_guards(df: pd.DataFrame) -> list[str]:
    multi = df[(df["max_n_entity"] > 1) | (df["max_n_icp"] > 1)]
    return [f"{len(multi)} rows with >1 ENTITY or INTERCOMPANY per LOB tuple"] if len(multi) else []


# ---------------------------------------------------------------------------
# Live gates
# ---------------------------------------------------------------------------
_BU_LOBS = {queries.STG_SEGMENTS[k] for terms in queries.BU_DEFS.values()
            for _, k in terms if k in queries.STG_SEGMENTS and k not in _CARVE}


def check_census(census: pd.DataFrame) -> list[str]:
    fails = []
    for rec in census.to_dict("records"):
        if rec["mismatch"]:
            fails.append(f"{rec['lob']}: COGS parent != children in {rec['mismatch']} slices")
        if rec["parent_only"] and rec["lob"] in _BU_LOBS and rec["lob"] != "LB_394":
            fails.append(f"{rec['lob']}: parent-only COGS in {rec['parent_only']} slices "
                         f"-- the std_mfg residual is no longer LB_394 alone")
    if not any(r["lob"] == "LB_394" and r["parent_only"] for r in census.to_dict("records")):
        fails.append("LB_394 no longer carries a parent-only COGS (census changed)")
    return fails


def check_reference(ref: pd.DataFrame, cube: tx.Cube) -> list[str]:
    fails = []
    by_fy = {r["fiscal_year"]: r for r in ref.to_dict("records")}
    fy27 = by_fy.get("FY27")
    if fy27 is None:
        fails.append("reference: no SEP26RF FY27 rows")
    else:
        for k, want in REFERENCE_FY27.items():
            if abs(round(float(fy27[k]), 1) - want) > 0.05:
                fails.append(f"reference FY27 {k}: {float(fy27[k]):,.2f} != {want}")
        total = sum(float(fy27[k]) for k in REFERENCE_FY27)
        if abs(round(total, 1) - REFERENCE_TOTAL_FY27) > 0.15:
            fails.append(f"reference FY27 total {total:,.2f} != {REFERENCE_TOTAL_FY27}")
    fy26 = by_fy.get("FY26")
    vintage = "Sep 2026 FC"
    if fy26 is None or vintage not in cube.vintages:
        fails.append(f"reference FY26 leg: {'no rows' if fy26 is None else vintage + ' not in cube'}")
        return fails
    comp = float(fy26["comp"])
    for line in _BUCKET_LINES:
        got = cube.segs[(vintage, line, tx.ANNUAL)]["l302"] / 1e6
        want = float(fy26["other_ex_comp" if line == "other" else line])
        if line == "other":
            got -= comp
        if abs(got - want) > 1e-4:
            fails.append(f"reference FY26 {line}: cube l302 {got:,.4f} != direct {want:,.4f}")
    return fails


def main() -> None:
    offline = "--offline" in sys.argv
    if queries.SOURCE != "STG":
        print("PNL_SOURCE is not STG: there are no BU pages to validate.")
        raise SystemExit(1)
    if offline:
        df, census, ref = pd.read_pickle(PICKLE), None, None
    else:
        df, census, ref = fetch_live()
    cube = tx.build_cube(df)
    print(f"{'offline ' + str(PICKLE) if offline else 'connection ' + CONN_NAME} · "
          f"{len(df):,} rows · {len(cube.vintages)} vintages")

    suites: list[tuple[str, str, list[str]]] = []
    n, f = check_identities(cube)
    suites.append(("IDENTITIES", f"{n:,} vintage x period x column cells", f))
    n, f = check_carveouts(cube)
    suites.append(("CARVE-OUTS", f"{n:,} cells", f))
    n, f = check_ties(cube)
    suites.append(("BU TIES", f"{n:,} BU-to-consolidated cells", f))
    n, f = check_omit(cube)
    suites.append(("BU_OMIT", f"{n} omitted buckets", f))
    suites.append(("ONE ENTITY", "max_n_entity / max_n_icp <= 1", check_guards(df)))
    if census is not None:
        suites.append(("COGS CENSUS", f"{len(census)} LOBs", check_census(census)))
        suites.append(("REFERENCE", "LB_302 SEP26RF FY27 + FY26 leg",
                       check_reference(ref, cube)))
        if ref is not None:
            for r in ref.to_dict("records"):
                print(f"  reference {r['fiscal_year']}: " + ", ".join(
                    f"{k} {float(r[k]):,.1f}" for k in (*REFERENCE_FY27, "comp")))

    failed = False
    for name, what, fails in suites:
        print(f"{name:<12} {'FAIL' if fails else 'pass'}  ({what})")
        for p in fails[:15]:
            print(f"  {p}")
        if len(fails) > 15:
            print(f"  ... and {len(fails) - 15} more")
        failed |= bool(fails)

    warnings = warn_marketing(cube)
    print(f"{'MARKETING':<12} {'warn' if warnings else 'pass'}  "
          f"(Marketing <= SG&A parent; a warning, not a gate)")
    for w in warnings[:10]:
        print(f"  {w}")
    if len(warnings) > 10:
        print(f"  ... and {len(warnings) - 10} more")

    print("\n" + ("FAILED" if failed else "ALL BU GATES PASS"))
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
