"""Idempotency support for TradePulse HTTP APIs.

The online inference surface must provide strong idempotency guarantees for
all state-free POST endpoints. The :mod:`IdempotencyCache` implemented here
stores canonicalised response payloads keyed by the caller-provided
``Idempotency-Key`` header. Each cached record tracks the request payload
fingerprint so conflicting replays can be rejected deterministically.

The implementation is intentionally lightweight – a bounded in-memory cache
with asyncio-aware locking – because the upstream API gateway performs
retry-with-idempotency on transport failures only. Persisting the ledger in a
shared datastore was deemed unnecessary for this stateless workload. If the
requirements change, the interface below can be swapped for a distributed
backend without touching the handlers.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


class IdempotencyConflictError(RuntimeError):
    """Raised when attempting to overwrite an idempotency record with a new payload."""

    def __init__(self, key: str) -> None:
        super().__init__(f"Idempotency key '{key}' already used with a different payload.")
        self.key = key


@dataclass(slots=True)
class IdempotencyRecord:
    """Materialised response for an idempotent request."""

    key: str
    payload_hash: str
    body: dict[str, Any]
    status_code: int
    headers: dict[str, str]
    stored_at: datetime
    expires_at: datetime

    @property
    def expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at


@dataclass(slots=True)
class IdempotencySnapshot:
    """Observability snapshot for the idempotency cache."""

    entries: int
    ttl_seconds: int


class IdempotencyCache:
    """Async-safe, bounded TTL cache for idempotent responses."""

    def __init__(self, ttl_seconds: int = 900, max_entries: int = 4096) -> None:
        self._ttl = int(ttl_seconds)
        self._max_entries = int(max_entries)
        self._entries: dict[str, IdempotencyRecord] = {}
        self._lock = asyncio.Lock()

    @property
    def ttl_seconds(self) -> int:
        return self._ttl

    async def get(self, key: str) -> IdempotencyRecord | None:
        async with self._lock:
            record = self._entries.get(key)
            if record is None:
                return None
            if record.expired:
                self._entries.pop(key, None)
                return None
            return record

    async def set(
        self,
        *,
        key: str,
        payload_hash: str,
        body: dict[str, Any],
        status_code: int,
        headers: dict[str, str],
    ) -> IdempotencyRecord:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self._ttl)
        record = IdempotencyRecord(
            key=key,
            payload_hash=payload_hash,
            body=dict(body),
            status_code=status_code,
            headers=dict(headers),
            stored_at=datetime.now(timezone.utc),
            expires_at=expires_at,
        )
        async with self._lock:
            self._purge_locked()
            existing = self._entries.get(key)
            if existing is not None and existing.payload_hash != payload_hash:
                raise IdempotencyConflictError(key)
            if len(self._entries) >= self._max_entries:
                oldest_key = min(
                    self._entries, key=lambda name: self._entries[name].stored_at
                )
                self._entries.pop(oldest_key, None)
            self._entries[key] = record
        return record

    async def purge(self) -> None:
        async with self._lock:
            self._purge_locked()

    async def snapshot(self) -> IdempotencySnapshot:
        async with self._lock:
            self._purge_locked()
            return IdempotencySnapshot(entries=len(self._entries), ttl_seconds=self._ttl)

    def _purge_locked(self) -> None:
        expired = [name for name, record in self._entries.items() if record.expired]
        for name in expired:
            self._entries.pop(name, None)


__all__ = [
    "IdempotencyCache",
    "IdempotencyConflictError",
    "IdempotencyRecord",
    "IdempotencySnapshot",
]

