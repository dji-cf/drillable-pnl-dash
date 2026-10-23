"""Offline checks for agent_chat's request building and response parsing.

Dev-only harness, deliberately NOT in snowflake.yml::artifacts. Needs no
Snowflake connection: the payloads below are shaped like the documented
DATA_AGENT_RUN / agent:run non-streaming response.

    .venv\\Scripts\\python.exe tools\\test_agent_chat.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agent_chat as ac  # noqa: E402

_ROW_TYPE = [
    {"name": "QUARTER", "type": "TEXT"},
    {"name": "REVENUE_M", "type": "FIXED"},
]
_ROWS = [["Q1", "1201.5"], ["Q2", "1310.25"]]

FULL = {
    "role": "assistant",
    "content": [
        {"type": "thinking", "thinking": {"text": "planning..."}},
        {"type": "tool_use", "tool_use": {"name": "FC_Segment_PL_Analytics",
                                          "input": {"query": "rev by qtr"}}},
        {"type": "tool_result", "tool_result": {
            "name": "FC_Segment_PL_Analytics", "status": "success",
            "content": [{"type": "json", "json": {
                "sql": "SELECT quarter, revenue_m FROM x",
                "result_set": {"resultSetMetaData": {"rowType": _ROW_TYPE},
                               "data": _ROWS},
            }}],
        }},
        {"type": "table", "table": {
            "title": "Revenue by quarter",
            "result_set": {"resultSetMetaData": {"rowType": _ROW_TYPE},
                           "data": _ROWS},
        }},
        {"type": "text", "text": "Total revenue is $2,511.8M."},
    ],
    "warnings": [{"code": "399569", "message": "TOOL_NOT_ACCESSIBLE: X"}],
}


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"{'pass' if ok else 'FAIL'}  {name}" + (f"  -- {detail}" if detail and not ok else ""))
    return ok


def main() -> None:
    results = []

    r = ac.parse_response(FULL)
    results.append(check("text extracted", r["text"] == "Total revenue is $2,511.8M.", r["text"]))
    results.append(check("table item wins over tool_result fallback",
                         len(r["tables"]) == 1 and r["tables"][0]["title"] == "Revenue by quarter",
                         str([t["title"] for t in r["tables"]])))
    df = r["tables"][0]["df"]
    results.append(check("columns from rowType", list(df.columns) == ["QUARTER", "REVENUE_M"],
                         str(list(df.columns))))
    results.append(check("FIXED column numeric", df["REVENUE_M"].sum() == 2511.75,
                         str(df["REVENUE_M"].tolist())))
    results.append(check("executed SQL captured", r["sql"] == ["SELECT quarter, revenue_m FROM x"],
                         str(r["sql"])))
    results.append(check("warnings surfaced", r["warnings"] == ["TOOL_NOT_ACCESSIBLE: X"],
                         str(r["warnings"])))
    results.append(check("no error on a good answer", r["error"] is None, str(r["error"])))

    no_table = {**FULL, "content": [c for c in FULL["content"] if c["type"] != "table"]}
    r = ac.parse_response(no_table)
    results.append(check("tool_result table used when no table item",
                         len(r["tables"]) == 1 and r["tables"][0]["title"] == "FC_Segment_PL_Analytics"))

    r = ac.parse_response({"role": "assistant", "content": []})
    results.append(check("empty content is an error", r["error"] == "The agent returned no answer."))

    r = ac.parse_response({"code": "399504", "message": "Error during execution"})
    results.append(check("fatal error event surfaced", r["error"] == "Error during execution", str(r["error"])))

    r = ac.parse_response({"status": "timed_out", "content": [{"type": "text", "text": "partial"}]})
    results.append(check("timed_out status is an error", "timed_out" in (r["error"] or "")))

    msg = ac.friendly_error(Exception(
        "SQL compilation error:\nUnknown user-defined function SNOWFLAKE.CORTEX.DATA_AGENT_RUN."))
    results.append(check("missing-grant error names the grant",
                         "CORTEX_AGENT_USER" in msg and ac.OWNER_ROLE in msg, msg))

    turns = [
        {"role": "user", "text": "q1"}, {"role": "assistant", "text": "a1", "error": None},
        {"role": "user", "text": "q2"}, {"role": "assistant", "text": "", "error": "boom"},
    ]
    msgs = ac.build_messages(turns, "q3")
    roles_texts = [(m["role"], m["content"][0]["text"]) for m in msgs]
    results.append(check("history drops failed pairs, ends with question",
                         roles_texts == [("user", "q1"), ("assistant", "a1"), ("user", "q3")],
                         str(roles_texts)))

    many = []
    for i in range(ac.HISTORY_PAIRS + 3):
        many += [{"role": "user", "text": f"q{i}"}, {"role": "assistant", "text": f"a{i}"}]
    msgs = ac.build_messages(many, "last")
    results.append(check("history capped at HISTORY_PAIRS",
                         len(msgs) == 2 * ac.HISTORY_PAIRS + 1, str(len(msgs))))

    results.append(check("$ escaped for markdown", ac._md("$5.0M") == r"\$5.0M"))

    failed = not all(results)
    print("\nFAILED" if failed else "\nALL PASS")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
