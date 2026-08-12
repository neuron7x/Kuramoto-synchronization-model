# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Coordinate idempotent operations within the lifetime of a process.

The coordinator keeps idempotency metadata in memory, providing restart-
resilient behaviour only for as long as the hosting process stays alive.
Entries age out once their acknowledgement and record TTLs expire, keeping the
cache bounded and signalling how long results are considered replay-safe. To
obtain true exactly-once guarantees across restarts or multiple workers, back
this coordinator with durable external storage and replicate its purging
policy."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Deque, Dict, Generic, Mapping, TypeVar

from .keys import IdempotencyKey, fingerprint_payload

LOGGER = logging.getLogger(__name__)

T = TypeVar("T")
Aggregator = Callable[[T, T], T]


class IdempotencyError(RuntimeError):
    """Base class for idempotency coordination issues."""

    status_code: int = 500

    def __init__(self, message: str, *, detail: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.detail = dict(detail or {})


class IdempotencyConflictError(IdempotencyError):
    """Raised when the same idempotency key receives conflicting payloads."""

    status_code = 409


class IdempotencyInputError(IdempotencyError):
    """Raised when retries should be rejected as unprocessable."""

    status_code = 422


class OperationStatus(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(slots=True)
class OperationAuditEvent:
    timestamp: datetime
    event: str
    detail: Mapping[str, Any]


@dataclass(slots=True)
class OperationRecord(Generic[T]):
    key: IdempotencyKey
    payload_fingerprint: str
    status: OperationStatus = OperationStatus.PENDING
    result_digest: str | None = None
    result_value: T | None = None
    failure_reason: str | None = None
    first_seen_monotonic: float = field(default_factory=time.monotonic)
    last_seen_monotonic: float = field(default_factory=time.monotonic)
    first_seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ack_deadline: float | None = None
    duplicates: int = 0
    collisions: int = 0
    audit: Deque[OperationAuditEvent] = field(default_factory=deque)


@dataclass(slots=True)
class OperationOutcome(Generic[T]):
    status: OperationStatus
    result: T | None
    from_cache: bool
    request_id: str
    operation_id: str
    first_seen: datetime
    last_seen: datetime
    acknowledged: bool
    duplicates: int
    collisions: int


class IdempotencyCoordinator(Generic[T]):
    """Coordinate replay-safe execution and acknowledgement of operations."""

    def __init__(
        self,
        *,
        ack_ttl_seconds: float = 300.0,
        record_ttl_seconds: float = 3600.0,
        audit_capacity: int = 64,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if ack_ttl_seconds <= 0:
            raise ValueError("ack_ttl_seconds must be positive")
        if record_ttl_seconds <= 0:
            raise ValueError("record_ttl_seconds must be positive")
        if audit_capacity <= 0:
            raise ValueError("audit_capacity must be positive")
        self._ack_ttl = ack_ttl_seconds
        self._record_ttl = record_ttl_seconds
        self._audit_capacity = audit_capacity
        self._clock = clock or time.monotonic
        self._records: Dict[str, OperationRecord[Any]] = {}
        self._lock = threading.RLock()
        self._collisions = 0
        self._duplicates = 0

    def register_attempt(
        self,
        key: IdempotencyKey,
        *,
        payload_fingerprint: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> OperationOutcome[Any]:
        """Register an attempt and return the current operation outcome."""

        fingerprint = payload_fingerprint or key.fingerprint
        now = self._clock()
        timestamp = self._timestamp()
        with self._lock:
            self._purge_locked(now)
            record = self._records.get(key.operation_id)
            if record is None:
                record = OperationRecord(key=key, payload_fingerprint=fingerprint)
                record.first_seen_monotonic = now
                record.last_seen_monotonic = now
                record.first_seen_at = timestamp
                record.last_seen_at = timestamp
                self._records[key.operation_id] = record
                self._append_audit(record, "registered", metadata)
                return self._outcome(record, from_cache=False)
            record.last_seen_monotonic = now
            record.last_seen_at = timestamp
            if record.payload_fingerprint != fingerprint:
                record.collisions += 1
                self._collisions += 1
                self._append_audit(
                    record,
                    "collision",
                    {"expected": record.payload_fingerprint, "actual": fingerprint}
                    | dict(metadata or {}),
                )
                LOGGER.warning(
                    "Idempotency collision detected",
                    extra={"operation_id": key.operation_id, "service": key.service},
                )
                raise IdempotencyConflictError(
                    "Idempotency key collision detected.",
                    detail={
                        "operation_id": key.operation_id,
                        "request_id": key.request_id,
                    },
                )
            record.duplicates += 1
            self._duplicates += 1
            self._append_audit(record, "duplicate", metadata)
            if record.status is OperationStatus.FAILED:
                raise IdempotencyInputError(
                    record.failure_reason or "Previous attempt failed and cannot be retried.",
                    detail={
                        "operation_id": key.operation_id,
                        "request_id": key.request_id,
                    },
                )
            return self._outcome(record, from_cache=True)

    def complete_success(
        self,
        key: IdempotencyKey,
        result: T,
        *,
        effect_signature: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        aggregator: Aggregator[T] | None = None,
    ) -> OperationOutcome[T]:
        """Record a successful outcome, optionally aggregating commutative effects."""

        digest = effect_signature or fingerprint_payload(result)
        now = self._clock()
        timestamp = self._timestamp()
        with self._lock:
            record = self._ensure_record(key)
            if record.payload_fingerprint != key.fingerprint:
                record.collisions += 1
                self._collisions += 1
                self._append_audit(
                    record,
                    "collision",
                    {"expected": record.payload_fingerprint, "actual": key.fingerprint},
                )
                raise IdempotencyConflictError(
                    "Conflicting payload for operation.",
                    detail={
                        "operation_id": key.operation_id,
                        "request_id": key.request_id,
                    },
                )
            record.last_seen_monotonic = now
            record.last_seen_at = timestamp
            if record.status is OperationStatus.SUCCEEDED:
                if record.result_digest != digest:
                    if aggregator is not None:
                        merged = aggregator(record.result_value, result)  # type: ignore[arg-type]
                        record.result_value = merged
                        record.result_digest = fingerprint_payload(merged)
                        record.last_seen_monotonic = now
                        record.last_seen_at = timestamp
                        record.ack_deadline = now + self._ack_ttl
                        self._append_audit(record, "commuted", metadata)
                        return self._outcome(record, from_cache=False)
                    record.collisions += 1
                    self._collisions += 1
                    self._append_audit(record, "result_conflict", metadata)
                    raise IdempotencyConflictError(
                        "Conflicting result detected for idempotent operation.",
                        detail={
                            "operation_id": key.operation_id,
                            "request_id": key.request_id,
                        },
                    )
                self._append_audit(record, "replayed", metadata)
                return self._outcome(record, from_cache=True)
            if record.status is OperationStatus.FAILED:
                raise IdempotencyInputError(
                    "Cannot mark a failed operation as successful without remediation.",
                    detail={
                        "operation_id": key.operation_id,
                        "request_id": key.request_id,
                    },
                )
            record.status = OperationStatus.SUCCEEDED
            record.result_value = result
            record.result_digest = digest
            record.ack_deadline = now + self._ack_ttl
            self._append_audit(record, "succeeded", metadata)
            return self._outcome(record, from_cache=False)

    def complete_failure(
        self,
        key: IdempotencyKey,
        *,
        reason: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> OperationOutcome[None]:
        now = self._clock()
        timestamp = self._timestamp()
        with self._lock:
            record = self._ensure_record(key)
            record.last_seen_monotonic = now
            record.last_seen_at = timestamp
            if record.status is OperationStatus.SUCCEEDED:
                raise IdempotencyInputError(
                    "Cannot mark a successful operation as failed without remediation.",
                    detail={
                        "operation_id": key.operation_id,
                        "request_id": key.request_id,
                    },
                )
            record.status = OperationStatus.FAILED
            record.failure_reason = reason
            record.ack_deadline = None
            self._append_audit(record, "failed", metadata)
            return self._outcome(record, from_cache=False)

    def acknowledge(self, operation_id: str) -> bool:
        """Extend the acknowledgement TTL for a successful operation."""

        now = self._clock()
        with self._lock:
            record = self._records.get(operation_id)
            if record is None or record.status is not OperationStatus.SUCCEEDED:
                return False
            record.ack_deadline = now + self._ack_ttl
            record.last_seen_monotonic = now
            record.last_seen_at = self._timestamp()
            self._append_audit(record, "acknowledged", None)
            return True

    def get_audit_trail(self, operation_id: str) -> tuple[OperationAuditEvent, ...]:
        with self._lock:
            record = self._records.get(operation_id)
            if record is None:
                return ()
            return tuple(record.audit)

    def metrics(self) -> Mapping[str, int]:
        with self._lock:
            now = self._clock()
            acknowledged = sum(
                1 for record in self._records.values() if self._ack_active(record, now)
            )
            return {
                "active_operations": len(self._records),
                "acknowledged_operations": acknowledged,
                "collisions": self._collisions,
                "duplicates": self._duplicates,
            }

    def purge(self) -> None:
        with self._lock:
            self._purge_locked(self._clock())

    def _ensure_record(self, key: IdempotencyKey) -> OperationRecord[Any]:
        record = self._records.get(key.operation_id)
        if record is None:
            raise IdempotencyError(
                "Operation must be registered before completion.",
                detail={"operation_id": key.operation_id, "request_id": key.request_id},
            )
        return record

    def _outcome(
        self,
        record: OperationRecord[Any],
        *,
        from_cache: bool,
    ) -> OperationOutcome[Any]:
        acknowledged = self._ack_active(record, self._clock())
        return OperationOutcome(
            status=record.status,
            result=record.result_value,
            from_cache=from_cache,
            request_id=record.key.request_id,
            operation_id=record.key.operation_id,
            first_seen=record.first_seen_at,
            last_seen=record.last_seen_at,
            acknowledged=acknowledged,
            duplicates=record.duplicates,
            collisions=record.collisions,
        )

    def _append_audit(
        self,
        record: OperationRecord[Any],
        event: str,
        metadata: Mapping[str, Any] | None,
    ) -> None:
        detail = dict(metadata or {})
        record.audit.append(
            OperationAuditEvent(timestamp=self._timestamp(), event=event, detail=detail)
        )
        while len(record.audit) > self._audit_capacity:
            record.audit.popleft()

    def _ack_active(self, record: OperationRecord[Any], now: float) -> bool:
        return record.ack_deadline is not None and record.ack_deadline >= now

    def _purge_locked(self, now: float) -> None:
        cutoff = now - self._record_ttl
        expired = [
            op_id for op_id, record in self._records.items() if record.last_seen_monotonic < cutoff
        ]
        for op_id in expired:
            del self._records[op_id]

    def _timestamp(self) -> datetime:
        return datetime.now(timezone.utc)


__all__ = [
    "IdempotencyCoordinator",
    "IdempotencyError",
    "IdempotencyConflictError",
    "IdempotencyInputError",
    "OperationAuditEvent",
    "OperationOutcome",
    "OperationStatus",
]
