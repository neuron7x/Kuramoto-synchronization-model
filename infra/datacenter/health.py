# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Data center health monitoring.

Provides continuous health monitoring for data centers with:
- Configurable health check intervals
- Latency measurement
- Resource utilization tracking
- Automatic health status updates
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Callable, Dict, List, Optional

from infra.datacenter.models import DataCenter, DataCenterStatus

logger = logging.getLogger(__name__)


@dataclass
class HealthCheckResult:
    """Result of a single health check.

    Attributes:
        dc_id: Data center ID that was checked
        timestamp: When the check was performed
        latency_ms: Measured latency
        success: Whether the check succeeded
        error_message: Error message if check failed
        metrics: Additional metrics from the check
    """

    dc_id: str
    timestamp: datetime
    latency_ms: float
    success: bool
    error_message: Optional[str] = None
    metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class HealthMonitorConfig:
    """Configuration for the health monitor.

    Attributes:
        check_interval_seconds: Default interval between checks
        timeout_seconds: Timeout for health check requests
        failure_threshold: Consecutive failures before marking unhealthy
        recovery_threshold: Consecutive successes before marking healthy
        latency_threshold_ms: Latency above this is considered degraded
        error_rate_threshold: Error rate above this is considered degraded
    """

    check_interval_seconds: int = 30
    timeout_seconds: float = 5.0
    failure_threshold: int = 3
    recovery_threshold: int = 2
    latency_threshold_ms: float = 500.0
    error_rate_threshold: float = 0.05


