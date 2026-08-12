# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core/architecture_integrator/component.py module."""

from __future__ import annotations

from datetime import datetime

import pytest

from core.architecture_integrator.component import (
    Component,
    ComponentHealth,
    ComponentMetadata,
    ComponentStatus,
)


class TestComponentStatus:
    """Tests for ComponentStatus enum."""

    def test_all_statuses_defined(self) -> None:
        """Test all expected statuses are defined."""
        expected = {
            "UNINITIALIZED",
            "INITIALIZING",
            "INITIALIZED",
            "STARTING",
            "RUNNING",
            "STOPPING",
            "STOPPED",
            "FAILED",
            "DEGRADED",
        }
        actual = {s.name for s in ComponentStatus}
        assert actual == expected

    def test_status_values(self) -> None:
        """Test status string values."""
        assert ComponentStatus.RUNNING.value == "running"
        assert ComponentStatus.FAILED.value == "failed"
        assert ComponentStatus.DEGRADED.value == "degraded"


class TestComponentHealth:
    """Tests for ComponentHealth dataclass."""

    def test_basic_creation(self) -> None:
        """Test basic health creation."""
        health = ComponentHealth(
            status=ComponentStatus.RUNNING,
            healthy=True,
            message="All systems operational",
        )
        assert health.status == ComponentStatus.RUNNING
        assert health.healthy is True
        assert health.message == "All systems operational"
        assert isinstance(health.last_check, datetime)
        assert health.metrics == {}

    def test_with_metrics(self) -> None:
        """Test health with metrics."""
        health = ComponentHealth(
            status=ComponentStatus.RUNNING,
            healthy=True,
            metrics={"cpu_usage": 45.0, "memory_mb": 256.0},
        )
        assert health.metrics["cpu_usage"] == 45.0
        assert health.metrics["memory_mb"] == 256.0

    def test_is_operational_running(self) -> None:
        """Test is_operational returns True for running status."""
        health = ComponentHealth(status=ComponentStatus.RUNNING, healthy=True)
        assert health.is_operational() is True

    def test_is_operational_degraded(self) -> None:
        """Test is_operational returns True for degraded status."""
        health = ComponentHealth(status=ComponentStatus.DEGRADED, healthy=False)
        assert health.is_operational() is True

    def test_is_operational_stopped(self) -> None:
        """Test is_operational returns False for stopped status."""
        health = ComponentHealth(status=ComponentStatus.STOPPED, healthy=False)
        assert health.is_operational() is False

    def test_is_failed(self) -> None:
        """Test is_failed method."""
        failed = ComponentHealth(status=ComponentStatus.FAILED, healthy=False)
        running = ComponentHealth(status=ComponentStatus.RUNNING, healthy=True)

        assert failed.is_failed() is True
        assert running.is_failed() is False

    def test_frozen_dataclass(self) -> None:
        """Test ComponentHealth is immutable (frozen)."""
        health = ComponentHealth(status=ComponentStatus.RUNNING, healthy=True)
        with pytest.raises(AttributeError):
            health.status = ComponentStatus.FAILED  # type: ignore[misc]


class TestComponentMetadata:
    """Tests for ComponentMetadata dataclass."""

    def test_minimal_creation(self) -> None:
        """Test creation with only required fields."""
        metadata = ComponentMetadata(name="test-component")
        assert metadata.name == "test-component"
        assert metadata.version == "1.0.0"
        assert metadata.description == ""
        assert metadata.tags == []
        assert metadata.dependencies == []
        assert metadata.provides == []
        assert metadata.configuration == {}

    def test_full_creation(self) -> None:
        """Test creation with all fields."""
        metadata = ComponentMetadata(
            name="data-ingestion",
            version="2.1.0",
            description="Handles data ingestion from external sources",
            tags=["core", "data"],
            dependencies=["database", "message-queue"],
            provides=["market-data", "historical-data"],
            configuration={"batch_size": 1000, "timeout": 30},
        )
        assert metadata.name == "data-ingestion"
        assert metadata.version == "2.1.0"
        assert "core" in metadata.tags
        assert "database" in metadata.dependencies
        assert "market-data" in metadata.provides
        assert metadata.configuration["batch_size"] == 1000


