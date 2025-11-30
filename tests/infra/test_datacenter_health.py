# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for data center health monitoring."""

from __future__ import annotations

from datetime import datetime, timezone

from infra.datacenter.health import (
    DataCenterHealthMonitor,
    HealthCheckResult,
    HealthMonitorConfig,
)
from infra.datacenter.models import (
    DataCenter,
    DataCenterConfig,
    DataCenterRegion,
    DataCenterStatus,
)


class TestHealthCheckResult:
    """Tests for HealthCheckResult."""

    def test_create_result(self) -> None:
        """Test creating a health check result."""
        now = datetime.now(timezone.utc)
        result = HealthCheckResult(
            dc_id="dc-test",
            timestamp=now,
            latency_ms=25.0,
            success=True,
        )
        assert result.dc_id == "dc-test"
        assert result.timestamp == now
        assert result.latency_ms == 25.0
        assert result.success is True
        assert result.error_message is None

    def test_create_failed_result(self) -> None:
        """Test creating a failed health check result."""
        now = datetime.now(timezone.utc)
        result = HealthCheckResult(
            dc_id="dc-test",
            timestamp=now,
            latency_ms=5000.0,
            success=False,
            error_message="Connection timeout",
        )
        assert result.success is False
        assert result.error_message == "Connection timeout"


class TestHealthMonitorConfig:
    """Tests for HealthMonitorConfig."""

    def test_default_values(self) -> None:
        """Test default config values."""
        config = HealthMonitorConfig()
        assert config.check_interval_seconds == 30
        assert config.timeout_seconds == 5.0
        assert config.failure_threshold == 3
        assert config.recovery_threshold == 2
        assert config.latency_threshold_ms == 500.0
        assert config.error_rate_threshold == 0.05

    def test_custom_values(self) -> None:
        """Test custom config values."""
        config = HealthMonitorConfig(
            check_interval_seconds=60,
            timeout_seconds=10.0,
            failure_threshold=5,
        )
        assert config.check_interval_seconds == 60
        assert config.timeout_seconds == 10.0
        assert config.failure_threshold == 5


