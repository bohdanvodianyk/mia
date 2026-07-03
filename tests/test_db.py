from mia.memory import db as db_module

_CORE_TABLES = [
    "messages", "sessions", "summaries", "facts", "projects", "tasks",
    "notes", "meetings", "settings", "action_trust", "token_usage", "events_log",
]


def test_init_db_creates_all_tables(tmp_path):
    conn = db_module.init_db(tmp_path / "t.db")
    tables = db_module.table_names(conn)
    for t in _CORE_TABLES:
        assert t in tables, f"missing table {t}"
    assert conn.execute("PRAGMA user_version;").fetchone()[0] == db_module.SCHEMA_VERSION
    conn.close()


def test_init_db_is_idempotent(tmp_path):
    p = tmp_path / "t.db"
    db_module.init_db(p).close()
    conn = db_module.init_db(p)  # second run must not raise
    assert "messages" in db_module.table_names(conn)
    conn.close()


def test_log_event_persists(tmp_path):
    conn = db_module.init_db(tmp_path / "t.db")
    db_module.log_event(conn, "INFO", "test", "hello")
    row = conn.execute("SELECT level, component, message FROM events_log;").fetchone()
    assert row["level"] == "INFO"
    assert row["message"] == "hello"
    conn.close()
