# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Physical constants for market modeling.

These constants provide normalized, dimensionless values for physics-inspired
market calculations. Values are scaled to typical market magnitudes for
numerical stability.
"""

from typing import Final


class PhysicsConstants:
    """Physical constants normalized for financial market scales.

    All constants are dimensionless and scaled for typical market conditions:
    - Prices in range [1, 10000]
    - Time in days/hours
    - Velocities as percent changes per unit time
    - Forces as market pressure indicators
    """

    # Newton's Laws
    # Market "mass" representing liquidity/capitalization (normalized)
    MARKET_MASS_SCALE: Final[float] = 1.0

    # Gravity
    # Gravitational constant for market attraction (normalized)
    # G = 6.674e-11 in SI, but we use dimensionless 1.0 for markets
    GRAVITATIONAL_CONSTANT: Final[float] = 1.0

    # Minimum distance to prevent singularities (in price space)
    MIN_DISTANCE: Final[float] = 1e-6

    # Thermodynamics
    # Boltzmann constant for market entropy (normalized)
    # k_B = 1.38e-23 J/K in SI, normalized to 1.0 for markets
    BOLTZMANN_CONSTANT: Final[float] = 1.0

    # Reference temperature for market systems (normalized)
    REFERENCE_TEMPERATURE: Final[float] = 300.0

    # Maxwell's Equations / Wave Propagation
    # Speed of information propagation in markets (normalized)
    # Represents how fast price signals travel
    SPEED_OF_INFORMATION: Final[float] = 1.0

    # Permeability and permittivity analogs (normalized)
    MARKET_PERMEABILITY: Final[float] = 1.0
    MARKET_PERMITTIVITY: Final[float] = 1.0

    # Relativity
    # Maximum relative velocity (speed of information)
    MAX_VELOCITY: Final[float] = 1.0

    # Reference frame velocity threshold
    VELOCITY_THRESHOLD: Final[float] = 0.1

    # Time-frequency uncertainty (Gabor limit)
    # Removed 2026-06-17: PLANCK_REDUCED / MIN_POSITION_UNCERTAINTY /
    # MIN_MOMENTUM_UNCERTAINTY were a fabricated ℏ=1.0 dressing a classical
    # std-product as Heisenberg ΔxΔp ≥ ℏ/2. core/physics/uncertainty.py now
    # implements the exact, anchored Gabor bound Δt·Δf ≥ 1/(4π) (INV-GABOR1),
    # which needs no Planck constant — the bound is the pure-math constant
    # 1/(4π), defined in uncertainty.py as GABOR_LIMIT.


__all__ = ["PhysicsConstants"]
