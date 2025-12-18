# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Vendor-agnostic telemetry interface for TradePulse.

This module provides a telemetry abstraction that supports multiple
backends (Prometheus, StatsD, OpenTelemetry, etc.) without vendor lock-in.
It includes sampling rules for controlling overhead in production.

Key features:
    - Protocol-based interface for metric collection
    - Sampling support to reduce always-on overhead
    - Timer context manager for latency measurement
    - No vendor lock-in (wraps existing backends)
"""

from __future__ import annotations

import logging
import random
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterator, Mapping, Protocol, runtime_checkable

LOGGER = logging.getLogger(__name__)


class MetricType(Enum):
    """Types of metrics supported by the telemetry interface."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass(frozen=True, slots=True)
class SamplingConfig:
    """Configuration for metric sampling.

    Attributes:
        default_rate: Default sampling rate (0.0-1.0, 1.0 = always sample)
        per_metric_rates: Override rates for specific metrics
        seed: Random seed for deterministic sampling in tests
    """

    default_rate: float = 1.0
    per_metric_rates: Mapping[str, float] = field(default_factory=dict)
    seed: int | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.default_rate <= 1.0:
            raise ValueError(f"default_rate must be 0.0-1.0, got {self.default_rate}")
        for name, rate in self.per_metric_rates.items():
            if not 0.0 <= rate <= 1.0:
                raise ValueError(f"Rate for {name} must be 0.0-1.0, got {rate}")

    def get_rate(self, metric_name: str) -> float:
        """Get the sampling rate for a specific metric."""
        return self.per_metric_rates.get(metric_name, self.default_rate)


class Sampler:
    """Implements sampling logic for metrics.

    Supports deterministic sampling when a seed is provided.
    """

    def __init__(self, config: SamplingConfig | None = None) -> None:
        self._config = config or SamplingConfig()
        self._rng = random.Random(self._config.seed)

    def should_sample(self, metric_name: str) -> bool:
        """Determine if a metric should be sampled.

        Args:
            metric_name: Name of the metric

        Returns:
            True if the metric should be recorded
        """
        rate = self._config.get_rate(metric_name)
        if rate >= 1.0:
            return True
        if rate <= 0.0:
            return False
        return self._rng.random() < rate


