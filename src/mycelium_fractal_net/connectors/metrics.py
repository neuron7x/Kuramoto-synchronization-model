# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Observability metrics for MFN ingestion pipeline.

This module provides lightweight metrics collection for monitoring
the ingestion pipeline without requiring external dependencies like Prometheus.

Metrics can be exported to various backends or queried programmatically.

Example:
    >>> metrics = IngestionMetrics(source="rest_api")
    >>> metrics.record_event_received()
    >>> metrics.record_event_processed(latency_ms=15.5)
    >>> print(metrics.summary())
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

__all__ = ["IngestionMetrics", "MetricSnapshot"]

logger = logging.getLogger(__name__)


@dataclass
class MetricSnapshot:
    """Point-in-time snapshot of ingestion metrics.

    Attributes:
        timestamp: Snapshot time
        source: Source identifier
        events_received: Total events received
        events_processed: Successfully processed events
        events_failed: Failed event count
        events_dropped: Dropped events (queue overflow)
        normalization_errors: Normalization failures
        mapping_errors: Mapping failures
        backend_errors: Backend call failures
        total_latency_ms: Cumulative processing latency
        avg_latency_ms: Average latency per event
        queue_length: Current queue depth
        lag_seconds: Estimated processing lag
    """

    timestamp: datetime
    source: str
    events_received: int = 0
    events_processed: int = 0
    events_failed: int = 0
    events_dropped: int = 0
    normalization_errors: int = 0
    mapping_errors: int = 0
    backend_errors: int = 0
    total_latency_ms: float = 0.0
    avg_latency_ms: float = 0.0
    queue_length: int = 0
    lag_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "events_received": self.events_received,
            "events_processed": self.events_processed,
            "events_failed": self.events_failed,
            "events_dropped": self.events_dropped,
            "normalization_errors": self.normalization_errors,
            "mapping_errors": self.mapping_errors,
            "backend_errors": self.backend_errors,
            "total_latency_ms": round(self.total_latency_ms, 2),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "queue_length": self.queue_length,
            "lag_seconds": round(self.lag_seconds, 2),
        }


