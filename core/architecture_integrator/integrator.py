# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Main Architecture Integrator implementation.

This module provides the primary ArchitectureIntegrator class that coordinates
all architectural integration concerns across the GeoSync system.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Sequence

from core.architecture_integrator.component import (
    Component,
    ComponentHealth,
    ComponentMetadata,
    ComponentStatus,
)
from core.architecture_integrator.lifecycle import LifecycleManager
from core.architecture_integrator.registry import ComponentRegistry
from core.architecture_integrator.validator import (
    ArchitectureValidator,
    ValidationResult,
)

logger = logging.getLogger(__name__)


class ArchitectureIntegrator:
    """Central coordinator for architectural integration across GeoSync.

    The ArchitectureIntegrator serves as the primary interface for managing
    system components, their lifecycles, dependencies, and architectural
    compliance. It provides a unified API for:

    - Component registration and discovery
    - Dependency management and validation
    - Lifecycle coordination (init, start, stop)
    - Health monitoring and aggregation
    - Architecture compliance validation

    Example:
        >>> integrator = ArchitectureIntegrator()
        >>> integrator.register_component(
        ...     name="data_ingestion",
        ...     instance=data_service,
        ...     dependencies=["config_service"]
        ... )
        >>> integrator.initialize_all()
        >>> integrator.start_all()
        >>> health = integrator.aggregate_health()
        >>> validation = integrator.validate_architecture()
    """

    def __init__(self) -> None:
        """Initialize the Architecture Integrator."""
        self._registry = ComponentRegistry()
        self._lifecycle = LifecycleManager(self._registry)
        self._validator = ArchitectureValidator(self._registry)
        self._event_handlers: dict[str, list[Callable[..., None]]] = {}

    @property
    def registry(self) -> ComponentRegistry:
        """Access the component registry."""
        return self._registry

    @property
    def lifecycle(self) -> LifecycleManager:
        """Access the lifecycle manager."""
        return self._lifecycle

    @property
    def validator(self) -> ArchitectureValidator:
        """Access the architecture validator."""
        return self._validator

    # ------------------------------------------------------------------
    # Component Registration
    # ------------------------------------------------------------------

    def register_component(
        self,
        name: str,
        instance: Any,
        *,
        version: str = "1.0.0",
        description: str = "",
        tags: list[str] | None = None,
        dependencies: list[str] | None = None,
        provides: list[str] | None = None,
        configuration: dict[str, Any] | None = None,
        init_hook: Callable[[], None] | None = None,
        start_hook: Callable[[], None] | None = None,
        stop_hook: Callable[[], None] | None = None,
        health_hook: Callable[[], ComponentHealth] | None = None,
    ) -> None:
        """Register a component with the integrator.

        Args:
            name: Unique component identifier
            instance: The component instance
            version: Component version
            description: Human-readable description
            tags: List of tags for categorization
            dependencies: List of component names or capabilities this depends on
            provides: List of capabilities this component provides
            configuration: Component configuration dictionary
            init_hook: Optional initialization callback
            start_hook: Optional startup callback
            stop_hook: Optional shutdown callback
            health_hook: Optional health check callback

        Raises:
            ValueError: If component with same name already exists
        """
        metadata = ComponentMetadata(
            name=name,
            version=version,
            description=description,
            tags=tags or [],
            dependencies=dependencies or [],
            provides=provides or [],
            configuration=configuration or {},
        )

        component = Component(
            metadata=metadata,
            instance=instance,
            init_hook=init_hook,
            start_hook=start_hook,
            stop_hook=stop_hook,
            health_hook=health_hook,
        )

        self._registry.register(component)
        logger.info(f"Registered component: {name}")
        self._emit_event("component_registered", name=name)

    def unregister_component(self, name: str) -> None:
        """Unregister a component.

        Args:
            name: Component name

        Raises:
            KeyError: If component not found
        """
        # Stop component if running
        component = self._registry.get(name)
        if component.status in {ComponentStatus.RUNNING, ComponentStatus.DEGRADED}:
            self._lifecycle.stop_component(name)

        self._registry.unregister(name)
        logger.info(f"Unregistered component: {name}")
        self._emit_event("component_unregistered", name=name)

    def get_component(self, name: str) -> Component:
        """Get a registered component.

        Args:
            name: Component name

        Returns:
            The requested component

        Raises:
            KeyError: If component not found
        """
        return self._registry.get(name)

    def list_components(self) -> Sequence[Component]:
        """List all registered components."""
        return self._registry.get_all()

    # ------------------------------------------------------------------
    # Lifecycle Management
    # ------------------------------------------------------------------

    def initialize_all(self, *, stop_on_error: bool = True) -> list[str]:
        """Initialize all components in dependency order.

        Args:
            stop_on_error: If True, stop on first error

        Returns:
            List of successfully initialized component names

        Raises:
            RuntimeError: If initialization fails and stop_on_error is True
        """
        logger.info("Initializing all components...")
        self._emit_event("initialization_started")
        try:
            result = self._lifecycle.initialize_all(stop_on_error=stop_on_error)
            logger.info(f"Initialized {len(result)} components")
            self._emit_event("initialization_completed", count=len(result))
            return result
        except Exception as exc:
            logger.error(f"Initialization failed: {exc}")
            self._emit_event("initialization_failed", error=str(exc))
            raise

    def start_all(self, *, stop_on_error: bool = True) -> list[str]:
        """Start all initialized components in dependency order.

        Args:
            stop_on_error: If True, stop on first error

        Returns:
            List of successfully started component names

        Raises:
            RuntimeError: If startup fails and stop_on_error is True
        """
        logger.info("Starting all components...")
        self._emit_event("startup_started")
        try:
            result = self._lifecycle.start_all(stop_on_error=stop_on_error)
            logger.info(f"Started {len(result)} components")
            self._emit_event("startup_completed", count=len(result))
            return result
        except Exception as exc:
            logger.error(f"Startup failed: {exc}")
            self._emit_event("startup_failed", error=str(exc))
            raise

    def stop_all(self) -> list[str]:
        """Stop all running components in reverse dependency order.

        Returns:
            List of successfully stopped component names
        """
        logger.info("Stopping all components...")
        self._emit_event("shutdown_started")
        result = self._lifecycle.stop_all()
        logger.info(f"Stopped {len(result)} components")
        self._emit_event("shutdown_completed", count=len(result))
        return result

    def initialize_component(self, name: str) -> None:
        """Initialize a specific component.

        Args:
            name: Component name

        Raises:
            KeyError: If component not found
            RuntimeError: If initialization fails
        """
        self._lifecycle.initialize_component(name)
        logger.info(f"Initialized component: {name}")
        self._emit_event("component_initialized", name=name)

    def start_component(self, name: str) -> None:
        """Start a specific component.

        Args:
            name: Component name

        Raises:
            KeyError: If component not found
            RuntimeError: If startup fails
        """
        self._lifecycle.start_component(name)
        logger.info(f"Started component: {name}")
        self._emit_event("component_started", name=name)

    def stop_component(self, name: str) -> None:
        """Stop a specific component.

        Args:
            name: Component name

        Raises:
            KeyError: If component not found
        """
        self._lifecycle.stop_component(name)
        logger.info(f"Stopped component: {name}")
        self._emit_event("component_stopped", name=name)

    def restart_component(self, name: str) -> None:
        """Restart a specific component.

        Args:
            name: Component name

        Raises:
            KeyError: If component not found
            RuntimeError: If restart fails
        """
        self._lifecycle.restart_component(name)
        logger.info(f"Restarted component: {name}")
        self._emit_event("component_restarted", name=name)

    # ------------------------------------------------------------------
    # Health Monitoring
    # ------------------------------------------------------------------

    def check_component_health(self, name: str) -> ComponentHealth:
        """Check health of a specific component.

        Args:
            name: Component name

        Returns:
            ComponentHealth for the component

        Raises:
            KeyError: If component not found
        """
        component = self._registry.get(name)
        return component.check_health()

    def aggregate_health(self) -> dict[str, ComponentHealth]:
        """Aggregate health status from all components.

        Returns:
            Dictionary mapping component names to their health status
        """
        health_map: dict[str, ComponentHealth] = {}

        for component in self._registry.get_all():
            try:
                health_map[component.metadata.name] = component.check_health()
            except Exception as exc:
                logger.error(f"Failed to check health of {component.metadata.name}: {exc}")

        return health_map

    def is_system_healthy(self) -> bool:
        """Check if all components are healthy.

        Returns:
            True if all components are healthy, False otherwise
        """
        health_map = self.aggregate_health()
        return all(health.healthy for health in health_map.values())

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_architecture(self) -> ValidationResult:
        """Validate architectural constraints and compliance.

        Returns:
            ValidationResult with all issues found
        """
        logger.info("Validating architecture...")
        result = self._validator.validate_all()
        logger.info(
            f"Validation completed: {len(result.issues)} issues found, passed={result.passed}"
        )
        return result

    def validate_component(self, name: str) -> ValidationResult:
        """Validate a specific component.

        Args:
            name: Component name

        Returns:
            ValidationResult for the component

        Raises:
            KeyError: If component not found
        """
        return self._validator.validate_component(name)

    def add_validation_rule(self, rule: Callable[[ComponentRegistry], list[Any]]) -> None:
        """Add a custom validation rule.

        Args:
            rule: Function that takes registry and returns list of validation issues
        """
        self._validator.add_custom_rule(rule)

    # ------------------------------------------------------------------
    # Event System
    # ------------------------------------------------------------------

    def on(self, event_name: str, handler: Callable[..., None]) -> None:
        """Register an event handler.

        Args:
            event_name: Name of the event to listen for
            handler: Callback function to invoke on event
        """
        if event_name not in self._event_handlers:
            self._event_handlers[event_name] = []
        self._event_handlers[event_name].append(handler)

    def _emit_event(self, event_name: str, **kwargs: Any) -> None:
        """Emit an event to registered handlers.

        Args:
            event_name: Name of the event
            **kwargs: Event data to pass to handlers
        """
        handlers = self._event_handlers.get(event_name, [])
        for handler in handlers:
            try:
                handler(**kwargs)
            except Exception as exc:
                logger.error(f"Event handler failed for {event_name}: {exc}")

    # ------------------------------------------------------------------
    # Utility Methods
    # ------------------------------------------------------------------

    def get_dependency_graph(self) -> dict[str, list[str]]:
        """Get the component dependency graph.

        Returns:
            Dictionary mapping component names to their dependencies
        """
        return self._registry.get_dependency_graph()

    def get_initialization_order(self) -> Sequence[str]:
        """Get the calculated initialization order for components.

        Returns:
            List of component names in initialization order

        Raises:
            ValueError: If circular dependencies detected
        """
        return self._registry.get_initialization_order()

    def get_status_summary(self) -> dict[str, int]:
        """Get a summary of component statuses.

        Returns:
            Dictionary mapping status names to counts
        """
        summary: dict[str, int] = {status.value: 0 for status in ComponentStatus}
        for component in self._registry.get_all():
            summary[component.status.value] += 1
        return summary

    def clear(self) -> None:
        """Remove all components from the integrator."""
        self.stop_all()
        self._registry.clear()
        logger.info("Cleared all components from integrator")
