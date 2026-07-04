"""Haiku fast-path router: trivial messages skip the more expensive model."""

from __future__ import annotations

from dataclasses import dataclass

from mia.agent import core
from mia.agent.prompts import ROUTER_SYSTEM


@dataclass(slots=True)
class Route:
    label: str  # "simple" | "complex"
    model: str
    input_tokens: int
    output_tokens: int

    @property
    def cost_usd(self) -> float:
        return core.cost_usd(self.model, self.input_tokens, self.output_tokens)


async def classify(client, model: str, text: str) -> Route:
    """Classify a message as simple/complex. Defaults to complex on doubt."""
    response = await client.messages.create(
        model=model,
        max_tokens=8,
        system=ROUTER_SYSTEM,
        messages=[{"role": "user", "content": text}],
    )
    raw = core._extract_text(response.content).lower()
    label = "simple" if "simple" in raw else "complex"
    return Route(
        label=label,
        model=response.model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