@runtime_checkable
class MetricsBackend(Protocol):
    """Protocol for metrics backend implementations.

    Backends handle the actual metric recording and export.
    """

    def increment_counter(
        self,
        name: str,
        value: float = 1.0,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Increment a counter metric.

        Args:
            name: Metric name
            value: Amount to increment by
            tags: Optional metric tags/labels
        """
        ...

    def set_gauge(
        self,
        name: str,
        value: float,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Set a gauge metric value.

        Args:
            name: Metric name
            value: Value to set
            tags: Optional metric tags/labels
        """
        ...

    def observe_histogram(
        self,
        name: str,
        value: float,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Record a value in a histogram.

        Args:
            name: Metric name
            value: Value to record
            tags: Optional metric tags/labels
        """
        ...


class NoOpBackend:
    """No-operation backend for when metrics are disabled."""

    def increment_counter(
        self,
        name: str,
        value: float = 1.0,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """No-op counter increment."""

    def set_gauge(
        self,
        name: str,
        value: float,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """No-op gauge set."""

    def observe_histogram(
        self,
        name: str,
        value: float,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """No-op histogram observation."""


class PrometheusBackend:
    """Backend that wraps core.utils.metrics.MetricsCollector for Prometheus."""

    def __init__(self, registry: Any = None) -> None:
        """Initialize with optional Prometheus registry.

        Args:
            registry: Prometheus registry (uses default if None)
        """
        self._registry = registry
        self._counters: dict[str, Any] = {}
        self._gauges: dict[str, Any] = {}
        self._histograms: dict[str, Any] = {}
        self._prometheus_available = self._check_prometheus()

    def _check_prometheus(self) -> bool:
        """Check if Prometheus client is available."""
        try:
            from prometheus_client import Counter, Gauge, Histogram  # noqa: F401

            return True
        except ImportError:
            LOGGER.warning("prometheus_client not installed, metrics disabled")
            return False

    def _get_or_create_counter(
        self, name: str, tags: Mapping[str, str] | None
    ) -> Any:
        """Get or create a counter metric."""
        if not self._prometheus_available:
            return None

        from prometheus_client import Counter

        label_names = tuple(sorted(tags.keys())) if tags else ()
        key = (name, label_names)

        if key not in self._counters:
            self._counters[key] = Counter(
                name.replace(".", "_"),
                f"Counter: {name}",
                labelnames=label_names,
                registry=self._registry,
            )
        return self._counters[key]

    def _get_or_create_gauge(
        self, name: str, tags: Mapping[str, str] | None
    ) -> Any:
        """Get or create a gauge metric."""
        if not self._prometheus_available:
            return None

        from prometheus_client import Gauge

        label_names = tuple(sorted(tags.keys())) if tags else ()
        key = (name, label_names)

        if key not in self._gauges:
            self._gauges[key] = Gauge(
                name.replace(".", "_"),
                f"Gauge: {name}",
                labelnames=label_names,
                registry=self._registry,
            )
        return self._gauges[key]

    def _get_or_create_histogram(
        self, name: str, tags: Mapping[str, str] | None
    ) -> Any:
        """Get or create a histogram metric."""
        if not self._prometheus_available:
            return None

        from prometheus_client import Histogram

        label_names = tuple(sorted(tags.keys())) if tags else ()
        key = (name, label_names)

        if key not in self._histograms:
            self._histograms[key] = Histogram(
                name.replace(".", "_"),
                f"Histogram: {name}",
                labelnames=label_names,
                registry=self._registry,
            )
        return self._histograms[key]

    def increment_counter(
        self,
        name: str,
        value: float = 1.0,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Increment a Prometheus counter."""
        counter = self._get_or_create_counter(name, tags)
        if counter is None:
            return
        if tags:
            counter.labels(**{k: v for k, v in sorted(tags.items())}).inc(value)
        else:
            counter.inc(value)

    def set_gauge(
        self,
        name: str,
        value: float,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Set a Prometheus gauge."""
        gauge = self._get_or_create_gauge(name, tags)
        if gauge is None:
            return
        if tags:
            gauge.labels(**{k: v for k, v in sorted(tags.items())}).set(value)
        else:
            gauge.set(value)

    def observe_histogram(
        self,
        name: str,
        value: float,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Observe a Prometheus histogram value."""
        histogram = self._get_or_create_histogram(name, tags)
        if histogram is None:
            return
        if tags:
            histogram.labels(**{k: v for k, v in sorted(tags.items())}).observe(value)
        else:
            histogram.observe(value)


class TelemetryClient:
    """Main telemetry client for recording metrics.

    Provides a high-level interface for recording metrics with
    sampling support and optional correlation ID propagation.

    Example:
        >>> telemetry = TelemetryClient()
        >>> telemetry.increment("requests.total", tags={"endpoint": "/api/v1"})
        >>> with telemetry.timer("operation.duration", tags={"op": "compute"}):
        ...     result = compute_something()
    """

    def __init__(
        self,
        backend: MetricsBackend | None = None,
        sampling: SamplingConfig | None = None,
        prefix: str = "tradepulse",
    ) -> None:
        """Initialize telemetry client.

        Args:
            backend: Metrics backend (default: NoOpBackend)
            sampling: Sampling configuration
            prefix: Metric name prefix
        """
        self._backend = backend or NoOpBackend()
        self._sampler = Sampler(sampling)
        self._prefix = prefix
        self._enabled = True

    @property
    def enabled(self) -> bool:
        """Check if telemetry is enabled."""
        return self._enabled

    def disable(self) -> None:
        """Disable telemetry collection."""
        self._enabled = False

    def enable(self) -> None:
        """Enable telemetry collection."""
        self._enabled = True

    def _full_name(self, name: str) -> str:
        """Get full metric name with prefix."""
        if self._prefix:
            return f"{self._prefix}.{name}"
        return name

    def increment(
        self,
        name: str,
        value: float = 1.0,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Increment a counter metric.

        Args:
            name: Metric name
            value: Amount to increment
            tags: Optional tags/labels
        """
        if not self._enabled:
            return

        full_name = self._full_name(name)
        if not self._sampler.should_sample(full_name):
            return

        self._backend.increment_counter(full_name, value, tags)

    def gauge(
        self,
        name: str,
        value: float,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Set a gauge metric value.

        Args:
            name: Metric name
            value: Value to set
            tags: Optional tags/labels
        """
        if not self._enabled:
            return

        full_name = self._full_name(name)
        if not self._sampler.should_sample(full_name):
            return

        self._backend.set_gauge(full_name, value, tags)

    def histogram(
        self,
        name: str,
        value: float,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Record a histogram value.

        Args:
            name: Metric name
            value: Value to record
            tags: Optional tags/labels
        """
        if not self._enabled:
            return

        full_name = self._full_name(name)
        if not self._sampler.should_sample(full_name):
            return

        self._backend.observe_histogram(full_name, value, tags)

    @contextmanager
    def timer(
        self,
        name: str,
        tags: Mapping[str, str] | None = None,
        *,
        record_on_error: bool = True,
    ) -> Iterator[dict[str, Any]]:
        """Context manager for timing operations.

        Records the elapsed time as a histogram value.

        Args:
            name: Metric name
            tags: Optional tags/labels
            record_on_error: Whether to record timing on exception

        Yields:
            Context dict for storing additional info

        Example:
            >>> with telemetry.timer("db.query", tags={"table": "orders"}) as ctx:
            ...     result = db.query(...)
            ...     ctx["rows"] = len(result)
        """
        ctx: dict[str, Any] = {}
        start = time.perf_counter()
        success = True

        try:
            yield ctx
        except Exception:
            success = False
            raise
        finally:
            elapsed = time.perf_counter() - start
            if success or record_on_error:
                merged_tags = dict(tags) if tags else {}
                merged_tags["status"] = "success" if success else "error"
                self.histogram(name, elapsed, merged_tags)


# Global telemetry instance
_telemetry: TelemetryClient | None = None


def get_telemetry(
    backend: MetricsBackend | None = None,
    sampling: SamplingConfig | None = None,
) -> TelemetryClient:
    """Get or create the global telemetry client.

    Args:
        backend: Optional metrics backend
        sampling: Optional sampling configuration

    Returns:
        Global TelemetryClient instance
    """
    global _telemetry
    if _telemetry is None:
        _telemetry = TelemetryClient(backend=backend, sampling=sampling)
    return _telemetry


def configure_telemetry(
    backend: MetricsBackend | None = None,
    sampling: SamplingConfig | None = None,
    prefix: str = "tradepulse",
) -> TelemetryClient:
    """Configure and return the global telemetry client.

    This replaces any existing global telemetry configuration.

    Args:
        backend: Metrics backend to use
        sampling: Sampling configuration
        prefix: Metric name prefix

    Returns:
        Configured TelemetryClient
    """
    global _telemetry
    _telemetry = TelemetryClient(backend=backend, sampling=sampling, prefix=prefix)
    return _telemetry


__all__ = [
    # Types
    "MetricType",
    "SamplingConfig",
    "Sampler",
    # Protocols
    "MetricsBackend",
    # Backends
    "NoOpBackend",
    "PrometheusBackend",
    # Client
    "TelemetryClient",
    # Functions
    "get_telemetry",
    "configure_telemetry",
]
