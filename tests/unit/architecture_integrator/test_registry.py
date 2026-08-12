# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core/architecture_integrator/registry.py module."""

from __future__ import annotations

import pytest

from core.architecture_integrator.component import Component, ComponentMetadata
from core.architecture_integrator.registry import ComponentRegistry


class TestComponentRegistry:
    """Tests for ComponentRegistry class."""

    def test_empty_registry(self) -> None:
        """Test empty registry initialization."""
        registry = ComponentRegistry()
        assert len(registry) == 0
        assert registry.get_all() == []

    def test_register_component(self) -> None:
        """Test registering a component."""
        registry = ComponentRegistry()
        metadata = ComponentMetadata(name="test-component")
        component = Component(metadata=metadata, instance=object())

        registry.register(component)

        assert len(registry) == 1
        assert "test-component" in registry
        assert registry.has_component("test-component")

    def test_register_duplicate_raises(self) -> None:
        """Test registering duplicate component raises error."""
        registry = ComponentRegistry()
        metadata = ComponentMetadata(name="test")
        component1 = Component(metadata=metadata, instance=object())
        component2 = Component(metadata=metadata, instance=object())

        registry.register(component1)

        with pytest.raises(ValueError, match="already registered"):
            registry.register(component2)

    def test_register_with_capabilities(self) -> None:
        """Test registering component with capabilities."""
        registry = ComponentRegistry()
        metadata = ComponentMetadata(
            name="data-service",
            provides=["market-data", "historical-data"],
        )
        component = Component(metadata=metadata, instance=object())

        registry.register(component)

        assert registry.has_capability("market-data")
        assert registry.has_capability("historical-data")

    def test_unregister_component(self) -> None:
        """Test unregistering a component."""
        registry = ComponentRegistry()
        metadata = ComponentMetadata(name="test", provides=["capability"])
        component = Component(metadata=metadata, instance=object())

        registry.register(component)
        registry.unregister("test")

        assert len(registry) == 0
        assert "test" not in registry
        assert not registry.has_capability("capability")

    def test_unregister_nonexistent_raises(self) -> None:
        """Test unregistering nonexistent component raises error."""
        registry = ComponentRegistry()

        with pytest.raises(KeyError, match="not found"):
            registry.unregister("nonexistent")

    def test_get_component(self) -> None:
        """Test getting a component by name."""
        registry = ComponentRegistry()
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=object())

        registry.register(component)
        retrieved = registry.get("test")

        assert retrieved == component

    def test_get_nonexistent_raises(self) -> None:
        """Test getting nonexistent component raises error."""
        registry = ComponentRegistry()

        with pytest.raises(KeyError, match="not found"):
            registry.get("nonexistent")

    def test_get_all(self) -> None:
        """Test getting all components."""
        registry = ComponentRegistry()
        components = []
        for i in range(3):
            metadata = ComponentMetadata(name=f"component-{i}")
            comp = Component(metadata=metadata, instance=object())
            components.append(comp)
            registry.register(comp)

        all_components = registry.get_all()

        assert len(all_components) == 3

    def test_get_by_tag(self) -> None:
        """Test getting components by tag."""
        registry = ComponentRegistry()
        metadata1 = ComponentMetadata(name="comp1", tags=["core", "data"])
        metadata2 = ComponentMetadata(name="comp2", tags=["core", "ui"])
        metadata3 = ComponentMetadata(name="comp3", tags=["ui"])

        registry.register(Component(metadata=metadata1, instance=object()))
        registry.register(Component(metadata=metadata2, instance=object()))
        registry.register(Component(metadata=metadata3, instance=object()))

        core_components = registry.get_by_tag("core")
        ui_components = registry.get_by_tag("ui")

        assert len(core_components) == 2
        assert len(ui_components) == 2

    def test_get_by_capability(self) -> None:
        """Test getting components by capability."""
        registry = ComponentRegistry()
        metadata1 = ComponentMetadata(name="db", provides=["storage"])
        metadata2 = ComponentMetadata(name="cache", provides=["storage", "caching"])

        registry.register(Component(metadata=metadata1, instance=object()))
        registry.register(Component(metadata=metadata2, instance=object()))

        storage_providers = registry.get_by_capability("storage")
        cache_providers = registry.get_by_capability("caching")
        missing = registry.get_by_capability("nonexistent")

        assert len(storage_providers) == 2
        assert len(cache_providers) == 1
        assert len(missing) == 0

    def test_has_component(self) -> None:
        """Test has_component method."""
        registry = ComponentRegistry()
        metadata = ComponentMetadata(name="test")
        registry.register(Component(metadata=metadata, instance=object()))

        assert registry.has_component("test") is True
        assert registry.has_component("nonexistent") is False

    def test_has_capability(self) -> None:
        """Test has_capability method."""
        registry = ComponentRegistry()
        metadata = ComponentMetadata(name="test", provides=["api"])
        registry.register(Component(metadata=metadata, instance=object()))

        assert registry.has_capability("api") is True
        assert registry.has_capability("nonexistent") is False

    def test_get_dependency_graph(self) -> None:
        """Test building dependency graph."""
        registry = ComponentRegistry()
        metadata1 = ComponentMetadata(name="a", dependencies=["b", "c"])
        metadata2 = ComponentMetadata(name="b", dependencies=["c"])
        metadata3 = ComponentMetadata(name="c", dependencies=[])

        registry.register(Component(metadata=metadata1, instance=object()))
        registry.register(Component(metadata=metadata2, instance=object()))
        registry.register(Component(metadata=metadata3, instance=object()))

        graph = registry.get_dependency_graph()

        assert graph["a"] == ["b", "c"]
        assert graph["b"] == ["c"]
        assert graph["c"] == []

    def test_validate_dependencies_satisfied(self) -> None:
        """Test validate_dependencies with all dependencies satisfied."""
        registry = ComponentRegistry()
        metadata1 = ComponentMetadata(name="app", dependencies=["db"])
        metadata2 = ComponentMetadata(name="db", dependencies=[])

        registry.register(Component(metadata=metadata1, instance=object()))
        registry.register(Component(metadata=metadata2, instance=object()))

        errors = registry.validate_dependencies()

        assert errors == []

    def test_validate_dependencies_by_capability(self) -> None:
        """Test validate_dependencies with capability-based dependencies."""
        registry = ComponentRegistry()
        metadata1 = ComponentMetadata(name="app", dependencies=["storage"])
        metadata2 = ComponentMetadata(name="db", provides=["storage"])

        registry.register(Component(metadata=metadata1, instance=object()))
        registry.register(Component(metadata=metadata2, instance=object()))

        errors = registry.validate_dependencies()

        assert errors == []

    def test_validate_dependencies_unsatisfied(self) -> None:
        """Test validate_dependencies with unsatisfied dependencies."""
        registry = ComponentRegistry()
        metadata = ComponentMetadata(name="app", dependencies=["missing-dep"])

        registry.register(Component(metadata=metadata, instance=object()))

        errors = registry.validate_dependencies()

        assert len(errors) == 1
        assert "missing-dep" in errors[0]

    def test_get_initialization_order_simple(self) -> None:
        """Test getting initialization order for simple graph."""
        registry = ComponentRegistry()
        metadata1 = ComponentMetadata(name="a", dependencies=["b"])
        metadata2 = ComponentMetadata(name="b", dependencies=["c"])
        metadata3 = ComponentMetadata(name="c", dependencies=[])

        registry.register(Component(metadata=metadata1, instance=object()))
        registry.register(Component(metadata=metadata2, instance=object()))
        registry.register(Component(metadata=metadata3, instance=object()))

        order = registry.get_initialization_order()

        # c should come before b, b before a
        assert order.index("c") < order.index("b")
        assert order.index("b") < order.index("a")

    def test_get_initialization_order_circular_raises(self) -> None:
        """Test circular dependencies raise error."""
        registry = ComponentRegistry()
        metadata1 = ComponentMetadata(name="a", dependencies=["b"])
        metadata2 = ComponentMetadata(name="b", dependencies=["a"])

        registry.register(Component(metadata=metadata1, instance=object()))
        registry.register(Component(metadata=metadata2, instance=object()))

        with pytest.raises(ValueError, match="Circular dependency"):
            registry.get_initialization_order()

    def test_get_initialization_order_with_capabilities(self) -> None:
        """Test initialization order with capability-based dependencies."""
        registry = ComponentRegistry()
        metadata1 = ComponentMetadata(name="app", dependencies=["storage"])
        metadata2 = ComponentMetadata(name="db", provides=["storage"])

        registry.register(Component(metadata=metadata1, instance=object()))
        registry.register(Component(metadata=metadata2, instance=object()))

        order = registry.get_initialization_order()

        # db (provides storage) should come before app (depends on storage)
        assert order.index("db") < order.index("app")

    def test_clear(self) -> None:
        """Test clearing the registry."""
        registry = ComponentRegistry()
        metadata = ComponentMetadata(name="test", provides=["api"])
        registry.register(Component(metadata=metadata, instance=object()))

        registry.clear()

        assert len(registry) == 0
        assert not registry.has_capability("api")

    def test_len(self) -> None:
        """Test __len__ method."""
        registry = ComponentRegistry()

        assert len(registry) == 0

        for i in range(5):
            metadata = ComponentMetadata(name=f"comp-{i}")
            registry.register(Component(metadata=metadata, instance=object()))

        assert len(registry) == 5

    def test_contains(self) -> None:
        """Test __contains__ method."""
        registry = ComponentRegistry()
        metadata = ComponentMetadata(name="test")
        registry.register(Component(metadata=metadata, instance=object()))

        assert "test" in registry
        assert "nonexistent" not in registry

    def test_unregister_preserves_other_capability_providers(self) -> None:
        """Test unregistering component preserves other capability providers."""
        registry = ComponentRegistry()
        metadata1 = ComponentMetadata(name="db1", provides=["storage"])
        metadata2 = ComponentMetadata(name="db2", provides=["storage"])

        registry.register(Component(metadata=metadata1, instance=object()))
        registry.register(Component(metadata=metadata2, instance=object()))

        registry.unregister("db1")

        assert registry.has_capability("storage")
        providers = registry.get_by_capability("storage")
        assert len(providers) == 1
        assert providers[0].metadata.name == "db2"
