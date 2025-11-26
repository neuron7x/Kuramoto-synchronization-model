"""Component registry for architecture integration.

This module provides a registry for managing components, their metadata,
and their relationships within the system architecture.
"""

from __future__ import annotations

from typing import Sequence

from core.architecture_integrator.component import Component


class ComponentRegistry:
    """Registry for managing system components and their relationships."""

    def __init__(self) -> None:
        self._components: dict[str, Component] = {}
        self._capabilities: dict[str, list[str]] = {}  # capability -> [component_names]

    def register(self, component: Component) -> None:
        """Register a component in the registry.

        Args:
            component: Component to register

        Raises:
            ValueError: If component with the same name already exists
        """
        name = component.metadata.name
        if name in self._components:
            raise ValueError(f"Component '{name}' is already registered")

        self._components[name] = component

        # Register capabilities
        for capability in component.get_provides():
            if capability not in self._capabilities:
                self._capabilities[capability] = []
            self._capabilities[capability].append(name)

    def unregister(self, name: str) -> None:
        """Remove a component from the registry.

        Args:
            name: Name of component to unregister

        Raises:
            KeyError: If component not found
        """
        if name not in self._components:
            raise KeyError(f"Component '{name}' not found in registry")

        component = self._components[name]

        # Remove from capabilities index
        for capability in component.get_provides():
            if capability in self._capabilities:
                self._capabilities[capability].remove(name)
                if not self._capabilities[capability]:
                    del self._capabilities[capability]

        del self._components[name]

    def get(self, name: str) -> Component:
        """Retrieve a component by name.

        Args:
            name: Component name

        Returns:
            The requested component

        Raises:
            KeyError: If component not found
        """
        if name not in self._components:
            raise KeyError(f"Component '{name}' not found in registry")
        return self._components[name]

    def get_all(self) -> Sequence[Component]:
        """Return all registered components."""
        return list(self._components.values())

    def get_by_tag(self, tag: str) -> Sequence[Component]:
        """Return all components with the specified tag."""
        return [comp for comp in self._components.values() if tag in comp.metadata.tags]

    def get_by_capability(self, capability: str) -> Sequence[Component]:
        """Return all components that provide a specific capability."""
        component_names = self._capabilities.get(capability, [])
        return [self._components[name] for name in component_names]

    def has_component(self, name: str) -> bool:
        """Check if a component is registered."""
        return name in self._components

    def has_capability(self, capability: str) -> bool:
        """Check if any component provides the specified capability."""
        return capability in self._capabilities

    def get_dependency_graph(self) -> dict[str, list[str]]:
        """Build a dependency graph for all components.

        Returns:
            Dictionary mapping component names to their dependency names
        """
        graph: dict[str, list[str]] = {}
        for name, component in self._components.items():
            graph[name] = list(component.get_dependencies())
        return graph

    def validate_dependencies(self) -> list[str]:
        """Validate that all component dependencies are satisfied.

        Returns:
            List of error messages for unsatisfied dependencies (empty if all satisfied)
        """
        errors: list[str] = []
        for name, component in self._components.items():
            for dep in component.get_dependencies():
                # Check if dependency is satisfied by component name or capability
                if not self.has_component(dep) and not self.has_capability(dep):
                    errors.append(
                        f"Component '{name}' depends on '{dep}' which is not available"
                    )
        return errors

    def get_initialization_order(self) -> Sequence[str]:
        """Calculate the order in which components should be initialized.

        Returns:
            List of component names in initialization order

        Raises:
            ValueError: If circular dependencies are detected
        """
        graph = self.get_dependency_graph()
        visited: set[str] = set()
        visiting: set[str] = set()
        order: list[str] = []

        def visit(node: str) -> None:
            if node in visited:
                return
            if node in visiting:
                raise ValueError(f"Circular dependency detected involving '{node}'")

            visiting.add(node)

            # Visit dependencies first
            for dep in graph.get(node, []):
                # Resolve dependency to actual component name
                if dep in graph:
                    visit(dep)
                else:
                    # Check if it's a capability
                    providers = self._capabilities.get(dep, [])
                    for provider in providers:
                        visit(provider)

            visiting.remove(node)
            visited.add(node)
            order.append(node)

        for component_name in graph:
            if component_name not in visited:
                visit(component_name)

        return order

    def clear(self) -> None:
        """Remove all components from the registry."""
        self._components.clear()
        self._capabilities.clear()

    def __len__(self) -> int:
        """Return the number of registered components."""
        return len(self._components)

    def __contains__(self, name: str) -> bool:
        """Check if a component is registered."""
        return name in self._components
