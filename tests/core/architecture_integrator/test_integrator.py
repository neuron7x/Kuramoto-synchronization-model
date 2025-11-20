"""Tests for the main ArchitectureIntegrator."""

from core.architecture_integrator import (
    ArchitectureIntegrator,
    ComponentHealth,
    ComponentStatus,
)


class TestComponent:
    """Test component implementation."""

    def __init__(self, name: str):
        self.name = name
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
            message="OK",
        )


def test_integrator_initialization():
    """Test creating an ArchitectureIntegrator."""
    integrator = ArchitectureIntegrator()

    assert integrator.registry is not None
    assert integrator.lifecycle is not None
    assert integrator.validator is not None


def test_integrator_register_component():
    """Test registering a component."""
    integrator = ArchitectureIntegrator()
    component = TestComponent("test")

    integrator.register_component(
        name="test",
        instance=component,
        description="Test component",
    )

    assert integrator.registry.has_component("test")


def test_integrator_unregister_component():
    """Test unregistering a component."""
    integrator = ArchitectureIntegrator()
    component = TestComponent("test")

    integrator.register_component(name="test", instance=component)
    integrator.unregister_component("test")

    assert not integrator.registry.has_component("test")


def test_integrator_initialize_all():
    """Test initializing all components."""
    integrator = ArchitectureIntegrator()

    comp1 = TestComponent("comp1")
    comp2 = TestComponent("comp2")

    integrator.register_component(name="comp1", instance=comp1)
    integrator.register_component(name="comp2", instance=comp2)

    result = integrator.initialize_all()

    assert len(result) == 2
    assert comp1.initialized
    assert comp2.initialized


def test_integrator_start_all():
    """Test starting all components."""
    integrator = ArchitectureIntegrator()

    comp1 = TestComponent("comp1")
    comp2 = TestComponent("comp2")

    integrator.register_component(name="comp1", instance=comp1)
    integrator.register_component(name="comp2", instance=comp2)

    integrator.initialize_all()
    result = integrator.start_all()

    assert len(result) == 2
    assert comp1.started
    assert comp2.started


def test_integrator_stop_all():
    """Test stopping all components."""
    integrator = ArchitectureIntegrator()

    comp1 = TestComponent("comp1")
    comp2 = TestComponent("comp2")

    integrator.register_component(name="comp1", instance=comp1)
    integrator.register_component(name="comp2", instance=comp2)

    integrator.initialize_all()
    integrator.start_all()
    result = integrator.stop_all()

    assert len(result) == 2
    assert comp1.stopped
    assert comp2.stopped


def test_integrator_lifecycle_with_dependencies():
    """Test lifecycle respects dependencies."""
    integrator = ArchitectureIntegrator()

    comp1 = TestComponent("comp1")
    comp2 = TestComponent("comp2")

    integrator.register_component(name="comp1", instance=comp1)
    integrator.register_component(
        name="comp2",
        instance=comp2,
        dependencies=["comp1"],
    )

    integrator.initialize_all()

    # comp1 should be initialized before comp2
    assert comp1.initialized
    assert comp2.initialized


def test_integrator_health_check():
    """Test checking component health."""
    integrator = ArchitectureIntegrator()
    component = TestComponent("test")

    integrator.register_component(name="test", instance=component)
    integrator.initialize_all()
    integrator.start_all()

    health = integrator.check_component_health("test")

    assert health.healthy
    assert health.status == ComponentStatus.RUNNING


def test_integrator_aggregate_health():
    """Test aggregating health from all components."""
    integrator = ArchitectureIntegrator()

    comp1 = TestComponent("comp1")
    comp2 = TestComponent("comp2")

    integrator.register_component(name="comp1", instance=comp1)
    integrator.register_component(name="comp2", instance=comp2)

    integrator.initialize_all()
    integrator.start_all()

    health_map = integrator.aggregate_health()

    assert len(health_map) == 2
    assert health_map["comp1"].healthy
    assert health_map["comp2"].healthy


def test_integrator_is_system_healthy():
    """Test checking overall system health."""
    integrator = ArchitectureIntegrator()

    comp1 = TestComponent("comp1")
    comp2 = TestComponent("comp2")

    integrator.register_component(name="comp1", instance=comp1)
    integrator.register_component(name="comp2", instance=comp2)

    integrator.initialize_all()
    integrator.start_all()

    assert integrator.is_system_healthy()


