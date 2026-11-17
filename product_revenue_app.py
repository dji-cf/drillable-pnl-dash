"""(DRAFT) NA Product Revenue (Megan) -- the entrypoint of a SEPARATE app.

Megan Coleman's Product Release view (NASE only), split out of the
Consolidated Financials app (Maya, 2026-11-10). All content is in
product_revenue.render().
"""
from __future__ import annotations

import streamlit as st

import product_revenue

st.set_page_config(page_title="(DRAFT) NA Product Revenue", layout="wide")
st.markdown("**(DRAFT)** Numbers under validation. Not final.")
product_revenue.render()
