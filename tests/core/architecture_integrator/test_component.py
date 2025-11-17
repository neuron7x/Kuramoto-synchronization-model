"""Tests for component abstraction."""

import pytest

from core.architecture_integrator.component import (
    Component,
    ComponentHealth,
    ComponentMetadata,
    ComponentStatus,
)


class MockComponent:
    """Mock component for testing."""

    def __init__(self):
        self.initialized = False
        self.started = False
        self.stopped = False

    def initialize(self):
        self.initialized = True

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def health_check(self):
        return ComponentHealth(
            status=ComponentStatus.RUNNING,
            healthy=True,
            message="All systems operational",
        )


def test_component_metadata_creation():
    """Test creating component metadata."""
    metadata = ComponentMetadata(
        name="test_component",
        version="1.0.0",
        description="Test component",
        tags=["test", "mock"],
        dependencies=["dep1", "dep2"],
        provides=["capability1"],
    )

    assert metadata.name == "test_component"
    assert metadata.version == "1.0.0"
    assert "test" in metadata.tags
    assert "dep1" in metadata.dependencies
    assert "capability1" in metadata.provides


def test_component_initialization():
    """Test component initialization."""
    mock = MockComponent()
    metadata = ComponentMetadata(name="test")
    component = Component(metadata=metadata, instance=mock)

    assert component.status == ComponentStatus.UNINITIALIZED

    component.initialize()

    assert component.status == ComponentStatus.INITIALIZED
    assert mock.initialized


def test_component_lifecycle():
    """Test full component lifecycle."""
    mock = MockComponent()
    metadata = ComponentMetadata(name="test")
    component = Component(metadata=metadata, instance=mock)

    # Initialize
    component.initialize()
    assert component.status == ComponentStatus.INITIALIZED

    # Start
    component.start()
    assert component.status == ComponentStatus.RUNNING
    assert mock.started

    # Stop
    component.stop()
    assert component.status == ComponentStatus.STOPPED
    assert mock.stopped


def test_component_health_check():
    """Test component health checking."""
    mock = MockComponent()
    metadata = ComponentMetadata(name="test")
    component = Component(metadata=metadata, instance=mock)

    component.initialize()
    component.start()

    health = component.check_health()

    assert health.status == ComponentStatus.RUNNING
    assert health.healthy
    assert "operational" in health.message.lower()


def test_component_with_hooks():
    """Test component with custom lifecycle hooks."""
    init_called = []
    start_called = []
    stop_called = []

    def init_hook():
        init_called.append(True)

    def start_hook():
        start_called.append(True)

    def stop_hook():
        stop_called.append(True)

    metadata = ComponentMetadata(name="test")
    component = Component(
        metadata=metadata,
        instance=None,
        init_hook=init_hook,
        start_hook=start_hook,
        stop_hook=stop_hook,
    )

    component.initialize()
    assert len(init_called) == 1

    component.start()
    assert len(start_called) == 1

    component.stop()
    assert len(stop_called) == 1


def test_component_cannot_start_before_init():
    """Test that component cannot start before initialization."""
    mock = MockComponent()
    metadata = ComponentMetadata(name="test")
    component = Component(metadata=metadata, instance=mock)

    with pytest.raises(RuntimeError, match="Cannot start component"):
        component.start()


def test_component_health_operational():
    """Test health operational check."""
    health = ComponentHealth(
        status=ComponentStatus.RUNNING,
        healthy=True,
    )
    assert health.is_operational()

    health = ComponentHealth(
        status=ComponentStatus.DEGRADED,
        healthy=False,
    )
    assert health.is_operational()

    health = ComponentHealth(
        status=ComponentStatus.STOPPED,
        healthy=False,
    )
    assert not health.is_operational()


def test_component_health_failed():
    """Test health failed check."""
    health = ComponentHealth(
        status=ComponentStatus.FAILED,
        healthy=False,
    )
    assert health.is_failed()

    health = ComponentHealth(
        status=ComponentStatus.RUNNING,
        healthy=True,
    )
    assert not health.is_failed()


def test_component_initialization_failure():
    """Test component initialization failure handling."""

    class FailingComponent:
        def initialize(self):
            raise RuntimeError("Init failed")

    metadata = ComponentMetadata(name="failing")
    component = Component(metadata=metadata, instance=FailingComponent())

    with pytest.raises(RuntimeError, match="Failed to initialize"):
        component.initialize()

    assert component.status == ComponentStatus.FAILED
