"""SQLite connection helpers and idempotent schema migration."""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path

SCHEMA_VERSION = 1


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
