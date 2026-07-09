"""Executors for the memory tools. Each takes the DB connection + tool input."""

from __future__ import annotations

import sqlite3

from mia.memory import db as dbm


def remember_fact(conn: sqlite3.Connection, content: str, category: str | None = None) -> str:
    content = (content or "").strip()
    if not content:
        return "Nothing to save — the fact was empty."
    fact_id = dbm.add_fact(conn, content, category=category, source="agent")
    return f"Saved (fact #{fact_id})."


def recall_facts(conn: sqlite3.Connection, query: str | None = None) -> str:
    facts = dbm.search_facts(conn, query) if query else dbm.list_facts(conn)
    if not facts:
        return "No matching facts stored."
    return "\n".join(f"- {f['content']}" for f in facts)


def forget_fact(conn: sqlite3.Connection, query: str) -> str:
    forgotten = dbm.archive_facts_matching(conn, query)
    if not forgotten:
        return "Nothing matched; nothing forgotten."
    return "Forgot: " + "; ".join(forgotten)
