# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for core/architecture_integrator/lifecycle.py module."""

from __future__ import annotations

import pytest

from core.architecture_integrator.component import Component, ComponentMetadata, ComponentStatus
from core.architecture_integrator.lifecycle import LifecycleManager
from core.architecture_integrator.registry import ComponentRegistry


class MockComponent:
    """Mock component for testing."""

    def __init__(self, *, fail_init: bool = False, fail_start: bool = False, fail_stop: bool = False):
        self.initialized = False
        self.started = False
        self.stopped = False
        self._fail_init = fail_init
        self._fail_start = fail_start
        self._fail_stop = fail_stop

    def initialize(self) -> None:
        if self._fail_init:
            raise ValueError("Initialization failed")
        self.initialized = True

    def start(self) -> None:
        if self._fail_start:
            raise ValueError("Start failed")
        self.started = True

    def stop(self) -> None:
        if self._fail_stop:
            raise ValueError("Stop failed")
        self.stopped = True


class TestLifecycleManager:
    """Tests for LifecycleManager class."""

    def test_initialization(self) -> None:
        """Test lifecycle manager initialization."""
        registry = ComponentRegistry()
        manager = LifecycleManager(registry)
        assert manager._registry == registry
        assert manager._on_error is None

    def test_set_error_handler(self) -> None:
        """Test setting error handler."""
        registry = ComponentRegistry()
        manager = LifecycleManager(registry)

        errors = []

        def handler(name: str, exc: Exception) -> None:
            errors.append((name, exc))

        manager.set_error_handler(handler)
        assert manager._on_error == handler

    def test_initialize_all_empty_registry(self) -> None:
        """Test initialize_all with empty registry."""
        registry = ComponentRegistry()
        manager = LifecycleManager(registry)

        result = manager.initialize_all()

        assert result == []

    def test_initialize_all_single_component(self) -> None:
        """Test initialize_all with single component."""
        registry = ComponentRegistry()
        mock = MockComponent()
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=mock)
        registry.register(component)

        manager = LifecycleManager(registry)
        result = manager.initialize_all()

        assert result == ["test"]
        assert mock.initialized is True
        assert component.status == ComponentStatus.INITIALIZED

    def test_initialize_all_respects_dependency_order(self) -> None:
        """Test initialize_all respects dependency order."""
        registry = ComponentRegistry()

        mock_a = MockComponent()
        mock_b = MockComponent()
        mock_c = MockComponent()

        init_order = []

        def track_init(mock, name):
            original = mock.initialize

            def wrapped():
                original()
                init_order.append(name)

            mock.initialize = wrapped

        track_init(mock_a, "a")
        track_init(mock_b, "b")
        track_init(mock_c, "c")

        # c has no deps, b depends on c, a depends on b
        metadata_c = ComponentMetadata(name="c", dependencies=[])
        metadata_b = ComponentMetadata(name="b", dependencies=["c"])
        metadata_a = ComponentMetadata(name="a", dependencies=["b"])

        registry.register(Component(metadata=metadata_c, instance=mock_c))
        registry.register(Component(metadata=metadata_b, instance=mock_b))
        registry.register(Component(metadata=metadata_a, instance=mock_a))

        manager = LifecycleManager(registry)
        manager.initialize_all()

        # Verify order: c before b, b before a
        assert init_order.index("c") < init_order.index("b")
        assert init_order.index("b") < init_order.index("a")

    def test_initialize_all_skip_already_initialized(self) -> None:
        """Test initialize_all skips already initialized components."""
        registry = ComponentRegistry()
        mock = MockComponent()
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=mock)
        component.status = ComponentStatus.INITIALIZED
        registry.register(component)

        manager = LifecycleManager(registry)
        result = manager.initialize_all()

        assert result == []  # Component was already initialized

    def test_initialize_all_failure_stops(self) -> None:
        """Test initialize_all stops on failure by default."""
        registry = ComponentRegistry()
        mock = MockComponent(fail_init=True)
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=mock)
        registry.register(component)

        manager = LifecycleManager(registry)

        with pytest.raises(RuntimeError, match="initialization failed"):
            manager.initialize_all()

    def test_initialize_all_failure_continues(self) -> None:
        """Test initialize_all can continue on failure."""
        registry = ComponentRegistry()

        mock1 = MockComponent(fail_init=True)
        mock2 = MockComponent()

        metadata1 = ComponentMetadata(name="comp1")
        metadata2 = ComponentMetadata(name="comp2")

        registry.register(Component(metadata=metadata1, instance=mock1))
        registry.register(Component(metadata=metadata2, instance=mock2))

        manager = LifecycleManager(registry)
        result = manager.initialize_all(stop_on_error=False)

        # comp2 should still be initialized
        assert "comp2" in result

    def test_initialize_all_calls_error_handler(self) -> None:
        """Test initialize_all calls error handler on failure."""
        registry = ComponentRegistry()
        mock = MockComponent(fail_init=True)
        metadata = ComponentMetadata(name="test")
        registry.register(Component(metadata=metadata, instance=mock))

        manager = LifecycleManager(registry)
        errors = []
        manager.set_error_handler(lambda name, exc: errors.append((name, str(exc))))

        with pytest.raises(RuntimeError):
            manager.initialize_all()

        assert len(errors) == 1
        assert errors[0][0] == "test"

    def test_start_all_empty_registry(self) -> None:
        """Test start_all with empty registry."""
        registry = ComponentRegistry()
        manager = LifecycleManager(registry)

        result = manager.start_all()

        assert result == []

    def test_start_all_starts_initialized_components(self) -> None:
        """Test start_all starts initialized components."""
        registry = ComponentRegistry()
        mock = MockComponent()
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=mock)
        component.status = ComponentStatus.INITIALIZED
        registry.register(component)

        manager = LifecycleManager(registry)
        result = manager.start_all()

        assert result == ["test"]
        assert mock.started is True
        assert component.status == ComponentStatus.RUNNING

    def test_start_all_skips_non_initialized(self) -> None:
        """Test start_all skips non-initialized components."""
        registry = ComponentRegistry()
        mock = MockComponent()
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=mock)
        # Leave as UNINITIALIZED
        registry.register(component)

        manager = LifecycleManager(registry)
        result = manager.start_all()

        assert result == []

    def test_start_all_failure_stops(self) -> None:
        """Test start_all stops on failure by default."""
        registry = ComponentRegistry()
        mock = MockComponent(fail_start=True)
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=mock)
        component.status = ComponentStatus.INITIALIZED
        registry.register(component)

        manager = LifecycleManager(registry)

        with pytest.raises(RuntimeError, match="startup failed"):
            manager.start_all()

    def test_start_all_calls_error_handler(self) -> None:
        """Test start_all calls error handler on failure."""
        registry = ComponentRegistry()
        mock = MockComponent(fail_start=True)
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=mock)
        component.status = ComponentStatus.INITIALIZED
        registry.register(component)

        manager = LifecycleManager(registry)
        errors = []
        manager.set_error_handler(lambda name, exc: errors.append(name))

        with pytest.raises(RuntimeError):
            manager.start_all()

        assert "test" in errors

    def test_stop_all_empty_registry(self) -> None:
        """Test stop_all with empty registry."""
        registry = ComponentRegistry()
        manager = LifecycleManager(registry)

        result = manager.stop_all()

        assert result == []

    def test_stop_all_stops_running_components(self) -> None:
        """Test stop_all stops running components."""
        registry = ComponentRegistry()
        mock = MockComponent()
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=mock)
        component.status = ComponentStatus.RUNNING
        registry.register(component)

        manager = LifecycleManager(registry)
        result = manager.stop_all()

        assert result == ["test"]
        assert mock.stopped is True
        assert component.status == ComponentStatus.STOPPED

    def test_stop_all_stops_degraded_components(self) -> None:
        """Test stop_all also stops degraded components."""
        registry = ComponentRegistry()
        mock = MockComponent()
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=mock)
        component.status = ComponentStatus.DEGRADED
        registry.register(component)

        manager = LifecycleManager(registry)
        result = manager.stop_all()

        assert result == ["test"]

    def test_stop_all_reverse_order(self) -> None:
        """Test stop_all uses reverse dependency order."""
        registry = ComponentRegistry()

        mock_a = MockComponent()
        mock_b = MockComponent()
        mock_c = MockComponent()

        stop_order = []

        def track_stop(mock, name):
            original = mock.stop

            def wrapped():
                original()
                stop_order.append(name)

            mock.stop = wrapped

        track_stop(mock_a, "a")
        track_stop(mock_b, "b")
        track_stop(mock_c, "c")

        # c has no deps, b depends on c, a depends on b
        metadata_c = ComponentMetadata(name="c", dependencies=[])
        metadata_b = ComponentMetadata(name="b", dependencies=["c"])
        metadata_a = ComponentMetadata(name="a", dependencies=["b"])

        comp_c = Component(metadata=metadata_c, instance=mock_c)
        comp_b = Component(metadata=metadata_b, instance=mock_b)
        comp_a = Component(metadata=metadata_a, instance=mock_a)

        comp_a.status = ComponentStatus.RUNNING
        comp_b.status = ComponentStatus.RUNNING
        comp_c.status = ComponentStatus.RUNNING

        registry.register(comp_c)
        registry.register(comp_b)
        registry.register(comp_a)

        manager = LifecycleManager(registry)
        manager.stop_all(reverse_order=True)

        # Reverse order: a before b, b before c
        assert stop_order.index("a") < stop_order.index("b")
        assert stop_order.index("b") < stop_order.index("c")

    def test_stop_all_continues_on_failure(self) -> None:
        """Test stop_all continues on failure."""
        registry = ComponentRegistry()

        mock1 = MockComponent(fail_stop=True)
        mock2 = MockComponent()

        metadata1 = ComponentMetadata(name="comp1")
        metadata2 = ComponentMetadata(name="comp2")

        comp1 = Component(metadata=metadata1, instance=mock1)
        comp2 = Component(metadata=metadata2, instance=mock2)

        comp1.status = ComponentStatus.RUNNING
        comp2.status = ComponentStatus.RUNNING

        registry.register(comp1)
        registry.register(comp2)

        manager = LifecycleManager(registry)
        result = manager.stop_all()

        # comp2 should still be stopped
        assert "comp2" in result

    def test_initialize_component(self) -> None:
        """Test initialize_component."""
        registry = ComponentRegistry()
        mock = MockComponent()
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=mock)
        registry.register(component)

        manager = LifecycleManager(registry)
        manager.initialize_component("test")

        assert component.status == ComponentStatus.INITIALIZED

    def test_initialize_component_with_uninitialized_dependency(self) -> None:
        """Test initialize_component fails if dependency not initialized."""
        registry = ComponentRegistry()

        mock_dep = MockComponent()
        mock_main = MockComponent()

        metadata_dep = ComponentMetadata(name="dep")
        metadata_main = ComponentMetadata(name="main", dependencies=["dep"])

        comp_dep = Component(metadata=metadata_dep, instance=mock_dep)
        comp_main = Component(metadata=metadata_main, instance=mock_main)

        registry.register(comp_dep)
        registry.register(comp_main)

        manager = LifecycleManager(registry)

        with pytest.raises(RuntimeError, match="dependency dep is not initialized"):
            manager.initialize_component("main")

    def test_initialize_component_with_missing_dependency(self) -> None:
        """Test initialize_component fails if dependency missing."""
        registry = ComponentRegistry()
        mock = MockComponent()
        metadata = ComponentMetadata(name="main", dependencies=["missing"])
        component = Component(metadata=metadata, instance=mock)
        registry.register(component)

        manager = LifecycleManager(registry)

        with pytest.raises(RuntimeError, match="dependency missing is not available"):
            manager.initialize_component("main")

    def test_start_component(self) -> None:
        """Test start_component."""
        registry = ComponentRegistry()
        mock = MockComponent()
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=mock)
        component.status = ComponentStatus.INITIALIZED
        registry.register(component)

        manager = LifecycleManager(registry)
        manager.start_component("test")

        assert component.status == ComponentStatus.RUNNING

    def test_start_component_with_non_running_dependency(self) -> None:
        """Test start_component fails if dependency not running."""
        registry = ComponentRegistry()

        mock_dep = MockComponent()
        mock_main = MockComponent()

        metadata_dep = ComponentMetadata(name="dep")
        metadata_main = ComponentMetadata(name="main", dependencies=["dep"])

        comp_dep = Component(metadata=metadata_dep, instance=mock_dep)
        comp_main = Component(metadata=metadata_main, instance=mock_main)

        comp_dep.status = ComponentStatus.INITIALIZED
        comp_main.status = ComponentStatus.INITIALIZED

        registry.register(comp_dep)
        registry.register(comp_main)

        manager = LifecycleManager(registry)

        with pytest.raises(RuntimeError, match="dependency dep is not running"):
            manager.start_component("main")

    def test_stop_component(self) -> None:
        """Test stop_component."""
        registry = ComponentRegistry()
        mock = MockComponent()
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=mock)
        component.status = ComponentStatus.RUNNING
        registry.register(component)

        manager = LifecycleManager(registry)
        manager.stop_component("test")

        assert component.status == ComponentStatus.STOPPED

    def test_restart_component(self) -> None:
        """Test restart_component."""
        registry = ComponentRegistry()
        mock = MockComponent()
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=mock)
        component.status = ComponentStatus.RUNNING
        registry.register(component)

        manager = LifecycleManager(registry)
        manager.restart_component("test")

        assert component.status == ComponentStatus.RUNNING
        assert mock.stopped is True
        assert mock.initialized is True
        assert mock.started is True
