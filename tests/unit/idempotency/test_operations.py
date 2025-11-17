from __future__ import annotations

from dataclasses import dataclass

import pytest

from core.idempotency import (
    IdempotencyConflictError,
    IdempotencyCoordinator,
    IdempotencyInputError,
    IdempotencyKeyFactory,
    OperationStatus,
)


@dataclass
class ManualClock:
    value: float = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, delta: float) -> None:
        self.value += delta


@pytest.fixture()
def key_factory() -> IdempotencyKeyFactory:
    return IdempotencyKeyFactory()


def test_key_factory_generates_stable_ids(key_factory: IdempotencyKeyFactory) -> None:
    key_a = key_factory.build(
        service="orders",
        operation="submit",
        dedupe_fields={"client_order_id": "abc", "amount": 5},
    )
    key_b = key_factory.build(
        service="orders",
        operation="submit",
        dedupe_fields={"amount": 5, "client_order_id": "abc"},
    )
    assert key_a.request_id == key_b.request_id
    assert key_a.operation_id == key_b.operation_id
    assert key_a.fingerprint == key_b.fingerprint


def test_key_factory_attempt_changes_operation_id(
    key_factory: IdempotencyKeyFactory,
) -> None:
    base_key = key_factory.build(
        service="orders",
        operation="submit",
        dedupe_fields={"client_order_id": "abc"},
    )
    retry_key = key_factory.build(
        service="orders",
        operation="submit",
        dedupe_fields={"client_order_id": "abc"},
        attempt=1,
    )
    assert base_key.request_id == retry_key.request_id
    assert base_key.operation_id != retry_key.operation_id


def test_coordinator_records_successful_replay(
    key_factory: IdempotencyKeyFactory,
) -> None:
    clock = ManualClock()
    coordinator = IdempotencyCoordinator(
        ack_ttl_seconds=10.0, record_ttl_seconds=60.0, clock=clock
    )
    key = key_factory.build(
        service="orders", operation="submit", dedupe_fields={"id": 1}
    )

    initial = coordinator.register_attempt(key)
    assert initial.status is OperationStatus.PENDING
    assert initial.from_cache is False

    completed = coordinator.complete_success(key, {"status": "accepted"})
    assert completed.status is OperationStatus.SUCCEEDED
    assert completed.from_cache is False
    assert completed.acknowledged is True

    # Subsequent attempt returns cached result
    replay = coordinator.register_attempt(key)
    assert replay.status is OperationStatus.SUCCEEDED
    assert replay.from_cache is True
    assert replay.result == {"status": "accepted"}


def test_coordinator_detects_conflicting_payloads(
    key_factory: IdempotencyKeyFactory,
) -> None:
    coordinator = IdempotencyCoordinator()
    key = key_factory.build(
        service="orders", operation="submit", dedupe_fields={"id": 1}
    )
    coordinator.register_attempt(key)
    with pytest.raises(IdempotencyConflictError):
        coordinator.register_attempt(key, payload_fingerprint="different")


def test_coordinator_rejects_retry_after_failure(
    key_factory: IdempotencyKeyFactory,
) -> None:
    coordinator = IdempotencyCoordinator()
    key = key_factory.build(
        service="orders", operation="submit", dedupe_fields={"id": 1}
    )
    coordinator.register_attempt(key)
    coordinator.complete_failure(key, reason="insufficient_margin")
    with pytest.raises(IdempotencyInputError):
        coordinator.register_attempt(key)


def test_coordinator_preserves_success_after_failure_attempt(
    key_factory: IdempotencyKeyFactory,
) -> None:
    coordinator = IdempotencyCoordinator()
    key = key_factory.build(
        service="orders", operation="submit", dedupe_fields={"id": 1}
    )

    coordinator.register_attempt(key)
    succeeded = coordinator.complete_success(key, {"status": "accepted"})
    assert succeeded.status is OperationStatus.SUCCEEDED

    with pytest.raises(IdempotencyInputError):
        coordinator.complete_failure(key, reason="broker_error")

    replay = coordinator.register_attempt(key)
    assert replay.status is OperationStatus.SUCCEEDED
    assert replay.result == {"status": "accepted"}
    assert replay.from_cache is True


def test_acknowledgement_ttl_expires(key_factory: IdempotencyKeyFactory) -> None:
    clock = ManualClock()
    coordinator = IdempotencyCoordinator(
        ack_ttl_seconds=5.0, record_ttl_seconds=120.0, clock=clock
    )
    key = key_factory.build(
        service="orders", operation="submit", dedupe_fields={"id": 1}
    )
    coordinator.register_attempt(key)
    coordinator.complete_success(key, {"status": "ok"})

    metrics = coordinator.metrics()
    assert metrics["acknowledged_operations"] == 1

    clock.advance(6.0)
    metrics = coordinator.metrics()
    assert metrics["acknowledged_operations"] == 0


def test_commutative_aggregation(key_factory: IdempotencyKeyFactory) -> None:
    clock = ManualClock()
    coordinator = IdempotencyCoordinator(clock=clock)
    key = key_factory.build(
        service="positions", operation="sync", dedupe_fields={"id": 1}
    )

    coordinator.register_attempt(key)
    coordinator.complete_success(key, ["A", "B"])

    coordinator.register_attempt(key)

    merged = coordinator.complete_success(
        key,
        ["B", "A"],
        aggregator=lambda existing, incoming: sorted(
            set((existing or [])) | set(incoming or [])
        ),
    )
    assert merged.status is OperationStatus.SUCCEEDED
    assert merged.result == ["A", "B"]
    assert merged.from_cache is False


def test_audit_trail_records_events(key_factory: IdempotencyKeyFactory) -> None:
    coordinator = IdempotencyCoordinator()
    key = key_factory.build(
        service="orders", operation="submit", dedupe_fields={"id": 1}
    )
    coordinator.register_attempt(key, metadata={"attempt": 1})
    coordinator.complete_success(key, {"status": "ok"}, metadata={"broker": "demo"})
    trail = coordinator.get_audit_trail(key.operation_id)
    assert len(trail) >= 2
    assert trail[0].event == "registered"
    assert trail[-1].event == "succeeded"


def test_metrics_track_duplicates_and_collisions(
    key_factory: IdempotencyKeyFactory,
) -> None:
    coordinator = IdempotencyCoordinator()
    key = key_factory.build(
        service="orders", operation="submit", dedupe_fields={"id": 1}
    )
    coordinator.register_attempt(key)
    coordinator.complete_success(key, {"status": "ok"})
    coordinator.register_attempt(key)
    with pytest.raises(IdempotencyConflictError):
        coordinator.register_attempt(key, payload_fingerprint="different")
    metrics = coordinator.metrics()
    assert metrics["duplicates"] == 1
    assert metrics["collisions"] == 1
