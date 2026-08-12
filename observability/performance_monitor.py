# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Enhanced performance monitoring system for production environments.

This module provides comprehensive performance monitoring including real-time
metrics collection, bottleneck detection, and performance regression tracking.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Container for performance metrics."""

    timestamp: float
    latency_ms: float
    throughput: float
    cpu_percent: float
    memory_mb: float
    error_rate: float
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class PerformanceBaseline:
    """Performance baseline for regression detection."""

    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    avg_throughput: float
    max_cpu_percent: float
    max_memory_mb: float


class PerformanceMonitor:
    """Real-time performance monitoring and bottleneck detection."""

    def __init__(self, baseline: Optional[PerformanceBaseline] = None):
        """Initialize performance monitor.

        Args:
            baseline: Optional baseline for regression detection
        """
        self.baseline = baseline
        self.metrics_history: List[PerformanceMetrics] = []
        self.bottlenecks: List[Dict] = []
        self._start_time = time.time()

    def record_metric(
        self,
        latency_ms: float,
        throughput: float = 0.0,
        cpu_percent: float = 0.0,
        memory_mb: float = 0.0,
        error_rate: float = 0.0,
        tags: Optional[Dict[str, str]] = None,
    ) -> None:
        """Record a performance metric.

        Args:
            latency_ms: Operation latency in milliseconds
            throughput: Operations per second
            cpu_percent: CPU utilization percentage
            memory_mb: Memory usage in MB
            error_rate: Error rate (0.0-1.0)
            tags: Additional tags for the metric
        """
        metric = PerformanceMetrics(
            timestamp=time.time(),
            latency_ms=latency_ms,
            throughput=throughput,
            cpu_percent=cpu_percent,
            memory_mb=memory_mb,
            error_rate=error_rate,
            tags=tags or {},
        )
        self.metrics_history.append(metric)

        # Check for bottlenecks
        self._detect_bottleneck(metric)

    def _detect_bottleneck(self, metric: PerformanceMetrics) -> None:
        """Detect performance bottlenecks.

        Args:
            metric: Current performance metric
        """
        if not self.baseline:
            return

        # Check latency regression
        if metric.latency_ms > self.baseline.p99_latency_ms * 1.5:
            self.bottlenecks.append(
                {
                    "type": "latency_spike",
                    "timestamp": metric.timestamp,
                    "value": metric.latency_ms,
                    "baseline": self.baseline.p99_latency_ms,
                    "severity": "high",
                }
            )
            logger.warning(
                f"Latency spike detected: {metric.latency_ms:.2f}ms "
                f"(baseline p99: {self.baseline.p99_latency_ms:.2f}ms)"
            )

        # Check throughput degradation
        if metric.throughput < self.baseline.avg_throughput * 0.5:
            self.bottlenecks.append(
                {
                    "type": "throughput_drop",
                    "timestamp": metric.timestamp,
                    "value": metric.throughput,
                    "baseline": self.baseline.avg_throughput,
                    "severity": "medium",
                }
            )

        # Check resource utilization
        if metric.cpu_percent > self.baseline.max_cpu_percent:
            self.bottlenecks.append(
                {
                    "type": "cpu_overload",
                    "timestamp": metric.timestamp,
                    "value": metric.cpu_percent,
                    "baseline": self.baseline.max_cpu_percent,
                    "severity": "high",
                }
            )

    def get_recent_metrics(self, window_seconds: float = 60.0) -> List[PerformanceMetrics]:
        """Get metrics from recent time window.

        Args:
            window_seconds: Time window in seconds

        Returns:
            List of metrics within the time window
        """
        cutoff = time.time() - window_seconds
        return [m for m in self.metrics_history if m.timestamp >= cutoff]

    def calculate_percentiles(self, window_seconds: float = 60.0) -> Dict[str, float]:
        """Calculate latency percentiles.

        Args:
            window_seconds: Time window in seconds

        Returns:
            Dictionary of percentile values
        """
        import numpy as np

        recent = self.get_recent_metrics(window_seconds)
        if not recent:
            return {}

        latencies = [m.latency_ms for m in recent]

        return {
            "p50": float(np.percentile(latencies, 50)),
            "p75": float(np.percentile(latencies, 75)),
            "p95": float(np.percentile(latencies, 95)),
            "p99": float(np.percentile(latencies, 99)),
            "max": float(np.max(latencies)),
            "avg": float(np.mean(latencies)),
        }

    def check_regression(self) -> Dict[str, bool]:
        """Check for performance regression against baseline.

        Returns:
            Dictionary indicating regression in various metrics
        """
        if not self.baseline:
            return {}

        recent = self.get_recent_metrics(window_seconds=300)  # 5 minute window
        if not recent:
            return {}

        import numpy as np

        latencies = [m.latency_ms for m in recent]
        throughputs = [m.throughput for m in recent if m.throughput > 0]

        p95 = float(np.percentile(latencies, 95))
        avg_throughput = float(np.mean(throughputs)) if throughputs else 0.0

        threshold = 0.1  # 10% regression threshold

        return {
            "latency_regression": (p95 - self.baseline.p95_latency_ms)
            / self.baseline.p95_latency_ms
            > threshold,
            "throughput_regression": (
                (self.baseline.avg_throughput - avg_throughput) / self.baseline.avg_throughput
                > threshold
                if avg_throughput > 0
                else False
            ),
        }

    def get_bottlenecks(self, severity: Optional[str] = None, limit: int = 10) -> List[Dict]:
        """Get detected bottlenecks.

        Args:
            severity: Filter by severity (high, medium, low)
            limit: Maximum number of bottlenecks to return

        Returns:
            List of bottleneck records
        """
        bottlenecks = self.bottlenecks

        if severity:
            bottlenecks = [b for b in bottlenecks if b.get("severity") == severity]

        return bottlenecks[-limit:]

    def get_summary(self) -> Dict:
        """Get performance monitoring summary.

        Returns:
            Summary dictionary with key metrics
        """
        recent = self.get_recent_metrics(window_seconds=300)

        if not recent:
            return {
                "status": "no_data",
                "uptime_seconds": time.time() - self._start_time,
            }

        import numpy as np

        latencies = [m.latency_ms for m in recent]
        throughputs = [m.throughput for m in recent if m.throughput > 0]
        error_rates = [m.error_rate for m in recent if m.error_rate > 0]

        summary = {
            "status": "healthy",
            "uptime_seconds": time.time() - self._start_time,
            "metrics_count": len(self.metrics_history),
            "recent_metrics_count": len(recent),
            "avg_latency_ms": float(np.mean(latencies)),
            "p95_latency_ms": float(np.percentile(latencies, 95)),
            "p99_latency_ms": float(np.percentile(latencies, 99)),
            "bottlenecks_count": len(self.bottlenecks),
        }

        if throughputs:
            summary["avg_throughput"] = float(np.mean(throughputs))

        if error_rates:
            summary["avg_error_rate"] = float(np.mean(error_rates))

        # Check health status
        regressions = self.check_regression()
        if any(regressions.values()):
            summary["status"] = "degraded"
            summary["regressions"] = regressions

        if len(self.bottlenecks) > 10:
            summary["status"] = "critical"

        return summary


class AnomalyDetector:
    """Statistical anomaly detection for performance metrics."""

    def __init__(self, window_size: int = 100):
        """Initialize anomaly detector.

        Args:
            window_size: Size of sliding window for baseline
        """
        self.window_size = window_size
        self.history: List[float] = []

    def add_value(self, value: float) -> bool:
        """Add a value and check for anomaly.

        Args:
            value: Metric value to check

        Returns:
            True if value is anomalous
        """
        self.history.append(value)

        # Keep only recent window
        if len(self.history) > self.window_size:
            self.history = self.history[-self.window_size :]

        return self.is_anomaly(value)

    def is_anomaly(self, value: float, threshold: float = 3.0) -> bool:
        """Check if value is anomalous using z-score.

        Args:
            value: Value to check
            threshold: Z-score threshold (default: 3.0)

        Returns:
            True if value is anomalous
        """
        if len(self.history) < 10:  # Need minimum data
            return False

        import numpy as np

        mean = float(np.mean(self.history))
        std = float(np.std(self.history))

        if std == 0:
            return False

        z_score = abs((value - mean) / std)
        return z_score > threshold

    def get_statistics(self) -> Dict[str, float]:
        """Get current statistics.

        Returns:
            Dictionary with mean, std, min, max
        """
        if not self.history:
            return {}

        import numpy as np

        return {
            "mean": float(np.mean(self.history)),
            "std": float(np.std(self.history)),
            "min": float(np.min(self.history)),
            "max": float(np.max(self.history)),
            "count": len(self.history),
        }
