# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Architecture Integrator for GeoSync.

This module provides centralized coordination and integration of architectural
components across the GeoSync system. The Architecture Integrator serves as
a unified orchestration layer that manages component lifecycles, validates
architectural constraints, and ensures proper integration between subsystems.

Key responsibilities:
- Component registration and discovery
- Dependency graph management and validation
- Configuration consistency across components
- Health check aggregation and monitoring
- Lifecycle coordination (initialization, startup, shutdown)
- Event-driven inter-component communication
- Architecture compliance validation

Example:
    >>> from core.architecture_integrator import ArchitectureIntegrator
    >>> integrator = ArchitectureIntegrator()
    >>> integrator.register_component("data_ingestion", data_service)
    >>> integrator.initialize_all()
    >>> health = integrator.aggregate_health()
"""

from core.architecture_integrator.component import (
    Component,
    ComponentHealth,
    ComponentMetadata,
    ComponentStatus,
)
from core.architecture_integrator.integrator import ArchitectureIntegrator
from core.architecture_integrator.lifecycle import (
    GracefulShutdownConfig,
    HealthAggregation,
    LifecycleEvent,
    LifecycleEventData,
    LifecycleEventHandler,
    LifecycleManager,
)
from core.architecture_integrator.registry import ComponentRegistry
from core.architecture_integrator.validator import (
    ArchitectureValidator,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
)

__all__ = [
    "ArchitectureIntegrator",
    "Component",
    "ComponentHealth",
    "ComponentStatus",
    "ComponentMetadata",
    "ComponentRegistry",
    "GracefulShutdownConfig",
    "HealthAggregation",
    "LifecycleEvent",
    "LifecycleEventData",
    "LifecycleEventHandler",
    "LifecycleManager",
    "ArchitectureValidator",
    "ValidationIssue",
    "ValidationSeverity",
    "ValidationResult",
]
