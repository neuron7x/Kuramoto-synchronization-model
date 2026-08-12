# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""High performance level 2 order book ingestion service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Protocol

from .consistency import ConsistencyError, ConsistencyValidator
from .metrics import MetricsRecorder
from .models import AppliedDiff, OrderBookDiff, OrderBookSnapshot, utc_now
from .state import OrderBookStateError, OrderBookStore


class SnapshotRequester(Protocol):
    """Abstraction to request fresh snapshots when recovery is needed."""

    def __call__(self, instrument: str, reason: str) -> None: ...


@dataclass(slots=True)
class IngestConfig:
    snapshot_interval: timedelta
    snapshot_depth: int | None
    max_snapshots: int = 32

    def __post_init__(self) -> None:
        if self.snapshot_interval <= timedelta(0):
            raise ValueError("snapshot interval must be positive")
        if self.snapshot_depth is not None and self.snapshot_depth <= 0:
            raise ValueError("snapshot depth must be positive")
        if self.max_snapshots <= 0:
            raise ValueError("max_snapshots must be positive")


class OrderBookIngestService:
    """Coordinates diff stream application, snapshots and recovery."""

    def __init__(
        self,
        *,
        config: IngestConfig,
        store: OrderBookStore | None = None,
        validator: ConsistencyValidator | None = None,
        metrics: MetricsRecorder | None = None,
        snapshot_requester: SnapshotRequester | None = None,
    ) -> None:
        self._config = config
        self._store = store or OrderBookStore(max_snapshots=config.max_snapshots)
        self._validator = validator or ConsistencyValidator()
        self._metrics = metrics
        self._snapshot_requester = snapshot_requester
        self._last_snapshot_event: Dict[str, datetime] = {}
        self._diff_since_snapshot: Dict[str, int] = {}

    def process_snapshot(self, snapshot: OrderBookSnapshot) -> None:
        self._validator.validate_snapshot(snapshot)
        state = self._store.for_instrument(snapshot.instrument)
        state.apply_snapshot(snapshot)
        self._last_snapshot_event[snapshot.instrument] = snapshot.ts_event
        self._diff_since_snapshot[snapshot.instrument] = 0
        if self._metrics:
            self._metrics.mark_snapshot(snapshot.instrument, snapshot.ts_event)
            freshness = utc_now() - snapshot.ts_event
            self._metrics.observe_freshness(snapshot.instrument, freshness)

    def process_diff(self, diff: OrderBookDiff) -> AppliedDiff | None:
        try:
            self._validator.validate_diff(diff)
        except ConsistencyError as exc:  # escalate as gap requiring snapshot
            if self._snapshot_requester:
                self._snapshot_requester(diff.instrument, f"consistency error: {exc}")
            raise

        state = self._store.for_instrument(diff.instrument)
        try:
            result = state.apply_diff(diff)
        except OrderBookStateError as exc:
            if self._metrics:
                self._metrics.increment_gap(diff.instrument)
            if self._snapshot_requester:
                self._snapshot_requester(diff.instrument, str(exc))
            raise

        if result is None:
            # diff arrived before baseline or is stale. Request snapshot if we never synced.
            if state.best_bid() is None and self._snapshot_requester:
                self._snapshot_requester(diff.instrument, "baseline missing")
            return None

        self._diff_since_snapshot[diff.instrument] = (
            self._diff_since_snapshot.get(diff.instrument, 0) + 1
        )
        latency = diff.ts_arrival - diff.ts_event
        now = utc_now()
        freshness = now - diff.ts_event
        if self._metrics:
            self._metrics.observe_latency(diff.instrument, latency)
            self._metrics.observe_freshness(diff.instrument, freshness)

        last_snapshot_event = self._last_snapshot_event.get(diff.instrument)
        due_snapshot = False
        if last_snapshot_event is None:
            due_snapshot = True
        else:
            if diff.ts_event - last_snapshot_event >= self._config.snapshot_interval:
                due_snapshot = True
        if not due_snapshot and self._diff_since_snapshot[diff.instrument] >= 1_000:
            # Safety fallback for extremely high throughput markets.
            due_snapshot = True

        if due_snapshot:
            # Request the full depth image so the periodic snapshot does not
            # truncate the in-memory book when it is re-applied.
            snapshot = state.get_snapshot()
            self.process_snapshot(snapshot)

        return result

    @property
    def store(self) -> OrderBookStore:
        return self._store
