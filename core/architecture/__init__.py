"""Core Architecture module defining the 7 key system principles.

This module provides the foundational architecture framework for TradePulse,
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
    ControllablePrinciple,
    IntegrativePrinciple,
    ModularPrinciple,
    NeuroOrientedPrinciple,
    ReproduciblePrinciple,
    RoleBasedPrinciple,
    SystemArchitecture,
    get_system_architecture,
)

__all__ = [
    "ArchitecturePrinciple",
    "NeuroOrientedPrinciple",
    "ModularPrinciple",
    "RoleBasedPrinciple",
    "IntegrativePrinciple",
    "ReproduciblePrinciple",
    "ControllablePrinciple",
    "AutonomousPrinciple",
    "SystemArchitecture",
    "get_system_architecture",
]
