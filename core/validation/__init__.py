"""Core validation modules for TradePulse system integrity.

This package provides comprehensive validation components built on three foundational
pillars as specified in the architecture:

- **Physics**: Thermodynamic energy constraints and conservation laws
- **Neuroscience**: Neural pathway coherence and signal integrity
- **Mathematical Logic**: Data validation with formal mathematical constraints

These validators ensure the system operates within physically plausible bounds,
maintains neurologically-inspired coherence, and enforces mathematical rigor
across all data transformations.

For more information, see the documentation at https://docs.tradepulse.io/validation
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
]
