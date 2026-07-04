"""Session lifecycle: auto-gap reset, history shape, and token accounting."""

from __future__ import annotations

import sqlite3

import pytest

from mia.memory import db as dbm


@pytest.fixture
def conn(tmp_path):
    c = dbm.init_db(tmp_path / "t.db")
    yield c
    c.close()


def _age_last_message(conn: sqlite3.Connection, session_id: int, hours: int) -> None:
    conn.execute(
        "UPDATE messages SET ts = datetime('now', ?) WHERE session_id = ?;",
        (f"-{hours} hours", session_id),
    )
    conn.commit()


def test_same_session_within_gap(conn):
    s1 = dbm.get_or_start_session(conn, chat_id=1)
    dbm.add_message(conn, 1, s1, "user", "hi")
    s2 = dbm.get_or_start_session(conn, chat_id=1)
    assert s1 == s2


def test_new_session_after_gap(conn):
    s1 = dbm.get_or_start_session(conn, chat_id=1)
    dbm.add_message(conn, 1, s1, "user", "hi")
    _age_last_message(conn, s1, hours=3)  # older than SESSION_GAP_HOURS
    s2 = dbm.get_or_start_session(conn, chat_id=1)
    assert s2 != s1
    ended = conn.execute("SELECT ended_at FROM sessions WHERE id = ?;", (s1,)).fetchone()
    assert ended["ended_at"] is not None


def test_reset_starts_new_session(conn):
    s1 = dbm.get_or_start_session(conn, chat_id=7)
    dbm.add_message(conn, 7, s1, "user", "hola")
    dbm.reset_session(conn, chat_id=7)
    s2 = dbm.get_or_start_session(conn, chat_id=7)
    assert s2 != s1


def test_history_is_ordered_and_role_filtered(conn):
    s = dbm.get_or_start_session(conn, chat_id=1)
    dbm.add_message(conn, 1, s, "user", "first")
    dbm.add_message(conn, 1, s, "assistant", "second")
    dbm.add_message(conn, 1, s, "system", "hidden")
    dbm.add_message(conn, 1, s, "user", "third")
    hist = dbm.get_history(conn, s, limit=10)
    assert [m["content"] for m in hist] == ["first", "second", "third"]
    assert all(m["role"] in ("user", "assistant") for m in hist)


def test_history_limit_keeps_latest(conn):
    s = dbm.get_or_start_session(conn, chat_id=1)
    for i in range(10):
        dbm.add_message(conn, 1, s, "user", f"m{i}")
    hist = dbm.get_history(conn, s, limit=3)
    assert [m["content"] for m in hist] == ["m7", "m8", "m9"]


def test_usage_month_to_date_groups_by_provider(conn):
    dbm.log_token_usage(conn, "anthropic", "claude-sonnet-4-6", 100, 50, 0.0011, "agent")
    dbm.log_token_usage(conn, "anthropic", "claude-haiku-4-5", 20, 5, 0.00004, "router")
    rows = {r["provider"]: r for r in dbm.usage_month_to_date(conn)}
    assert rows["anthropic"]["calls"] == 2
    assert rows["anthropic"]["input_tokens"] == 120
    assert rows["anthropic"]["output_tokens"] == 55
