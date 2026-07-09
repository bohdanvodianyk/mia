"""Offline units for Phase 3: facts, settings, projects, context, tools."""

from __future__ import annotations

import pytest

from mia.memory import context as memctx
from mia.memory import db as dbm
from mia.onboarding import interview
from mia.tools import registry


@pytest.fixture
def conn(tmp_path):
    c = dbm.init_db(tmp_path / "t.db")
    yield c
    c.close()


# ── facts ─────────────────────────────────────────────────────────

def test_add_list_archive_facts(conn):
    fid = dbm.add_fact(conn, "The owner's name is Bohdan.", category="profile")
    assert [f["content"] for f in dbm.list_facts(conn)] == ["The owner's name is Bohdan."]
    assert dbm.archive_fact(conn, fid) is True
    assert dbm.list_facts(conn) == []
    assert dbm.archive_fact(conn, fid) is False  # already archived


def test_search_and_forget_matching(conn):
    dbm.add_fact(conn, "Sister is Olena.")
    dbm.add_fact(conn, "Likes espresso.")
    assert len(dbm.search_facts(conn, "Olena")) == 1
    forgotten = dbm.archive_facts_matching(conn, "Olena")
    assert forgotten == ["Sister is Olena."]
    assert len(dbm.list_facts(conn)) == 1


# ── settings & projects ───────────────────────────────────────────

def test_settings_and_onboarded(conn):
    assert dbm.get_setting(conn, "timezone", "def") == "def"
    dbm.set_setting(conn, "timezone", "Europe/Madrid")
    dbm.set_setting(conn, "timezone", "Europe/Kyiv")  # upsert
    assert dbm.get_setting(conn, "timezone") == "Europe/Kyiv"
    assert dbm.is_onboarded(conn) is False
    dbm.set_setting(conn, "onboarded", "1")
    assert dbm.is_onboarded(conn) is True


def test_projects(conn):
    dbm.add_project(conn, "MIA assistant", "personal AI")
    dbm.add_project(conn, "Paper X")
    assert [p["name"] for p in dbm.list_projects(conn)] == ["MIA assistant", "Paper X"]


# ── rolling summary & pruning ─────────────────────────────────────

def test_summary_roundtrip(conn):
    assert dbm.latest_summary(conn, 1) is None
    dbm.add_summary(conn, 1, "first")
    dbm.add_summary(conn, 1, "second")
    assert dbm.latest_summary(conn, 1) == "second"


def test_prune_messages_before(conn):
    s = dbm.get_or_start_session(conn, chat_id=1)
    dbm.add_message(conn, 1, s, "user", "old")
    conn.execute("UPDATE messages SET ts = datetime('now', '-10 days');")
    conn.commit()
    dbm.add_message(conn, 1, s, "user", "new")
    cutoff = "9999-01-01 00:00:00"  # prune everything strictly before this
    # Prune before 8 days ago: only the 10-day-old row goes.
    from datetime import UTC, datetime, timedelta

    before = (datetime.now(UTC) - timedelta(days=8)).strftime("%Y-%m-%d %H:%M:%S")
    assert dbm.prune_messages_before(conn, before) == 1
    remaining = [m["content"] for m in dbm.get_history(conn, s)]
    assert remaining == ["new"]
    assert cutoff  # (silence lint on the illustrative constant)


# ── context builder ───────────────────────────────────────────────

def test_build_context_empty(conn):
    assert memctx.build_context(conn, 1) == ""


def test_build_context_includes_facts_and_projects(conn):
    dbm.add_fact(conn, "Name is Bohdan.")
    dbm.add_project(conn, "MIA")
    dbm.add_summary(conn, 1, "Talked about scheduling.")
    block = memctx.build_context(conn, 1)
    assert "Bohdan" in block
    assert "MIA" in block
    assert "scheduling" in block


def test_build_context_respects_budget(conn):
    for i in range(500):
        dbm.add_fact(conn, f"Fact number {i} with some padding text.")
    block = memctx.build_context(conn, 1, token_budget=200)
    assert memctx.approx_tokens(block) <= 200


# ── tool dispatch ─────────────────────────────────────────────────

def test_dispatch_remember_recall_forget(conn):
    assert "Saved" in registry.dispatch("remember_fact", {"content": "Loves tea."}, conn)
    assert "Loves tea." in registry.dispatch("recall_facts", {}, conn)
    assert "Loves tea." in registry.dispatch("recall_facts", {"query": "tea"}, conn)
    assert "Forgot" in registry.dispatch("forget_fact", {"query": "tea"}, conn)
    assert registry.dispatch("recall_facts", {"query": "tea"}, conn) == "No matching facts stored."


def test_dispatch_unknown_tool(conn):
    assert "Unknown tool" in registry.dispatch("nope", {}, conn)


def test_remember_fact_rejects_empty(conn):
    assert "empty" in registry.dispatch("remember_fact", {"content": "  "}, conn)


# ── onboarding normalizers ────────────────────────────────────────

def test_normalize_tz_city_and_iana():
    assert interview._normalize_tz("Madrid", "UTC") == "Europe/Madrid"
    assert interview._normalize_tz("America/New_York", "UTC") == "America/New_York"
    assert interview._normalize_tz("someplace", "Europe/Madrid") == "Europe/Madrid"


def test_normalize_time():
    assert interview._normalize_time("around 08:00 please") == "08:00"
    assert interview._normalize_time("7:5") is None
    assert interview._normalize_time("no time here") is None


def test_is_skip():
    assert interview._is_skip("skip") is True
    assert interview._is_skip("Madrid") is False
