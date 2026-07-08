"""Telegram handlers. The owner lock lives in the handler filters (see main)."""

from __future__ import annotations

import html
import logging

from telegram import Message, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from mia.agent import core, router
from mia.agent.prompts import system_prompt
from mia.bot.feedback import run_with_feedback, send_reply
from mia.memory import db as dbm
from mia.voice import transcribe as vt

log = logging.getLogger("mia.bot")

# Simple messages are cheap to answer with the router model; complex ones go to
# the default (Sonnet) model with more history.
_SIMPLE_HISTORY = 6
_COMPLEX_HISTORY = 20

_HELP = """\
I'm Mia — your assistant, here in Telegram. Talk to me in Ukrainian, English, \
or Spanish; I'll reply in kind.

Things you can ask me right now:
• "Explain like I'm busy: what's the difference between OAuth and OIDC?"
• "Draft a 3-line reply declining a meeting, polite but firm."
• "Help me think through how to split this project into milestones."
• "¿Cómo digo 'te aviso cuando lo tenga listo' de forma más formal?"
• "Rewrite this to sound calmer: <paste text>"
• "Summarise this in 3 bullets: <paste text>"

Commands: /start, /help, /usage, /reset.
Calendar, email, voice notes, and memory arrive in later phases."""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hi, I'm Mia — your personal assistant. Send me a message in Ukrainian, "
        "English, or Spanish and I'll help.\n\nTry /help for examples."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(_HELP)


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = context.bot_data["conn"]
    dbm.reset_session(conn, update.effective_chat.id)
    await update.message.reply_text("Fresh start — I've cleared this conversation's context.")


async def usage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = context.bot_data["conn"]
    rows = dbm.usage_month_to_date(conn)
    if not rows:
        await update.message.reply_text("No usage recorded yet this month.")
        return
    lines = ["Month-to-date usage:"]
    total = 0.0
    for r in rows:
        total += r["cost_usd"] or 0.0
        lines.append(
            f"• {r['provider']}: ${r['cost_usd'] or 0:.4f} "
            f"({r['calls']} calls, {r['input_tokens'] or 0}+{r['output_tokens'] or 0} tok)"
        )
    lines.append(f"Total: ${total:.4f}")
    await update.message.reply_text("\n".join(lines))


async def _respond(
    message: Message, context: ContextTypes.DEFAULT_TYPE, chat_id: int,
    text: str, modality: str,
) -> None:
    """Shared path for a user utterance (typed or transcribed) → Claude → reply."""
    conn = context.bot_data["conn"]
    client = context.bot_data["anthropic"]
    settings = context.bot_data["settings"]

    session_id = dbm.get_or_start_session(conn, chat_id)
    dbm.add_message(conn, chat_id, session_id, "user", text, modality)

    async def work() -> core.Reply:
        route = await router.classify(client, settings.claude_model_router, text)
        dbm.log_token_usage(
            conn, "anthropic", route.model, route.input_tokens, route.output_tokens,
            route.cost_usd, "router",
        )
        if route.label == "simple":
            model = settings.claude_model_router
            purpose = "chat"
            history = dbm.get_history(conn, session_id, limit=_SIMPLE_HISTORY)
        else:
            model = settings.claude_model_default
            purpose = "agent"
            history = dbm.get_history(conn, session_id, limit=_COMPLEX_HISTORY)
        reply = await core.generate(client, model, system_prompt(), history)
        dbm.log_token_usage(
            conn, "anthropic", reply.model, reply.input_tokens, reply.output_tokens,
            reply.cost_usd, purpose,
        )
        return reply

    try:
        reply, progress = await run_with_feedback(message, work())
    except Exception:
        log.exception("Failed to answer message in chat %s", chat_id)
        await message.reply_text(
            "Something went wrong reaching my brain just now — try again in a moment."
        )
        return

    dbm.add_message(conn, chat_id, session_id, "assistant", reply.text)
    await send_reply(message, progress, reply.text)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _respond(
        update.message, context, update.effective_chat.id,
        update.message.text, modality="text",
    )


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = context.bot_data["conn"]
    settings = context.bot_data["settings"]
    openai_client = context.bot_data["openai"]
    voice = update.message.voice

    if voice.duration and voice.duration > vt.MAX_VOICE_SECONDS:
        minutes = vt.MAX_VOICE_SECONDS // 60
        await update.message.reply_text(
            f"That note is a bit long for me — send one under {minutes} minutes "
            "and I'll transcribe it."
        )
        return

    try:
        await update.message.chat.send_action(ChatAction.TYPING)
        tg_file = await voice.get_file()
        audio = await tg_file.download_as_bytearray()
        transcript = await vt.transcribe(openai_client, settings.whisper_model, bytes(audio))
    except Exception:
        log.exception("Voice transcription failed in chat %s", update.effective_chat.id)
        await update.message.reply_text(
            "I couldn't transcribe that just now — mind sending it again?"
        )
        return

    # Audio is never persisted; only cost and the transcript are recorded.
    dbm.log_token_usage(
        conn, "openai", settings.whisper_model, 0, 0,
        vt.transcription_cost(voice.duration or 0), "transcription",
    )

    if not transcript:
        await update.message.reply_text(
            "I couldn't make out any speech in that — try again, a little closer to the mic?"
        )
        return

    # Echo the transcript in italics so the owner can verify what I heard.
    await update.message.reply_text(
        f"🎤 <i>{html.escape(transcript)}</i>", parse_mode=ParseMode.HTML
    )
    await _respond(
        update.message, context, update.effective_chat.id, transcript, modality="voice",
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Last-resort handler so no failure is ever silent (plan design rule #5)."""
    log.exception("Unhandled bot error", exc_info=context.error)
