# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Metrics collection interfaces for order book ingestion."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from threading import RLock
from typing import Dict


class MetricsRecorder(ABC):
    """Abstract sink for ingest metrics."""

    @abstractmethod
    def observe_latency(self, instrument: str, latency: timedelta) -> None: ...

    @abstractmethod
    def observe_freshness(self, instrument: str, freshness: timedelta) -> None: ...

    @abstractmethod
    def increment_gap(self, instrument: str) -> None: ...

    @abstractmethod
    def mark_snapshot(self, instrument: str, ts_event: datetime) -> None: ...


@dataclass(slots=True)
class MetricsSample:
    latency_ms: float | None = None
    freshness_ms: float | None = None
    gap_events: int = 0
    last_snapshot_ts: datetime | None = None


class InMemoryMetricsRecorder(MetricsRecorder):
    """Thread-safe recorder keeping the last observation per instrument."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._samples: Dict[str, MetricsSample] = defaultdict(MetricsSample)

    def observe_latency(self, instrument: str, latency: timedelta) -> None:
        with self._lock:
            sample = self._samples[instrument]
            sample.latency_ms = latency.total_seconds() * 1_000

    def observe_freshness(self, instrument: str, freshness: timedelta) -> None:
        with self._lock:
            sample = self._samples[instrument]
            sample.freshness_ms = freshness.total_seconds() * 1_000

    def increment_gap(self, instrument: str) -> None:
        with self._lock:
            sample = self._samples[instrument]
            sample.gap_events += 1

    def mark_snapshot(self, instrument: str, ts_event: datetime) -> None:
        with self._lock:
            sample = self._samples[instrument]
            sample.last_snapshot_ts = ts_event

    def snapshot(self) -> Dict[str, MetricsSample]:
        with self._lock:
            return {
                instrument: MetricsSample(**asdict(sample))
                for instrument, sample in self._samples.items()
            }
