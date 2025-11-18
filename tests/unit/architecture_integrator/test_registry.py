# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""
Comprehensive test suite for architecture_integrator/registry.py

Tests component registry functionality including registration, lookup,
dependency management, and initialization ordering.

Following 2025 best practices with comprehensive edge case coverage.
"""
import pytest
from unittest.mock import Mock

from core.architecture_integrator.component import Component, ComponentMetadata
from core.architecture_integrator.registry import ComponentRegistry


class TestComponentRegistryBasics:
    """Test basic registry operations."""

    def test_registry_initialization(self):
        """Test creating empty registry."""
        registry = ComponentRegistry()
        assert len(registry) == 0
        assert registry.get_all() == []

    def test_register_component(self):
        """Test registering a component."""
        registry = ComponentRegistry()
        metadata = ComponentMetadata(name="TestComponent")
        component = Component(metadata=metadata, instance=Mock())
        
        registry.register(component)
        
        assert len(registry) == 1
        assert registry.has_component("TestComponent")
        assert component in registry.get_all()

    def test_register_duplicate_raises_error(self):
        """Test that registering duplicate component raises ValueError."""
        registry = ComponentRegistry()
        metadata = ComponentMetadata(name="Duplicate")
        component1 = Component(metadata=metadata, instance=Mock())
        component2 = Component(metadata=metadata, instance=Mock())
        
        registry.register(component1)
        
        with pytest.raises(ValueError, match="already registered"):
            registry.register(component2)

    def test_get_component(self):
        """Test retrieving a component by name."""
        registry = ComponentRegistry()
        metadata = ComponentMetadata(name="TestComponent")
        component = Component(metadata=metadata, instance=Mock())
        
        registry.register(component)
        retrieved = registry.get("TestComponent")
        
        assert retrieved == component

    def test_get_nonexistent_component_raises_error(self):
        """Test that getting nonexistent component raises KeyError."""
        registry = ComponentRegistry()
        
        with pytest.raises(KeyError, match="not found"):
            registry.get("NonExistent")

    def test_unregister_component(self):
        """Test unregistering a component."""
        registry = ComponentRegistry()
        metadata = ComponentMetadata(name="TestComponent")
        component = Component(metadata=metadata, instance=Mock())
        
        registry.register(component)
        assert registry.has_component("TestComponent")
        
        registry.unregister("TestComponent")
        assert not registry.has_component("TestComponent")

    def test_unregister_nonexistent_raises_error(self):
        """Test that unregistering nonexistent component raises KeyError."""
        registry = ComponentRegistry()
        
        with pytest.raises(KeyError, match="not found"):
            registry.unregister("NonExistent")

    def test_contains_operator(self):
        """Test __contains__ operator."""
        registry = ComponentRegistry()
        metadata = ComponentMetadata(name="TestComponent")
        component = Component(metadata=metadata, instance=Mock())
        
        assert "TestComponent" not in registry
        registry.register(component)
        assert "TestComponent" in registry


class TestComponentRegistryCapabilities:
    """Test capability-based component lookup."""

    def test_register_component_with_capabilities(self):
        """Test that capabilities are indexed on registration."""
        registry = ComponentRegistry()
        metadata = ComponentMetadata(
            name="DataSource",
            provides=["market_data", "tick_data"],
        )
        component = Component(metadata=metadata, instance=Mock())
        
        registry.register(component)
        
        assert registry.has_capability("market_data")
        assert registry.has_capability("tick_data")

    def test_get_by_capability(self):
        """Test retrieving components by capability."""
        registry = ComponentRegistry()
        
        metadata1 = ComponentMetadata(name="Source1", provides=["data"])
        component1 = Component(metadata=metadata1, instance=Mock())
        
        metadata2 = ComponentMetadata(name="Source2", provides=["data"])
        component2 = Component(metadata=metadata2, instance=Mock())
        
        registry.register(component1)
        registry.register(component2)
        
        providers = registry.get_by_capability("data")
        assert len(providers) == 2
        assert component1 in providers
        assert component2 in providers

    def test_get_by_nonexistent_capability(self):
        """Test getting components by capability that doesn't exist."""
        registry = ComponentRegistry()
        providers = registry.get_by_capability("nonexistent")
        assert providers == []

    def test_unregister_removes_capabilities(self):
        """Test that unregistering removes capability mappings."""
        registry = ComponentRegistry()
        metadata = ComponentMetadata(
            name="DataSource",
            provides=["market_data"],
        )
        component = Component(metadata=metadata, instance=Mock())
        
        registry.register(component)
        assert registry.has_capability("market_data")
        
        registry.unregister("DataSource")
        assert not registry.has_capability("market_data")


