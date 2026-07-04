"""Latency feedback: instant typing action, and a progress note when slow.

Plan weakness #1 — agent calls can take several seconds and a silent bot reads
as broken. We always show the typing action within ~1s, and if the work runs
past a threshold we post an editable progress message that becomes the answer.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable

from telegram import Message
from telegram.constants import ChatAction

_TELEGRAM_LIMIT = 4096
_SPLIT_AT = 4000  # leave headroom below the hard limit


async def run_with_feedback[T](
    message: Message,
    work: Awaitable[T],
    *,
    threshold: float = 5.0,
    note: str = "One moment…",
) -> tuple[T, Message | None]:
    """Run `work`, showing typing immediately and a progress note if it's slow.

    Returns the work's result and the progress message (or None if it finished
    before the threshold), so the caller can edit the note into the reply.
    """
    try:
        await message.chat.send_action(ChatAction.TYPING)
    except Exception:  # feedback must never sink the actual work
        pass

    task = asyncio.ensure_future(work)
    progress: Message | None = None
    done, _ = await asyncio.wait({task}, timeout=threshold)
    if task not in done:
        try:
            progress = await message.reply_text(note)
        except Exception:
            progress = None
    result = await task
    return result, progress


def _split(text: str) -> list[str]:
    """Split over-long replies on line boundaries to fit Telegram's limit."""
    if len(text) <= _TELEGRAM_LIMIT:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > _SPLIT_AT:
        cut = remaining.rfind("\n", 0, _SPLIT_AT)
        if cut <= 0:
            cut = _SPLIT_AT
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


async def send_reply(message: Message, progress: Message | None, text: str) -> None:
    """Deliver the reply, reusing the progress message when one was posted."""
    text = text or "…"
    chunks = _split(text)
    if progress is not None:
        try:
            await progress.edit_text(chunks[0])
        except Exception:
            await message.reply_text(chunks[0])
    else:
        await message.reply_text(chunks[0])
    for chunk in chunks[1:]:
        await message.reply_text(chunk)
