"""Build the memory context injected into the system prompt.

Profile facts + active projects + the rolling summary, trimmed to a token
budget (plan: memory is injected, not implied — ≤ 3k tokens).
"""

from __future__ import annotations

import sqlite3

from mia.memory import db as dbm

# Rough char-per-token heuristic — good enough to bound the injected block
# without a tokenizer round-trip on every message.
_CHARS_PER_TOKEN = 4


def _approx_tokens(text: str) -> int:
    return len(text) // _CHARS_PER_TOKEN


def build_context(
    conn: sqlite3.Connection, chat_id: int, token_budget: int = 3000
) -> str:
    """Return a compact profile block, or "" if nothing is known yet."""
    char_budget = token_budget * _CHARS_PER_TOKEN
    sections: list[str] = []
    used = 0

    facts = dbm.list_facts(conn)
    if facts:
        # Facts get the lion's share of the budget; stop before overflowing.
        fact_lines: list[str] = []
        for f in facts:
            line = f"- {f['content']}"
            if used + len(line) > char_budget * 0.7:
                break
            fact_lines.append(line)
            used += len(line)
        if fact_lines:
            sections.append("Facts:\n" + "\n".join(fact_lines))

    projects = dbm.list_projects(conn)
    if projects:
        line = "Active projects: " + ", ".join(p["name"] for p in projects)
        if used + len(line) <= char_budget:
            sections.append(line)
            used += len(line)

    summary = dbm.latest_summary(conn, chat_id)
    if summary:
        remaining = char_budget - used
        if remaining > 200:
            trimmed = summary[:remaining].rstrip()
            sections.append("Recent context:\n" + trimmed)

    return "\n\n".join(sections)


# Re-exported for callers that only need the estimate.
approx_tokens = _approx_tokens
