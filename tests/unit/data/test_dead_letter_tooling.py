# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.data.dead_letter import (
    DeadLetterItem,
    DeadLetterQueue,
    DeadLetterReason,
    DeadLetterReplayController,
)


class _ModelDumping:
    def __init__(self, value: int) -> None:
        self.value = value

    def model_dump(self) -> dict[str, int]:
        return {"value": self.value}


class _CustomObject:
    def __repr__(self) -> str:
        return "<custom>"


def test_queue_requires_positive_thresholds() -> None:
    with pytest.raises(ValueError):
        DeadLetterQueue(max_items=0)
    with pytest.raises(ValueError):
        DeadLetterQueue(toxicity_threshold=0)
    with pytest.raises(ValueError):
        DeadLetterQueue(unload_slo_seconds=0.0)


def test_queue_push_enriches_item() -> None:
    queue = DeadLetterQueue(max_items=2)
    item = queue.push(
        _ModelDumping(5),
        ValueError("boom"),
        context="snapshot",
        metadata={"origin": "unit"},
    )
    assert isinstance(item, DeadLetterItem)
    assert item.metadata == {"origin": "unit"}
    peeked = queue.peek()
    assert len(peeked) == 1
    assert isinstance(peeked[0], DeadLetterItem)
    assert peeked[0].payload == {"value": 5}
    assert peeked[0].reason == DeadLetterReason.VALIDATION_ERROR
    assert peeked[0].metadata["origin"] == "unit"
    analytics = queue.analytics()
    assert analytics["by_context"]["snapshot"] == 1


def test_queue_normalises_custom_objects() -> None:
    queue = DeadLetterQueue(max_items=2)
    queue.push(_CustomObject(), "error", context="stream")
    assert queue.peek()[0].payload == "<custom>"


def test_queue_identifies_toxic_payloads() -> None:
    queue = DeadLetterQueue(max_items=10, toxicity_threshold=2)
    queue.push({"id": 1}, "error", context="stream")
    toxic_item = queue.push({"id": 1}, "error", context="stream")
    toxic_entries = queue.identify_toxic_items()
    assert toxic_entries
    assert toxic_entries[0].id == toxic_item.id
    assert toxic_entries[0].toxic is True
    assert toxic_entries[0].reason == DeadLetterReason.TOXIC_PAYLOAD


def test_queue_acknowledge_and_audit() -> None:
    queue = DeadLetterQueue(max_items=2, audit_path=None)
    item = queue.push({"id": 1}, "error", context="ops")
    queue.acknowledge(item.id, operator="operator")
    assert queue.peek() == []
    audit = queue.audit_log()
    assert audit
    assert audit[-1]["action"] == "acknowledged"
    assert audit[-1]["operator"] == "operator"


def test_queue_mark_retry_increments_attempts() -> None:
    queue = DeadLetterQueue(max_items=2)
    item = queue.push({"id": 1}, "error", context="ops")
    updated = queue.mark_retry(item.id, operator="operator")
    assert updated is not None
    assert updated.attempts == 2


def test_queue_persist_includes_metadata(tmp_path: Path) -> None:
    queue = DeadLetterQueue(max_items=2)
    queue.push({"id": 1}, "error", context="persist", metadata={"a": 1})
    target = tmp_path / "dead_letters.json"
    queue.persist(target)
    saved = json.loads(target.read_text(encoding="utf-8"))
    assert len(saved) == 1
    record = saved[0]
    assert record["context"] == "persist"
    assert record["metadata"]["a"] == 1
    assert "payload_digest" in record


@pytest.mark.asyncio
async def test_replay_controller_replays_successfully() -> None:
    queue = DeadLetterQueue(max_items=4)
    first = queue.push({"id": 1}, "error", context="fetch")
    queue.push({"id": 2}, "error", context="fetch")

    processed: list[str] = []

    async def handler(item: DeadLetterItem) -> bool:
        processed.append(item.id)
        return True

    controller = DeadLetterReplayController(
        queue,
        handler,
        operator="tester",
        replay_limit=5,
    )
    results = await controller.replay()
    assert results["success"] == 2
    assert queue.peek() == []
    audit = queue.audit_log()
    assert {entry["action"] for entry in audit} >= {"replayed"}
    assert len(processed) == 2
    assert first.id in processed


@pytest.mark.asyncio
async def test_replay_controller_enforces_idempotency() -> None:
    queue = DeadLetterQueue(max_items=4, toxicity_threshold=3)
    queue.push({"id": 1}, "error", context="fetch")

    async def handler(_: DeadLetterItem) -> bool:
        return True

    controller = DeadLetterReplayController(
        queue,
        handler,
        operator="tester",
        replay_limit=5,
        idempotency_ttl=10.0,
    )

    await controller.replay()

    # Re-enqueue the same payload to trigger duplicate skip
    queue.push({"id": 1}, "error", context="fetch")
    results = await controller.replay()
    assert results["skipped"] == 1
    audit = queue.audit_log()
    assert any(entry["action"] == "replay_skipped_duplicate" for entry in audit)
