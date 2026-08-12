# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Core validation modules for GeoSync system integrity.

This package provides comprehensive validation components built on three foundational
pillars as specified in the architecture:

- **Physics**: Thermodynamic energy constraints and conservation laws
- **Neuroscience**: Neural pathway coherence and signal integrity
- **Mathematical Logic**: Data validation with formal mathematical constraints
- **System Integration**: Unified validation across all domains

These validators ensure the system operates within physically plausible bounds,
maintains neurologically-inspired coherence, and enforces mathematical rigor
across all data transformations.

For more information, see the documentation at https://docs.geosync.io/validation
"""

from .mathematical_logic import (
    DataIntegrityReport,
    MathematicalLogicValidator,
    ValidationResult,
)
from .neuro_integrity import (
    NeuroIntegrity,
    NeuroIntegrityConfig,
    NeuroIntegrityReport,
    PathwayState,
)
from .physics_validator import (
    EnergyBounds,
    PhysicsConstraintReport,
    PhysicsValidator,
    ThermodynamicState,
)
from .system_integrator import (
    SystemHealthLevel,
    SystemIntegrator,
    SystemState,
    SystemValidationConfig,
    SystemValidationReport,
    compute_system_health_score,
)

__all__ = [
    # Physics validation
    "PhysicsValidator",
    "ThermodynamicState",
    "PhysicsConstraintReport",
    "EnergyBounds",
    # Neuro integrity
    "NeuroIntegrity",
    "NeuroIntegrityConfig",
    "NeuroIntegrityReport",
    "PathwayState",
    # Mathematical logic
    "MathematicalLogicValidator",
    "ValidationResult",
    "DataIntegrityReport",
    # System integration
    "SystemIntegrator",
    "SystemState",
    "SystemValidationConfig",
    "SystemValidationReport",
    "SystemHealthLevel",
    "compute_system_health_score",
]
