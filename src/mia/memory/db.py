"""SQLite connection helpers, schema migration, and Phase 1 data access.

All timestamps are UTC text in SQLite's ``CURRENT_TIMESTAMP`` format
(``YYYY-MM-DD HH:MM:SS``). Helpers that compare times parse against that shape.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from importlib import resources
from pathlib import Path

SCHEMA_VERSION = 1

# Long-term memory persists across sessions; a conversation session is a short
# working window that resets after this much inactivity (plan weakness #3).
SESSION_GAP_HOURS = 2
_TS_FORMAT = "%Y-%m-%d %H:%M:%S"


def _parse_ts(value: str) -> datetime:
    return datetime.strptime(value, _TS_FORMAT).replace(tzinfo=UTC)


def _load_schema() -> str:
    return resources.files("mia.memory").joinpath("schema.sql").read_text(encoding="utf-8")


def connect(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def init_db(db_path: Path | str) -> sqlite3.Connection:
    """Create the database file (and parent dir) and apply the schema idempotently."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    conn.executescript(_load_schema())
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION};")
    conn.commit()
    return conn


def table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
    ).fetchall()
    return {r[0] for r in rows}


def log_event(conn: sqlite3.Connection, level: str, component: str, message: str) -> None:
    """Persist an operational event to events_log."""
    conn.execute(
        "INSERT INTO events_log (level, component, message) VALUES (?, ?, ?);",
        (level, component, message),
    )
    conn.commit()


# ── Sessions & messages ───────────────────────────────────────────

def _active_session(conn: sqlite3.Connection, chat_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM sessions WHERE chat_id = ? AND ended_at IS NULL "
        "ORDER BY id DESC LIMIT 1;",
        (chat_id,),
    ).fetchone()


def _last_message_ts(conn: sqlite3.Connection, session_id: int) -> str | None:
    row = conn.execute(
        "SELECT ts FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT 1;",
        (session_id,),
    ).fetchone()
    return row["ts"] if row else None


def close_session(conn: sqlite3.Connection, session_id: int) -> None:
    conn.execute(
        "UPDATE sessions SET ended_at = CURRENT_TIMESTAMP WHERE id = ? AND ended_at IS NULL;",
        (session_id,),
    )
    conn.commit()


def reset_session(conn: sqlite3.Connection, chat_id: int) -> None:
    """Manually end the active session (the `/reset` override)."""
    sess = _active_session(conn, chat_id)
    if sess is not None:
        close_session(conn, sess["id"])


def get_or_start_session(
    conn: sqlite3.Connection, chat_id: int, gap_hours: int = SESSION_GAP_HOURS
) -> int:
    """Return the active session id, auto-starting a fresh one after inactivity."""
    sess = _active_session(conn, chat_id)
    if sess is not None:
        last = _last_message_ts(conn, sess["id"])
        if last is not None and datetime.now(UTC) - _parse_ts(last) > timedelta(
            hours=gap_hours
        ):
            close_session(conn, sess["id"])
            sess = None
    if sess is not None:
        return sess["id"]
    cur = conn.execute("INSERT INTO sessions (chat_id) VALUES (?);", (chat_id,))
    conn.commit()
    return int(cur.lastrowid)


def add_message(
    conn: sqlite3.Connection,
    chat_id: int,
    session_id: int,
    role: str,
    content: str,
    modality: str = "text",
) -> None:
    conn.execute(
        "INSERT INTO messages (chat_id, session_id, role, content, modality) "
        "VALUES (?, ?, ?, ?, ?);",
        (chat_id, session_id, role, content, modality),
    )
    conn.commit()


def get_history(
    conn: sqlite3.Connection, session_id: int, limit: int = 20
) -> list[dict[str, str]]:
    """Return the tail of a session as Claude-shaped messages (oldest first)."""
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE session_id = ? AND role IN "
        "('user', 'assistant') ORDER BY id DESC LIMIT ?;",
        (session_id, limit),
    ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


# ── Token & cost accounting ───────────────────────────────────────

def log_token_usage(
    conn: sqlite3.Connection,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    purpose: str,
) -> None:
    conn.execute(
        "INSERT INTO token_usage (provider, model, input_tokens, output_tokens, "
        "cost_usd, purpose) VALUES (?, ?, ?, ?, ?, ?);",
        (provider, model, input_tokens, output_tokens, cost_usd, purpose),
    )
    conn.commit()


