"""Structured logging utilities for the cortex service."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any


class JsonLogFormatter(logging.Formatter):
    """Serialize log records to JSON for ingestion by observability stacks."""

    def format(
        self, record: logging.LogRecord
    ) -> str:  # noqa: D401 - documented at class level
        payload: dict[str, Any] = {
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = record.stack_info
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in payload:
                continue
            try:
                json.dumps({key: value})
            except TypeError:
                continue
            payload[key] = value
        return json.dumps(payload, separators=(",", ":"))


def configure_logging(level: str) -> None:
    """Initialise logging configuration once at startup."""

    root_logger = logging.getLogger()
    root_logger.setLevel(level.upper())
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    root_logger.handlers.clear()
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger instance."""

    return logging.getLogger(name)


__all__ = ["configure_logging", "get_logger", "JsonLogFormatter"]
