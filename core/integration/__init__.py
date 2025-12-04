"""Unified System Integration for TradePulse.

This module provides a unified integration layer that combines all TradePulse
modules and services into a single, cohesive system. It bridges:

- Architecture Integrator (component lifecycle and coordination)
- TradePulse Orchestrator (service orchestration)
- Service Registry (microservices management)
- Agent Coordinator (agent coordination and task management)

The SystemIntegrator serves as the primary entry point for bootstrapping
and managing the entire TradePulse platform.

Example:
    >>> from core.integration import SystemIntegrator
    >>> integrator = SystemIntegrator()
    >>> integrator.bootstrap()
    >>> integrator.start_all()
    >>> health = integrator.get_system_health()
"""

from core.integration.adapters import (
    AgentCoordinatorAdapter,
    ServiceRegistryAdapter,
)
from core.integration.system_integrator import (
    IntegrationConfig,
    SystemIntegrator,
    SystemIntegratorBuilder,
)

__all__ = [
    "AgentCoordinatorAdapter",
    "IntegrationConfig",
    "ServiceRegistryAdapter",
    "SystemIntegrator",
    "SystemIntegratorBuilder",
]
