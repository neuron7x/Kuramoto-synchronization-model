# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Core Architecture module defining the 7 key system principles.

This module provides the foundational architecture framework for GeoSync,
implementing seven critical design principles:

1. **Neuro-oriented** (Нейроорієнтована): Brain-inspired computational models
2. **Modular** (Модульна): Loosely coupled, independently deployable components
3. **Role-based** (Рольова): Clear separation of responsibilities and access control
4. **Integrative** (Інтегративна): Seamless component integration and data flow
5. **Reproducible** (Відтворювана): Deterministic behavior and auditable state
6. **Controllable** (Контрольована): Full operational oversight and intervention
7. **Autonomous** (Автономна): Self-regulating and adaptive behavior

For detailed architecture documentation, see:
- docs/ARCHITECTURE.md
- docs/CONCEPTUAL_ARCHITECTURE_UA.md
"""

from core.architecture.system_principles import (
    ArchitecturePrinciple,
    AutonomousPrinciple,
    AutonomyLevel,
    ComponentRole,
    ControlAction,
    ControllablePrinciple,
    IntegrationContract,
    IntegrativePrinciple,
    ModularPrinciple,
    ModuleCapability,
    NeuroOrientedPrinciple,
    PrincipleStatus,
    PrincipleViolation,
    ReproduciblePrinciple,
    RoleBasedPrinciple,
    StateSnapshot,
    SystemArchitecture,
    get_system_architecture,
)

__all__ = [
    # Principles
    "ArchitecturePrinciple",
    "NeuroOrientedPrinciple",
    "ModularPrinciple",
    "RoleBasedPrinciple",
    "IntegrativePrinciple",
    "ReproduciblePrinciple",
    "ControllablePrinciple",
    "AutonomousPrinciple",
    # System
    "SystemArchitecture",
    "get_system_architecture",
    # Enums
    "PrincipleStatus",
    "ComponentRole",
    "AutonomyLevel",
    "ModuleCapability",
    # Data Classes
    "PrincipleViolation",
    "IntegrationContract",
    "StateSnapshot",
    "ControlAction",
]
