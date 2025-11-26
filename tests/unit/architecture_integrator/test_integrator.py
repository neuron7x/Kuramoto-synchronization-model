# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for core/architecture_integrator/integrator.py module."""

from __future__ import annotations

import pytest

from core.architecture_integrator.component import (
    ComponentHealth,
    ComponentStatus,
)
from core.architecture_integrator.integrator import ArchitectureIntegrator


class MockService:
    """Mock service for testing."""

    def __init__(
        self,
        *,
        fail_init: bool = False,
        fail_start: bool = False,
        fail_stop: bool = False,
        healthy: bool = True,
    ):
        self.initialized = False
        self.started = False
        self.stopped = False
        self._fail_init = fail_init
        self._fail_start = fail_start
        self._fail_stop = fail_stop
        self._healthy = healthy

    def initialize(self) -> None:
        if self._fail_init:
            raise ValueError("Init failed")
        self.initialized = True

    def start(self) -> None:
        if self._fail_start:
            raise ValueError("Start failed")
        self.started = True

    def stop(self) -> None:
        if self._fail_stop:
            raise ValueError("Stop failed")
        self.stopped = True

    def health_check(self) -> ComponentHealth:
        return ComponentHealth(
            status=(
                ComponentStatus.RUNNING if self._healthy else ComponentStatus.DEGRADED
            ),
            healthy=self._healthy,
            message="OK" if self._healthy else "Unhealthy",
        )


