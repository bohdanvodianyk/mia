"""Telegram handlers. The owner lock lives in the handler filters (see main)."""

from __future__ import annotations

import html
import logging

from telegram import Message, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from mia.agent import core, router
from mia.agent.prompts import system_prompt
from mia.bot import keyboards
from mia.bot.feedback import run_with_feedback, send_reply
from mia.memory import context as memctx
from mia.memory import db as dbm
from mia.onboarding import interview
from mia.tools import registry
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
• "What's the latest on <topic>?" — I can search the web for current info.

You can also send a **voice note** — I'll transcribe it and reply. Tell me \
things about yourself and I'll remember them across chats.

Commands: /start (setup), /help, /usage, /memory (see & forget what I know), /reset.
Calendar and email arrive in later phases."""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = context.bot_data["conn"]
    if not dbm.is_onboarded(conn):
        await interview.start(update, context)
        return
    name = dbm.get_setting(conn, "owner_name")
    hi = f"Hi {name}" if name else "Hi"
    await update.message.reply_text(
        f"{hi} — I'm here. Ask me anything, send a voice note, or /help for ideas."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(_HELP)


async def memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = context.bot_data["conn"]
    facts = dbm.list_facts(conn)
    if not facts:
        await update.message.reply_text(
            "I haven't saved anything about you yet. Tell me something, or run "
            "/start to set up."
        )
        return
    await update.message.reply_text(
        "Here's what I remember. Tap 🗑 to forget an item:",
        reply_markup=keyboards.facts_keyboard(facts),
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    settings = context.bot_data["settings"]
    if update.effective_user.id != settings.owner_telegram_id:
        await query.answer()
        return
    conn = context.bot_data["conn"]
    data = query.data or ""
    if not data.startswith(keyboards.DELETE_FACT_PREFIX):
        await query.answer()
        return
    try:
        fact_id = int(data[len(keyboards.DELETE_FACT_PREFIX):])
    except ValueError:
        await query.answer()
        return
    dbm.archive_fact(conn, fact_id)
    await query.answer("Forgotten.")
    facts = dbm.list_facts(conn)
    if facts:
        await query.edit_message_text(
            "Here's what I remember. Tap 🗑 to forget an item:",
            reply_markup=keyboards.facts_keyboard(facts),
        )
    else:
        await query.edit_message_text("All clear — I have no saved facts now.")


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
    memory_context = memctx.build_context(conn, chat_id)

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
            purpose = "search" if route.needs_web else "agent"
            history = dbm.get_history(conn, session_id, limit=_COMPLEX_HISTORY)

        # Every turn gets memory context + memory tools. web_search is attached
        # ONLY when the router says the question needs live information: its
        # definition costs ~3.9k input tokens per call, which quadrupled the
        # price of ordinary chat when it was always on.
        tools = list(registry.MEMORY_TOOLS)
        if route.needs_web:
            tools.append(registry.web_search_tool(model))
        reply = await core.generate_with_tools(
            client, model, system_prompt(memory_context, with_tools=True), history,
            tools=tools,
            execute=lambda name, tool_input: registry.dispatch(name, tool_input, conn),
            max_iterations=settings.max_tool_iterations,
        )
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
    if interview.is_active(context):
        await interview.handle(update, context)
        return
    await _respond(
        update.message, context, update.effective_chat.id,
        update.message.text, modality="text",
    )


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if interview.is_active(context):
        await update.message.reply_text(
            "Let's finish setup first — please answer the last question by text."
        )
        return
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
