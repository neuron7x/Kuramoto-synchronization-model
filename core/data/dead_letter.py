# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Dead-letter queue management and replay tooling for ingestion pipelines."""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import Any, Awaitable, Callable, Deque, Dict, Iterable, Optional
from uuid import uuid4

from core.data.adapters.base import RetryConfig
from core.utils.logging import get_logger

logger = get_logger(__name__)

AuditRecord = Dict[str, Any]


class DeadLetterReason(str, Enum):
    """Categorisation for dead-lettered payloads."""

    VALIDATION_ERROR = "validation_error"
    SCHEMA_MISMATCH = "schema_mismatch"
    TRANSIENT_FAILURE = "transient_failure"
    DOWNSTREAM_TIMEOUT = "downstream_timeout"
    TOXIC_PAYLOAD = "toxic_payload"
    UNKNOWN = "unknown"


@dataclass(slots=True, frozen=True)
class DeadLetterItem:
    """Record captured when payload processing fails."""

    id: str
    payload: Any
    error: str
    context: str
    timestamp: float
    reason: DeadLetterReason
    attempts: int
    payload_digest: str
    toxic: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def asdict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation of the item."""

        return {
            "id": self.id,
            "payload": self.payload,
            "error": self.error,
            "context": self.context,
            "timestamp": self.timestamp,
            "reason": self.reason.value,
            "attempts": self.attempts,
            "payload_digest": self.payload_digest,
            "toxic": self.toxic,
            "metadata": self.metadata,
        }


class DeadLetterQueue:
    """In-memory bounded dead-letter queue retaining the latest failures."""

    def __init__(
        self,
        max_items: int = 1024,
        *,
        persistent_path: str | os.PathLike[str] | None = None,
        audit_path: str | os.PathLike[str] | None = None,
        toxicity_threshold: int = 5,
        unload_slo_seconds: float = 5.0,
    ) -> None:
        if max_items <= 0:
            raise ValueError("max_items must be positive")
        if toxicity_threshold <= 0:
            raise ValueError("toxicity_threshold must be positive")
        if unload_slo_seconds <= 0:
            raise ValueError("unload_slo_seconds must be positive")

        self._items: Deque[DeadLetterItem] = deque(maxlen=max_items)
        self._max_items = max_items
        self._persistent_path = (
            Path(persistent_path) if persistent_path is not None else None
        )
        self._audit_path = Path(audit_path) if audit_path is not None else None
        self._toxicity_threshold = toxicity_threshold
        self._failure_counts: Counter[str] = Counter()
        self._analytics_by_reason: Counter[str] = Counter()
        self._analytics_by_context: Counter[str] = Counter()
        self._unload_slo_seconds = unload_slo_seconds
        self._audit_log: list[AuditRecord] = []
        self._lock = Lock()

        if self._persistent_path is not None:
            self._persistent_path.parent.mkdir(parents=True, exist_ok=True)
        if self._audit_path is not None:
            self._audit_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Queue operations
    # ------------------------------------------------------------------
    def push(
        self,
        payload: Any,
        error: Exception | str,
        *,
        context: str,
        reason: DeadLetterReason | str | None = None,
        metadata: Optional[dict[str, Any]] = None,
        attempts: int = 1,
    ) -> DeadLetterItem:
        """Append a new item to the queue with analytical enrichments."""

        metadata = dict(metadata or {})
        message = str(error)
        normalised_payload = self._normalise_payload(payload)
        digest = self._compute_digest(normalised_payload)

        detected_reason = self._resolve_reason(reason, error)

        self._failure_counts[digest] += 1
        toxic = self._failure_counts[digest] >= self._toxicity_threshold
        if toxic:
            detected_reason = DeadLetterReason.TOXIC_PAYLOAD

        item = DeadLetterItem(
            id=str(uuid4()),
            payload=normalised_payload,
            error=message,
            context=context,
            timestamp=time.time(),
            reason=detected_reason,
            attempts=max(1, attempts),
            payload_digest=digest,
            toxic=toxic,
            metadata=metadata,
        )

        with self._lock:
            self._items.append(item)
        self._analytics_by_reason[detected_reason.value] += 1
        self._analytics_by_context[context] += 1
        self._persist_item(item)

        if toxic:
            logger.error(
                "dead_letter_toxic_detected",
                digest=digest,
                context=context,
                error=message,
            )
        else:
            logger.debug(
                "dead_letter_enqueued",
                size=len(self._items),
                context=context,
                reason=detected_reason.value,
            )
        return item

    def drain(self) -> list[DeadLetterItem]:
        with self._lock:
            items = list(self._items)
            self._items.clear()
        return items

    def peek(self) -> list[DeadLetterItem]:
        with self._lock:
            return list(self._items)

    def acknowledge(
        self,
        item_id: str,
        *,
        operator: str,
        notes: str | None = None,
        outcome: str = "acknowledged",
    ) -> DeadLetterItem | None:
        """Remove an item after successful handling and audit the action."""

        with self._lock:
            snapshot = list(self._items)
            remaining = [item for item in snapshot if item.id != item_id]
            removed_items = [item for item in snapshot if item.id == item_id]
            self._items = deque(remaining, maxlen=self._max_items)

        item = removed_items[0] if removed_items else None
        if item is not None:
            self._record_audit(
                action=outcome,
                operator=operator,
                item=item,
                notes=notes,
            )
        return item

    def mark_retry(
        self,
        item_id: str,
        *,
        operator: str,
        notes: str | None = None,
    ) -> DeadLetterItem | None:
        """Increment attempt metadata and audit a retry decision."""

        with self._lock:
            updated: list[DeadLetterItem] = []
            target: DeadLetterItem | None = None
            for existing in self._items:
                if existing.id == item_id:
                    target = DeadLetterItem(
                        id=existing.id,
                        payload=existing.payload,
                        error=existing.error,
                        context=existing.context,
                        timestamp=existing.timestamp,
                        reason=existing.reason,
                        attempts=existing.attempts + 1,
                        payload_digest=existing.payload_digest,
                        toxic=existing.toxic,
                        metadata=existing.metadata,
                    )
                    updated.append(target)
                else:
                    updated.append(existing)
            self._items = deque(updated, maxlen=self._max_items)

        if target is not None:
            self._record_audit(
                action="retry_marked",
                operator=operator,
                item=target,
                notes=notes,
            )
        return target

    def __len__(self) -> int:  # pragma: no cover - trivial accessor
        with self._lock:
            return len(self._items)

    @property
    def max_items(self) -> int:  # pragma: no cover - trivial accessor
        return self._max_items

    # ------------------------------------------------------------------
    # Persistence & analytics
    # ------------------------------------------------------------------
    def persist(
        self,
        path: str | os.PathLike[str] | None = None,
        *,
        drain: bool = False,
    ) -> Path:
        """Persist the queue content to ``path`` for operational triage."""

        target = Path(path) if path is not None else self._persistent_path
        if target is None:
            raise ValueError("No persistence path configured for dead-letter queue")

        start = time.perf_counter()
        with self._lock:
            if drain:
                items = list(self._items)
                self._items.clear()
            else:
                items = list(self._items)
            payload = [item.asdict() for item in items]

            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")

        duration = time.perf_counter() - start
        if duration > self._unload_slo_seconds:
            logger.warning(
                "dead_letter_persist_slo_breach",
                duration=duration,
                slo=self._unload_slo_seconds,
                destination=str(target),
            )
        else:
            logger.debug(
                "dead_letter_persisted",
                duration=duration,
                destination=str(target),
            )

        return target

    def analytics(self) -> dict[str, Any]:
        """Return aggregate failure analytics for observability."""

        return {
            "by_reason": dict(self._analytics_by_reason),
            "by_context": dict(self._analytics_by_context),
            "total_unique_failures": len(self._failure_counts),
            "toxicity_threshold": self._toxicity_threshold,
        }

    def identify_toxic_items(self) -> list[DeadLetterItem]:
        """Return a snapshot of items flagged as toxic."""

        return [item for item in self.peek() if item.toxic]

    def audit_log(self) -> list[AuditRecord]:
        """Return a copy of the audit log."""

        return list(self._audit_log)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _persist_item(self, item: DeadLetterItem) -> None:
        if self._persistent_path is None:
            return
        record = json.dumps(item.asdict(), sort_keys=True)
        with self._lock:
            with self._persistent_path.open("a", encoding="utf-8") as handle:
                handle.write(record)
                handle.write("\n")

    def _record_audit(
        self,
        *,
        action: str,
        operator: str,
        item: DeadLetterItem,
        notes: str | None = None,
    ) -> None:
        entry: AuditRecord = {
            "action": action,
            "operator": operator,
            "item_id": item.id,
            "context": item.context,
            "reason": item.reason.value,
            "timestamp": time.time(),
        }
        if notes:
            entry["notes"] = notes

        self._audit_log.append(entry)
        if self._audit_path is not None:
            with self._audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, sort_keys=True))
                handle.write("\n")

    @staticmethod
    def _normalise_payload(payload: Any) -> Any:
        if hasattr(payload, "model_dump"):
            try:
                return payload.model_dump()
            except Exception:  # pragma: no cover - defensive guard
                return repr(payload)
        if isinstance(payload, (dict, list, tuple, str, int, float, type(None))):
            return payload
        return repr(payload)

    @staticmethod
    def _compute_digest(payload: Any) -> str:
        try:
            encoded = json.dumps(payload, sort_keys=True, default=str)
        except TypeError:
            encoded = repr(payload)
        return sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _resolve_reason(
        reason: DeadLetterReason | str | None,
        error: Exception | str,
    ) -> DeadLetterReason:
        if isinstance(reason, DeadLetterReason):
            return reason
        if isinstance(reason, str):
            try:
                return DeadLetterReason(reason)
            except ValueError:
                logger.debug("dead_letter_unknown_reason", provided=reason)
        if isinstance(error, (ValueError, KeyError)):
            return DeadLetterReason.VALIDATION_ERROR
        if isinstance(error, (asyncio.TimeoutError, TimeoutError)):
            return DeadLetterReason.DOWNSTREAM_TIMEOUT
        if isinstance(error, (ConnectionError, OSError)):
            return DeadLetterReason.TRANSIENT_FAILURE
        return DeadLetterReason.UNKNOWN


class DeadLetterReplayController:
    """Governed replay orchestration with exponential backoff and audit."""

    def __init__(
        self,
        queue: DeadLetterQueue,
        handler: Callable[[DeadLetterItem], Awaitable[bool | None]],
        *,
        operator: str = "system",
        replay_limit: int = 50,
        idempotency_ttl: float = 600.0,
        retry: Optional[RetryConfig] = None,
    ) -> None:
        if replay_limit <= 0:
            raise ValueError("replay_limit must be positive")
        if idempotency_ttl <= 0:
            raise ValueError("idempotency_ttl must be positive")

        self._queue = queue
        self._handler = handler
        self._operator = operator
        self._replay_limit = replay_limit
        self._idempotency_ttl = idempotency_ttl
        self._retry = retry or RetryConfig(attempts=3, multiplier=0.5, max_backoff=10.0)
        self._recent_replays: dict[str, float] = {}
        self._lock = Lock()

    async def replay(
        self,
        *,
        reason_filter: DeadLetterReason | None = None,
        toxic_only: bool = False,
    ) -> dict[str, int]:
        """Replay queued items honoring governance constraints."""

        candidates = self._select_candidates(
            self._queue.peek(), reason_filter=reason_filter, toxic_only=toxic_only
        )
        results = Counter(success=0, failed=0, skipped=0)

        for item in candidates:
            if self._is_duplicate(item):
                results["skipped"] += 1
                self._queue._record_audit(  # pylint: disable=protected-access
                    action="replay_skipped_duplicate",
                    operator=self._operator,
                    item=item,
                    notes="digest in idempotency window",
                )
                continue

            success = await self._process_with_retry(item)
            if success:
                self._register_replay(item)
                self._queue.acknowledge(
                    item.id,
                    operator=self._operator,
                    notes="replayed successfully",
                    outcome="replayed",
                )
                results["success"] += 1
            else:
                self._queue.mark_retry(
                    item.id,
                    operator=self._operator,
                    notes="replay failed",
                )
                results["failed"] += 1

        return dict(results)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _select_candidates(
        self,
        items: Iterable[DeadLetterItem],
        *,
        reason_filter: DeadLetterReason | None,
        toxic_only: bool,
    ) -> list[DeadLetterItem]:
        selected: list[DeadLetterItem] = []
        for item in items:
            if len(selected) >= self._replay_limit:
                break
            if reason_filter is not None and item.reason != reason_filter:
                continue
            if toxic_only and not item.toxic:
                continue
            selected.append(item)
        return selected

    def _is_duplicate(self, item: DeadLetterItem) -> bool:
        now = time.monotonic()
        with self._lock:
            self._recent_replays = {
                digest: ts
                for digest, ts in self._recent_replays.items()
                if now - ts < self._idempotency_ttl
            }
            ts = self._recent_replays.get(item.payload_digest)
            return ts is not None

    def _register_replay(self, item: DeadLetterItem) -> None:
        with self._lock:
            self._recent_replays[item.payload_digest] = time.monotonic()

    async def _process_with_retry(self, item: DeadLetterItem) -> bool:
        attempt = 0
        while attempt < self._retry.attempts:
            attempt += 1
            try:
                should_ack = await self._handler(item)
            except Exception as exc:  # pragma: no cover - exercised in tests
                logger.warning(
                    "dead_letter_replay_error",
                    item_id=item.id,
                    digest=item.payload_digest,
                    attempt=attempt,
                    error=str(exc),
                )
                if attempt >= self._retry.attempts:
                    return False
                delay = self._retry.compute_backoff(attempt)
                await asyncio.sleep(delay)
                continue

            if should_ack is False:
                return False
            return True
        return False


__all__ = [
    "DeadLetterItem",
    "DeadLetterQueue",
    "DeadLetterReason",
    "DeadLetterReplayController",
]