def test_integrator_validate_architecture():
    """Test architecture validation."""
    integrator = ArchitectureIntegrator()

    comp1 = TestComponent("comp1")
    integrator.register_component(name="comp1", instance=comp1)

    result = integrator.validate_architecture()

    # Should pass with no blocking issues
    assert result is not None


def test_integrator_validate_component():
    """Test validating a specific component."""
    integrator = ArchitectureIntegrator()

    comp1 = TestComponent("comp1")
    integrator.register_component(name="comp1", instance=comp1)

    integrator.initialize_all()
    integrator.start_all()

    result = integrator.validate_component("comp1")

    assert result.passed


def test_integrator_event_system():
    """Test event handling."""
    integrator = ArchitectureIntegrator()
    events_received = []

    def handler(**kwargs):
        events_received.append(kwargs)

    integrator.on("component_registered", handler)

    comp1 = TestComponent("comp1")
    integrator.register_component(name="comp1", instance=comp1)

    assert len(events_received) == 1
    assert events_received[0]["name"] == "comp1"


def test_integrator_get_dependency_graph():
    """Test getting dependency graph."""
    integrator = ArchitectureIntegrator()

    comp1 = TestComponent("comp1")
    comp2 = TestComponent("comp2")

    integrator.register_component(name="comp1", instance=comp1)
    integrator.register_component(
        name="comp2",
        instance=comp2,
        dependencies=["comp1"],
    )

    graph = integrator.get_dependency_graph()

    assert "comp1" in graph
    assert "comp2" in graph
    assert "comp1" in graph["comp2"]


def test_integrator_get_initialization_order():
    """Test getting initialization order."""
    integrator = ArchitectureIntegrator()

    comp1 = TestComponent("comp1")
    comp2 = TestComponent("comp2")
    comp3 = TestComponent("comp3")

    integrator.register_component(name="comp1", instance=comp1)
    integrator.register_component(
        name="comp2",
        instance=comp2,
        dependencies=["comp1"],
    )
    integrator.register_component(
        name="comp3",
        instance=comp3,
        dependencies=["comp2"],
    )

    order = integrator.get_initialization_order()

    assert order.index("comp1") < order.index("comp2")
    assert order.index("comp2") < order.index("comp3")


def test_integrator_get_status_summary():
    """Test getting status summary."""
    integrator = ArchitectureIntegrator()

    comp1 = TestComponent("comp1")
    comp2 = TestComponent("comp2")

    integrator.register_component(name="comp1", instance=comp1)
    integrator.register_component(name="comp2", instance=comp2)

    integrator.initialize_all()

    summary = integrator.get_status_summary()

    assert summary["initialized"] == 2
    assert summary["uninitialized"] == 0


def test_integrator_restart_component():
    """Test restarting a component."""
    integrator = ArchitectureIntegrator()
    component = TestComponent("test")

    integrator.register_component(name="test", instance=component)
    integrator.initialize_all()
    integrator.start_all()

    assert component.started

    # Reset for test
    component.started = False
    component.initialized = False

    integrator.restart_component("test")

    # Should be reinitialized and started
    assert component.initialized
    assert component.started


def test_integrator_clear():
    """Test clearing all components."""
    integrator = ArchitectureIntegrator()

    comp1 = TestComponent("comp1")
    comp2 = TestComponent("comp2")

    integrator.register_component(name="comp1", instance=comp1)
    integrator.register_component(name="comp2", instance=comp2)

    assert len(integrator.list_components()) == 2

    integrator.clear()

    assert len(integrator.list_components()) == 0


def test_integrator_with_custom_hooks():
    """Test component registration with custom hooks."""
    integrator = ArchitectureIntegrator()
    calls = []

    def init_hook():
        calls.append("init")

    def start_hook():
        calls.append("start")

    def stop_hook():
        calls.append("stop")

    integrator.register_component(
        name="test",
        instance=None,
        init_hook=init_hook,
        start_hook=start_hook,
        stop_hook=stop_hook,
    )

    integrator.initialize_all()
    integrator.start_all()
    integrator.stop_all()

    assert calls == ["init", "start", "stop"]