class DataCenterHealthMonitor:
    """Monitors health of data centers.

    Provides health checking capabilities with configurable thresholds
    and automatic status updates based on check results.
    """

    def __init__(self, config: Optional[HealthMonitorConfig] = None):
        """Initialize the health monitor.

        Args:
            config: Health monitoring configuration
        """
        self.config = config or HealthMonitorConfig()
        self._lock = RLock()
        self._failure_counts: Dict[str, int] = {}
        self._success_counts: Dict[str, int] = {}
        self._last_check_times: Dict[str, datetime] = {}
        self._check_history: Dict[str, List[HealthCheckResult]] = {}
        self._health_checker: Optional[Callable[[str], HealthCheckResult]] = None

    def register_health_checker(
        self, checker: Callable[[str], HealthCheckResult]
    ) -> None:
        """Register a custom health check function.

        Args:
            checker: Function that performs health check for a DC ID
        """
        self._health_checker = checker

    def check_health(self, dc: DataCenter) -> HealthCheckResult:
        """Perform a health check on a data center.

        Args:
            dc: Data center to check

        Returns:
            Result of the health check
        """
        with self._lock:
            start_time = time.monotonic()
            now = datetime.now(timezone.utc)

            # Use custom checker if registered
            if self._health_checker:
                try:
                    result = self._health_checker(dc.id)
                except Exception as e:
                    result = HealthCheckResult(
                        dc_id=dc.id,
                        timestamp=now,
                        latency_ms=float((time.monotonic() - start_time) * 1000),
                        success=False,
                        error_message=str(e),
                    )
            else:
                # Default simulated check based on current health
                latency = dc.health.latency_ms + random.uniform(-5, 5)
                success = dc.status != DataCenterStatus.OFFLINE
                result = HealthCheckResult(
                    dc_id=dc.id,
                    timestamp=now,
                    latency_ms=max(0.0, latency),
                    success=success,
                    metrics={
                        "cpu": dc.health.cpu_utilization,
                        "memory": dc.health.memory_utilization,
                        "disk": dc.health.disk_utilization,
                    },
                )

            self._record_result(dc.id, result)
            self._update_data_center_health(dc, result)
            return result

    def _record_result(self, dc_id: str, result: HealthCheckResult) -> None:
        """Record a health check result.

        Args:
            dc_id: Data center ID
            result: Health check result
        """
        if dc_id not in self._check_history:
            self._check_history[dc_id] = []

        self._check_history[dc_id].append(result)

        # Keep only last 100 results
        if len(self._check_history[dc_id]) > 100:
            self._check_history[dc_id] = self._check_history[dc_id][-100:]

        self._last_check_times[dc_id] = result.timestamp

        if result.success:
            self._success_counts[dc_id] = self._success_counts.get(dc_id, 0) + 1
            self._failure_counts[dc_id] = 0
        else:
            self._failure_counts[dc_id] = self._failure_counts.get(dc_id, 0) + 1
            self._success_counts[dc_id] = 0

    def _update_data_center_health(
        self, dc: DataCenter, result: HealthCheckResult
    ) -> None:
        """Update data center health based on check result.

        Args:
            dc: Data center to update
            result: Health check result
        """
        dc.health.last_check = result.timestamp
        dc.health.latency_ms = result.latency_ms

        # Update metrics from result
        if result.metrics:
            if "cpu" in result.metrics:
                dc.health.cpu_utilization = result.metrics["cpu"]
            if "memory" in result.metrics:
                dc.health.memory_utilization = result.metrics["memory"]
            if "disk" in result.metrics:
                dc.health.disk_utilization = result.metrics["disk"]

        # Determine health status
        failure_count = self._failure_counts.get(dc.id, 0)
        success_count = self._success_counts.get(dc.id, 0)

        if failure_count >= self.config.failure_threshold:
            dc.health.is_healthy = False
            if dc.status == DataCenterStatus.ACTIVE:
                dc.status = DataCenterStatus.DEGRADED
                logger.warning(
                    f"Data center {dc.id} marked as degraded after "
                    f"{failure_count} consecutive failures"
                )
        elif (
            success_count >= self.config.recovery_threshold and not dc.health.is_healthy
        ):
            dc.health.is_healthy = True
            if dc.status == DataCenterStatus.DEGRADED:
                dc.status = DataCenterStatus.ACTIVE
                logger.info(
                    f"Data center {dc.id} recovered after "
                    f"{success_count} consecutive successes"
                )

        # Check latency threshold
        if result.latency_ms > self.config.latency_threshold_ms:
            if dc.status == DataCenterStatus.ACTIVE:
                dc.status = DataCenterStatus.DEGRADED
                logger.warning(
                    f"Data center {dc.id} degraded due to high latency: "
                    f"{result.latency_ms:.1f}ms"
                )

    def is_check_due(self, dc: DataCenter) -> bool:
        """Check if a health check is due for a data center.

        Args:
            dc: Data center to check

        Returns:
            True if a check should be performed
        """
        with self._lock:
            last_check = self._last_check_times.get(dc.id)
            if last_check is None:
                return True

            interval = timedelta(
                seconds=dc.config.health_check_interval_seconds
                or self.config.check_interval_seconds
            )
            now = datetime.now(timezone.utc)
            return now - last_check >= interval

    def get_check_history(self, dc_id: str, limit: int = 10) -> List[HealthCheckResult]:
        """Get recent health check results for a data center.

        Args:
            dc_id: Data center ID
            limit: Maximum number of results to return

        Returns:
            List of recent health check results
        """
        with self._lock:
            history = self._check_history.get(dc_id, [])
            return list(history[-limit:])

    def get_availability_percentage(
        self, dc_id: str, window_minutes: int = 60
    ) -> float:
        """Calculate availability percentage for a data center.

        Args:
            dc_id: Data center ID
            window_minutes: Time window to consider

        Returns:
            Availability percentage (0.0 to 100.0)
        """
        with self._lock:
            history = self._check_history.get(dc_id, [])
            if not history:
                return 100.0

            cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
            recent_checks = [r for r in history if r.timestamp >= cutoff]

            if not recent_checks:
                return 100.0

            successful = sum(1 for r in recent_checks if r.success)
            return (successful / len(recent_checks)) * 100.0

    def get_average_latency(
        self, dc_id: str, window_minutes: int = 60
    ) -> Optional[float]:
        """Calculate average latency for a data center.

        Args:
            dc_id: Data center ID
            window_minutes: Time window to consider

        Returns:
            Average latency in milliseconds, or None if no data
        """
        with self._lock:
            history = self._check_history.get(dc_id, [])
            if not history:
                return None

            cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
            recent_checks = [r for r in history if r.timestamp >= cutoff and r.success]

            if not recent_checks:
                return None

            total_latency = sum(r.latency_ms for r in recent_checks)
            return total_latency / len(recent_checks)

    def get_health_summary(self, dc_id: str) -> Dict:
        """Get a health summary for a data center.

        Args:
            dc_id: Data center ID

        Returns:
            Dictionary with health summary information
        """
        with self._lock:
            return {
                "dc_id": dc_id,
                "last_check": self._last_check_times.get(dc_id),
                "failure_count": self._failure_counts.get(dc_id, 0),
                "success_count": self._success_counts.get(dc_id, 0),
                "availability_1h": self.get_availability_percentage(dc_id, 60),
                "availability_24h": self.get_availability_percentage(dc_id, 1440),
                "avg_latency_1h": self.get_average_latency(dc_id, 60),
                "total_checks": len(self._check_history.get(dc_id, [])),
            }
