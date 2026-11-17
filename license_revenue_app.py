"""(DRAFT) Revenue by License (Global) -- the entrypoint of a SEPARATE app (Maya, 2026-11-17).

All content is in license_revenue.render().
"""
from __future__ import annotations

import streamlit as st

import license_revenue

st.set_page_config(page_title="(DRAFT) Revenue by License", layout="wide")
st.markdown("**(DRAFT)** Numbers under validation. Not final.")
license_revenue.render()