class TestComponentRegistryTagging:
    """Test tag-based component lookup."""

    def test_get_by_tag(self):
        """Test retrieving components by tag."""
        registry = ComponentRegistry()
        
        metadata1 = ComponentMetadata(name="Comp1", tags=["critical", "data"])
        component1 = Component(metadata=metadata1, instance=Mock())
        
        metadata2 = ComponentMetadata(name="Comp2", tags=["critical"])
        component2 = Component(metadata=metadata2, instance=Mock())
        
        metadata3 = ComponentMetadata(name="Comp3", tags=["data"])
        component3 = Component(metadata=metadata3, instance=Mock())
        
        registry.register(component1)
        registry.register(component2)
        registry.register(component3)
        
        critical_components = registry.get_by_tag("critical")
        assert len(critical_components) == 2
        assert component1 in critical_components
        assert component2 in critical_components

    def test_get_by_nonexistent_tag(self):
        """Test getting components by tag that doesn't exist."""
        registry = ComponentRegistry()
        metadata = ComponentMetadata(name="Comp1", tags=["existing"])
        component = Component(metadata=metadata, instance=Mock())
        registry.register(component)
        
        result = registry.get_by_tag("nonexistent")
        assert result == []


class TestComponentRegistryDependencies:
    """Test dependency management."""

    def test_get_dependency_graph(self):
        """Test building dependency graph."""
        registry = ComponentRegistry()
        
        metadata1 = ComponentMetadata(name="A", dependencies=[])
        metadata2 = ComponentMetadata(name="B", dependencies=["A"])
        metadata3 = ComponentMetadata(name="C", dependencies=["A", "B"])
        
        registry.register(Component(metadata=metadata1, instance=Mock()))
        registry.register(Component(metadata=metadata2, instance=Mock()))
        registry.register(Component(metadata=metadata3, instance=Mock()))
        
        graph = registry.get_dependency_graph()
        
        assert graph["A"] == []
        assert graph["B"] == ["A"]
        assert graph["C"] == ["A", "B"]

    def test_validate_dependencies_success(self):
        """Test validation with satisfied dependencies."""
        registry = ComponentRegistry()
        
        metadata1 = ComponentMetadata(name="A")
        metadata2 = ComponentMetadata(name="B", dependencies=["A"])
        
        registry.register(Component(metadata=metadata1, instance=Mock()))
        registry.register(Component(metadata=metadata2, instance=Mock()))
        
        errors = registry.validate_dependencies()
        assert errors == []

    def test_validate_dependencies_missing(self):
        """Test validation with missing dependencies."""
        registry = ComponentRegistry()
        
        metadata = ComponentMetadata(name="B", dependencies=["A"])
        registry.register(Component(metadata=metadata, instance=Mock()))
        
        errors = registry.validate_dependencies()
        assert len(errors) == 1
        assert "depends on 'A'" in errors[0]

    def test_validate_dependencies_capability(self):
        """Test validation with dependency satisfied by capability."""
        registry = ComponentRegistry()
        
        metadata1 = ComponentMetadata(name="Provider", provides=["data_service"])
        metadata2 = ComponentMetadata(name="Consumer", dependencies=["data_service"])
        
        registry.register(Component(metadata=metadata1, instance=Mock()))
        registry.register(Component(metadata=metadata2, instance=Mock()))
        
        errors = registry.validate_dependencies()
        assert errors == []


class TestComponentRegistryInitializationOrder:
    """Test initialization order calculation."""

    def test_initialization_order_simple(self):
        """Test initialization order with simple dependency chain."""
        registry = ComponentRegistry()
        
        metadata1 = ComponentMetadata(name="A", dependencies=[])
        metadata2 = ComponentMetadata(name="B", dependencies=["A"])
        metadata3 = ComponentMetadata(name="C", dependencies=["B"])
        
        registry.register(Component(metadata=metadata1, instance=Mock()))
        registry.register(Component(metadata=metadata2, instance=Mock()))
        registry.register(Component(metadata=metadata3, instance=Mock()))
        
        order = registry.get_initialization_order()
        
        # A must come before B, B before C
        assert order.index("A") < order.index("B")
        assert order.index("B") < order.index("C")

    def test_initialization_order_parallel_dependencies(self):
        """Test initialization order with parallel dependencies."""
        registry = ComponentRegistry()
        
        metadata1 = ComponentMetadata(name="A", dependencies=[])
        metadata2 = ComponentMetadata(name="B", dependencies=[])
        metadata3 = ComponentMetadata(name="C", dependencies=["A", "B"])
        
        registry.register(Component(metadata=metadata1, instance=Mock()))
        registry.register(Component(metadata=metadata2, instance=Mock()))
        registry.register(Component(metadata=metadata3, instance=Mock()))
        
        order = registry.get_initialization_order()
        
        # A and B must come before C
        assert order.index("A") < order.index("C")
        assert order.index("B") < order.index("C")

    def test_initialization_order_circular_dependency(self):
        """Test that circular dependencies are detected."""
        registry = ComponentRegistry()
        
        # Create circular dependency: A -> B -> C -> A
        metadata1 = ComponentMetadata(name="A", dependencies=["C"])
        metadata2 = ComponentMetadata(name="B", dependencies=["A"])
        metadata3 = ComponentMetadata(name="C", dependencies=["B"])
        
        registry.register(Component(metadata=metadata1, instance=Mock()))
        registry.register(Component(metadata=metadata2, instance=Mock()))
        registry.register(Component(metadata=metadata3, instance=Mock()))
        
        with pytest.raises(ValueError, match="Circular dependency"):
            registry.get_initialization_order()

    def test_initialization_order_with_capabilities(self):
        """Test initialization order with capability-based dependencies."""
        registry = ComponentRegistry()
        
        metadata1 = ComponentMetadata(name="Provider", provides=["service"])
        metadata2 = ComponentMetadata(name="Consumer", dependencies=["service"])
        
        registry.register(Component(metadata=metadata1, instance=Mock()))
        registry.register(Component(metadata=metadata2, instance=Mock()))
        
        order = registry.get_initialization_order()
        
        assert order.index("Provider") < order.index("Consumer")

    def test_initialization_order_no_dependencies(self):
        """Test initialization order with independent components."""
        registry = ComponentRegistry()
        
        metadata1 = ComponentMetadata(name="A")
        metadata2 = ComponentMetadata(name="B")
        metadata3 = ComponentMetadata(name="C")
        
        registry.register(Component(metadata=metadata1, instance=Mock()))
        registry.register(Component(metadata=metadata2, instance=Mock()))
        registry.register(Component(metadata=metadata3, instance=Mock()))
        
        order = registry.get_initialization_order()
        
        # All components should be in the order
        assert len(order) == 3
        assert set(order) == {"A", "B", "C"}


