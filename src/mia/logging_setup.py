"""Structured logging: stdout + rotating file, plus an events_log DB sink."""

from __future__ import annotations

import logging
import sqlite3
from logging.handlers import RotatingFileHandler
from pathlib import Path

from mia.memory import db as db_module

_LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


class EventsLogHandler(logging.Handler):
    """Persists WARNING+ log records into the events_log table.

    Wires the `events_log` table into standard logging so any operational
    warning or error is durably recorded, not just printed.
    """

    def __init__(self, conn: sqlite3.Connection, level: int = logging.WARNING) -> None:
        super().__init__(level=level)
        self._conn = conn

    def emit(self, record: logging.LogRecord) -> None:
        try:
            db_module.log_event(
                self._conn,
                level=record.levelname,
                component=record.name,
                message=record.getMessage(),
            )
        except Exception:  # never let logging crash the app
            self.handleError(record)


def setup_logging(log_file: Path, level: str = "INFO") -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()

    fmt = logging.Formatter(_LOG_FORMAT)

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    root.addHandler(stream)

    file_handler = RotatingFileHandler(
        log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)


def attach_events_log(conn: sqlite3.Connection) -> None:
    """Route WARNING+ records into the events_log DB table."""
    logging.getLogger().addHandler(EventsLogHandler(conn))
