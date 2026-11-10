"""Product Revenue (NA) -- the 5th top tab of the Collectibles Financial Dashboard.

Net Revenue excluding intercompany, by license > product release (COA), by
month / quarter / FY. North America only: the GM plan (Sep 2026 FC, SEP26RF)
covers entity CO_31010 (NASE), LOB LB_312 and nothing else. Requested by Megan
Coleman (FP&A); see docs/fleet/cfd-prodrev-na.md for the tie-out to her file.

- FY26 months come from GMPLN_PRODUCT_RELEASE_BY_COA_MONTHLY_V (the view behind
  Megan's "Product Release" file; ties to her FY26 4,086,943,019.71 exactly).
- Later FYs come from GMPLN_PL_BY_SKU_CHANNEL_V: Net Revenue minus
  Intercompany Revenue, 12 real months only.
- GMPLN has no license. Each COA takes the PRICING_LICENSE of its SKUs
  (DESA_SILVER.PRICING.SKU, first 9 chars of the base SKU); COAs with no match
  are kept under "(No license)".
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import data

NO_LICENSE = "(No license)"
TOTAL = "Total"

PRODUCT_REVENUE_SQL = """
WITH px AS (
    SELECT LEFT(sku, 9) AS sku9, MAX(pricing_license) AS license
    FROM DESA_SILVER.PRICING.SKU
    WHERE pricing_license IS NOT NULL
    GROUP BY 1
),
sku_rev AS (
    SELECT v.coa, v.fiscal_year, v.period_date, px.license,
           SUM(IFF(v.acx_line = 'ACX_Net Revenue', v.amount, -v.amount)) AS net_rev
    FROM ORACLE_DATA_PROD.FCT_EPM.GMPLN_PL_BY_SKU_CHANNEL_V v
    LEFT JOIN px ON LEFT(SPLIT_PART(v.sku, '-', 1), 9) = px.sku9
    WHERE v.scenario = 'SEP26RF' AND v.version = 'Final'
      AND v.entity = 'CO_31010' AND v.lob = 'LB_312'
      AND v.month IN ('Jan','Feb','Mar','Apr','May','Jun',
                      'Jul','Aug','Sep','Oct','Nov','Dec')
      AND v.acx_line IN ('ACX_Net Revenue', 'ACX_Intercompany Revenue')
    GROUP BY 1, 2, 3, 4
),
coa_license AS (
    SELECT coa, license FROM (
        SELECT coa, license, SUM(ABS(net_rev)) AS w
        FROM sku_rev WHERE license IS NOT NULL GROUP BY 1, 2)
    QUALIFY ROW_NUMBER() OVER (PARTITION BY coa ORDER BY w DESC, license) = 1
),
rel AS (
    SELECT coa, product_name,
           netrev_jan26, netrev_feb26, netrev_mar26, netrev_apr26,
           netrev_may26, netrev_jun26, netrev_jul26, netrev_aug26,
           netrev_sep26, netrev_oct26, netrev_nov26, netrev_dec26
    FROM ORACLE_DATA_PROD.FCT_EPM.GMPLN_PRODUCT_RELEASE_BY_COA_MONTHLY_V
    WHERE forecast_asof = 'SEP26RF' AND current_fy = 'FY26'
),
fy26 AS (
    SELECT coa, 'FY26' AS fiscal_year,
           DATE_FROM_PARTS(2026, TO_NUMBER(DECODE(mon,
               'NETREV_JAN26', 1, 'NETREV_FEB26', 2, 'NETREV_MAR26', 3,
               'NETREV_APR26', 4, 'NETREV_MAY26', 5, 'NETREV_JUN26', 6,
               'NETREV_JUL26', 7, 'NETREV_AUG26', 8, 'NETREV_SEP26', 9,
               'NETREV_OCT26', 10, 'NETREV_NOV26', 11, 'NETREV_DEC26', 12)), 1)
               AS period_date,
           net_rev
    FROM rel UNPIVOT (net_rev FOR mon IN (
        netrev_jan26, netrev_feb26, netrev_mar26, netrev_apr26,
        netrev_may26, netrev_jun26, netrev_jul26, netrev_aug26,
        netrev_sep26, netrev_oct26, netrev_nov26, netrev_dec26))
),
later AS (
    SELECT coa, fiscal_year, period_date, SUM(net_rev) AS net_rev
    FROM sku_rev WHERE fiscal_year = 'FY27' GROUP BY 1, 2, 3
),
allrev AS (SELECT * FROM fy26 UNION ALL SELECT * FROM later)
SELECT COALESCE(l.license, '(No license)') AS license,
       a.coa,
       COALESCE(r.product_name, a.coa) AS product_name,
       a.fiscal_year,
       a.period_date,
       SUM(a.net_rev) AS net_rev
