# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import httpx
import pytest

from src.audit import (
    AuditIntegrityError,
    AuditLedgerEntry,
    AuditLogger,
    AuditRecord,
    JsonLinesAuditStore,
    SiemAuditSink,
)


def _fixed_clock():
    from datetime import datetime, timezone

    return datetime(2024, 12, 31, 23, 59, tzinfo=timezone.utc)


def _make_record() -> AuditRecord:
    logger = AuditLogger(secret="integration-secret", clock=_fixed_clock)
    return logger.log_event(
        event_type="remote_admin_test",
        actor="integration",
        ip_address="198.51.100.10",
        details={"action": "toggle", "token": "secret"},
    )


def test_audit_logger_persists_signed_records(tmp_path: Path) -> None:
    store_path = tmp_path / "audit.jsonl"
    store = JsonLinesAuditStore(store_path)
    logger = AuditLogger(secret="integration-secret", store=store, clock=_fixed_clock)

    record = logger.log_event(
        event_type="kill_switch_engaged",
        actor="ops",
        ip_address="203.0.113.5",
        details={"reason": "manual"},
    )

    contents = store_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(contents) == 1
    persisted = json.loads(contents[0])
    assert persisted["record"]["signature"] == record.signature

    restored = AuditRecord.model_validate(persisted["record"])
    assert logger.verify(restored) is True
    assert store.verify_integrity(verifier=logger.verify)


def test_json_lines_store_replays_ordered_entries(tmp_path: Path) -> None:
    store_path = tmp_path / "audit.jsonl"
    store = JsonLinesAuditStore(store_path)
    logger = AuditLogger(secret="integration-secret", store=store, clock=_fixed_clock)

    records: list[AuditRecord] = []
    for event in ("engaged", "confirmed", "reset"):
        records.append(
            logger.log_event(
                event_type=f"kill_switch_{event}",
                actor="ops",
                ip_address="203.0.113.5",
                details={"reason": event},
            )
        )

    replayed: list[AuditLedgerEntry] = list(store.replay(verifier=logger.verify))
    assert [entry.sequence for entry in replayed] == [0, 1, 2]
    assert [entry.record.signature for entry in replayed] == [
        record.signature for record in records
    ]
    # Ensure chain hashes link entries together.
    assert replayed[1].chain_hash != replayed[0].chain_hash
    assert replayed[2].chain_hash != replayed[1].chain_hash


def test_json_lines_store_detects_tampering(tmp_path: Path) -> None:
    store_path = tmp_path / "audit.jsonl"
    store = JsonLinesAuditStore(store_path)
    logger = AuditLogger(secret="integration-secret", store=store, clock=_fixed_clock)

    logger.log_event(
        event_type="kill_switch_engaged",
        actor="ops",
        ip_address="203.0.113.5",
        details={"reason": "manual"},
    )

    # Corrupt the stored payload by changing the actor.
    envelope = json.loads(store_path.read_text(encoding="utf-8"))
    envelope["record"]["actor"] = "intruder"
    store_path.write_text(json.dumps(envelope), encoding="utf-8")

    assert store.verify_integrity(verifier=logger.verify) is False
    with pytest.raises(AuditIntegrityError):
        list(store.replay(verifier=logger.verify))


def test_siem_sink_retries_until_success(tmp_path: Path) -> None:
    attempts = 0
    received: list[dict[str, object]] = []
    completed = threading.Event()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise httpx.ReadTimeout("timeout", request=request)
        payload = json.loads(request.content.decode("utf-8"))
        received.append(payload)
        completed.set()
        return httpx.Response(202)

    client = httpx.Client(
        base_url="https://siem.example.com", transport=httpx.MockTransport(handler)
    )
    sink = SiemAuditSink(
        "/ingest",
        tmp_path / "spool",
        http_client=client,
        base_backoff_seconds=0.01,
        max_backoff_seconds=0.05,
    )
    try:
        sink(_make_record())
        assert completed.wait(timeout=2.0)
        assert attempts == 2
        assert received[0]["event_type"] == "remote_admin_test"
        assert not list((tmp_path / "spool").glob("*.json"))
    finally:
        sink.close()
        client.close()


def test_siem_sink_moves_to_dead_letter_after_retries(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("downstream unavailable", request=request)

    client = httpx.Client(
        base_url="https://siem.example.com", transport=httpx.MockTransport(handler)
    )
    sink = SiemAuditSink(
        "/ingest",
        tmp_path / "spool",
        http_client=client,
        max_retries=1,
        base_backoff_seconds=0.01,
        max_backoff_seconds=0.05,
    )
    try:
        sink(_make_record())
        deadline = time.time() + 2.0
        dead_letter_dir = tmp_path / "spool" / "dead-letter"
        while time.time() < deadline and not list(dead_letter_dir.glob("*.json")):
            time.sleep(0.05)
        files = list(dead_letter_dir.glob("*.json"))
        assert files, "expected record to be moved to dead-letter queue"
        contents = json.loads(files[0].read_text(encoding="utf-8"))
        assert contents["attempts"] >= 2
    finally:
        sink.close()
        client.close()
