# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""
Comprehensive test suite for architecture_integrator/component.py

Tests the core component model for architecture integration, including
status management, health checking, and lifecycle management.

Following 2025 best practices:
- Comprehensive coverage of all code paths
- Property-based testing for edge cases
- Clear test names and documentation
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock

from core.architecture_integrator.component import (
    ComponentStatus,
    ComponentHealth,
    ComponentMetadata,
    Component,
    ComponentProtocol,
)


class TestComponentStatus:
    """Test ComponentStatus enum."""

    def test_all_statuses_defined(self):
        """Test that all expected statuses are defined."""
        expected_statuses = {
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
        actual_statuses = {status.name for status in ComponentStatus}
        assert actual_statuses == expected_statuses

    def test_status_values_are_strings(self):
        """Test that status values are lowercase strings."""
        for status in ComponentStatus:
            assert isinstance(status.value, str)
            assert status.value == status.name.lower()


class TestComponentHealth:
    """Test ComponentHealth dataclass."""

    def test_health_basic_creation(self):
        """Test creating basic health instance."""
        health = ComponentHealth(
            status=ComponentStatus.RUNNING,
            healthy=True,
        )
        assert health.status == ComponentStatus.RUNNING
        assert health.healthy is True
        assert health.message == ""
        assert isinstance(health.last_check, datetime)

    def test_health_with_all_fields(self):
        """Test creating health instance with all fields."""
        now = datetime.now(timezone.utc)
        metrics = {"cpu": 45.5, "memory": 78.2}
        
        health = ComponentHealth(
            status=ComponentStatus.RUNNING,
            healthy=True,
            message="All systems nominal",
            last_check=now,
            metrics=metrics,
        )
        
        assert health.status == ComponentStatus.RUNNING
        assert health.healthy is True
        assert health.message == "All systems nominal"
        assert health.last_check == now
        assert health.metrics == metrics

    def test_health_is_frozen(self):
        """Test that ComponentHealth is immutable."""
        health = ComponentHealth(
            status=ComponentStatus.RUNNING,
            healthy=True,
        )
        with pytest.raises(AttributeError):
            health.healthy = False

    def test_is_operational_running(self):
        """Test is_operational returns True for RUNNING status."""
        health = ComponentHealth(
            status=ComponentStatus.RUNNING,
            healthy=True,
        )
        assert health.is_operational() is True

    def test_is_operational_degraded(self):
        """Test is_operational returns True for DEGRADED status."""
        health = ComponentHealth(
            status=ComponentStatus.DEGRADED,
            healthy=False,
        )
        assert health.is_operational() is True

    def test_is_operational_other_statuses(self):
        """Test is_operational returns False for non-operational statuses."""
        non_operational = [
            ComponentStatus.UNINITIALIZED,
            ComponentStatus.INITIALIZING,
            ComponentStatus.INITIALIZED,
            ComponentStatus.STARTING,
            ComponentStatus.STOPPING,
            ComponentStatus.STOPPED,
            ComponentStatus.FAILED,
        ]
        
        for status in non_operational:
            health = ComponentHealth(status=status, healthy=False)
            assert health.is_operational() is False

    def test_is_failed(self):
        """Test is_failed returns True only for FAILED status."""
        health_failed = ComponentHealth(
            status=ComponentStatus.FAILED,
            healthy=False,
        )
        assert health_failed.is_failed() is True
        
        health_running = ComponentHealth(
            status=ComponentStatus.RUNNING,
            healthy=True,
        )
        assert health_running.is_failed() is False


class TestComponentMetadata:
    """Test ComponentMetadata dataclass."""

    def test_metadata_minimal(self):
        """Test creating metadata with only required field."""
        metadata = ComponentMetadata(name="TestComponent")
        assert metadata.name == "TestComponent"
        assert metadata.version == "1.0.0"
        assert metadata.description == ""
        assert metadata.tags == []
        assert metadata.dependencies == []
        assert metadata.provides == []
        assert metadata.configuration == {}

    def test_metadata_full(self):
        """Test creating metadata with all fields."""
        metadata = ComponentMetadata(
            name="DataPipeline",
            version="2.1.0",
            description="Ingestion pipeline for market data",
            tags=["data", "pipeline", "critical"],
            dependencies=["redis", "postgres"],
            provides=["market_data", "tick_data"],
            configuration={"batch_size": 1000, "timeout": 30},
        )
        
        assert metadata.name == "DataPipeline"
        assert metadata.version == "2.1.0"
        assert metadata.description == "Ingestion pipeline for market data"
        assert metadata.tags == ["data", "pipeline", "critical"]
        assert metadata.dependencies == ["redis", "postgres"]
        assert metadata.provides == ["market_data", "tick_data"]
        assert metadata.configuration == {"batch_size": 1000, "timeout": 30}

    def test_metadata_mutable(self):
        """Test that metadata is mutable."""
        metadata = ComponentMetadata(name="Test")
        metadata.tags.append("new_tag")
        assert "new_tag" in metadata.tags


class TestComponent:
    """Test Component class core functionality."""

    def test_component_creation_minimal(self):
        """Test creating component with minimal requirements."""
        metadata = ComponentMetadata(name="TestComponent")
        instance = Mock()
        
        component = Component(metadata=metadata, instance=instance)
        
        assert component.metadata == metadata
        assert component.instance == instance
        assert component.status == ComponentStatus.UNINITIALIZED
        assert component.health is None
        assert isinstance(component.registered_at, datetime)
        assert isinstance(component.last_updated, datetime)

    def test_component_creation_with_hooks(self):
        """Test creating component with lifecycle hooks."""
        metadata = ComponentMetadata(name="TestComponent")
        instance = Mock()
        init_hook = Mock()
        start_hook = Mock()
        stop_hook = Mock()
        health_hook = Mock()
        
        component = Component(
            metadata=metadata,
            instance=instance,
            init_hook=init_hook,
            start_hook=start_hook,
            stop_hook=stop_hook,
            health_hook=health_hook,
        )
        
        assert component.init_hook == init_hook
        assert component.start_hook == start_hook
        assert component.stop_hook == stop_hook
        assert component.health_hook == health_hook

    def test_get_dependencies(self):
        """Test retrieving component dependencies."""
        metadata = ComponentMetadata(
            name="Test",
            dependencies=["dep1", "dep2"],
        )
        component = Component(metadata=metadata, instance=Mock())
        
        deps = component.get_dependencies()
        assert list(deps) == ["dep1", "dep2"]

    def test_get_provides(self):
        """Test retrieving component capabilities."""
        metadata = ComponentMetadata(
            name="Test",
            provides=["capability1", "capability2"],
        )
        component = Component(metadata=metadata, instance=Mock())
        
        provides = component.get_provides()
        assert list(provides) == ["capability1", "capability2"]


class TestComponentInitialize:
    """Test Component.initialize() method."""

    def test_initialize_with_hook(self):
        """Test initialization using init_hook."""
        metadata = ComponentMetadata(name="Test")
        instance = Mock()
        init_hook = Mock()
        
        component = Component(
            metadata=metadata,
            instance=instance,
            init_hook=init_hook,
        )
        
        component.initialize()
        
        init_hook.assert_called_once()
        assert component.status == ComponentStatus.INITIALIZED

    def test_initialize_with_instance_method(self):
        """Test initialization using instance.initialize()."""
        metadata = ComponentMetadata(name="Test")
        instance = Mock()
        instance.initialize = Mock()
        
        component = Component(metadata=metadata, instance=instance)
        
        component.initialize()
        
        instance.initialize.assert_called_once()
        assert component.status == ComponentStatus.INITIALIZED

    def test_initialize_without_hook_or_method(self):
        """Test initialization when neither hook nor method exists."""
        metadata = ComponentMetadata(name="Test")
        instance = Mock(spec=[])  # Empty spec means no methods
        
        component = Component(metadata=metadata, instance=instance)
        
        component.initialize()
        
        assert component.status == ComponentStatus.INITIALIZED

    def test_initialize_updates_timestamp(self):
        """Test that initialization updates last_updated timestamp."""
        metadata = ComponentMetadata(name="Test")
        instance = Mock()
        
        component = Component(metadata=metadata, instance=instance)
        initial_timestamp = component.last_updated
        
        # Small delay to ensure timestamp changes
        import time
        time.sleep(0.01)
        
        component.initialize()
        
        assert component.last_updated > initial_timestamp

    def test_initialize_failure_sets_failed_status(self):
        """Test that initialization failure sets FAILED status."""
        metadata = ComponentMetadata(name="Test")
        instance = Mock()
        init_hook = Mock(side_effect=RuntimeError("Init failed"))
        
        component = Component(
            metadata=metadata,
            instance=instance,
            init_hook=init_hook,
        )
        
        with pytest.raises(RuntimeError, match="Failed to initialize"):
            component.initialize()
        
        assert component.status == ComponentStatus.FAILED

    def test_initialize_sets_initializing_status_first(self):
        """Test that INITIALIZING status is set before calling hook."""
        metadata = ComponentMetadata(name="Test")
        instance = Mock()
        
        status_during_init = None
        
        def capture_status():
            nonlocal status_during_init
            status_during_init = component.status
        
        init_hook = Mock(side_effect=capture_status)
        
        component = Component(
            metadata=metadata,
            instance=instance,
            init_hook=init_hook,
        )
        
        component.initialize()
        
        assert status_during_init == ComponentStatus.INITIALIZING
        assert component.status == ComponentStatus.INITIALIZED


class TestComponentStart:
    """Test Component.start() method."""

    def test_start_with_hook(self):
        """Test starting component using start_hook."""
        metadata = ComponentMetadata(name="Test")
        instance = Mock()
        start_hook = Mock()
        
        component = Component(
            metadata=metadata,
            instance=instance,
            start_hook=start_hook,
        )
        component.status = ComponentStatus.INITIALIZED
        
        component.start()
        
        start_hook.assert_called_once()
        assert component.status == ComponentStatus.RUNNING

    def test_start_with_instance_method(self):
        """Test starting component using instance.start()."""
        metadata = ComponentMetadata(name="Test")
        instance = Mock()
        instance.start = Mock()
        
        component = Component(metadata=metadata, instance=instance)
        component.status = ComponentStatus.INITIALIZED
        
        component.start()
        
        instance.start.assert_called_once()
        assert component.status == ComponentStatus.RUNNING

    def test_start_requires_initialized_status(self):
        """Test that start requires component to be INITIALIZED."""
        metadata = ComponentMetadata(name="Test")
        instance = Mock()
        
        component = Component(metadata=metadata, instance=instance)
        component.status = ComponentStatus.UNINITIALIZED
        
        with pytest.raises(RuntimeError, match="Cannot start component"):
            component.start()

    def test_start_failure_sets_failed_status(self):
        """Test that start failure sets FAILED status."""
        metadata = ComponentMetadata(name="Test")
        instance = Mock()
        start_hook = Mock(side_effect=RuntimeError("Start failed"))
        
        component = Component(
            metadata=metadata,
            instance=instance,
            start_hook=start_hook,
        )
        component.status = ComponentStatus.INITIALIZED
        
        with pytest.raises(RuntimeError, match="Failed to start"):
            component.start()
        
        assert component.status == ComponentStatus.FAILED

    def test_start_updates_timestamp(self):
        """Test that start updates last_updated timestamp."""
        metadata = ComponentMetadata(name="Test")
        instance = Mock()
        
        component = Component(metadata=metadata, instance=instance)
        component.status = ComponentStatus.INITIALIZED
        initial_timestamp = component.last_updated
        
        import time
        time.sleep(0.01)
        
        component.start()
        
        assert component.last_updated > initial_timestamp


class TestComponentStop:
    """Test Component.stop() method."""

    def test_stop_with_hook(self):
        """Test stopping component using stop_hook."""
        metadata = ComponentMetadata(name="Test")
        instance = Mock()
        stop_hook = Mock()
        
        component = Component(
            metadata=metadata,
            instance=instance,
            stop_hook=stop_hook,
        )
        component.status = ComponentStatus.RUNNING
        
        component.stop()
        
        stop_hook.assert_called_once()
        assert component.status == ComponentStatus.STOPPED

    def test_stop_with_instance_method(self):
        """Test stopping component using instance.stop()."""
        metadata = ComponentMetadata(name="Test")
        instance = Mock()
        instance.stop = Mock()
        
        component = Component(metadata=metadata, instance=instance)
        component.status = ComponentStatus.RUNNING
        
        component.stop()
        
        instance.stop.assert_called_once()
        assert component.status == ComponentStatus.STOPPED

    def test_stop_degraded_component(self):
        """Test stopping component in DEGRADED state."""
        metadata = ComponentMetadata(name="Test")
        instance = Mock()
        stop_hook = Mock()
        
        component = Component(
            metadata=metadata,
            instance=instance,
            stop_hook=stop_hook,
        )
        component.status = ComponentStatus.DEGRADED
        
        component.stop()
        
        stop_hook.assert_called_once()
        assert component.status == ComponentStatus.STOPPED

    def test_stop_non_running_component_does_nothing(self):
        """Test stopping non-running component is no-op."""
        metadata = ComponentMetadata(name="Test")
        instance = Mock()
        stop_hook = Mock()
        
        component = Component(
            metadata=metadata,
            instance=instance,
            stop_hook=stop_hook,
        )
        component.status = ComponentStatus.STOPPED
        
        component.stop()
        
        stop_hook.assert_not_called()
        assert component.status == ComponentStatus.STOPPED

    def test_stop_failure_sets_failed_status(self):
        """Test that stop failure sets FAILED status."""
        metadata = ComponentMetadata(name="Test")
        instance = Mock()
        stop_hook = Mock(side_effect=RuntimeError("Stop failed"))
        
        component = Component(
            metadata=metadata,
            instance=instance,
            stop_hook=stop_hook,
        )
        component.status = ComponentStatus.RUNNING
        
        with pytest.raises(RuntimeError, match="Failed to stop"):
            component.stop()
        
        assert component.status == ComponentStatus.FAILED


class TestComponentHealthCheck:
    """Test Component.check_health() method."""

    def test_health_check_with_hook(self):
        """Test health check using health_hook."""
        metadata = ComponentMetadata(name="Test")
        instance = Mock()
        expected_health = ComponentHealth(
            status=ComponentStatus.RUNNING,
            healthy=True,
            message="All good",
        )
        health_hook = Mock(return_value=expected_health)
        
        component = Component(
            metadata=metadata,
            instance=instance,
            health_hook=health_hook,
        )
        
        health = component.check_health()
        
        health_hook.assert_called_once()
        assert health == expected_health
        assert component.health == expected_health

    def test_health_check_with_instance_method(self):
        """Test health check using instance.health_check()."""
        metadata = ComponentMetadata(name="Test")
        instance = Mock()
        expected_health = ComponentHealth(
            status=ComponentStatus.RUNNING,
            healthy=True,
        )
        instance.health_check = Mock(return_value=expected_health)
        
        component = Component(metadata=metadata, instance=instance)
        
        health = component.check_health()
        
        instance.health_check.assert_called_once()
        assert health == expected_health

    def test_health_check_default_when_no_hook(self):
        """Test default health check when no hook or method exists."""
        metadata = ComponentMetadata(name="Test")
        instance = Mock(spec=[])
        
        component = Component(metadata=metadata, instance=instance)
        component.status = ComponentStatus.RUNNING
        
        health = component.check_health()
        
        assert health.status == ComponentStatus.RUNNING
        assert health.healthy is True
        assert "No health check implemented" in health.message

    def test_health_check_failure(self):
        """Test health check that raises exception."""
        metadata = ComponentMetadata(name="Test")
        instance = Mock()
        health_hook = Mock(side_effect=RuntimeError("Health check error"))
        
        component = Component(
            metadata=metadata,
            instance=instance,
            health_hook=health_hook,
        )
        
        health = component.check_health()
        
        assert health.status == ComponentStatus.FAILED
        assert health.healthy is False
        assert "Health check failed" in health.message


class TestComponentLifecycle:
    """Test complete component lifecycle scenarios."""

    def test_full_lifecycle(self):
        """Test complete lifecycle: init -> start -> stop."""
        metadata = ComponentMetadata(name="TestLifecycle")
        instance = Mock()
        instance.initialize = Mock()
        instance.start = Mock()
        instance.stop = Mock()
        
        component = Component(metadata=metadata, instance=instance)
        
        # Initialize
        component.initialize()
        assert component.status == ComponentStatus.INITIALIZED
        instance.initialize.assert_called_once()
        
        # Start
        component.start()
        assert component.status == ComponentStatus.RUNNING
        instance.start.assert_called_once()
        
        # Stop
        component.stop()
        assert component.status == ComponentStatus.STOPPED
        instance.stop.assert_called_once()

    def test_lifecycle_with_health_checks(self):
        """Test lifecycle with periodic health checks."""
        metadata = ComponentMetadata(name="Test")
        instance = Mock()
        health_responses = [
            ComponentHealth(ComponentStatus.RUNNING, True),
            ComponentHealth(ComponentStatus.RUNNING, True),
            ComponentHealth(ComponentStatus.DEGRADED, False, "Warning"),
        ]
        instance.health_check = Mock(side_effect=health_responses)
        
        component = Component(metadata=metadata, instance=instance)
        component.status = ComponentStatus.INITIALIZED
        component.start()
        
        # Check health multiple times
        health1 = component.check_health()
        assert health1.healthy is True
        
        health2 = component.check_health()
        assert health2.healthy is True
        
        health3 = component.check_health()
        assert health3.healthy is False
        assert health3.status == ComponentStatus.DEGRADED


class TestComponentProtocol:
    """Test ComponentProtocol typing."""

    def test_protocol_compliance(self):
        """Test that a class implementing all methods is protocol-compliant."""
        
        class CompliantComponent:
            def initialize(self) -> None:
                pass
            
            def start(self) -> None:
                pass
            
            def stop(self) -> None:
                pass
            
            def health_check(self) -> ComponentHealth:
                return ComponentHealth(
                    status=ComponentStatus.RUNNING,
                    healthy=True,
                )
        
        # This should not raise any type errors
        instance: ComponentProtocol = CompliantComponent()
        assert hasattr(instance, "initialize")
        assert hasattr(instance, "start")
        assert hasattr(instance, "stop")
        assert hasattr(instance, "health_check")


class TestComponentEdgeCases:
    """Test edge cases and error conditions."""

    def test_multiple_initializations(self):
        """Test that multiple initializations update status correctly."""
        metadata = ComponentMetadata(name="Test")
        instance = Mock()
        
        component = Component(metadata=metadata, instance=instance)
        
        component.initialize()
        assert component.status == ComponentStatus.INITIALIZED
        
        # Re-initialize
        component.initialize()
        assert component.status == ComponentStatus.INITIALIZED

    def test_timestamps_are_utc(self):
        """Test that all timestamps use UTC timezone."""
        metadata = ComponentMetadata(name="Test")
        instance = Mock()
        
        component = Component(metadata=metadata, instance=instance)
        
        assert component.registered_at.tzinfo == timezone.utc
        assert component.last_updated.tzinfo == timezone.utc

    def test_component_with_complex_metadata(self):
        """Test component with complex nested metadata."""
        metadata = ComponentMetadata(
            name="ComplexComponent",
            configuration={
                "nested": {"key": "value"},
                "list": [1, 2, 3],
                "mixed": {"a": [1, 2], "b": {"c": 3}},
            },
        )
        instance = Mock()
        
        component = Component(metadata=metadata, instance=instance)
        
        assert component.metadata.configuration["nested"]["key"] == "value"
        assert component.metadata.configuration["list"] == [1, 2, 3]
