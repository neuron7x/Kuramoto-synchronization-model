"""TradePulse Integration Module.

This module re-exports the unified system integration components from the
core.integration package, providing a clean API for integrating all
TradePulse modules and services into a unified system.

Example:
    >>> from tradepulse.integration import SystemIntegrator, SystemIntegratorBuilder
    >>> builder = SystemIntegratorBuilder()
    >>> integrator = builder.with_auto_start(True).build()
    >>> integrator.bootstrap()
    >>> health = integrator.get_unified_health()
"""

__CANONICAL__ = True

# Re-export from core.integration
from core.integration import (
    AgentCoordinatorAdapter,
    IntegrationConfig,
    ServiceRegistryAdapter,
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