class TestComponentRegistryUtilities:
    """Test utility methods."""

    def test_clear(self):
        """Test clearing all components."""
        registry = ComponentRegistry()
        
        metadata1 = ComponentMetadata(name="A", provides=["service"])
        metadata2 = ComponentMetadata(name="B")
        
        registry.register(Component(metadata=metadata1, instance=Mock()))
        registry.register(Component(metadata=metadata2, instance=Mock()))
        
        assert len(registry) == 2
        assert registry.has_capability("service")
        
        registry.clear()
        
        assert len(registry) == 0
        assert not registry.has_capability("service")
        assert registry.get_all() == []

    def test_len_operator(self):
        """Test __len__ operator."""
        registry = ComponentRegistry()
        
        assert len(registry) == 0
        
        for i in range(5):
            metadata = ComponentMetadata(name=f"Comp{i}")
            registry.register(Component(metadata=metadata, instance=Mock()))
        
        assert len(registry) == 5


class TestComponentRegistryEdgeCases:
    """Test edge cases and complex scenarios."""

    def test_component_with_multiple_capabilities(self):
        """Test component providing multiple capabilities."""
        registry = ComponentRegistry()
        
        metadata = ComponentMetadata(
            name="MultiProvider",
            provides=["service1", "service2", "service3"],
        )
        component = Component(metadata=metadata, instance=Mock())
        
        registry.register(component)
        
        for capability in ["service1", "service2", "service3"]:
            assert registry.has_capability(capability)
            providers = registry.get_by_capability(capability)
            assert component in providers

    def test_complex_dependency_graph(self):
        """Test complex dependency resolution."""
        registry = ComponentRegistry()
        
        # Create diamond dependency: D depends on B and C, both depend on A
        metadata_a = ComponentMetadata(name="A")
        metadata_b = ComponentMetadata(name="B", dependencies=["A"])
        metadata_c = ComponentMetadata(name="C", dependencies=["A"])
        metadata_d = ComponentMetadata(name="D", dependencies=["B", "C"])
        
        registry.register(Component(metadata=metadata_a, instance=Mock()))
        registry.register(Component(metadata=metadata_b, instance=Mock()))
        registry.register(Component(metadata=metadata_c, instance=Mock()))
        registry.register(Component(metadata=metadata_d, instance=Mock()))
        
        order = registry.get_initialization_order()
        
        # A must come first, D must come last
        assert order.index("A") < order.index("B")
        assert order.index("A") < order.index("C")
        assert order.index("B") < order.index("D")
        assert order.index("C") < order.index("D")

    def test_multiple_providers_same_capability(self):
        """Test multiple components providing same capability."""
        registry = ComponentRegistry()
        
        for i in range(3):
            metadata = ComponentMetadata(
                name=f"Provider{i}",
                provides=["common_service"],
            )
            registry.register(Component(metadata=metadata, instance=Mock()))
        
        providers = registry.get_by_capability("common_service")
        assert len(providers) == 3

    def test_self_dependency_detection(self):
        """Test that self-dependencies are handled."""
        registry = ComponentRegistry()
        
        # Component depending on itself
        metadata = ComponentMetadata(name="A", dependencies=["A"])
        registry.register(Component(metadata=metadata, instance=Mock()))
        
        with pytest.raises(ValueError, match="Circular dependency"):
            registry.get_initialization_order()
