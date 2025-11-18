"""Lifecycle management for system components.

This module provides lifecycle coordination for components, ensuring proper
initialization, startup, and shutdown sequences based on dependency ordering.
"""

from __future__ import annotations

import logging
from typing import Callable

from core.architecture_integrator.component import ComponentStatus
from core.architecture_integrator.registry import ComponentRegistry

logger = logging.getLogger(__name__)


class LifecycleManager:
    """Manages the lifecycle of system components."""

    def __init__(self, registry: ComponentRegistry) -> None:
        """Initialize the lifecycle manager.

        Args:
            registry: Component registry to manage
        """
        self._registry = registry
        self._on_error: Callable[[str, Exception], None] | None = None

    def set_error_handler(self, handler: Callable[[str, Exception], None]) -> None:
        """Set a callback for lifecycle errors.

        Args:
            handler: Function to call with (component_name, exception) on errors
        """
        self._on_error = handler

    def initialize_all(self, *, stop_on_error: bool = True) -> list[str]:
        """Initialize all components in dependency order.

        Args:
            stop_on_error: If True, stop initialization on first error

        Returns:
            List of successfully initialized component names

        Raises:
            RuntimeError: If initialization fails and stop_on_error is True
        """
        try:
            order = self._registry.get_initialization_order()
        except ValueError as exc:
            logger.error(f"Failed to determine initialization order: {exc}")
            raise

        initialized: list[str] = []

        for name in order:
            try:
                component = self._registry.get(name)
                if component.status == ComponentStatus.UNINITIALIZED:
                    logger.info(f"Initializing component: {name}")
                    component.initialize()
                    initialized.append(name)
                    logger.info(f"Component {name} initialized successfully")
            except Exception as exc:
                logger.error(f"Failed to initialize component {name}: {exc}")
                if self._on_error:
                    self._on_error(name, exc)
                if stop_on_error:
                    raise RuntimeError(f"Component initialization failed: {name}") from exc

        return initialized

    def start_all(self, *, stop_on_error: bool = True) -> list[str]:
        """Start all initialized components in dependency order.

        Args:
            stop_on_error: If True, stop startup on first error

        Returns:
            List of successfully started component names

        Raises:
            RuntimeError: If startup fails and stop_on_error is True
        """
        try:
            order = self._registry.get_initialization_order()
        except ValueError as exc:
            logger.error(f"Failed to determine startup order: {exc}")
            raise

        started: list[str] = []

        for name in order:
            try:
                component = self._registry.get(name)
                if component.status == ComponentStatus.INITIALIZED:
                    logger.info(f"Starting component: {name}")
                    component.start()
                    started.append(name)
                    logger.info(f"Component {name} started successfully")
                elif component.status != ComponentStatus.RUNNING:
                    logger.warning(f"Component {name} not in INITIALIZED state, skipping start")
            except Exception as exc:
                logger.error(f"Failed to start component {name}: {exc}")
                if self._on_error:
                    self._on_error(name, exc)
                if stop_on_error:
                    raise RuntimeError(f"Component startup failed: {name}") from exc

        return started

    def stop_all(self, *, reverse_order: bool = True) -> list[str]:
        """Stop all running components.

        Args:
            reverse_order: If True, stop in reverse dependency order

        Returns:
            List of successfully stopped component names
        """
        try:
            order = self._registry.get_initialization_order()
            if reverse_order:
                order = list(reversed(order))
        except ValueError as exc:
            logger.error(f"Failed to determine shutdown order: {exc}")
            # Continue with arbitrary order
            order = [comp.metadata.name for comp in self._registry.get_all()]

        stopped: list[str] = []

        for name in order:
            try:
                component = self._registry.get(name)
                if component.status in {
                    ComponentStatus.RUNNING,
                    ComponentStatus.DEGRADED,
                }:
                    logger.info(f"Stopping component: {name}")
                    component.stop()
                    stopped.append(name)
                    logger.info(f"Component {name} stopped successfully")
            except Exception as exc:
                logger.error(f"Failed to stop component {name}: {exc}")
                if self._on_error:
                    self._on_error(name, exc)
                # Continue stopping other components

        return stopped

    def initialize_component(self, name: str) -> None:
        """Initialize a specific component.

        Args:
            name: Component name

        Raises:
            KeyError: If component not found
            RuntimeError: If initialization fails
        """
        component = self._registry.get(name)

        # Check dependencies are initialized
        for dep in component.get_dependencies():
            if self._registry.has_component(dep):
                dep_component = self._registry.get(dep)
                if dep_component.status == ComponentStatus.UNINITIALIZED:
                    raise RuntimeError(
                        f"Cannot initialize {name}: dependency {dep} is not initialized"
                    )
            elif not self._registry.has_capability(dep):
                raise RuntimeError(f"Cannot initialize {name}: dependency {dep} is not available")

        component.initialize()

    def start_component(self, name: str) -> None:
        """Start a specific component.

        Args:
            name: Component name

        Raises:
            KeyError: If component not found
            RuntimeError: If startup fails
        """
        component = self._registry.get(name)

        # Check dependencies are running
        for dep in component.get_dependencies():
            if self._registry.has_component(dep):
                dep_component = self._registry.get(dep)
                if dep_component.status not in {
                    ComponentStatus.RUNNING,
                    ComponentStatus.DEGRADED,
                }:
                    raise RuntimeError(f"Cannot start {name}: dependency {dep} is not running")

        component.start()

    def stop_component(self, name: str) -> None:
        """Stop a specific component.

        Args:
            name: Component name

        Raises:
            KeyError: If component not found
        """
        component = self._registry.get(name)
        component.stop()

    def restart_component(self, name: str) -> None:
        """Restart a specific component.

        Args:
            name: Component name

        Raises:
            KeyError: If component not found
            RuntimeError: If restart fails
        """
        self.stop_component(name)
        # Re-initialize and start
        component = self._registry.get(name)
        component.status = ComponentStatus.UNINITIALIZED
        self.initialize_component(name)
        self.start_component(name)
