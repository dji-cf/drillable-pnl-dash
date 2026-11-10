"""Pure chart logic for the Product Revenue (NA) view (pandas only).

Megan Coleman's artifact rules (meeting "Claude Artifact Clarifications",
2026-10-30; Slack DM D0CCD1N88CT 2026-10-30 11:48 ET):
  1. License = first 3 letters of the COA code (NFL2418 -> NFL). COAs that are
     not "3 letters + digit" (10003 "NFL - General", UNKNOWN, PD02624) are Other.
  2. Release $ = COAs with a license prefix; Other = everything else. Other is
     its own block at the bottom of each bar.
  3. Bar % = license $ / quarter release $ (excl. Other).
     Quarter chip % = quarter $ (incl. Other) / FY $.
  4. Size tier per COA per quarter from the edges the caller passes in.
  5. Release count per license = COAs, each counted in its peak quarter only.
No streamlit, no Snowflake: tools/test_prodrev_viz.py imports this module.
"""
from __future__ import annotations

import re

import pandas as pd

OTHER = "Other"
TENTPOLE = "Tentpole"
_PREFIX = re.compile(r"^([A-Za-z]{3})[0-9]")


def license_from_coa(coa) -> str:
    """Rule 1: 'NFL2418' -> 'NFL'; '10003', 'UNKNOWN', None -> 'Other'."""
    m = _PREFIX.match(str(coa or "").strip())
    return m.group(1).upper() if m else OTHER


def quarter_label(dates: pd.Series) -> pd.Series:
    """Q1'26 style, same text as product_revenue._period(grain='Quarter')."""
    d = pd.to_datetime(dates)
    return "Q" + d.dt.quarter.astype(str) + "'" + d.dt.strftime("%y")


def tier_labels(edges) -> list[str]:
    """(10e6, 25e6, 35e6, 50e6) -> ['<10M', '10-25M', '25-35M', '35-50M', 'Tentpole']."""
    m = [f"{e / 1e6:g}" for e in edges]
    return [f"<{m[0]}M"] + [f"{a}-{b}M" for a, b in zip(m, m[1:])] + [TENTPOLE]


def size_tier(amount: float, edges) -> str:
    """Rule 4: lower edge inclusive; amount >= last edge is 'Tentpole'."""
    labels = tier_labels(edges)
    for i, e in enumerate(edges):
        if amount < e:
            return labels[i]
    return labels[-1]


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Add coa_license (rule 1) and quarter to the flat load() rows."""
    return df.assign(coa_license=df["coa"].map(license_from_coa),
                     quarter=quarter_label(df["period_date"]))


def _quarter_order(df: pd.DataFrame) -> list[str]:
    first = df.groupby("quarter")["period_date"].min().sort_values()
    return first.index.tolist()


def quarter_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per quarter: total $, release $, Other $, Other %, FY $, chip % (rule 3)."""
    df = prepare(df) if "coa_license" not in df else df
    is_other = df["coa_license"] == OTHER
    g = df.assign(release=df["net_rev"].where(~is_other, 0.0),
                  other=df["net_rev"].where(is_other, 0.0))
    out = g.groupby(["fiscal_year", "quarter"], as_index=False)[["net_rev", "release", "other"]].sum()
    out = out.rename(columns={"net_rev": "total"})
    out["fy_total"] = out.groupby("fiscal_year")["total"].transform("sum")
    out["chip_pct"] = out["total"] / out["fy_total"]
    out["other_pct"] = out["other"] / out["total"]
    order = {q: i for i, q in enumerate(_quarter_order(df))}
    return out.sort_values("quarter", key=lambda s: s.map(order)).reset_index(drop=True)


def release_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Rule 5: each release COA counted once, in its peak quarter ($ max).

    Ties go to the earlier quarter. Returns quarter, coa_license, releases.
    """
    df = prepare(df) if "coa_license" not in df else df
    rel = df[df["coa_license"] != OTHER]
    if rel.empty:
        return pd.DataFrame(columns=["quarter", "coa_license", "releases"])
    order = {q: i for i, q in enumerate(_quarter_order(df))}
    q = rel.groupby(["coa_license", "coa", "quarter"], as_index=False)["net_rev"].sum()
    q["qi"] = q["quarter"].map(order)
    q = q.sort_values(["coa", "net_rev", "qi"], ascending=[True, False, True])
    peak = q.drop_duplicates("coa")
    return (peak.groupby(["quarter", "coa_license"], as_index=False)["coa"].count()
            .rename(columns={"coa": "releases"}))


def bar_frame(df: pd.DataFrame, by: str, edges) -> pd.DataFrame:
    """One row per (quarter, segment) for a stacked bar.

    by = "license": segment = COA-prefix license; label = code + bar % + count.
    by = "tier": segment = size tier of each COA's quarter $; % of release $.
    Other is always the bottom block (stack order 0); its pct is of the full bar.
    Columns: quarter, segment, net_rev, pct, releases, y0, y1, label, chip.
    """
    df = prepare(df) if "coa_license" not in df else df
    summ = quarter_summary(df).set_index("quarter")
    if by == "tier":
        cq = df.groupby(["quarter", "coa_license", "coa"], as_index=False)["net_rev"].sum()
        cq["segment"] = [OTHER if lic == OTHER else size_tier(v, edges)
                         for lic, v in zip(cq["coa_license"], cq["net_rev"])]
        seg = cq.groupby(["quarter", "segment"], as_index=False)["net_rev"].sum()
        seg["releases"] = 0  # counts are per license, not per tier
        rank = {t: i + 1 for i, t in enumerate(tier_labels(edges))}
    else:
        seg = (df.groupby(["quarter", "coa_license"], as_index=False)["net_rev"].sum()
               .rename(columns={"coa_license": "segment"}))
        cnt = release_counts(df).rename(columns={"coa_license": "segment"})
        seg = seg.merge(cnt, on=["quarter", "segment"], how="left")
        seg["releases"] = seg["releases"].fillna(0).astype(int)
        size = seg[seg["segment"] != OTHER].groupby("segment")["net_rev"].sum()
        # Biggest license sits just above Other.
        rank = {s: i + 1 for i, s in enumerate(size.sort_values(ascending=False).index)}
    rank[OTHER] = 0
    seg["stack"] = seg["segment"].map(rank)
    rel = seg["quarter"].map(summ["release"])
    tot = seg["quarter"].map(summ["total"])
    seg["pct"] = (seg["net_rev"] / rel).where(seg["segment"] != OTHER, seg["net_rev"] / tot)
    qorder = {q: i for i, q in enumerate(summ.index)}
    seg = seg.sort_values(["quarter", "stack"], key=lambda s: s.map(qorder) if s.name == "quarter" else s)
    seg["y1"] = seg.groupby("quarter")["net_rev"].cumsum()
    seg["y0"] = seg["y1"] - seg["net_rev"]

    def _label(r) -> str:
        if r["segment"] == OTHER:
            return f"Other {r['pct']:.1%} of bar"
        txt = f"{r['segment']} {r['pct']:.1%}"
        if by != "tier" and r["releases"]:
            txt += f" · {r['releases']}"
        return txt

    seg["label"] = seg.apply(_label, axis=1)
    seg["chip"] = [f"{q} · {summ.loc[q, 'chip_pct']:.1%} of {summ.loc[q, 'fiscal_year']}"
                   for q in seg["quarter"]]
    return seg.reset_index(drop=True)[["quarter", "segment", "net_rev", "pct", "releases",
                                       "stack", "y0", "y1", "label", "chip"]]
