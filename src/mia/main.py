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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mia", description="Mia personal assistant")
    parser.add_argument("--check", action="store_true", help="Boot check (Gate G0), then exit")
    parser.add_argument("--version", action="version", version=f"mia {__version__}")
    args = parser.parse_args(argv)

    settings = load_settings()

    if args.check:
        return _check(settings)

    # The Telegram bot runtime lands in Phase 1.
    print("Mia scaffold ready. The Telegram bot runtime is implemented in Phase 1.")
    print("Run `python -m mia.main --check` to verify the Phase 0 gate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
