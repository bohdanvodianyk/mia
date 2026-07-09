"""The Claude reply path plus token-cost accounting.

Phase 1 is a single Claude call (system prompt + session history -> reply). The
shape is kept deliberately loop-ready so the tool-use iterations from Phase 4
can slot in without reworking callers.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

# Anthropic USD pricing per 1M tokens (input, output). Verify at each phase's
# build against https://platform.claude.com/docs/en/about-claude/pricing.
PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
}

# Server-side web search is billed separately from tokens: $10 / 1,000 searches.
WEB_SEARCH_USD_PER_REQUEST = 0.01


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Token cost of a single call. Unknown models cost 0 (logged, not guessed)."""
    inp, out = PRICING.get(model, (0.0, 0.0))
    return (input_tokens * inp + output_tokens * out) / 1_000_000


def _web_search_requests(response) -> int:
    stu = getattr(response.usage, "server_tool_use", None)
    return getattr(stu, "web_search_requests", 0) or 0 if stu else 0


@dataclass(slots=True)
class Reply:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    web_search_requests: int = 0

    @property
    def cost_usd(self) -> float:
        return (
            cost_usd(self.model, self.input_tokens, self.output_tokens)
            + self.web_search_requests * WEB_SEARCH_USD_PER_REQUEST
        )


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


async def generate_with_tools(
    client,
    model: str,
    system: str,
    messages: list[dict],
    tools: list[dict],
    execute: Callable[[str, dict], str],
    max_iterations: int = 8,
    max_tokens: int = 1024,
) -> Reply:
    """Manual tool-use loop: call Claude, run any tools, feed results back.

    `execute(name, input)` runs a tool synchronously and returns its string
    result. Token usage is summed across every iteration so the whole turn is
    costed as one Reply.
    """
    convo: list[dict] = list(messages)
    total_in = total_out = total_web = 0
    final_model = model
    response = None

    for _ in range(max_iterations):
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            messages=convo,
        )
        total_in += response.usage.input_tokens
        total_out += response.usage.output_tokens
        total_web += _web_search_requests(response)
        final_model = response.model

        if response.stop_reason == "tool_use":
            # A client-side tool (e.g. memory) needs executing. Preserve the
            # assistant turn, then answer every client tool call in one message.
            convo.append({"role": "assistant", "content": response.content})
            results = [
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": execute(block.name, block.input),
                }
                for block in response.content
                if getattr(block, "type", None) == "tool_use"
            ]
            convo.append({"role": "user", "content": results})
            continue

        if response.stop_reason == "pause_turn":
            # A server-side tool (web search) hit its iteration limit; re-send
            # the assistant turn as-is and the server resumes where it left off.
            convo.append({"role": "assistant", "content": response.content})
            continue

        break  # end_turn, max_tokens, refusal, ...

    text = _extract_text(response.content) if response is not None else ""
    return Reply(
        text=text or "…",
        model=final_model,
        input_tokens=total_in,
        output_tokens=total_out,
        web_search_requests=total_web,
    )
