"""Offline agent-layer units: pricing, reply splitting, prompt content."""

from __future__ import annotations

from mia.agent import core
from mia.agent.prompts import ROUTER_SYSTEM, system_prompt
from mia.bot.feedback import _split
from mia.tools import registry


def test_cost_sonnet():
    # 1M input + 1M output at $3 / $15.
    assert core.cost_usd("claude-sonnet-4-6", 1_000_000, 1_000_000) == 18.0


def test_cost_haiku():
    assert core.cost_usd("claude-haiku-4-5", 1_000_000, 0) == 1.0


def test_cost_unknown_model_is_zero():
    assert core.cost_usd("mystery", 1_000_000, 1_000_000) == 0.0


def test_reply_cost_property():
    r = core.Reply(text="hi", model="claude-haiku-4-5", input_tokens=1000, output_tokens=1000)
    assert r.cost_usd == (1000 * 1.0 + 1000 * 5.0) / 1_000_000


def test_split_short_text_is_single_chunk():
    assert _split("short") == ["short"]


def test_split_long_text_stays_under_limit():
    text = "\n".join(f"line {i}" for i in range(2000))
    chunks = _split(text)
    assert len(chunks) > 1
    assert all(len(c) <= 4096 for c in chunks)


def test_system_prompt_covers_languages_and_length():
    p = system_prompt()
    assert "Ukrainian" in p and "English" in p and "Spanish" in p
    assert "8 lines" in p


def test_router_prompt_labels():
    assert "simple" in ROUTER_SYSTEM and "complex" in ROUTER_SYSTEM


def test_web_search_tool_variant_by_model():
    assert registry.web_search_tool("claude-sonnet-4-6")["type"] == "web_search_20260209"
    assert (
        registry.web_search_tool("claude-haiku-4-5-20251001")["type"]
        == "web_search_20250305"
    )
    assert registry.web_search_tool("claude-sonnet-4-6")["name"] == "web_search"


def test_reply_cost_includes_web_search_surcharge():
    r = core.Reply(
        text="x", model="claude-sonnet-4-6", input_tokens=0, output_tokens=0,
        web_search_requests=3,
    )
    assert r.cost_usd == 3 * core.WEB_SEARCH_USD_PER_REQUEST


def test_system_prompt_mentions_web_when_tools():
    assert "web_search" in system_prompt(with_tools=True)
    assert "web_search" not in system_prompt(with_tools=False)
