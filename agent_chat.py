"""Sidebar chat with Snowflake Cortex Agents.

Calls go through SNOWFLAKE.CORTEX.DATA_AGENT_RUN on the app's own connection
(data.call_scalar): in-database SQL, so no REST client, token handling or extra
external access integration. The function is non-streaming, so each answer
arrives whole after the agent finishes, which can take tens of seconds.

ACCESS. Deployed, this runs as the app owner, POWER_ANALYST_ORACLE_PROD, with no
secondary roles. Calling an agent needs SNOWFLAKE.CORTEX_AGENT_USER (or
CORTEX_USER) on that role, plus USAGE on the agent and on whatever its tools
read. The role holds both database roles (confirmed 2026-10-26 via SHOW GRANTS)
and owns FC_FORECAST_ANALYST and its three semantic views. An "Unknown
user-defined function" error therefore points at the session (e.g. a restricted
scope hiding SNOWFLAKE.CORTEX) rather than a missing grant; friendly_error()
says so.

CONVERSATION. Stateless: each question re-sends the last few answered
question/answer pairs as text (no server-side threads). Tables and SQL from
earlier answers are shown but not re-sent.
"""
from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

import data

#: The agents the chat offers, display name -> fully qualified name. An
#: allowlist on purpose: nothing typed into the chat can choose the object run.
AGENTS: dict[str, str] = {
    "FC Forecast Analyst": "ORACLE_DATA_PROD.SANDBOX.FC_FORECAST_ANALYST",
}

#: Deploy-time owner (snowflake.yml / `snow streamlit deploy --role`), named in
#: the grant message only.
OWNER_ROLE = "POWER_ANALYST_ORACLE_PROD"

#: Answered question/answer pairs re-sent as context with each new question.
HISTORY_PAIRS = 5

_RUN_SQL = "SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(?, ?)"

#: session_state key: {agent fqn: [turn, ...]}, turns appended in user/assistant
#: pairs so a conversation per agent survives switching between them.
_STATE = "agent_chat"

_NUMERIC_TYPES = ("FIXED", "NUMBER", "DECIMAL", "REAL", "FLOAT", "DOUBLE", "INT")


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------
def _text_message(role: str, text: str) -> dict:
    return {"role": role, "content": [{"type": "text", "text": text}]}


def build_messages(turns: list[dict], question: str) -> list[dict]:
    """The request's ``messages``: recent answered pairs, then the question.

    Only pairs whose answer succeeded and has text are kept, so the history
    always alternates user/assistant and starts with a user turn.
    """
    pairs = []
    for user, reply in zip(turns[0::2], turns[1::2]):
        if reply.get("error") or not reply.get("text"):
            continue
        pairs.append((user["text"], reply["text"]))
    msgs = []
    for q, a in pairs[-HISTORY_PAIRS:]:
        msgs += [_text_message("user", q), _text_message("assistant", a)]
    msgs.append(_text_message("user", question))
    return msgs


def run_agent(fqn: str, turns: list[dict], question: str) -> dict:
    """Ask ``fqn`` the question; return the parsed reply (see parse_response).

    Never raises: a failed call comes back as a reply with ``error`` set, so the
    chat can show it in place.
    """
    body = json.dumps({"messages": build_messages(turns, question),
                       "stream": False})
    try:
        raw = data.call_scalar(_RUN_SQL, [fqn, body])
    except Exception as exc:  # noqa: BLE001 -- any failure is shown in the chat
        return _empty_reply(error=friendly_error(exc))
    try:
        resp = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except ValueError:
        return _empty_reply(error="The agent returned a response that is not JSON.")
    return parse_response(resp)


def friendly_error(exc: Exception) -> str:
    """A message that says what to do, for the failures we can recognise."""
    msg = str(exc)
    if "DATA_AGENT_RUN" in msg and "Unknown" in msg:
        return (
            "This session cannot see SNOWFLAKE.CORTEX.DATA_AGENT_RUN. "
            f"{OWNER_ROLE} holds SNOWFLAKE.CORTEX_AGENT_USER, so check that the "
            "app runs as that role and that no restricted session scope is "
            f"hiding SNOWFLAKE.CORTEX functions.\n\n`{msg}`"
        )
    if "does not exist or not authorized" in msg:
        return (
            "The agent, or something it reads, does not exist or this app's role "
            f"cannot access it.\n\n`{msg}`"
        )
    return f"The agent call failed.\n\n`{msg}`"


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------
def _empty_reply(error: str | None = None) -> dict:
    return {"role": "assistant", "text": "", "tables": [], "charts": [],
            "sql": [], "warnings": [], "error": error}


