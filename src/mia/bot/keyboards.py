"""Inline keyboards. Callback data stays short (Telegram's 64-byte cap)."""

from __future__ import annotations

import sqlite3

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

DELETE_FACT_PREFIX = "delfact:"


def _truncate(text: str, limit: int = 40) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def facts_keyboard(facts: list[sqlite3.Row]) -> InlineKeyboardMarkup:
    """One delete button per fact."""
    rows = [
        [
            InlineKeyboardButton(
                f"🗑 {_truncate(f['content'])}",
                callback_data=f"{DELETE_FACT_PREFIX}{f['id']}",
            )
        ]
        for f in facts
    ]
    return InlineKeyboardMarkup(rows)
