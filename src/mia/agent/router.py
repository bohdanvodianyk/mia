"""Haiku fast-path router: trivial messages skip the more expensive model."""

from __future__ import annotations

from dataclasses import dataclass

from mia.agent import core
from mia.agent.prompts import ROUTER_SYSTEM


@dataclass(slots=True)
class Route:
    label: str  # "search" | "simple" | "complex"
    model: str
    input_tokens: int
    output_tokens: int

    @property
    def cost_usd(self) -> float:
        return core.cost_usd(self.model, self.input_tokens, self.output_tokens)

    @property
    def needs_web(self) -> bool:
        return self.label == "search"


def parse_label(raw: str) -> str:
    """Map the router's reply to a label. Unrecognized output → complex."""
    raw = (raw or "").lower()
    if "search" in raw:
        return "search"
    if "simple" in raw:
        return "simple"
    return "complex"


async def classify(client, model: str, text: str) -> Route:
    """Classify a message as search/simple/complex.

    Only the `search` label gets the web_search tool attached downstream — that
    tool's definition costs ~3.9k input tokens per call, so attaching it to
    every message quadrupled the cost of ordinary chat.
    """
    response = await client.messages.create(
        model=model,
        max_tokens=8,
        system=ROUTER_SYSTEM,
        messages=[{"role": "user", "content": text}],
    )
    label = parse_label(core._extract_text(response.content))
    return Route(
        label=label,
        model=response.model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
