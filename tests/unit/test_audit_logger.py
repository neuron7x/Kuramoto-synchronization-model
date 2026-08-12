# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from application.secrets.manager import ManagedSecret, ManagedSecretConfig
from src.audit.audit_logger import AuditLogger, AuditRecord, HttpAuditSink


def _fixed_clock() -> datetime:
    return datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)


def _make_record() -> AuditRecord:
    logger = AuditLogger(secret="unit-secret-value", clock=_fixed_clock)
    return logger.log_event(
        event_type="unit_test",
        actor="tester",
        ip_address="203.0.113.10",
        details={"action": "engage", "token": "sensitive"},
    )


def test_audit_logger_emits_signed_records() -> None:
    records: list[AuditRecord] = []
    audit_logger = AuditLogger(secret="unit-secret-value", sink=records.append, clock=_fixed_clock)

    record = audit_logger.log_event(
        event_type="kill_switch_engaged",
        actor="ops",
        ip_address="203.0.113.5",
        details={"reason": "manual"},
    )

    assert record.actor == "ops"
    assert record.details == {"reason": "manual"}
    assert audit_logger.verify(record) is True
    assert records == [record]


def test_audit_logger_detects_tampering() -> None:
    audit_logger = AuditLogger(secret="unit-secret-value", clock=_fixed_clock)
    record = audit_logger.log_event(
        event_type="kill_switch_engaged",
        actor="ops",
        ip_address="203.0.113.5",
        details={"reason": "manual"},
    )

    tampered = record.model_copy(update={"details": {"reason": "tampered"}})
    assert audit_logger.verify(record) is True
    assert audit_logger.verify(tampered) is False


def test_http_audit_sink_posts_payload() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(202)

    client = httpx.Client(
        base_url="https://audit.example.com", transport=httpx.MockTransport(handler)
    )
    sink = HttpAuditSink("/ingest", http_client=client, timeout=1.0)
    try:
        sink(_make_record())
    finally:
        client.close()

    assert len(captured) == 1
    request = captured[0]
    assert request.method == "POST"
    assert request.url.path == "/ingest"
    payload = request.content.decode("utf-8")
    assert "unit_test" in payload


def test_http_audit_sink_logs_failures(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.ERROR, logger="geosync.audit.http_sink")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = httpx.Client(
        base_url="https://audit.example.com", transport=httpx.MockTransport(handler)
    )
    sink = HttpAuditSink("/ingest", http_client=client, timeout=1.0)
    try:
        sink(_make_record())
    finally:
        client.close()

    assert "Failed to forward audit record" in caplog.text


def test_audit_logger_uses_rotated_secret(tmp_path: Path) -> None:
    secret_path = tmp_path / "audit_secret"
    secret_path.write_text("initial-managed-secret", encoding="utf-8")
    managed = ManagedSecret(
        config=ManagedSecretConfig(name="audit_secret", path=secret_path, min_length=16),
        fallback=None,
        refresh_interval_seconds=0.0,
    )
    audit_logger = AuditLogger(secret_resolver=managed.get_secret, clock=_fixed_clock)

    first_record = audit_logger.log_event(
        event_type="kill_switch_engaged",
        actor="ops",
        ip_address="203.0.113.5",
        details={"reason": "manual"},
    )

    secret_path.write_text("rotated-managed-secret", encoding="utf-8")
    managed.force_refresh()

    second_record = audit_logger.log_event(
        event_type="kill_switch_engaged",
        actor="ops",
        ip_address="203.0.113.5",
        details={"reason": "manual"},
    )

    assert audit_logger.verify(second_record) is True
    # After rotation the previous signature no longer validates with the new key.
    assert audit_logger.verify(first_record) is False