def _frame(result_set: Any) -> pd.DataFrame | None:
    """A DataFrame from a SQL-API style result_set, numeric columns as numbers."""
    if not isinstance(result_set, dict):
        return None
    rows = result_set.get("data")
    if not isinstance(rows, list):
        return None
    row_type = (result_set.get("resultSetMetaData") or {}).get("rowType") or []
    names = [c.get("name", f"col_{i}") for i, c in enumerate(row_type)]
    width = len(rows[0]) if rows else len(names)
    if len(names) != width:
        names = [f"col_{i}" for i in range(width)]
    df = pd.DataFrame(rows, columns=names)
    for col, meta in zip(names, row_type):
        if str(meta.get("type", "")).upper().startswith(_NUMERIC_TYPES):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def parse_response(resp: dict) -> dict:
    """The parts of a DATA_AGENT_RUN response the chat shows.

    Returns {role, text, tables: [{title, df}], charts: [vega-lite dict],
    sql: [str], warnings: [str], error: str | None}. Tables come from the
    response's ``table`` items; only when there are none do tool results'
    result sets stand in, so the same data is not shown twice.
    """
    reply = _empty_reply()
    if not isinstance(resp, dict):
        reply["error"] = "The agent returned an empty response."
        return reply

    texts: list[str] = []
    fallback_tables: list[dict] = []
    for item in resp.get("content") or []:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind == "text" and item.get("text"):
            texts.append(item["text"])
        elif kind == "table":
            table = item.get("table") or {}
            df = _frame(table.get("result_set"))
            if df is not None:
                reply["tables"].append({"title": table.get("title") or "", "df": df})
        elif kind == "chart":
            spec = (item.get("chart") or {}).get("chart_spec")
            try:
                reply["charts"].append(json.loads(spec) if isinstance(spec, str) else spec)
            except ValueError:
                pass
        elif kind == "tool_result":
            result = item.get("tool_result") or {}
            for part in result.get("content") or []:
                payload = part.get("json") if isinstance(part, dict) else None
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("sql"), str) and payload["sql"].strip():
                    reply["sql"].append(payload["sql"].strip())
                df = _frame(payload.get("result_set"))
                if df is not None:
                    fallback_tables.append({"title": result.get("name") or "", "df": df})
    if not reply["tables"]:
        reply["tables"] = fallback_tables

    reply["text"] = "\n\n".join(t.strip() for t in texts if t.strip())
    reply["warnings"] = [
        w.get("message") or str(w) for w in resp.get("warnings") or []
        if isinstance(w, dict)
    ]

    err = resp.get("error")
    if isinstance(err, dict) and err.get("message"):
        reply["error"] = err["message"]
    elif resp.get("status") in ("error", "cancelled", "timed_out"):
        reply["error"] = f"The agent run ended with status '{resp['status']}'."
    elif not reply["text"] and not reply["tables"] and resp.get("message"):
        # A fatal error event: {"code": ..., "message": ...}.
        reply["error"] = str(resp["message"])
    elif not reply["text"] and not reply["tables"]:
        reply["error"] = "The agent returned no answer."
    return reply


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
def _md(text: str) -> str:
    """Escape '$' so figures like $5,425.2M are not read as LaTeX math."""
    return text.replace("$", r"\$")


def _render_turn(turn: dict) -> None:
    with st.chat_message(turn["role"]):
        if turn.get("text"):
            st.markdown(_md(turn["text"]))
        for table in turn.get("tables") or []:
            if table["title"]:
                st.caption(table["title"])
            st.dataframe(table["df"], hide_index=True, width="stretch")
        for spec in turn.get("charts") or []:
            st.vega_lite_chart(spec, width="stretch")
        for warning in turn.get("warnings") or []:
            st.warning(warning, icon=":material/warning:")
        if turn.get("error"):
            st.error(turn["error"], icon=":material/error:")
        if turn.get("sql"):
            with st.expander("SQL", icon=":material/code:"):
                for sql in turn["sql"]:
                    st.code(sql, language="sql")


def _clear(fqn: str) -> None:
    st.session_state[_STATE][fqn] = []


@st.fragment
def _chat() -> None:
    """The chat body. A fragment, so a question reruns only this, not the page."""
    # A picker only when there is something to pick.
    if len(AGENTS) > 1:
        name = st.selectbox("Agent", list(AGENTS), key="agent_chat_agent")
    else:
        name = next(iter(AGENTS))
        st.caption(f"Chatting with **{name}**")
    fqn = AGENTS[name]
    turns = st.session_state.setdefault(_STATE, {}).setdefault(fqn, [])

    # Created first so it sits above the input, filled once the input is read.
    history = st.container(height=460, border=True)
    question = st.chat_input(f"Ask {name}...", key="agent_chat_input")

    with history:
        if not turns and not question:
            st.caption("Ask about revenue, margin or EBITDA by segment, month, "
                       "license or forecast version.")
        for turn in turns:
            _render_turn(turn)

    # Answered before the Clear button is drawn, so the button already knows
    # about this turn. The new turn renders into the history box above.
    if question:
        user = {"role": "user", "text": question}
        with history:
            _render_turn(user)
            with st.spinner(f"{name} is working on it..."):
                reply = run_agent(fqn, turns, question)
            _render_turn(reply)
        turns += [user, reply]

    st.button("Clear chat", on_click=_clear, args=(fqn,), disabled=not turns,
              icon=":material/delete_sweep:", key="agent_chat_clear")


def render() -> None:
    """The chat section, for the entrypoint's sidebar."""
    st.subheader("Ask the data", anchor=False)
    _chat()
