"""CSS for the statement grid and the page shell.

Two separate stylesheets, and the split is not cosmetic:

TABLE_CSS ships to the Component v2 renderer via its ``css=`` parameter. That
component renders inside a SHADOW DOM (interactive.py never passes
isolate_styles, so the isolating default applies), which page-level styles
cannot pierce. Injecting this with st.markdown would silently do nothing.

PAGE_CSS is injected into the page for the parts that are ordinary Streamlit
markup -- the dark header band and the KPI tiles.

Everything from ``table`` down to ``tr.collapsed`` is ported from the source
deck (HTML lines 43-98) close to verbatim, because the pixel fidelity of the
statement is the point of the exercise. The one addition is ``tr.gap-row``, for
the four rows the source cannot express -- the deck had no notion of those.
"""
from __future__ import annotations

import streamlit as st

# ---------------------------------------------------------------------------
# Inside the component's shadow DOM
# ---------------------------------------------------------------------------
TABLE_CSS = """
:host { display: block; }
* , *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

.table-wrap {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 1px 4px rgba(0,0,0,.08);
  overflow-x: auto;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Arial, sans-serif;
  color: #1a2b4a;
}

table { border-collapse: collapse; width: 100%; font-size: 12px; }

/* ── Group header row ── */
thead tr.group-row th {
  padding: 8px 8px 6px; font-size: 11px; font-weight: 800; text-align: center;
  letter-spacing: .3px; white-space: nowrap;
  border-bottom: 1px solid rgba(255,255,255,.1);
}
thead tr.group-row th.lbl-th {
  background: #1a2b4a; color: transparent; min-width: 210px; text-align: left;
  border-right: 2px solid #2d4a7a; position: sticky; left: 0; z-index: 4;
}
thead tr.group-row th.grp-comp   { background: #2d4a6e; color: #a8c0dd; border-left: 2px solid #1a2b4a; }
thead tr.group-row th.grp-curr   { background: #1a3560; color: #e0eaf7; border-left: 2px solid #1a2b4a; }
thead tr.group-row th.grp-growth { background: #1e3a4a; color: #7dd3c8; border-left: 2px solid #1a2b4a; }
thead tr.group-row th.grp-solo   { background: #1a3560; color: #e0eaf7; border-left: 2px solid #1a2b4a; }

/* ── Period sub-header ── */
thead tr.period-row th {
  padding: 5px 8px; font-size: 10px; font-weight: 700; text-align: right;
  white-space: nowrap; letter-spacing: .3px;
  border-right: 1px solid rgba(255,255,255,.08);
}
thead tr.period-row th.lbl-th {
  background: #1a2b4a; color: #7a99c0; text-align: left;
  border-right: 2px solid #2d4a7a; padding-left: 10px; font-size: 11px;
  position: sticky; left: 0; z-index: 4;
}
thead tr.period-row th.ph-comp   { background: #253d60; color: #8aaac8; }
thead tr.period-row th.ph-curr   { background: #1f3d6a; color: #b8d0ec; }
thead tr.period-row th.ph-growth { background: #1a3344; color: #6bc7be; }
thead tr.period-row th.ph-solo   { background: #1f3d6a; color: #b8d0ec; }
thead tr.period-row th.pf        { border-left: 2px solid #1a2b4a; }
thead tr.period-row th.fy-col    { font-style: italic; }

/* ── Body ── */
tbody tr { transition: background .08s; }
tbody tr:hover td { filter: brightness(.96); }
td {
  padding: 5px 10px; text-align: right;
  border-bottom: 1px solid #edf0f5; border-right: 1px solid #edf0f5;
  white-space: nowrap; font-variant-numeric: tabular-nums;
}
td.lbl {
  text-align: left; padding-left: 10px; position: sticky; left: 0; z-index: 2;
  background: inherit; border-right: 2px solid #d4daea !important;
  color: #2d4063; min-width: 210px;
}
td.pf { border-left: 2px solid #d4daea !important; }
td.comp-cell { color: #5a6e8a; background: #f8f9fc; }
td.curr-cell { color: #1a2b4a; background: #fff; }
td.gc    { font-weight: 700; font-size: 11.5px; background: #f4f7fb; }
td.gpos  { color: #16a34a; background: #f0faf3; }
td.gneg  { color: #dc2626; background: #fff5f5; }
td.gflat { color: #8a9ab8; background: #f4f7fb; }

tr.section-hdr td {
  background: #edf0f8 !important; font-weight: 800; font-size: 11px;
  text-transform: uppercase; letter-spacing: .6px; color: #1a2b4a;
  cursor: pointer; user-select: none; padding: 7px 10px;
  border-bottom: 1px solid #c8d0e0;
}
tr.section-hdr td.lbl { background: #e6eaf5 !important; }
tr.section-hdr:hover td { filter: brightness(.97); }
.sarr { margin-right: 6px; font-size: 9px; color: #4d7ab8; }

tr.row-sub td.lbl { padding-left: 22px; color: #4a5a74; }
tr.row-subtotal td { background: #f5f7fc; font-weight: 600; }
tr.row-subtotal td.lbl { padding-left: 14px; }
tr.row-total td {
  background: #e8edf7; font-weight: 700; font-size: 12px;
  border-top: 1.5px solid #b8c5d8; border-bottom: 1.5px solid #b8c5d8;
}
tr.row-total td.lbl { color: #1a2b4a; padding-left: 8px; }
tr.row-margin td {
  background: #e4eaf8; font-weight: 700; font-size: 12px;
  border-top: 2px solid #b0bcd4;
}
tr.row-margin td.lbl { color: #1a2b4a; padding-left: 8px; }
tr.row-sub td.comp-cell      { background: #f5f7fc; }
tr.row-subtotal td.comp-cell { background: #eff2f8; }
tr.row-total td.comp-cell    { background: #dde3f0; }
tr.row-margin td.comp-cell   { background: #dae0f2; }
tr.row-subtotal td.gc { background: #eef2f8; }
tr.row-total td.gc    { background: #dce4f2; }
tr.row-total td.gpos  { background: #e2f2e6; }
tr.row-total td.gneg  { background: #fde8e8; }
tr.collapsed { display: none !important; }

/* Placeholder cells (not in the deck): present, aligned, visibly not a figure.
   Only the four rows the source cannot express reach this state. */
tr.gap-row td.curr-cell,
tr.gap-row td.comp-cell { color: #b3bccb; font-style: italic; }
tr.gap-row td.lbl { color: #6a7488; }
"""

