"""Logging utilities that emit structured JSON payloads."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable

__all__ = ["StructuredLogFormatter", "configure_logging"]

_RESERVED_LOG_FIELDS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
}


class StructuredLogFormatter(logging.Formatter):
    """Format log records into canonical JSON payloads."""

    def format(self, record: logging.LogRecord) -> str:
        payload = self.format_to_dict(record)
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)

    def format_to_dict(self, record: logging.LogRecord) -> dict[str, Any]:
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        payload: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOG_FIELDS:
                continue
            if key == "message":
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return payload


class _StructuredSinkHandler(logging.Handler):
    """Handler that forwards structured log payloads to a callable sink."""

    def __init__(
        self, sink: Callable[[dict[str, Any]], None], formatter: StructuredLogFormatter
    ) -> None:
        super().__init__()
        self._sink = sink
        self.formatter = formatter

    def emit(
        self, record: logging.LogRecord
    ) -> None:  # pragma: no cover - errors handled by logging
        try:
            payload = self.formatter.format_to_dict(record)
            self._sink(payload)
        except Exception:
            self.handleError(record)


def _resolve_level(level: int | str) -> int:
    if isinstance(level, int):
        return level
    numeric = logging.getLevelName(level.upper())
    if isinstance(numeric, int):
        return numeric
    raise ValueError(f"Unknown log level: {level}")


def configure_logging(
    *,
    level: int | str = logging.INFO,
    sink: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    """Configure the root logger to emit structured logs.

    Parameters
    ----------
    level:
        Logging level expressed as an integer or human readable string.
    sink:
        Optional callable that receives the structured payload for each log record.
        When omitted, logs are written to ``sys.stderr`` using JSON formatting.
    """

    numeric_level = _resolve_level(level)
    formatter = StructuredLogFormatter()

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    if sink is None:
        handler: logging.Handler = logging.StreamHandler()
        handler.setFormatter(formatter)
    else:
        handler = _StructuredSinkHandler(sink, formatter)

    root_logger.addHandler(handler)
