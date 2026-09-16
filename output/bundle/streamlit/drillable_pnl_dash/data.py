"""Snowflake connection and the cached loaders for the Drillable P&L dashboard.

Local runs read the connection from ~/.snowflake/connections.toml, selected by
SNOWFLAKE_DEFAULT_CONNECTION_NAME. run.ps1 (or .env) can override it; the
fallback below means a bare `streamlit run` works with no env setup.

Role note. Deployed to Streamlit-in-Snowflake this app runs owner's-rights as
POWER_ANALYST_ORACLE_PROD with NO secondary roles. queries.MASTER_SQL was
verified under `USE SECONDARY ROLES NONE` before being written. If you add a
query, verify it the same way -- a query that works in a Snowsight worksheet
under your own inherited roles can still fail in the deployed app.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

import queries

# Must match snowflake.yml::query_warehouse.
_WAREHOUSE = os.getenv("SNOWFLAKE_WAREHOUSE") or "ANALYTICS_WAREHOUSE"

_CACHE_TTL = timedelta(hours=2)

# Streamlit-in-Snowflake's CONTAINER runtime is SPCS under the hood: it mounts a
# short-lived OAuth login token here and sets SNOWFLAKE_ACCOUNT/SNOWFLAKE_HOST.
# The path existing means we are running INSIDE Snowflake, not on a laptop.
_SPCS_TOKEN_PATH = "/snowflake/session/token"


def _running_in_snowflake() -> bool:
    """True when hosted by Streamlit-in-Snowflake or a Snowpark Container service."""
    if os.path.exists(_SPCS_TOKEN_PATH):
        return True
    try:
        from snowflake.snowpark.context import get_active_session

        get_active_session()
        return True
    except Exception:
        return False


# Local `streamlit run` ONLY. Hosted in SiS the runtime provides a connection
# named 'default'; overriding SNOWFLAKE_DEFAULT_CONNECTION_NAME there makes the
# connector hunt for a named connection that does not exist and fail with
# "Default connection ... cannot be found, known ones are ['default']". Hence the
# _running_in_snowflake() guard -- this fallback is local-only.
#
# HIDR_PROD is chosen over FANATICS_COLLECTIBLES_PROD on purpose: it is the only
# entry in ~/.snowflake/connections.toml that pins
# role = POWER_ANALYST_ORACLE_PROD, warehouse = ANALYTICS_WAREHOUSE and
# database = ORACLE_DATA_PROD -- i.e. it reproduces the DEPLOYED app's identity
# locally, on the same account (vxb09319.us-east-1). Running local checks under
# your own broader roles is how you ship SQL that works on your laptop and
# fails in SiS.
#
# This must be an entry name that literally exists in connections.toml. A wrong
# name fails with "Missing Snowflake connection configuration", which reads like
# a missing file rather than a wrong key. Override via .env or the environment.
_DEFAULT_CONN_NAME = "HIDR_PROD"

if not _running_in_snowflake():
    _CONN_NAME = (
        os.getenv("SNOWFLAKE_DEFAULT_CONNECTION_NAME") or _DEFAULT_CONN_NAME
    )
    os.environ["SNOWFLAKE_DEFAULT_CONNECTION_NAME"] = _CONN_NAME


def _spcs_connection_kwargs() -> dict | None:
    """Connector kwargs for a standalone SPCS run, or None when local."""
    try:
        with open(_SPCS_TOKEN_PATH) as f:
            token = f.read()
    except OSError:
        return None
    return {
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "host": os.environ["SNOWFLAKE_HOST"],
        "authenticator": "oauth",
        "token": token,
        "warehouse": _WAREHOUSE,
    }


@st.cache_resource(show_spinner=False)
def _connection():
    """One pooled Snowflake connection for the app session.

    Instantiated as st.connection("snowflake") with NO connection_name or
    warehouse kwargs on purpose: Streamlit's SnowflakeConnection._connect only
    takes the connections.toml default path when the instance is named exactly
    "snowflake" and no extra kwargs are passed. Passing connection_name= raises
    "got multiple values for keyword argument"; passing warehouse= skips the
    default-connection path and fails with "User is empty" / 251005. The
    warehouse is therefore set by a USE statement after connecting.
    """
    if _running_in_snowflake():
        try:
            conn = st.connection("snowflake", type="snowflake")
        except Exception:
            spcs = _spcs_connection_kwargs()
            conn = (
                st.connection("snowflake", type="snowflake", **spcs)
                if spcs is not None
                else st.connection("snowflake", type="snowflake")
            )
    else:
        conn = st.connection("snowflake", type="snowflake")
    if _WAREHOUSE:
        try:
            conn.query(f"USE WAREHOUSE {_WAREHOUSE}", ttl=0)
        except Exception:
            # A deployed SiS app already has query_warehouse set from the
            # manifest, so a failure here is not fatal.
            pass
    return conn


def _q(sql: str, ttl: timedelta = _CACHE_TTL) -> pd.DataFrame:
    """Run ``sql``, lowercase the column names, return a DataFrame.

    No params argument by design -- see the caching note in queries.py. Every
    statement this app runs is a literal with no binds.
    """
    df = _connection().query(sql, ttl=ttl)
    df.columns = [c.lower() for c in df.columns]
    return df


# --------------------------------------------------------------------------
# The one feed
# --------------------------------------------------------------------------
@st.cache_data(ttl=_CACHE_TTL, show_spinner="Loading P&L cube...")
def load_master() -> tuple[pd.DataFrame, datetime]:
    """The whole cube -- every vintage, period, grain and P&L line -- plus the
    UTC instant it was pulled.

    Exceptions are deliberately NOT caught here. @st.cache_data does not
    memoize exceptions but DOES memoize returned values, so a loader that
    swallowed its own error and returned an empty frame would cache that empty
    for the full 2h TTL and render a convincing "no data" dashboard after one
    transient failure. Let it raise; streamlit_app.py catches it, shows the real
    error, and offers a Retry that calls load_master.clear().

    ``pulled_at`` is captured INSIDE the cached body, so a cache hit keeps the
    original pull time -- a real freshness stamp rather than a render clock.
    """
    df = _q(queries.MASTER_SQL)
    pulled_at = datetime.now(timezone.utc)

    for col in [f"seg_{k}" for k in queries.SEGMENTS]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    df["period_date"] = pd.to_datetime(df["period_date"], errors="coerce")
    df["forecast_asof_date"] = pd.to_datetime(df["forecast_asof_date"], errors="coerce")
    # Nullable boolean: NULL at QUARTER/YEAR grain is meaningful (not-applicable),
    # so it must survive rather than collapse to False.
    df["is_actual_month"] = df["is_actual_month"].astype("boolean")

    for col in ("vintage_key", "scenario_label", "fiscal_year", "period",
                "period_type", "pl_line"):
        df[col] = df[col].astype(str)

    return df, pulled_at
