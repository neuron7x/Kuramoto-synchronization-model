# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Structured logging utilities for the cortex service."""

from __future__ import annotations

import json
import logging
import sys
from ipaddress import ip_address as parse_ip_address
from typing import IO, Any


class JsonLogFormatter(logging.Formatter):
    """Serialize log records to JSON for ingestion by observability stacks."""

    def format(self, record: logging.LogRecord) -> str:
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


class StructuredAuditLogger:
    """Production audit adapter that emits JSON audit events.

    The ``trace_id`` field is mandatory and must be present in ``details``.
    """

    def __init__(self, *, stream: IO[str] | None = None) -> None:
        self._stream = stream or sys.stderr

    def log_event(
        self,
        *,
        event_type: str,
        actor: str,
        ip_address: str,
        details: dict[str, object],
    ) -> dict[str, object]:
        trace_id = details.get("trace_id")
        if not isinstance(trace_id, str) or not trace_id.strip():
            raise ValueError("StructuredAuditLogger requires non-empty details['trace_id']")
        try:
            parse_ip_address(ip_address)
        except ValueError as exc:
            raise ValueError(f"Invalid ip_address: {ip_address}") from exc

        # Audit-event timestamp routed through ``default_clock()`` so a
        # FrozenClock keeps cortex logs deterministic in replay tests.
        from geosync.core.compat import default_clock, safe_isoformat

        payload: dict[str, object] = {
            "ts": safe_isoformat(default_clock().now()),
            "event_type": event_type,
            "actor": actor,
            "ip_address": ip_address,
            "trace_id": trace_id,
            "details": details,
        }
        try:
            self._stream.write(json.dumps(payload, separators=(",", ":")) + "\n")
            self._stream.flush()
        except OSError as exc:
            raise RuntimeError("Failed to write audit payload to stream") from exc
        return payload


__all__ = [
    "configure_logging",
    "get_logger",
    "JsonLogFormatter",
    "StructuredAuditLogger",
]
