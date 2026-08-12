# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Audit utilities shared across sandbox services."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from threading import Lock
from typing import Deque, Iterable

from .models import AuditEvent


class InMemoryAuditLog:
    """Thread-safe audit log with bounded history."""

    def __init__(self, capacity: int = 256) -> None:
        self._capacity = capacity
        self._events: Deque[AuditEvent] = deque(maxlen=capacity)
        self._lock = Lock()

    def record(self, event: AuditEvent) -> None:
        with self._lock:
            self._events.append(event)

    def snapshot(self) -> list[AuditEvent]:
        with self._lock:
            return list(self._events)

    def emit(
        self, source: str, category: str, message: str, payload: dict | None = None
    ) -> AuditEvent:
        event = AuditEvent(
            source=source,
            category=category,
            message=message,
            created_at=datetime.now(timezone.utc),
            payload=payload or {},
        )
        self.record(event)
        return event

    def extend(self, events: Iterable[AuditEvent]) -> None:
        for event in events:
            self.record(event)
