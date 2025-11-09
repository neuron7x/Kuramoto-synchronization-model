"""Idempotency primitives for ensuring at-least-once delivery semantics."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Deque, Dict


@dataclass
class IdempotencyRecord:
    event_id: str
    timestamp: float


class EventIdempotencyStore:
    """Interface for tracking processed event identifiers."""

    def was_processed(self, event_id: str) -> bool:
        raise NotImplementedError

    def mark_processed(self, event_id: str) -> None:
        raise NotImplementedError

    def purge(self, ttl_seconds: int | None = None) -> None:
        raise NotImplementedError


class InMemoryEventIdempotencyStore(EventIdempotencyStore):
    """Thread-safe in-memory idempotency store with optional TTL eviction."""

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._records: Dict[str, IdempotencyRecord] = {}
        self._order: Deque[IdempotencyRecord] = deque()

    def was_processed(self, event_id: str) -> bool:
        with self._lock:
            record = self._records.get(event_id)
            if record is None:
                return False
            if self._ttl_seconds and time.time() - record.timestamp > self._ttl_seconds:
                # Expired entries are removed lazily
                self._delete_locked(event_id)
                return False
            return True

    def mark_processed(self, event_id: str) -> None:
        now = time.time()
        with self._lock:
            record = self._records.get(event_id)
            if record is None:
                record = IdempotencyRecord(event_id=event_id, timestamp=now)
                self._records[event_id] = record
            else:
                try:
                    self._order.remove(record)
                except ValueError:
                    # Record might already have been evicted from the deque.
                    pass
                record.timestamp = now
            self._order.append(record)
            self._evict_locked(now)

    def purge(self, ttl_seconds: int | None = None) -> None:
        with self._lock:
            effective_ttl = self._ttl_seconds if ttl_seconds is None else ttl_seconds
            expiry = time.time() - effective_ttl if effective_ttl is not None else None
            self._evict_locked(expiry_reference=expiry)

    def _evict_locked(
        self, reference_time: float | None = None, expiry_reference: float | None = None
    ) -> None:
        """Evict stale entries while holding the lock."""

        if reference_time is None:
            reference_time = time.time()
        ttl = self._ttl_seconds
        while self._order:
            record = self._order[0]
            expired = False
            if expiry_reference is not None:
                expired = record.timestamp < expiry_reference
            elif ttl:
                expired = reference_time - record.timestamp > ttl
            if not expired:
                break
            self._order.popleft()
            current = self._records.get(record.event_id)
            if current is record or (
                current is not None and current.timestamp == record.timestamp
            ):
                self._records.pop(record.event_id, None)

    def _delete_locked(self, event_id: str) -> None:
        self._records.pop(event_id, None)
        # Defer deque cleanup to eviction to keep complexity amortised.


def current_timestamp() -> datetime:
    return datetime.now(timezone.utc)
