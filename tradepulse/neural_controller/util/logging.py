"""Structured logging utilities for the neural controller."""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict

_DEFAULT_LOGGER_NAME = "tradepulse.neural_controller"


def setup_logger(level: str = "INFO") -> None:
    """Configure root logging with a JSON formatter.

    The configuration is idempotent to avoid duplicating handlers when unit
    tests import the package repeatedly. The log level respects both the
    ``level`` argument and the ``TRADEPULSE_NEURO_LOG_LEVEL`` environment
    variable (the environment variable wins when provided).
    """

    env_level = os.environ.get("TRADEPULSE_NEURO_LOG_LEVEL")
    resolved_level = env_level or level
    lvl = getattr(logging, (resolved_level or "INFO").upper(), logging.INFO)

    root = logging.getLogger()
    if root.handlers:
        root.setLevel(lvl)
        return

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(_JsonLogFormatter())
    root.addHandler(handler)
    root.setLevel(lvl)


def log_decision(event: Dict[str, Any]) -> None:
    """Emit a structured decision record to the controller logger."""

    logger = logging.getLogger(f"{_DEFAULT_LOGGER_NAME}.decision")
    logger.info("controller_decision", extra={"event": "neuro.decision", "payload": event})



class _JsonLogFormatter(logging.Formatter):
    """Format log records as newline-delimited JSON."""

    default_time_format = "%Y-%m-%dT%H:%M:%S"
    default_msec_format = "%s.%03dZ"

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401 - inherited docstring
        payload: Dict[str, Any] = {
            "ts": self.formatTime(record, self.default_time_format),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if hasattr(record, "event"):
            payload["event"] = getattr(record, "event")
        if hasattr(record, "payload"):
            payload["payload"] = getattr(record, "payload")
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)

