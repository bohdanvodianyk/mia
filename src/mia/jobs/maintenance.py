"""Nightly maintenance: roll recent conversation into a summary, prune old rows.

Keeps the context builder fed with a rolling summary while bounding raw history
(plan: nightly summarization; raw history pruned after 7 days).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from mia.agent import core
from mia.memory import db as dbm

log = logging.getLogger("mia.jobs")

RETENTION_DAYS = 7
_TS_FORMAT = "%Y-%m-%d %H:%M:%S"
_MIN_MESSAGES_TO_SUMMARIZE = 4
_MAX_TRANSCRIPT_CHARS = 12_000

_SUMMARY_SYSTEM = (
    "You maintain a concise rolling memory of a person's conversations with "
    "their assistant. Merge the new exchanges into the existing summary. Keep "
    "it under ~200 words, factual, in English, focused on durable context "
    "(who they are, what they're working on, decisions, open threads). Drop "
    "stale chit-chat. Return only the updated summary."
)


async def nightly_maintenance(conn, client, model: str, chat_id: int) -> None:
    """Update the rolling summary from the last week, then prune old messages."""
    now = datetime.now(UTC)
    window_start = (now - timedelta(days=RETENTION_DAYS)).strftime(_TS_FORMAT)

    try:
        rows = dbm.messages_since(conn, chat_id, window_start)
        if len(rows) >= _MIN_MESSAGES_TO_SUMMARIZE:
            await _update_summary(conn, client, model, chat_id, rows)
        pruned = dbm.prune_messages_before(conn, window_start)
        log.info("Nightly maintenance: %d msgs summarized window, %d pruned", len(rows), pruned)
        dbm.log_event(conn, "INFO", "jobs", f"nightly maintenance ok ({pruned} pruned)")
    except Exception:
        log.exception("Nightly maintenance failed")


async def _update_summary(conn, client, model: str, chat_id: int, rows) -> None:
    transcript = "\n".join(f"{r['role']}: {r['content']}" for r in rows)[-_MAX_TRANSCRIPT_CHARS:]
    existing = dbm.latest_summary(conn, chat_id) or "(none yet)"
    user_block = (
        f"Existing summary:\n{existing}\n\nNew conversation:\n{transcript}\n\n"
        "Updated summary:"
    )
    reply = await core.generate(
        client, model, _SUMMARY_SYSTEM,
        [{"role": "user", "content": user_block}], max_tokens=512,
    )
    if reply.text:
        dbm.add_summary(
            conn, chat_id, reply.text,
            period_start=rows[0]["ts"], period_end=rows[-1]["ts"],
        )
        dbm.log_token_usage(
            conn, "anthropic", reply.model, reply.input_tokens, reply.output_tokens,
            reply.cost_usd, "summary",
        )


def start_scheduler(app):
    """Attach an AsyncIOScheduler to the running bot loop (called in post_init)."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    settings = app.bot_data["settings"]
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        nightly_maintenance,
        CronTrigger(hour=3, minute=30),
        kwargs={
            "conn": app.bot_data["conn"],
            "client": app.bot_data["anthropic"],
            "model": settings.claude_model_router,
            "chat_id": settings.owner_telegram_id,
        },
        id="nightly_maintenance",
        replace_existing=True,
    )
    scheduler.start()
    app.bot_data["scheduler"] = scheduler
    log.info("Scheduler started — nightly maintenance at 03:30 UTC")
    return scheduler
