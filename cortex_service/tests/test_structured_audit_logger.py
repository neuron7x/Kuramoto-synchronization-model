# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import io
import json
from datetime import datetime

import pytest

from cortex_service.app.logger import StructuredAuditLogger


def test_structured_audit_logger_requires_trace_id() -> None:
    logger = StructuredAuditLogger(stream=io.StringIO())
    with pytest.raises(ValueError):
        logger.log_event(
            event_type="cache.write",
            actor="tester",
            ip_address="127.0.0.1",
            details={},
        )


def test_structured_audit_logger_emits_json() -> None:
    stream = io.StringIO()
    logger = StructuredAuditLogger(stream=stream)
    payload = logger.log_event(
        event_type="cache.write",
        actor="tester",
        ip_address="127.0.0.1",
        details={"trace_id": "abc-123", "k": "v"},
    )

    line = stream.getvalue().strip()
    parsed = json.loads(line)
    assert parsed["event_type"] == "cache.write"
    assert parsed["trace_id"] == "abc-123"
    assert payload["trace_id"] == "abc-123"


def test_structured_audit_logger_rejects_whitespace_trace_id() -> None:
    logger = StructuredAuditLogger(stream=io.StringIO())
    with pytest.raises(ValueError):
        logger.log_event(
            event_type="cache.write",
            actor="tester",
            ip_address="127.0.0.1",
            details={"trace_id": "   "},
        )


def test_structured_audit_logger_accepts_unicode_details() -> None:
    stream = io.StringIO()
    logger = StructuredAuditLogger(stream=stream)
    payload = logger.log_event(
        event_type="cache.write",
        actor="тестер",
        ip_address="127.0.0.1",
        details={"trace_id": "unicode-1", "note": "дані"},
    )
    assert payload["details"]["note"] == "дані"


def test_structured_audit_logger_payload_contains_iso_timestamp() -> None:
    stream = io.StringIO()
    logger = StructuredAuditLogger(stream=stream)
    payload = logger.log_event(
        event_type="cache.write",
        actor="tester",
        ip_address="127.0.0.1",
        details={"trace_id": "abc-iso"},
    )
    assert isinstance(datetime.fromisoformat(str(payload["ts"])), datetime)


class _BrokenStream:
    def write(self, _: str) -> int:
        raise OSError("disk full")

    def flush(self) -> None:
        return None


def test_structured_audit_logger_stream_write_failure() -> None:
    logger = StructuredAuditLogger(stream=_BrokenStream())  # type: ignore[arg-type]
    with pytest.raises(RuntimeError):
        logger.log_event(
            event_type="cache.write",
            actor="tester",
            ip_address="127.0.0.1",
            details={"trace_id": "broken"},
        )