class TestArchitectureIntegrator:
    """Tests for ArchitectureIntegrator class."""

    def test_initialization(self) -> None:
        """Test integrator initialization."""
        integrator = ArchitectureIntegrator()
        assert integrator.registry is not None
        assert integrator.lifecycle is not None
        assert integrator.validator is not None

    def test_register_component_basic(self) -> None:
        """Test basic component registration."""
        integrator = ArchitectureIntegrator()
        service = MockService()

        integrator.register_component(name="test", instance=service)

        assert "test" in integrator.registry
        component = integrator.get_component("test")
        assert component.metadata.name == "test"

    def test_register_component_full(self) -> None:
        """Test component registration with all parameters."""
        integrator = ArchitectureIntegrator()
        service = MockService()

        integrator.register_component(
            name="service",
            instance=service,
            version="2.0.0",
            description="Test service",
            tags=["core", "data"],
            dependencies=["db"],
            provides=["api"],
            configuration={"port": 8080},
        )

        component = integrator.get_component("service")
        assert component.metadata.version == "2.0.0"
        assert component.metadata.description == "Test service"
        assert "core" in component.metadata.tags
        assert "db" in component.metadata.dependencies
        assert "api" in component.metadata.provides
        assert component.metadata.configuration["port"] == 8080

    def test_register_component_with_hooks(self) -> None:
        """Test component registration with custom hooks."""
        integrator = ArchitectureIntegrator()
        hook_calls = []

        def init_hook():
            hook_calls.append("init")

        def start_hook():
            hook_calls.append("start")

        def stop_hook():
            hook_calls.append("stop")

        integrator.register_component(
            name="test",
            instance=object(),
            init_hook=init_hook,
            start_hook=start_hook,
            stop_hook=stop_hook,
        )

        component = integrator.get_component("test")
        component.initialize()
        component.start()
        component.stop()

        assert hook_calls == ["init", "start", "stop"]

    def test_register_duplicate_raises(self) -> None:
        """Test registering duplicate component raises error."""
        integrator = ArchitectureIntegrator()

        integrator.register_component(name="test", instance=object())

        with pytest.raises(ValueError, match="already registered"):
            integrator.register_component(name="test", instance=object())

    def test_unregister_component(self) -> None:
        """Test unregistering a component."""
        integrator = ArchitectureIntegrator()
        service = MockService()

        integrator.register_component(name="test", instance=service)
        integrator.unregister_component("test")

        assert "test" not in integrator.registry

    def test_unregister_stops_running_component(self) -> None:
        """Test unregister stops running component first."""
        integrator = ArchitectureIntegrator()
        service = MockService()

        integrator.register_component(name="test", instance=service)
        integrator.initialize_component("test")
        integrator.start_component("test")
        integrator.unregister_component("test")

        assert service.stopped is True

    def test_get_component_not_found(self) -> None:
        """Test get_component raises for nonexistent component."""
        integrator = ArchitectureIntegrator()

        with pytest.raises(KeyError):
            integrator.get_component("nonexistent")

    def test_list_components(self) -> None:
        """Test listing all components."""
        integrator = ArchitectureIntegrator()

        integrator.register_component(name="a", instance=object())
        integrator.register_component(name="b", instance=object())
        integrator.register_component(name="c", instance=object())

        components = integrator.list_components()
        names = [c.metadata.name for c in components]

        assert len(components) == 3
        assert "a" in names
        assert "b" in names
        assert "c" in names

    def test_initialize_all(self) -> None:
        """Test initializing all components."""
        integrator = ArchitectureIntegrator()
        service1 = MockService()
        service2 = MockService()

        integrator.register_component(name="svc1", instance=service1)
        integrator.register_component(name="svc2", instance=service2)

        result = integrator.initialize_all()

        assert len(result) == 2
        assert service1.initialized is True
        assert service2.initialized is True

    def test_start_all(self) -> None:
        """Test starting all components."""
        integrator = ArchitectureIntegrator()
        service = MockService()

        integrator.register_component(name="test", instance=service)
        integrator.initialize_all()
        result = integrator.start_all()

        assert len(result) == 1
        assert service.started is True

    def test_stop_all(self) -> None:
        """Test stopping all components."""
        integrator = ArchitectureIntegrator()
        service = MockService()

        integrator.register_component(name="test", instance=service)
        integrator.initialize_all()
        integrator.start_all()
        result = integrator.stop_all()

        assert len(result) == 1
        assert service.stopped is True

    def test_initialize_component(self) -> None:
        """Test initializing a specific component."""
        integrator = ArchitectureIntegrator()
        service = MockService()

        integrator.register_component(name="test", instance=service)
        integrator.initialize_component("test")

        assert service.initialized is True

    def test_start_component(self) -> None:
        """Test starting a specific component."""
        integrator = ArchitectureIntegrator()
        service = MockService()

        integrator.register_component(name="test", instance=service)
        integrator.initialize_component("test")
        integrator.start_component("test")

        assert service.started is True

    def test_stop_component(self) -> None:
        """Test stopping a specific component."""
        integrator = ArchitectureIntegrator()
        service = MockService()

        integrator.register_component(name="test", instance=service)
        integrator.initialize_all()
        integrator.start_all()
        integrator.stop_component("test")

        assert service.stopped is True

    def test_restart_component(self) -> None:
        """Test restarting a specific component."""
        integrator = ArchitectureIntegrator()
        service = MockService()

        integrator.register_component(name="test", instance=service)
        integrator.initialize_all()
        integrator.start_all()
        integrator.restart_component("test")

        assert service.stopped is True
        assert service.initialized is True
        assert service.started is True

    def test_check_component_health(self) -> None:
        """Test checking component health."""
        integrator = ArchitectureIntegrator()
        service = MockService(healthy=True)

        integrator.register_component(name="test", instance=service)

        health = integrator.check_component_health("test")
        assert health.healthy is True

    def test_aggregate_health(self) -> None:
        """Test aggregating health from all components."""
        integrator = ArchitectureIntegrator()
        service1 = MockService(healthy=True)
        service2 = MockService(healthy=False)

        integrator.register_component(name="healthy", instance=service1)
        integrator.register_component(name="unhealthy", instance=service2)

        health_map = integrator.aggregate_health()

        assert len(health_map) == 2
        assert health_map["healthy"].healthy is True
        assert health_map["unhealthy"].healthy is False

    def test_is_system_healthy_all_healthy(self) -> None:
        """Test is_system_healthy when all components healthy."""
        integrator = ArchitectureIntegrator()
        service1 = MockService(healthy=True)
        service2 = MockService(healthy=True)

        integrator.register_component(name="svc1", instance=service1)
        integrator.register_component(name="svc2", instance=service2)

        assert integrator.is_system_healthy() is True

    def test_is_system_healthy_some_unhealthy(self) -> None:
        """Test is_system_healthy when some components unhealthy."""
        integrator = ArchitectureIntegrator()
        service1 = MockService(healthy=True)
        service2 = MockService(healthy=False)

        integrator.register_component(name="svc1", instance=service1)
        integrator.register_component(name="svc2", instance=service2)

        assert integrator.is_system_healthy() is False

    def test_validate_architecture(self) -> None:
        """Test architecture validation."""
        integrator = ArchitectureIntegrator()
        integrator.register_component(name="test", instance=object())

        result = integrator.validate_architecture()

        assert result is not None
        assert isinstance(result.passed, bool)

    def test_validate_component(self) -> None:
        """Test validating a specific component."""
        integrator = ArchitectureIntegrator()
        integrator.register_component(name="test", instance=object())

        result = integrator.validate_component("test")

        assert result.passed is True

    def test_add_validation_rule(self) -> None:
        """Test adding custom validation rule."""
        integrator = ArchitectureIntegrator()

        def custom_rule(registry):
            return []

        integrator.add_validation_rule(custom_rule)
        # Rule should be added (tested by running validation)
        result = integrator.validate_architecture()
        assert result is not None

    def test_event_handlers(self) -> None:
        """Test event handlers."""
        integrator = ArchitectureIntegrator()
        events = []

        def handler(**kwargs):
            events.append(kwargs)

        integrator.on("component_registered", handler)
        integrator.register_component(name="test", instance=object())

        assert len(events) == 1
        assert events[0]["name"] == "test"

    def test_multiple_event_handlers(self) -> None:
        """Test multiple handlers for same event."""
        integrator = ArchitectureIntegrator()
        calls = []

        def handler1(**kwargs):
            calls.append("h1")

        def handler2(**kwargs):
            calls.append("h2")

        integrator.on("component_registered", handler1)
        integrator.on("component_registered", handler2)
        integrator.register_component(name="test", instance=object())

        assert calls == ["h1", "h2"]

    def test_event_handler_failure_does_not_propagate(self) -> None:
        """Test that failing event handler doesn't stop execution."""
        integrator = ArchitectureIntegrator()

        def failing_handler(**kwargs):
            raise ValueError("Handler error")

        integrator.on("component_registered", failing_handler)
        # Should not raise
        integrator.register_component(name="test", instance=object())

    def test_get_dependency_graph(self) -> None:
        """Test getting dependency graph."""
        integrator = ArchitectureIntegrator()

        integrator.register_component(name="a", instance=object(), dependencies=["b"])
        integrator.register_component(name="b", instance=object())

        graph = integrator.get_dependency_graph()

        assert graph["a"] == ["b"]
        assert graph["b"] == []

    def test_get_initialization_order(self) -> None:
        """Test getting initialization order."""
        integrator = ArchitectureIntegrator()

        integrator.register_component(name="a", instance=object(), dependencies=["b"])
        integrator.register_component(name="b", instance=object(), dependencies=["c"])
        integrator.register_component(name="c", instance=object())

        order = integrator.get_initialization_order()

        assert order.index("c") < order.index("b")
        assert order.index("b") < order.index("a")

    def test_get_status_summary(self) -> None:
        """Test getting status summary."""
        integrator = ArchitectureIntegrator()

        integrator.register_component(name="a", instance=MockService())
        integrator.register_component(name="b", instance=MockService())
        integrator.register_component(name="c", instance=MockService())

        summary = integrator.get_status_summary()

        assert summary["uninitialized"] == 3

    def test_clear(self) -> None:
        """Test clearing all components."""
        integrator = ArchitectureIntegrator()
        service = MockService()

        integrator.register_component(name="test", instance=service)
        integrator.initialize_all()
        integrator.start_all()

        integrator.clear()

        assert len(integrator.list_components()) == 0
        assert service.stopped is True

    def test_lifecycle_events(self) -> None:
        """Test lifecycle events are emitted."""
        integrator = ArchitectureIntegrator()
        events = []

        integrator.on("initialization_started", lambda: events.append("init_start"))
        integrator.on(
            "initialization_completed", lambda **kw: events.append("init_done")
        )
        integrator.on("startup_started", lambda: events.append("start_start"))
        integrator.on("startup_completed", lambda **kw: events.append("start_done"))
        integrator.on("shutdown_started", lambda: events.append("stop_start"))
        integrator.on("shutdown_completed", lambda **kw: events.append("stop_done"))

        integrator.register_component(name="test", instance=MockService())
        integrator.initialize_all()
        integrator.start_all()
        integrator.stop_all()

        assert "init_start" in events
        assert "init_done" in events
        assert "start_start" in events
        assert "start_done" in events
        assert "stop_start" in events
        assert "stop_done" in events

    def test_initialize_all_failure_emits_event(self) -> None:
        """Test that initialization failure emits event."""
        integrator = ArchitectureIntegrator()
        events = []

        integrator.on(
            "initialization_failed", lambda **kw: events.append(kw.get("error"))
        )

        service = MockService(fail_init=True)
        integrator.register_component(name="test", instance=service)

        with pytest.raises(RuntimeError):
            integrator.initialize_all()

        assert len(events) == 1

    def test_start_all_failure_emits_event(self) -> None:
        """Test that startup failure emits event."""
        integrator = ArchitectureIntegrator()
        events = []

        integrator.on("startup_failed", lambda **kw: events.append(kw.get("error")))

        service = MockService(fail_start=True)
        integrator.register_component(name="test", instance=service)
        integrator.initialize_all()

        with pytest.raises(RuntimeError):
            integrator.start_all()

        assert len(events) == 1
