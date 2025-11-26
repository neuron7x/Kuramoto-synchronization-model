"""Tests for component registry."""

import pytest

from core.architecture_integrator.component import Component, ComponentMetadata
from core.architecture_integrator.registry import ComponentRegistry


def create_test_component(
    name: str, deps: list[str] = None, provides: list[str] = None
):
    """Helper to create test components."""
    metadata = ComponentMetadata(
        name=name,
        dependencies=deps or [],
        provides=provides or [],
    )
    return Component(metadata=metadata, instance=None)


def test_registry_register_component():
    """Test registering a component."""
    registry = ComponentRegistry()
    component = create_test_component("test")

    registry.register(component)

    assert registry.has_component("test")
    assert len(registry) == 1


def test_registry_duplicate_registration():
    """Test that duplicate registration raises error."""
    registry = ComponentRegistry()
    component1 = create_test_component("test")
    component2 = create_test_component("test")

    registry.register(component1)

    with pytest.raises(ValueError, match="already registered"):
        registry.register(component2)


def test_registry_unregister_component():
    """Test unregistering a component."""
    registry = ComponentRegistry()
    component = create_test_component("test")

    registry.register(component)
    assert registry.has_component("test")

    registry.unregister("test")
    assert not registry.has_component("test")


def test_registry_get_component():
    """Test getting a component by name."""
    registry = ComponentRegistry()
    component = create_test_component("test")

    registry.register(component)
    retrieved = registry.get("test")

    assert retrieved is component


def test_registry_get_nonexistent_component():
    """Test getting a nonexistent component raises error."""
    registry = ComponentRegistry()

    with pytest.raises(KeyError):
        registry.get("nonexistent")


def test_registry_get_all():
    """Test getting all components."""
    registry = ComponentRegistry()
    comp1 = create_test_component("comp1")
    comp2 = create_test_component("comp2")

    registry.register(comp1)
    registry.register(comp2)

    all_components = registry.get_all()

    assert len(all_components) == 2
    assert comp1 in all_components
    assert comp2 in all_components


def test_registry_get_by_tag():
    """Test getting components by tag."""
    registry = ComponentRegistry()

    comp1_meta = ComponentMetadata(name="comp1", tags=["core", "data"])
    comp1 = Component(metadata=comp1_meta, instance=None)

    comp2_meta = ComponentMetadata(name="comp2", tags=["core"])
    comp2 = Component(metadata=comp2_meta, instance=None)

    comp3_meta = ComponentMetadata(name="comp3", tags=["optional"])
    comp3 = Component(metadata=comp3_meta, instance=None)

    registry.register(comp1)
    registry.register(comp2)
    registry.register(comp3)

    core_components = registry.get_by_tag("core")

    assert len(core_components) == 2
    assert comp1 in core_components
    assert comp2 in core_components


def test_registry_get_by_capability():
    """Test getting components by capability."""
    registry = ComponentRegistry()

    comp1 = create_test_component("comp1", provides=["data_ingestion"])
    comp2 = create_test_component("comp2", provides=["data_ingestion", "analytics"])
    comp3 = create_test_component("comp3", provides=["execution"])

    registry.register(comp1)
    registry.register(comp2)
    registry.register(comp3)

    ingestion_providers = registry.get_by_capability("data_ingestion")

    assert len(ingestion_providers) == 2
    assert comp1 in ingestion_providers
    assert comp2 in ingestion_providers


def test_registry_dependency_graph():
    """Test building dependency graph."""
    registry = ComponentRegistry()

    comp1 = create_test_component("comp1", deps=[])
    comp2 = create_test_component("comp2", deps=["comp1"])
    comp3 = create_test_component("comp3", deps=["comp1", "comp2"])

    registry.register(comp1)
    registry.register(comp2)
    registry.register(comp3)

    graph = registry.get_dependency_graph()

    assert graph["comp1"] == []
    assert graph["comp2"] == ["comp1"]
    assert set(graph["comp3"]) == {"comp1", "comp2"}


def test_registry_validate_dependencies_success():
    """Test dependency validation with satisfied dependencies."""
    registry = ComponentRegistry()

    comp1 = create_test_component("comp1")
    comp2 = create_test_component("comp2", deps=["comp1"])

    registry.register(comp1)
    registry.register(comp2)

    errors = registry.validate_dependencies()

    assert len(errors) == 0


def test_registry_validate_dependencies_failure():
    """Test dependency validation with missing dependencies."""
    registry = ComponentRegistry()

    comp1 = create_test_component("comp1", deps=["missing"])

    registry.register(comp1)

    errors = registry.validate_dependencies()

    assert len(errors) > 0
    assert "missing" in errors[0]


def test_registry_initialization_order_simple():
    """Test initialization order with simple dependencies."""
    registry = ComponentRegistry()

    comp1 = create_test_component("comp1")
    comp2 = create_test_component("comp2", deps=["comp1"])
    comp3 = create_test_component("comp3", deps=["comp2"])

    registry.register(comp1)
    registry.register(comp2)
    registry.register(comp3)

    order = registry.get_initialization_order()

    # comp1 must come before comp2, comp2 before comp3
    assert order.index("comp1") < order.index("comp2")
    assert order.index("comp2") < order.index("comp3")


def test_registry_initialization_order_diamond():
    """Test initialization order with diamond dependency."""
    registry = ComponentRegistry()

    comp1 = create_test_component("comp1")
    comp2 = create_test_component("comp2", deps=["comp1"])
    comp3 = create_test_component("comp3", deps=["comp1"])
    comp4 = create_test_component("comp4", deps=["comp2", "comp3"])

    registry.register(comp1)
    registry.register(comp2)
    registry.register(comp3)
    registry.register(comp4)

    order = registry.get_initialization_order()

    # comp1 must come first
    assert order[0] == "comp1"
    # comp2 and comp3 must come before comp4
    assert order.index("comp2") < order.index("comp4")
    assert order.index("comp3") < order.index("comp4")


def test_registry_circular_dependency_detection():
    """Test detection of circular dependencies."""
    registry = ComponentRegistry()

    comp1 = create_test_component("comp1", deps=["comp2"])
    comp2 = create_test_component("comp2", deps=["comp1"])

    registry.register(comp1)
    registry.register(comp2)

    with pytest.raises(ValueError, match="Circular dependency"):
        registry.get_initialization_order()


def test_registry_clear():
    """Test clearing the registry."""
    registry = ComponentRegistry()

    comp1 = create_test_component("comp1")
    comp2 = create_test_component("comp2")

    registry.register(comp1)
    registry.register(comp2)

    assert len(registry) == 2

    registry.clear()

    assert len(registry) == 0


def test_registry_contains():
    """Test __contains__ operator."""
    registry = ComponentRegistry()
    comp = create_test_component("test")

    assert "test" not in registry

    registry.register(comp)

    assert "test" in registry


def test_registry_capability_dependency():
    """Test initialization order with capability-based dependencies."""
    registry = ComponentRegistry()

    # comp1 provides a capability
    comp1 = create_test_component("comp1", provides=["data_service"])
    # comp2 depends on the capability
    comp2 = create_test_component("comp2", deps=["data_service"])

    registry.register(comp1)
    registry.register(comp2)

    order = registry.get_initialization_order()

    # comp1 must come before comp2
    assert order.index("comp1") < order.index("comp2")