def usage_month_to_date(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Per-provider token + cost totals since the first of the current UTC month."""
    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return conn.execute(
        "SELECT provider, SUM(input_tokens) AS input_tokens, "
        "SUM(output_tokens) AS output_tokens, SUM(cost_usd) AS cost_usd, "
        "COUNT(*) AS calls FROM token_usage WHERE ts >= ? GROUP BY provider "
        "ORDER BY cost_usd DESC;",
        (month_start.strftime(_TS_FORMAT),),
    ).fetchall()


# ── Long-term memory: facts ───────────────────────────────────────

def add_fact(
    conn: sqlite3.Connection, content: str, category: str | None = None,
    source: str = "agent",
) -> int:
    cur = conn.execute(
        "INSERT INTO facts (category, content, source) VALUES (?, ?, ?);",
        (category, content, source),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_facts(conn: sqlite3.Connection, include_archived: bool = False) -> list[sqlite3.Row]:
    if include_archived:
        return conn.execute("SELECT * FROM facts ORDER BY id;").fetchall()
    return conn.execute("SELECT * FROM facts WHERE archived = 0 ORDER BY id;").fetchall()


def search_facts(conn: sqlite3.Connection, query: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM facts WHERE archived = 0 AND content LIKE ? ORDER BY id;",
        (f"%{query}%",),
    ).fetchall()


def archive_fact(conn: sqlite3.Connection, fact_id: int) -> bool:
    cur = conn.execute(
        "UPDATE facts SET archived = 1 WHERE id = ? AND archived = 0;", (fact_id,)
    )
    conn.commit()
    return cur.rowcount > 0


def archive_facts_matching(conn: sqlite3.Connection, query: str) -> list[str]:
    """Archive active facts whose text matches `query`; return what was forgotten."""
    rows = conn.execute(
        "SELECT id, content FROM facts WHERE archived = 0 AND content LIKE ?;",
        (f"%{query}%",),
    ).fetchall()
    for r in rows:
        conn.execute("UPDATE facts SET archived = 1 WHERE id = ?;", (r["id"],))
    conn.commit()
    return [r["content"] for r in rows]


# ── Settings (key/value) ──────────────────────────────────────────

def get_setting(
    conn: sqlite3.Connection, key: str, default: str | None = None
) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?;", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value;",
        (key, str(value)),
    )
    conn.commit()


def is_onboarded(conn: sqlite3.Connection) -> bool:
    return get_setting(conn, "onboarded") == "1"


# ── Projects ──────────────────────────────────────────────────────

def add_project(
    conn: sqlite3.Connection, name: str, description: str | None = None
) -> int:
    cur = conn.execute(
        "INSERT INTO projects (name, description) VALUES (?, ?);", (name, description)
    )
    conn.commit()
    return int(cur.lastrowid)


def list_projects(conn: sqlite3.Connection, status: str = "active") -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM projects WHERE status = ? ORDER BY id;", (status,)
    ).fetchall()


# ── Rolling summaries & history pruning ───────────────────────────

def latest_summary(conn: sqlite3.Connection, chat_id: int) -> str | None:
    row = conn.execute(
        "SELECT summary FROM summaries WHERE chat_id = ? ORDER BY id DESC LIMIT 1;",
        (chat_id,),
    ).fetchone()
    return row["summary"] if row else None


def add_summary(
    conn: sqlite3.Connection, chat_id: int, summary: str,
    period_start: str | None = None, period_end: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO summaries (chat_id, period_start, period_end, summary) "
        "VALUES (?, ?, ?, ?);",
        (chat_id, period_start, period_end, summary),
    )
    conn.commit()


def messages_since(
    conn: sqlite3.Connection, chat_id: int, since_iso: str
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT role, content, ts FROM messages WHERE chat_id = ? AND ts >= ? "
        "AND role IN ('user', 'assistant') ORDER BY id;",
        (chat_id, since_iso),
    ).fetchall()


def prune_messages_before(conn: sqlite3.Connection, before_iso: str) -> int:
    cur = conn.execute("DELETE FROM messages WHERE ts < ?;", (before_iso,))
    conn.commit()
    return cur.rowcount
