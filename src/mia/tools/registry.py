"""Tool registry: the JSON schemas the agent sees, and a dispatcher.

Phase 3 ships the memory tools. Calendar/Gmail/etc. register here in later
phases; the agent loop in `agent/core.py` stays generic.
"""

from __future__ import annotations

import logging
import sqlite3

from mia.tools import memory

log = logging.getLogger("mia.tools")

_FACT_CATEGORIES = [
    "profile", "preference", "relationship", "project", "schedule", "other",
]

MEMORY_TOOLS = [
    {
        "name": "remember_fact",
        "description": (
            "Save a durable personal fact about the owner — a name, role, "
            "preference, relationship, ongoing project, date, or context worth "
            "keeping across conversations. Save quietly; do not announce it "
            "unless the owner asks. Do not save transient chit-chat."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The fact, as a short self-contained sentence.",
                },
                "category": {
                    "type": "string",
                    "enum": _FACT_CATEGORIES,
                    "description": "Rough category for the fact.",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "recall_facts",
        "description": (
            "Look up stored facts about the owner. Optionally pass a query to "
            "filter by keyword; omit it to list everything known."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keyword to filter facts by (optional).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "forget_fact",
        "description": (
            "Forget (archive) stored facts that match a description. Use when "
            "the owner asks you to forget something."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Text describing the fact(s) to forget.",
                },
            },
            "required": ["query"],
        },
    },
]


def dispatch(name: str, tool_input: dict, conn: sqlite3.Connection) -> str:
    """Execute a tool by name, returning a string result for the agent."""
    try:
        if name == "remember_fact":
            return memory.remember_fact(
                conn, tool_input.get("content", ""), tool_input.get("category")
            )
        if name == "recall_facts":
            return memory.recall_facts(conn, tool_input.get("query"))
        if name == "forget_fact":
            return memory.forget_fact(conn, tool_input.get("query", ""))
        return f"Unknown tool: {name}"
    except Exception as exc:  # tools must not crash the agent loop
        log.exception("Tool %s failed", name)
        return f"Tool error: {exc}"