# ---------------------------------------------------------------------------
# Page-level
# ---------------------------------------------------------------------------
PAGE_CSS = """
<style>
/* Tighten Streamlit's default page padding so the grid gets the width. */
.block-container { padding-top: 1.4rem; padding-bottom: 2rem; max-width: 100%; }

.shell-header {
  background: #1a2b4a; border-radius: 8px; padding: 13px 22px;
  margin-bottom: 14px; box-shadow: 0 2px 8px rgba(0,0,0,.18);
}
.shell-header h1 {
  color: #fff; font-size: 17px; font-weight: 700; margin: 0;
  white-space: nowrap; letter-spacing: -.2px;
}
.shell-header .sub { color: #7a99c0; font-size: 11px; margin-top: 3px; }

.tiles-row { display: flex; gap: 14px; margin: 4px 0 16px; }
.tile {
  background: #fff; border-radius: 8px; padding: 14px 18px; flex: 1;
  box-shadow: 0 1px 4px rgba(0,0,0,.08); border-top: 3px solid #4d7ab8;
  min-width: 0;
}
.tile-lbl {
  font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .7px; color: #6b7fa3;
}
.tile-val {
  font-size: 27px; font-weight: 700; color: #1a2b4a; margin-top: 4px;
  line-height: 1.1; letter-spacing: -.5px;
}
.tile-val.muted { color: #b3bccb; font-size: 22px; }
.tile-delta {
  font-size: 12px; font-style: italic; margin-top: 3px; color: #9aaccc;
  min-height: 16px;
}
.tile-delta.pos { color: #16a34a; }
.tile-delta.neg { color: #dc2626; }
</style>
"""


def inject() -> None:
    """Add the page-level stylesheet. Safe to call once per script run."""
    st.markdown(PAGE_CSS, unsafe_allow_html=True)
