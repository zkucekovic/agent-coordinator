"""Diagnostic logger for agent-coordinator.

Writes structured log entries to {workspace}/coordinator-debug.log.
Each entry is a single line: ISO timestamp | LEVEL | message (+ optional JSON context).

The log is always written even when the TUI is in alternate-screen mode —
it is the authoritative record of what happened, especially on crashes.
"""

from __future__ import annotations

import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_LOG_FILENAME = ".coordinator-debug.log"

# Module-level logger so any file can do:
#   from agent_coordinator.infrastructure.diagnostic_log import get_logger
#   log = get_logger()
_logger: logging.Logger | None = None
_log_path: Path | None = None


class _OneLineFormatter(logging.Formatter):
    """Formats records as:  2024-01-02T15:04:05Z | LEVEL    | message  {ctx}"""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%f"
        )[:-3] + "Z"
        level = record.levelname.ljust(8)
        msg = record.getMessage()

        # Extra context dict attached via log.info("msg", extra={"ctx": {...}})
        ctx = getattr(record, "ctx", None)
        ctx_str = ""
        if ctx:
            try:
                ctx_str = "  " + json.dumps(ctx, default=str)
            except Exception:
                ctx_str = f"  {ctx!r}"

        exc_str = ""
        if record.exc_info:
            exc_str = "\n" + "".join(traceback.format_exception(*record.exc_info)).rstrip()

        return f"{ts} | {level} | {msg}{ctx_str}{exc_str}"


def setup(workspace: Path) -> Path:
    """Initialise the file logger for this run. Call once from main()."""
    global _logger, _log_path

    log_path = workspace / _LOG_FILENAME
    _log_path = log_path

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(_OneLineFormatter())
    handler.setLevel(logging.DEBUG)

    logger = logging.getLogger("agent_coordinator")
    logger.setLevel(logging.DEBUG)
    # Avoid duplicate handlers if called multiple times (e.g. tests)
    logger.handlers = [handler]
    logger.propagate = False

    _logger = logger

    logger.info("=== session start ===", extra={"ctx": {"python": sys.version.split()[0]}})
    return log_path


def get_logger() -> logging.Logger:
    """Return the module logger (always safe to call, even before setup())."""
    if _logger is not None:
        return _logger
    # Fallback: stderr logger so callers don't need to check
    fallback = logging.getLogger("agent_coordinator.fallback")
    if not fallback.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(_OneLineFormatter())
        fallback.addHandler(h)
        fallback.setLevel(logging.WARNING)
    return fallback


def log_crash(exc: BaseException, context: str = "") -> None:
    """Log an unhandled exception with full traceback."""
    log = get_logger()
    msg = f"CRASH{' in ' + context if context else ''}: {type(exc).__name__}: {exc}"
    log.critical(msg, exc_info=exc)


def log_path() -> Path | None:
    """Return the current log file path (None if not set up yet)."""
    return _log_path