class TestDataCenterHealthMonitor:
    """Tests for DataCenterHealthMonitor."""

    def _create_test_dc(
        self, dc_id: str = "dc-test", status: DataCenterStatus = DataCenterStatus.ACTIVE
    ) -> DataCenter:
        """Create a test data center."""
        config = DataCenterConfig(
            id=dc_id,
            name="Test DC",
            region=DataCenterRegion.US_EAST,
        )
        return DataCenter(config=config, status=status)

    def test_check_health_success(self) -> None:
        """Test successful health check."""
        monitor = DataCenterHealthMonitor()
        dc = self._create_test_dc()

        result = monitor.check_health(dc)

        assert result.dc_id == "dc-test"
        assert result.success is True
        assert result.latency_ms >= 0

    def test_check_health_offline(self) -> None:
        """Test health check for offline DC."""
        monitor = DataCenterHealthMonitor()
        dc = self._create_test_dc(status=DataCenterStatus.OFFLINE)

        result = monitor.check_health(dc)

        assert result.success is False

    def test_custom_health_checker(self) -> None:
        """Test with custom health checker."""
        monitor = DataCenterHealthMonitor()

        def custom_checker(dc_id: str) -> HealthCheckResult:
            return HealthCheckResult(
                dc_id=dc_id,
                timestamp=datetime.now(timezone.utc),
                latency_ms=42.0,
                success=True,
                metrics={"custom": 123.0},
            )

        monitor.register_health_checker(custom_checker)
        dc = self._create_test_dc()

        result = monitor.check_health(dc)

        assert result.latency_ms == 42.0
        assert result.metrics.get("custom") == 123.0

    def test_custom_checker_exception(self) -> None:
        """Test custom checker that raises exception."""
        monitor = DataCenterHealthMonitor()

        def failing_checker(dc_id: str) -> HealthCheckResult:
            raise RuntimeError("Connection failed")

        monitor.register_health_checker(failing_checker)
        dc = self._create_test_dc()

        result = monitor.check_health(dc)

        assert result.success is False
        assert "Connection failed" in (result.error_message or "")

    def test_failure_threshold_marks_unhealthy(self) -> None:
        """Test that reaching failure threshold marks DC unhealthy."""
        config = HealthMonitorConfig(failure_threshold=3)
        monitor = DataCenterHealthMonitor(config=config)

        def failing_checker(dc_id: str) -> HealthCheckResult:
            return HealthCheckResult(
                dc_id=dc_id,
                timestamp=datetime.now(timezone.utc),
                latency_ms=100.0,
                success=False,
                error_message="Failed",
            )

        monitor.register_health_checker(failing_checker)
        dc = self._create_test_dc()
        dc.health.is_healthy = True

        # First two failures shouldn't mark unhealthy
        monitor.check_health(dc)
        assert dc.health.is_healthy is True

        monitor.check_health(dc)
        assert dc.health.is_healthy is True

        # Third failure should mark unhealthy
        monitor.check_health(dc)
        assert dc.health.is_healthy is False

    def test_recovery_threshold_marks_healthy(self) -> None:
        """Test that reaching recovery threshold marks DC healthy."""
        config = HealthMonitorConfig(recovery_threshold=2, failure_threshold=1)
        monitor = DataCenterHealthMonitor(config=config)

        dc = self._create_test_dc()
        dc.health.is_healthy = False
        dc.status = DataCenterStatus.DEGRADED

        def success_checker(dc_id: str) -> HealthCheckResult:
            return HealthCheckResult(
                dc_id=dc_id,
                timestamp=datetime.now(timezone.utc),
                latency_ms=50.0,
                success=True,
            )

        monitor.register_health_checker(success_checker)

        # First success shouldn't mark healthy yet
        monitor.check_health(dc)
        assert dc.health.is_healthy is False

        # Second success should mark healthy
        monitor.check_health(dc)
        assert dc.health.is_healthy is True

    def test_high_latency_marks_degraded(self) -> None:
        """Test that high latency marks DC as degraded."""
        config = HealthMonitorConfig(latency_threshold_ms=100.0)
        monitor = DataCenterHealthMonitor(config=config)

        def high_latency_checker(dc_id: str) -> HealthCheckResult:
            return HealthCheckResult(
                dc_id=dc_id,
                timestamp=datetime.now(timezone.utc),
                latency_ms=500.0,
                success=True,
            )

        monitor.register_health_checker(high_latency_checker)
        dc = self._create_test_dc()

        monitor.check_health(dc)

        assert dc.status == DataCenterStatus.DEGRADED

    def test_is_check_due_first_check(self) -> None:
        """Test is_check_due returns True for first check."""
        monitor = DataCenterHealthMonitor()
        dc = self._create_test_dc()

        assert monitor.is_check_due(dc) is True

    def test_is_check_due_after_recent_check(self) -> None:
        """Test is_check_due returns False after recent check."""
        config = HealthMonitorConfig(check_interval_seconds=30)
        monitor = DataCenterHealthMonitor(config=config)
        dc = self._create_test_dc()

        monitor.check_health(dc)

        assert monitor.is_check_due(dc) is False

    def test_get_check_history(self) -> None:
        """Test getting check history."""
        monitor = DataCenterHealthMonitor()
        dc = self._create_test_dc()

        # Perform multiple checks
        for _ in range(5):
            monitor.check_health(dc)

        history = monitor.get_check_history(dc.id, limit=3)
        assert len(history) == 3

    def test_get_availability_percentage(self) -> None:
        """Test calculating availability percentage."""
        monitor = DataCenterHealthMonitor()

        def alternating_checker(dc_id: str) -> HealthCheckResult:
            # Alternate between success and failure
            counter = getattr(alternating_checker, "counter", 0)
            alternating_checker.counter = counter + 1  # type: ignore[attr-defined]
            return HealthCheckResult(
                dc_id=dc_id,
                timestamp=datetime.now(timezone.utc),
                latency_ms=50.0,
                success=(counter % 2 == 0),
            )

        monitor.register_health_checker(alternating_checker)
        dc = self._create_test_dc()

        # Perform 4 checks (2 success, 2 failure)
        for _ in range(4):
            monitor.check_health(dc)

        availability = monitor.get_availability_percentage(dc.id)
        assert availability == 50.0

    def test_get_availability_no_history(self) -> None:
        """Test availability with no history returns 100."""
        monitor = DataCenterHealthMonitor()
        availability = monitor.get_availability_percentage("nonexistent")
        assert availability == 100.0

    def test_get_average_latency(self) -> None:
        """Test calculating average latency."""
        monitor = DataCenterHealthMonitor()
        latencies = [10.0, 20.0, 30.0, 40.0]
        call_count = 0

        def latency_checker(dc_id: str) -> HealthCheckResult:
            nonlocal call_count
            latency = latencies[call_count % len(latencies)]
            call_count += 1
            return HealthCheckResult(
                dc_id=dc_id,
                timestamp=datetime.now(timezone.utc),
                latency_ms=latency,
                success=True,
            )

        monitor.register_health_checker(latency_checker)
        dc = self._create_test_dc()

        for _ in range(4):
            monitor.check_health(dc)

        avg_latency = monitor.get_average_latency(dc.id)
        assert avg_latency == 25.0  # (10+20+30+40)/4

    def test_get_average_latency_no_history(self) -> None:
        """Test average latency with no history returns None."""
        monitor = DataCenterHealthMonitor()
        avg_latency = monitor.get_average_latency("nonexistent")
        assert avg_latency is None

    def test_get_health_summary(self) -> None:
        """Test getting health summary."""
        monitor = DataCenterHealthMonitor()
        dc = self._create_test_dc()

        monitor.check_health(dc)

        summary = monitor.get_health_summary(dc.id)

        assert summary["dc_id"] == dc.id
        assert summary["last_check"] is not None
        assert summary["failure_count"] == 0
        assert summary["success_count"] == 1
        assert "availability_1h" in summary
        assert "avg_latency_1h" in summary
