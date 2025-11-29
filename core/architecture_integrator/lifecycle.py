"""Lifecycle management for system components.

This module provides lifecycle coordination for components, ensuring proper
initialization, startup, and shutdown sequences based on dependency ordering.

Extended capabilities include:
- Event hooks for lifecycle state transitions
- Graceful shutdown with configurable timeouts
- Configuration reload at runtime
- Health check aggregation
- Recovery mechanisms for failed components
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Mapping

from core.architecture_integrator.component import ComponentHealth, ComponentStatus
from core.architecture_integrator.registry import ComponentRegistry

logger = logging.getLogger(__name__)


class LifecycleEvent(str, Enum):
    """Events emitted during component lifecycle transitions."""

    INITIALIZING = "initializing"
    INITIALIZED = "initialized"
    STARTING = "starting"
    STARTED = "started"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    DEGRADED = "degraded"
    RECOVERED = "recovered"
    CONFIG_RELOADED = "config_reloaded"
    HEALTH_CHECK = "health_check"


@dataclass(frozen=True, slots=True)
class LifecycleEventData:
    """Data associated with a lifecycle event."""

    event: LifecycleEvent
    component_name: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    previous_status: ComponentStatus | None = None
    new_status: ComponentStatus | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    error: Exception | None = None


@dataclass(slots=True)
class GracefulShutdownConfig:
    """Configuration for graceful shutdown behavior."""

    timeout_seconds: float = 30.0
    drain_period_seconds: float = 5.0
    force_after_timeout: bool = True
    max_retry_attempts: int = 3


@dataclass(slots=True)
class HealthAggregation:
    """Aggregated health status across all components."""

    overall_healthy: bool
    total_components: int
    healthy_count: int
    degraded_count: int
    failed_count: int
    component_health: dict[str, ComponentHealth]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def health_percentage(self) -> float:
        """Calculate percentage of healthy components."""
        if self.total_components == 0:
            return 100.0
        return (self.healthy_count / self.total_components) * 100.0


# Type alias for lifecycle event handlers
LifecycleEventHandler = Callable[[LifecycleEventData], None]


class LifecycleManager:
    """Manages the lifecycle of system components.

    Provides extended capabilities including:
    - Event hooks for monitoring lifecycle transitions
    - Graceful shutdown with configurable timeouts
    - Configuration reload at runtime
    - Health aggregation across all components
    - Recovery mechanisms for failed components
    """

    def __init__(
        self,
        registry: ComponentRegistry,
        *,
        shutdown_config: GracefulShutdownConfig | None = None,
    ) -> None:
        """Initialize the lifecycle manager.

        Args:
            registry: Component registry to manage
            shutdown_config: Configuration for graceful shutdown behavior
        """
        self._registry = registry
        self._on_error: Callable[[str, Exception], None] | None = None
        self._event_handlers: list[LifecycleEventHandler] = []
        self._shutdown_config = shutdown_config or GracefulShutdownConfig()
        self._configurations: dict[str, Mapping[str, Any]] = {}

    def set_error_handler(self, handler: Callable[[str, Exception], None]) -> None:
        """Set a callback for lifecycle errors.

        Args:
            handler: Function to call with (component_name, exception) on errors
        """
        self._on_error = handler

    def add_event_handler(self, handler: LifecycleEventHandler) -> None:
        """Register a handler for lifecycle events.

        Args:
            handler: Function to call when lifecycle events occur
        """
        if handler not in self._event_handlers:
            self._event_handlers.append(handler)

    def remove_event_handler(self, handler: LifecycleEventHandler) -> None:
        """Remove a previously registered event handler.

        Args:
            handler: Handler to remove
        """
        if handler in self._event_handlers:
            self._event_handlers.remove(handler)

    def _emit_event(self, event_data: LifecycleEventData) -> None:
        """Emit a lifecycle event to all registered handlers.

        Args:
            event_data: Event data to emit
        """
        for handler in self._event_handlers:
            try:
                handler(event_data)
            except Exception as exc:
                logger.warning(f"Event handler failed for {event_data.event}: {exc}")

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
                    previous_status = component.status
                    self._emit_event(
                        LifecycleEventData(
                            event=LifecycleEvent.INITIALIZING,
                            component_name=name,
                            previous_status=previous_status,
                        )
                    )
                    logger.info(f"Initializing component: {name}")
                    component.initialize()
                    initialized.append(name)
                    self._emit_event(
                        LifecycleEventData(
                            event=LifecycleEvent.INITIALIZED,
                            component_name=name,
                            previous_status=previous_status,
                            new_status=component.status,
                        )
                    )
                    logger.info(f"Component {name} initialized successfully")
            except Exception as exc:
                logger.error(f"Failed to initialize component {name}: {exc}")
                self._emit_event(
                    LifecycleEventData(
                        event=LifecycleEvent.FAILED,
                        component_name=name,
                        error=exc,
                        metadata={"phase": "initialization"},
                    )
                )
                if self._on_error:
                    self._on_error(name, exc)
                if stop_on_error:
                    raise RuntimeError(
                        f"Component initialization failed: {name}"
                    ) from exc

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
                    previous_status = component.status
                    self._emit_event(
                        LifecycleEventData(
                            event=LifecycleEvent.STARTING,
                            component_name=name,
                            previous_status=previous_status,
                        )
                    )
                    logger.info(f"Starting component: {name}")
                    component.start()
                    started.append(name)
                    self._emit_event(
                        LifecycleEventData(
                            event=LifecycleEvent.STARTED,
                            component_name=name,
                            previous_status=previous_status,
                            new_status=component.status,
                        )
                    )
                    logger.info(f"Component {name} started successfully")
                elif component.status != ComponentStatus.RUNNING:
                    logger.warning(
                        f"Component {name} not in INITIALIZED state, skipping start"
                    )
            except Exception as exc:
                logger.error(f"Failed to start component {name}: {exc}")
                self._emit_event(
                    LifecycleEventData(
                        event=LifecycleEvent.FAILED,
                        component_name=name,
                        error=exc,
                        metadata={"phase": "startup"},
                    )
                )
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
                    previous_status = component.status
                    self._emit_event(
                        LifecycleEventData(
                            event=LifecycleEvent.STOPPING,
                            component_name=name,
                            previous_status=previous_status,
                        )
                    )
                    logger.info(f"Stopping component: {name}")
                    component.stop()
                    stopped.append(name)
                    self._emit_event(
                        LifecycleEventData(
                            event=LifecycleEvent.STOPPED,
                            component_name=name,
                            previous_status=previous_status,
                            new_status=component.status,
                        )
                    )
                    logger.info(f"Component {name} stopped successfully")
            except Exception as exc:
                logger.error(f"Failed to stop component {name}: {exc}")
                self._emit_event(
                    LifecycleEventData(
                        event=LifecycleEvent.FAILED,
                        component_name=name,
                        error=exc,
                        metadata={"phase": "shutdown"},
                    )
                )
                if self._on_error:
                    self._on_error(name, exc)
                # Continue stopping other components

        return stopped

    def graceful_shutdown(
        self,
        *,
        config: GracefulShutdownConfig | None = None,
    ) -> list[str]:
        """Perform a graceful shutdown of all components.

        This method implements a controlled shutdown sequence:
        1. Signal all components to begin draining
        2. Wait for drain period to allow in-flight work to complete
        3. Stop components in reverse dependency order
        4. Force stop any remaining components if timeout exceeded

        Args:
            config: Override shutdown configuration

        Returns:
            List of successfully stopped component names
        """
        shutdown_config = config or self._shutdown_config
        stopped: list[str] = []
        start_time = time.monotonic()

        logger.info(
            f"Starting graceful shutdown (timeout={shutdown_config.timeout_seconds}s, "
            f"drain={shutdown_config.drain_period_seconds}s)"
        )

        # Emit drain start event for all running components
        running_components = [
            comp.metadata.name
            for comp in self._registry.get_all()
            if comp.status in {ComponentStatus.RUNNING, ComponentStatus.DEGRADED}
        ]

        # Drain period - allow in-flight work to complete
        if shutdown_config.drain_period_seconds > 0:
            logger.info(
                f"Entering drain period ({shutdown_config.drain_period_seconds}s) "
                f"for {len(running_components)} components"
            )
            time.sleep(shutdown_config.drain_period_seconds)

        # Stop components in reverse order with timeout awareness
        try:
            order = self._registry.get_initialization_order()
            order = list(reversed(order))
        except ValueError:
            order = running_components

        for name in order:
            elapsed = time.monotonic() - start_time
            remaining_time = shutdown_config.timeout_seconds - elapsed

            if remaining_time <= 0:
                if shutdown_config.force_after_timeout:
                    logger.warning(
                        "Shutdown timeout exceeded, force stopping remaining components"
                    )
                    # Force stop remaining components
                    for remaining_name in order[order.index(name) :]:
                        try:
                            component = self._registry.get(remaining_name)
                            if component.status in {
                                ComponentStatus.RUNNING,
                                ComponentStatus.DEGRADED,
                            }:
                                component.stop()
                                stopped.append(remaining_name)
                        except Exception as exc:
                            logger.error(
                                f"Force stop failed for {remaining_name}: {exc}"
                            )
                    break
                else:
                    logger.warning(
                        "Shutdown timeout exceeded, skipping remaining components"
                    )
                    break

            try:
                component = self._registry.get(name)
                if component.status in {
                    ComponentStatus.RUNNING,
                    ComponentStatus.DEGRADED,
                }:
                    self._emit_event(
                        LifecycleEventData(
                            event=LifecycleEvent.STOPPING,
                            component_name=name,
                            previous_status=component.status,
                            metadata={"graceful": True},
                        )
                    )
                    component.stop()
                    stopped.append(name)
                    self._emit_event(
                        LifecycleEventData(
                            event=LifecycleEvent.STOPPED,
                            component_name=name,
                            new_status=component.status,
                            metadata={"graceful": True},
                        )
                    )
            except Exception as exc:
                logger.error(f"Graceful stop failed for {name}: {exc}")
                if self._on_error:
                    self._on_error(name, exc)

        total_time = time.monotonic() - start_time
        logger.info(
            f"Graceful shutdown completed: {len(stopped)} components stopped "
            f"in {total_time:.2f}s"
        )
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
                raise RuntimeError(
                    f"Cannot initialize {name}: dependency {dep} is not available"
                )

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
                    raise RuntimeError(
                        f"Cannot start {name}: dependency {dep} is not running"
                    )

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

    def aggregate_health(self) -> HealthAggregation:
        """Aggregate health status across all registered components.

        Returns:
            HealthAggregation containing overall system health status
        """
        components = self._registry.get_all()
        component_health: dict[str, ComponentHealth] = {}
        healthy_count = 0
        degraded_count = 0
        failed_count = 0

        for component in components:
            health = component.check_health()
            component_health[component.metadata.name] = health

            if health.status == ComponentStatus.RUNNING and health.healthy:
                healthy_count += 1
            elif health.status == ComponentStatus.DEGRADED:
                degraded_count += 1
            elif health.status == ComponentStatus.FAILED or not health.healthy:
                failed_count += 1
            else:
                # Components not yet running are considered healthy if not failed
                if health.status != ComponentStatus.FAILED:
                    healthy_count += 1
                else:
                    failed_count += 1

            self._emit_event(
                LifecycleEventData(
                    event=LifecycleEvent.HEALTH_CHECK,
                    component_name=component.metadata.name,
                    new_status=health.status,
                    metadata={"healthy": health.healthy, "message": health.message},
                )
            )

        total = len(components)
        overall_healthy = failed_count == 0 and degraded_count == 0

        return HealthAggregation(
            overall_healthy=overall_healthy,
            total_components=total,
            healthy_count=healthy_count,
            degraded_count=degraded_count,
            failed_count=failed_count,
            component_health=component_health,
        )

    def store_configuration(
        self,
        component_name: str,
        configuration: Mapping[str, Any],
    ) -> None:
        """Store configuration for a component.

        Args:
            component_name: Name of the component
            configuration: Configuration mapping to store
        """
        self._configurations[component_name] = dict(configuration)
        logger.debug(f"Stored configuration for component: {component_name}")

    def get_configuration(self, component_name: str) -> Mapping[str, Any] | None:
        """Retrieve stored configuration for a component.

        Args:
            component_name: Name of the component

        Returns:
            Configuration mapping if found, None otherwise
        """
        return self._configurations.get(component_name)

    def reload_configuration(
        self,
        component_name: str,
        new_configuration: Mapping[str, Any],
        *,
        restart_required: bool = False,
    ) -> bool:
        """Reload configuration for a running component.

        This method updates the stored configuration and optionally restarts
        the component to apply the changes.

        Args:
            component_name: Name of the component to configure
            new_configuration: New configuration to apply
            restart_required: If True, restart the component after updating config

        Returns:
            True if configuration was successfully reloaded

        Raises:
            KeyError: If component not found
        """
        component = self._registry.get(component_name)
        old_config = self._configurations.get(component_name, {})

        # Store new configuration (make a copy to ensure isolation)
        self._configurations[component_name] = dict(new_configuration)

        # Update component metadata configuration using a defensive copy
        # to avoid unintended sharing of mutable state
        new_config_copy = dict(new_configuration)
        for key, value in new_config_copy.items():
            component.metadata.configuration[key] = value

        self._emit_event(
            LifecycleEventData(
                event=LifecycleEvent.CONFIG_RELOADED,
                component_name=component_name,
                metadata={
                    "old_config_keys": list(old_config.keys()),
                    "new_config_keys": list(new_configuration.keys()),
                    "restart_required": restart_required,
                },
            )
        )

        logger.info(f"Configuration reloaded for component: {component_name}")

        if restart_required and component.status in {
            ComponentStatus.RUNNING,
            ComponentStatus.DEGRADED,
        }:
            logger.info(f"Restarting component {component_name} to apply configuration")
            self.restart_component(component_name)

        return True

    def recover_component(
        self,
        name: str,
        *,
        max_attempts: int = 3,
        delay_seconds: float = 1.0,
        include_stopped: bool = True,
    ) -> bool:
        """Attempt to recover a failed or stopped component.

        This method tries to restart a component with exponential backoff.
        By default, it recovers both FAILED and STOPPED components. Use
        the include_stopped parameter to control whether STOPPED components
        should be recovered.

        Args:
            name: Component name to recover
            max_attempts: Maximum recovery attempts
            delay_seconds: Initial delay between attempts (doubles each attempt)
            include_stopped: If True, recover STOPPED components too; if False,
                            only recover FAILED components

        Returns:
            True if recovery was successful

        Raises:
            KeyError: If component not found
        """
        component = self._registry.get(name)

        target_statuses = {ComponentStatus.FAILED}
        if include_stopped:
            target_statuses.add(ComponentStatus.STOPPED)

        if component.status not in target_statuses:
            logger.info(
                f"Component {name} is not in recoverable state "
                f"(current: {component.status.value}), no recovery needed"
            )
            return True

        logger.info(f"Attempting to recover component: {name}")

        current_delay = delay_seconds
        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(f"Recovery attempt {attempt}/{max_attempts} for {name}")

                # Reset to uninitialized state
                component.status = ComponentStatus.UNINITIALIZED

                # Re-initialize
                self.initialize_component(name)

                # Start if initialization succeeded
                if component.status == ComponentStatus.INITIALIZED:
                    self.start_component(name)

                if component.status == ComponentStatus.RUNNING:
                    self._emit_event(
                        LifecycleEventData(
                            event=LifecycleEvent.RECOVERED,
                            component_name=name,
                            new_status=component.status,
                            metadata={"attempts": attempt},
                        )
                    )
                    logger.info(
                        f"Component {name} recovered successfully after "
                        f"{attempt} attempt(s)"
                    )
                    return True

            except Exception as exc:
                logger.warning(f"Recovery attempt {attempt} failed for {name}: {exc}")
                if attempt < max_attempts:
                    time.sleep(current_delay)
                    current_delay *= 2  # Exponential backoff

        logger.error(
            f"Failed to recover component {name} after {max_attempts} attempts"
        )
        return False

    def recover_all_failed(
        self,
        *,
        max_attempts: int = 3,
        delay_seconds: float = 1.0,
        include_stopped: bool = True,
    ) -> dict[str, bool]:
        """Attempt to recover all failed components.

        Args:
            max_attempts: Maximum recovery attempts per component
            delay_seconds: Initial delay between attempts
            include_stopped: If True, recover STOPPED components too; if False,
                            only recover FAILED components

        Returns:
            Dictionary mapping component names to recovery success status
        """
        results: dict[str, bool] = {}
        target_statuses = {ComponentStatus.FAILED}
        if include_stopped:
            target_statuses.add(ComponentStatus.STOPPED)

        failed_components = [
            comp for comp in self._registry.get_all() if comp.status in target_statuses
        ]

        for component in failed_components:
            name = component.metadata.name
            results[name] = self.recover_component(
                name,
                max_attempts=max_attempts,
                delay_seconds=delay_seconds,
                include_stopped=include_stopped,
            )

        return results

    def get_component_status(self, name: str) -> ComponentStatus:
        """Get the current status of a component.

        Args:
            name: Component name

        Returns:
            Current component status

        Raises:
            KeyError: If component not found
        """
        return self._registry.get(name).status

    def get_all_statuses(self) -> dict[str, ComponentStatus]:
        """Get status of all registered components.

        Returns:
            Dictionary mapping component names to their statuses
        """
        return {comp.metadata.name: comp.status for comp in self._registry.get_all()}
