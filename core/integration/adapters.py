# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Adapters for integrating modules with the unified system.

This module provides adapter classes that bridge various GeoSync subsystems
with the unified SystemIntegrator. Each adapter implements the component
protocol to enable lifecycle management and health monitoring.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List

from core.architecture_integrator.component import ComponentHealth, ComponentStatus

if TYPE_CHECKING:
    from application.microservices.registry import ServiceRegistry
    from modules.agent_coordinator import AgentCoordinator


class ServiceRegistryAdapter:
    """Adapter for ServiceRegistry to work with the unified system.

    Bridges the ServiceRegistry microservices management with the
    Architecture Integrator's component lifecycle protocol.
    """

    def __init__(self, registry: ServiceRegistry) -> None:
        """Initialize adapter with a ServiceRegistry instance.

        Args:
            registry: ServiceRegistry instance to adapt
        """
        self._registry = registry
        self._initialized = False
        self._started = False

    def initialize(self) -> None:
        """Initialize the service registry."""
        # ServiceRegistry is typically created with services already initialized
        self._initialized = True

    def start(self) -> None:
        """Start all services in the registry."""
        self._registry.start_all()
        self._started = True

    def stop(self) -> None:
        """Stop all services in the registry."""
        self._registry.stop_all()
        self._started = False

    def health_check(self) -> ComponentHealth:
        """Check health of all services in the registry.

        Returns:
            ComponentHealth aggregating status from all services
        """
        if not self._initialized:
            return ComponentHealth(
                status=ComponentStatus.UNINITIALIZED,
                healthy=False,
                message="Service registry not initialized",
            )

        if not self._started:
            return ComponentHealth(
                status=ComponentStatus.INITIALIZED,
                healthy=True,
                message="Service registry initialized but not started",
            )

        # Check individual service states
        services = self._registry.services()
        unhealthy_services: List[str] = []
        metrics: Dict[str, float] = {"total_services": float(len(services))}

        # Import ServiceState at runtime to avoid circular imports
        from application.microservices.base import ServiceState

        for service in services:
            if service.state == ServiceState.ERROR:
                unhealthy_services.append(service.name)

        healthy_count = len(services) - len(unhealthy_services)
        metrics["healthy_services"] = float(healthy_count)

        if unhealthy_services:
            return ComponentHealth(
                status=ComponentStatus.DEGRADED,
                healthy=False,
                message=f"Unhealthy services: {', '.join(unhealthy_services)}",
                metrics=metrics,
            )

        return ComponentHealth(
            status=ComponentStatus.RUNNING,
            healthy=True,
            message=f"All {len(services)} services operational",
            metrics=metrics,
        )

    @property
    def registry(self) -> ServiceRegistry:
        """Access the underlying ServiceRegistry."""
        return self._registry

    def get_service_names(self) -> List[str]:
        """Get list of registered service names."""
        return [s.name for s in self._registry.services()]


class AgentCoordinatorAdapter:
    """Adapter for AgentCoordinator to work with the unified system.

    Bridges the AgentCoordinator task management with the
    Architecture Integrator's component lifecycle protocol.
    """

    def __init__(self, coordinator: AgentCoordinator) -> None:
        """Initialize adapter with an AgentCoordinator instance.

        Args:
            coordinator: AgentCoordinator instance to adapt
        """
        self._coordinator = coordinator
        self._initialized = False
        self._started = False

    def initialize(self) -> None:
        """Initialize the agent coordinator."""
        # AgentCoordinator is typically ready after construction
        self._initialized = True

    def start(self) -> None:
        """Start the agent coordinator and begin processing tasks."""
        self._started = True

    def stop(self) -> None:
        """Stop the agent coordinator and clear pending tasks."""
        # Make emergency stop decision to halt all agents
        self._coordinator.make_decision(
            "emergency_stop",
            {"reason": "system shutdown"},
        )
        self._started = False

    def health_check(self) -> ComponentHealth:
        """Check health of the agent coordinator.

        Returns:
            ComponentHealth with coordinator status
        """
        if not self._initialized:
            return ComponentHealth(
                status=ComponentStatus.UNINITIALIZED,
                healthy=False,
                message="Agent coordinator not initialized",
            )

        if not self._started:
            return ComponentHealth(
                status=ComponentStatus.INITIALIZED,
                healthy=True,
                message="Agent coordinator initialized but not started",
            )

        # Get system health from coordinator
        health_data = self._coordinator.get_system_health()
        health_score = float(health_data.get("health_score", 0))

        metrics: Dict[str, float] = {
            "health_score": health_score,
            "total_agents": float(health_data.get("total_agents", 0)),
            "active_agents": float(health_data.get("active_agents", 0)),
            "error_agents": float(health_data.get("error_agents", 0)),
            "queued_tasks": float(health_data.get("queued_tasks", 0)),
            "active_tasks": float(health_data.get("active_tasks", 0)),
        }

        error_agents = int(health_data.get("error_agents", 0))
        if error_agents > 0:
            return ComponentHealth(
                status=ComponentStatus.DEGRADED,
                healthy=False,
                message=f"{error_agents} agents in error state",
                metrics=metrics,
            )

        if health_score < 50.0:
            return ComponentHealth(
                status=ComponentStatus.DEGRADED,
                healthy=False,
                message=f"System health score low: {health_score:.1f}",
                metrics=metrics,
            )

        return ComponentHealth(
            status=ComponentStatus.RUNNING,
            healthy=True,
            message=f"Agent coordinator operational (health: {health_score:.1f})",
            metrics=metrics,
        )

    @property
    def coordinator(self) -> AgentCoordinator:
        """Access the underlying AgentCoordinator."""
        return self._coordinator

    def get_agent_count(self) -> int:
        """Get the number of registered agents."""
        summary = self._coordinator.get_coordination_summary()
        return summary.get("registered_agents", 0)

    def process_pending_tasks(self) -> List[str]:
        """Process any pending tasks in the coordinator queue.

        Returns:
            List of processed task IDs
        """
        if not self._started:
            return []
        return self._coordinator.process_tasks()


def create_service_registry_adapter(
    registry: ServiceRegistry,
) -> ServiceRegistryAdapter:
    """Factory function to create a ServiceRegistryAdapter.

    Args:
        registry: ServiceRegistry instance to adapt

    Returns:
        Configured ServiceRegistryAdapter
    """
    return ServiceRegistryAdapter(registry)


def create_agent_coordinator_adapter(
    coordinator: AgentCoordinator,
) -> AgentCoordinatorAdapter:
    """Factory function to create an AgentCoordinatorAdapter.

    Args:
        coordinator: AgentCoordinator instance to adapt

    Returns:
        Configured AgentCoordinatorAdapter
    """
    return AgentCoordinatorAdapter(coordinator)