class IngestionMetrics:
    """Thread-safe metrics collector for ingestion pipeline.

    Provides counters, gauges, and timing metrics for monitoring
    the health and performance of the ingestion pipeline.

    All operations are thread-safe using a lock.

    Attributes:
        source: Source identifier for metrics
    """

    def __init__(self, source: str = "unknown") -> None:
        """Initialize metrics collector.

        Args:
            source: Source identifier for labeling metrics
        """
        self.source = source
        self._lock = threading.Lock()
        self._start_time = time.monotonic()

        # Counters
        self._events_received = 0
        self._events_processed = 0
        self._events_failed = 0
        self._events_dropped = 0
        self._normalization_errors = 0
        self._mapping_errors = 0
        self._backend_errors = 0

        # Timing
        self._total_latency_ms = 0.0
        self._last_event_time: float | None = None

        # Gauges
        self._queue_length = 0
        self._lag_seconds = 0.0

    def record_event_received(self) -> None:
        """Record an event received from source."""
        with self._lock:
            self._events_received += 1
            self._last_event_time = time.monotonic()

    def record_event_processed(self, latency_ms: float = 0.0) -> None:
        """Record a successfully processed event.

        Args:
            latency_ms: Processing latency in milliseconds
        """
        with self._lock:
            self._events_processed += 1
            self._total_latency_ms += latency_ms

    def record_event_failed(self) -> None:
        """Record a failed event."""
        with self._lock:
            self._events_failed += 1

    def record_event_dropped(self) -> None:
        """Record a dropped event (queue overflow)."""
        with self._lock:
            self._events_dropped += 1

    def record_normalization_error(self) -> None:
        """Record a normalization error."""
        with self._lock:
            self._normalization_errors += 1
            self._events_failed += 1

    def record_mapping_error(self) -> None:
        """Record a mapping error."""
        with self._lock:
            self._mapping_errors += 1
            self._events_failed += 1

    def record_backend_error(self) -> None:
        """Record a backend error."""
        with self._lock:
            self._backend_errors += 1
            self._events_failed += 1

    def update_queue_length(self, length: int) -> None:
        """Update current queue length gauge.

        Args:
            length: Current queue depth
        """
        with self._lock:
            self._queue_length = length

    def update_lag(self, lag_seconds: float) -> None:
        """Update processing lag gauge.

        Args:
            lag_seconds: Estimated lag in seconds
        """
        with self._lock:
            self._lag_seconds = lag_seconds

    def snapshot(self) -> MetricSnapshot:
        """Get current metrics snapshot.

        Returns:
            MetricSnapshot with current values
        """
        with self._lock:
            avg_latency = 0.0
            if self._events_processed > 0:
                avg_latency = self._total_latency_ms / self._events_processed

            return MetricSnapshot(
                timestamp=datetime.now(timezone.utc),
                source=self.source,
                events_received=self._events_received,
                events_processed=self._events_processed,
                events_failed=self._events_failed,
                events_dropped=self._events_dropped,
                normalization_errors=self._normalization_errors,
                mapping_errors=self._mapping_errors,
                backend_errors=self._backend_errors,
                total_latency_ms=self._total_latency_ms,
                avg_latency_ms=avg_latency,
                queue_length=self._queue_length,
                lag_seconds=self._lag_seconds,
            )

    def summary(self) -> str:
        """Get human-readable metrics summary.

        Returns:
            Formatted summary string
        """
        snap = self.snapshot()
        runtime = time.monotonic() - self._start_time

        lines = [
            f"=== Ingestion Metrics: {self.source} ===",
            f"Runtime: {runtime:.1f}s",
            f"Events received: {snap.events_received}",
            f"Events processed: {snap.events_processed}",
            f"Events failed: {snap.events_failed}",
            f"  - Normalization errors: {snap.normalization_errors}",
            f"  - Mapping errors: {snap.mapping_errors}",
            f"  - Backend errors: {snap.backend_errors}",
            f"Events dropped: {snap.events_dropped}",
            f"Avg latency: {snap.avg_latency_ms:.2f}ms",
            f"Queue length: {snap.queue_length}",
            f"Lag: {snap.lag_seconds:.2f}s",
        ]

        if snap.events_received > 0:
            success_rate = (snap.events_processed / snap.events_received) * 100
            lines.append(f"Success rate: {success_rate:.1f}%")

        if runtime > 0:
            throughput = snap.events_processed / runtime
            lines.append(f"Throughput: {throughput:.1f} events/sec")

        return "\n".join(lines)

    def reset(self) -> None:
        """Reset all metrics to zero."""
        with self._lock:
            self._start_time = time.monotonic()
            self._events_received = 0
            self._events_processed = 0
            self._events_failed = 0
            self._events_dropped = 0
            self._normalization_errors = 0
            self._mapping_errors = 0
            self._backend_errors = 0
            self._total_latency_ms = 0.0
            self._last_event_time = None
            self._queue_length = 0
            self._lag_seconds = 0.0

    def log_summary(self, level: int = logging.INFO) -> None:
        """Log metrics summary.

        Args:
            level: Logging level to use
        """
        logger.log(level, self.summary())

    # Properties for direct access

    @property
    def events_received(self) -> int:
        """Total events received."""
        with self._lock:
            return self._events_received

    @property
    def events_processed(self) -> int:
        """Successfully processed events."""
        with self._lock:
            return self._events_processed

    @property
    def events_failed(self) -> int:
        """Failed events."""
        with self._lock:
            return self._events_failed

    @property
    def success_rate(self) -> float:
        """Success rate as percentage."""
        with self._lock:
            if self._events_received == 0:
                return 100.0
            return (self._events_processed / self._events_received) * 100

    @property
    def avg_latency_ms(self) -> float:
        """Average processing latency in milliseconds."""
        with self._lock:
            if self._events_processed == 0:
                return 0.0
            return self._total_latency_ms / self._events_processed