class TestComponent:
    """Tests for Component class."""

    def test_basic_creation(self) -> None:
        """Test basic component creation."""
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=object())
        assert component.status == ComponentStatus.UNINITIALIZED
        assert component.health is None

    def test_initialize_with_instance_method(self) -> None:
        """Test initialization using instance method."""

        class MockComponent:
            initialized = False

            def initialize(self) -> None:
                self.initialized = True

        mock = MockComponent()
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=mock)

        component.initialize()

        assert mock.initialized is True
        assert component.status == ComponentStatus.INITIALIZED

    def test_initialize_with_hook(self) -> None:
        """Test initialization using custom hook."""
        hook_called = []

        def init_hook() -> None:
            hook_called.append(True)

        metadata = ComponentMetadata(name="test")
        component = Component(
            metadata=metadata,
            instance=object(),
            init_hook=init_hook,
        )

        component.initialize()

        assert len(hook_called) == 1
        assert component.status == ComponentStatus.INITIALIZED

    def test_initialize_failure(self) -> None:
        """Test initialization failure sets FAILED status."""

        class FailingComponent:
            def initialize(self) -> None:
                raise ValueError("Init failed")

        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=FailingComponent())

        with pytest.raises(RuntimeError, match="Failed to initialize"):
            component.initialize()

        assert component.status == ComponentStatus.FAILED

    def test_start_requires_initialized_status(self) -> None:
        """Test start requires INITIALIZED status."""
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=object())

        with pytest.raises(RuntimeError, match="Cannot start component"):
            component.start()

    def test_start_with_instance_method(self) -> None:
        """Test start using instance method."""

        class MockComponent:
            started = False

            def initialize(self) -> None:
                pass

            def start(self) -> None:
                self.started = True

        mock = MockComponent()
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=mock)

        component.initialize()
        component.start()

        assert mock.started is True
        assert component.status == ComponentStatus.RUNNING

    def test_start_with_hook(self) -> None:
        """Test start using custom hook."""
        hook_called = []

        def start_hook() -> None:
            hook_called.append(True)

        metadata = ComponentMetadata(name="test")
        component = Component(
            metadata=metadata,
            instance=object(),
            start_hook=start_hook,
        )
        component.status = ComponentStatus.INITIALIZED

        component.start()

        assert len(hook_called) == 1
        assert component.status == ComponentStatus.RUNNING

    def test_start_failure(self) -> None:
        """Test start failure sets FAILED status."""

        class FailingComponent:
            def initialize(self) -> None:
                pass

            def start(self) -> None:
                raise ValueError("Start failed")

        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=FailingComponent())
        component.status = ComponentStatus.INITIALIZED

        with pytest.raises(RuntimeError, match="Failed to start"):
            component.start()

        assert component.status == ComponentStatus.FAILED

    def test_stop_running_component(self) -> None:
        """Test stopping a running component."""

        class MockComponent:
            stopped = False

            def stop(self) -> None:
                self.stopped = True

        mock = MockComponent()
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=mock)
        component.status = ComponentStatus.RUNNING

        component.stop()

        assert mock.stopped is True
        assert component.status == ComponentStatus.STOPPED

    def test_stop_non_running_component(self) -> None:
        """Test stop is no-op for non-running component."""
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=object())
        component.status = ComponentStatus.STOPPED

        # Should not raise
        component.stop()

        assert component.status == ComponentStatus.STOPPED

    def test_stop_with_hook(self) -> None:
        """Test stop using custom hook."""
        hook_called = []

        def stop_hook() -> None:
            hook_called.append(True)

        metadata = ComponentMetadata(name="test")
        component = Component(
            metadata=metadata,
            instance=object(),
            stop_hook=stop_hook,
        )
        component.status = ComponentStatus.RUNNING

        component.stop()

        assert len(hook_called) == 1
        assert component.status == ComponentStatus.STOPPED

    def test_stop_failure(self) -> None:
        """Test stop failure sets FAILED status."""

        class FailingComponent:
            def stop(self) -> None:
                raise ValueError("Stop failed")

        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=FailingComponent())
        component.status = ComponentStatus.RUNNING

        with pytest.raises(RuntimeError, match="Failed to stop"):
            component.stop()

        assert component.status == ComponentStatus.FAILED

    def test_health_check_with_instance_method(self) -> None:
        """Test health check using instance method."""

        class MockComponent:
            def health_check(self) -> ComponentHealth:
                return ComponentHealth(
                    status=ComponentStatus.RUNNING,
                    healthy=True,
                    message="OK",
                )

        mock = MockComponent()
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=mock)

        health = component.check_health()

        assert health.healthy is True
        assert health.status == ComponentStatus.RUNNING
        assert component.health == health

    def test_health_check_with_hook(self) -> None:
        """Test health check using custom hook."""

        def health_hook() -> ComponentHealth:
            return ComponentHealth(
                status=ComponentStatus.DEGRADED,
                healthy=False,
                message="High load",
            )

        metadata = ComponentMetadata(name="test")
        component = Component(
            metadata=metadata,
            instance=object(),
            health_hook=health_hook,
        )

        health = component.check_health()

        assert health.status == ComponentStatus.DEGRADED
        assert health.healthy is False

    def test_health_check_no_implementation(self) -> None:
        """Test health check without implementation returns default."""
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=object())
        component.status = ComponentStatus.RUNNING

        health = component.check_health()

        assert health.healthy is True
        assert "No health check implemented" in health.message

    def test_health_check_failure(self) -> None:
        """Test health check failure returns error health."""

        class FailingComponent:
            def health_check(self) -> ComponentHealth:
                raise ValueError("Health check failed")

        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=FailingComponent())

        health = component.check_health()

        assert health.healthy is False
        assert health.status == ComponentStatus.FAILED
        assert "Health check failed" in health.message

    def test_get_dependencies(self) -> None:
        """Test get_dependencies returns metadata dependencies."""
        metadata = ComponentMetadata(
            name="test",
            dependencies=["db", "cache"],
        )
        component = Component(metadata=metadata, instance=object())

        deps = component.get_dependencies()

        assert "db" in deps
        assert "cache" in deps

    def test_get_provides(self) -> None:
        """Test get_provides returns metadata provides."""
        metadata = ComponentMetadata(
            name="test",
            provides=["api", "data"],
        )
        component = Component(metadata=metadata, instance=object())

        provides = component.get_provides()

        assert "api" in provides
        assert "data" in provides

    def test_last_updated_changes_on_lifecycle(self) -> None:
        """Test last_updated timestamp updates on lifecycle changes."""

        class MockComponent:
            def initialize(self) -> None:
                pass

        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=MockComponent())

        initial_time = component.last_updated

        component.initialize()

        assert component.last_updated >= initial_time
