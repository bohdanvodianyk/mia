"""Mia entrypoint. `--check` runs the Phase 0 acceptance gate (G0)."""

from __future__ import annotations

import argparse
import logging
import sys

from mia import __version__
from mia.config import Settings, load_settings
from mia.logging_setup import attach_events_log, setup_logging
from mia.memory import db as db_module

log = logging.getLogger("mia.main")

_EXPECTED_TABLES = {
    "sessions", "messages", "summaries", "facts", "projects", "tasks",
    "notes", "meetings", "settings", "action_trust", "token_usage", "events_log",
}


def _check(settings: Settings) -> int:
    """Gate G0: boot, create DB, log redacted config, exit 0."""
    settings.ensure_dirs()
    setup_logging(settings.log_file, settings.log_level)

    conn = db_module.init_db(settings.db_path)
    attach_events_log(conn)

    tables = db_module.table_names(conn)
    missing = _EXPECTED_TABLES - tables

    log.info("Mia v%s starting --check (env=%s)", __version__, settings.mia_env)
    log.info("Config: %s", settings.redacted_summary())
    log.info("Database: %s (%d tables)", settings.db_path, len(tables))
    db_module.log_event(conn, "INFO", "main", f"--check boot ok, {len(tables)} tables")

    if missing:
        log.error("Schema incomplete, missing tables: %s", sorted(missing))
        conn.close()
        return 1

    log.info("Gate G0 OK — scaffold boots, DB ready, config loaded.")
    conn.close()
    return 0


# Secrets the runtime cannot start without. Reported plainly if unset.
_REQUIRED_FOR_RUN = {
    "owner_telegram_id": "OWNER_TELEGRAM_ID (your numeric Telegram id, from @userinfobot)",
    "telegram_bot_token": "TELEGRAM_BOT_TOKEN (from @BotFather)",
    "anthropic_api_key": "ANTHROPIC_API_KEY (from console.anthropic.com)",
    "openai_api_key": "OPENAI_API_KEY (Whisper voice transcription, from platform.openai.com)",
}


def _run(settings: Settings) -> int:
    """Phase 1 runtime: owner-locked Telegram bot over long-polling."""
    settings.ensure_dirs()
    setup_logging(settings.log_file, settings.log_level)

    missing = [hint for attr, hint in _REQUIRED_FOR_RUN.items() if not getattr(settings, attr)]
    if missing:
        for hint in missing:
            log.error("Missing required config: %s", hint)
        log.error("Set these in .env, then run again. (Gate G0 does not need them.)")
        return 1

    # Imported lazily so `--check` (Gate G0) runs without the provider SDKs.
    from anthropic import AsyncAnthropic
    from openai import AsyncOpenAI
    from telegram.ext import Application, CommandHandler, MessageHandler, filters

    from mia.bot import handlers

    conn = db_module.init_db(settings.db_path)
    attach_events_log(conn)

    client = AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value())
    openai_client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())

    app = Application.builder().token(settings.telegram_bot_token.get_secret_value()).build()
    app.bot_data.update(conn=conn, anthropic=client, openai=openai_client, settings=settings)

    # Owner lock: filter every handler to the owner's user id. Non-owner updates
    # match no handler and are silently ignored (plan §8, non-negotiable).
    owner = filters.User(user_id=settings.owner_telegram_id)
    app.add_handler(CommandHandler("start", handlers.start, filters=owner))
    app.add_handler(CommandHandler("help", handlers.help_command, filters=owner))
    app.add_handler(CommandHandler("usage", handlers.usage, filters=owner))
    app.add_handler(CommandHandler("reset", handlers.reset, filters=owner))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & owner, handlers.on_text))
    app.add_handler(MessageHandler(filters.VOICE & owner, handlers.on_voice))
    app.add_error_handler(handlers.on_error)

    log.info(
        "Mia v%s online — polling, owner locked to id %s",
        __version__, settings.owner_telegram_id,
    )
    db_module.log_event(conn, "INFO", "main", "bot started (polling)")
    app.run_polling()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mia", description="Mia personal assistant")
    parser.add_argument("--check", action="store_true", help="Boot check (Gate G0), then exit")
    parser.add_argument("--version", action="version", version=f"mia {__version__}")
    args = parser.parse_args(argv)

    settings = load_settings()

    if args.check:
        return _check(settings)

    return _run(settings)


if __name__ == "__main__":
    sys.exit(main())