FROM allrev a
LEFT JOIN coa_license l ON l.coa = a.coa
LEFT JOIN rel r ON r.coa = a.coa
WHERE a.net_rev <> 0
GROUP BY 1, 2, 3, 4, 5
ORDER BY 1, 2, 5
"""


def load() -> pd.DataFrame:
    """Flat rows: license, coa, product_name, fiscal_year, period_date, net_rev ($)."""
    df = data._q(PRODUCT_REVENUE_SQL)
    df["period_date"] = pd.to_datetime(df["period_date"])
    df["net_rev"] = pd.to_numeric(df["net_rev"]).astype(float)
    return df


def _period(df: pd.DataFrame, grain: str) -> pd.Series:
    d = df["period_date"]
    if grain == "Month":
        return d.dt.strftime("%Y-%m")
    if grain == "Quarter":
        return "Q" + d.dt.quarter.astype(str) + "'" + d.dt.strftime("%y")
    return df["fiscal_year"]


def pivot(df: pd.DataFrame, grain: str) -> pd.DataFrame:
    """License subtotal row, then its releases, then a Total row; values in $M."""
    df = df.assign(period=_period(df, grain))
    cols = sorted(df["period"].unique(), key=lambda p: df.loc[df["period"] == p, "period_date"].min())
    rel = df.pivot_table(index=["license", "coa", "product_name"], columns="period",
                         values="net_rev", aggfunc="sum", fill_value=0.0)[cols]
    lic = rel.groupby(level="license").sum()
    # Biggest license first, "(No license)" last.
    order = lic.sum(axis=1).sort_values(ascending=False).index.tolist()
    if NO_LICENSE in order:
        order.remove(NO_LICENSE)
        order.append(NO_LICENSE)
    rows = []
    for name in order:
        rows.append({"License": name, "COA": "", "Product release": f"{name} total", **lic.loc[name]})
        part = rel.loc[name]
        part = part.loc[part.sum(axis=1).sort_values(ascending=False).index]
        for (coa, prod), vals in part.iterrows():
            rows.append({"License": "", "COA": coa, "Product release": prod, **vals})
    rows.append({"License": TOTAL, "COA": "", "Product release": "", **rel.sum()})
    out = pd.DataFrame(rows)
    out[cols] = out[cols] / 1e6
    return out


def render() -> None:
    st.subheader("Product Revenue (NA) - Net Revenue ex intercompany, $M")
    st.caption("GM plan, Sep 2026 FC (SEP26RF), entity CO_31010, LOB LB_312. "
               "License from DESA_SILVER.PRICING.SKU; unmatched releases under "
               f"\"{NO_LICENSE}\".")
    grain = st.segmented_control("Period", ["Month", "Quarter", "FY"],
                                 default="Quarter", key="prodrev_grain") or "Quarter"
    try:
        df = load()
    except Exception as e:  # noqa: BLE001 -- show the error, keep the other tabs alive
        st.error(f"Could not load product revenue: {e}")
        return
    if df.empty:
        st.info("No product revenue rows.")
        return
    if (df["fiscal_year"] == "FY27").any():
        # Maya, 2026-11-03 15:24: keep FY27, flag the gap to Megan's file.
        st.caption("FY27 is $157M below Megan's file; under review with Megan.")
    table = pivot(df, grain)
    num_cols = [c for c in table.columns if c not in ("License", "COA", "Product release")]
    st.dataframe(table, hide_index=True, width="stretch",
                 column_config={c: st.column_config.NumberColumn(c, format="%.1f")
                                for c in num_cols})
    st.download_button("Download CSV (flat, $)",
                       df.to_csv(index=False).encode("utf-8"),
                       file_name="product_revenue_na.csv", mime="text/csv",
                       key="prodrev_csv")
