"""The Claude reply path plus token-cost accounting.

Phase 1 is a single Claude call (system prompt + session history -> reply). The
shape is kept deliberately loop-ready so the tool-use iterations from Phase 4
can slot in without reworking callers.
"""

from __future__ import annotations

from dataclasses import dataclass

# Anthropic USD pricing per 1M tokens (input, output). Verify at each phase's
# build against https://platform.claude.com/docs/en/about-claude/pricing.
PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Cost of a single call. Unknown models cost 0 (logged, not guessed)."""
    inp, out = PRICING.get(model, (0.0, 0.0))
    return (input_tokens * inp + output_tokens * out) / 1_000_000


@dataclass(slots=True)
class Reply:
    text: str
    model: str
    input_tokens: int
    output_tokens: int

    @property
    def cost_usd(self) -> float:
        return cost_usd(self.model, self.input_tokens, self.output_tokens)


def _extract_text(content: list) -> str:
    parts = [block.text for block in content if getattr(block, "type", None) == "text"]
    return "".join(parts).strip()


async def generate(
    client,
    model: str,
    system: str,
    messages: list[dict[str, str]],
    max_tokens: int = 1024,
) -> Reply:
    """One Claude turn. `messages` already ends with the user's latest turn.

    Thinking is omitted deliberately: on Sonnet 4.6 that runs without extended
    thinking, keeping chat replies snappy (plan weakness #1).
    """
    response = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    return Reply(
        text=_extract_text(response.content),
        model=response.model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
