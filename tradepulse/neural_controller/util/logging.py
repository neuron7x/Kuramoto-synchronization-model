"""Structured logging utilities for the neural controller."""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict

_DEFAULT_LOGGER_NAME = "tradepulse.neural_controller"
_DECISION_DEFAULTS: Dict[str, Any] = {
    "mode": "GREEN",
    "action": "hold",
    "D": 0.0,
    "H": 0.0,
    "M": 0.0,
    "E": 0.0,
    "S": 0.0,
    "RPE": 0.0,
    "belief": 0.0,
    "alloc_main": 0.0,
    "alloc_alt": 0.0,
    "alloc_scale": 1.0,
    "temperature": 1.0,
    "sync_order": 1.0,
}
_NUMERIC_FIELDS = {
    "D",
    "H",
    "M",
    "E",
    "S",
    "RPE",
    "belief",
    "alloc_main",
    "alloc_alt",
    "alloc_scale",
    "temperature",
    "sync_order",
}


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
    if not logger.isEnabledFor(logging.INFO):
        return

    payload: Dict[str, Any] = dict(_DECISION_DEFAULTS)
    for key, value in event.items():
        if key in _NUMERIC_FIELDS:
            try:
                payload[key] = float(value)
            except (TypeError, ValueError):
                continue
        elif key == "mode":
            payload[key] = str(value).upper()
        elif key == "action":
            payload[key] = str(value)
        elif key not in payload:
            payload[key] = value
    message = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    logger.info(message, extra={"event": "neuro.decision", "payload": payload})


class _JsonLogFormatter(logging.Formatter):
    """Format log records as newline-delimited JSON."""

    default_time_format = "%Y-%m-%dT%H:%M:%S"
    default_msec_format = "%s.%03dZ"

    def format(
        self, record: logging.LogRecord
    ) -> str:  # noqa: D401 - inherited docstring
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
