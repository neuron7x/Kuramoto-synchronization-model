# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Physics-inspired market modeling framework.

This module provides fundamental physical laws and constants for physics-inspired
algorithmic trading. By grounding market models in physical principles, we aim to:

1. Reduce noise in predictions through deterministic constraints
2. Improve stability via conservation laws
3. Enhance interpretability through physical analogies
4. Provide falsifiable hypotheses for market behavior

The seven fundamental laws integrated are:
- Newton's Laws of Motion (momentum, force, inertia)
- Universal Gravitation (market entity attraction)
- Conservation Laws (energy, momentum)
- Thermodynamics (entropy, free energy, equilibrium)
- Maxwell's Equations (field theory, wave propagation)
- Relativity (reference frames, time dilation)
- Heisenberg's Uncertainty Principle (position-momentum tradeoff)
"""

from .constants import PhysicsConstants
from .conservation import (
    check_energy_conservation,
    check_momentum_conservation,
    compute_market_energy,
    compute_market_momentum,
)
from .gravity import (
    compute_market_gravity,
    gravitational_force,
    gravitational_potential,
    market_gravity_center,
)
from .maxwell import (
    compute_market_field_curl,
    compute_market_field_divergence,
    propagate_price_wave,
    wave_energy,
)
from .newton import (
    compute_acceleration,
    compute_force,
    compute_momentum,
    compute_price_acceleration,
    compute_price_velocity,
)
from .relativity import (
    compute_relative_time,
    lorentz_factor,
    lorentz_transform,
    relativistic_momentum,
    time_dilation_factor,
    velocity_addition,
)
from .thermodynamics import (
    boltzmann_entropy,
    compute_free_energy,
    compute_market_temperature,
    gibbs_free_energy,
    is_thermodynamic_equilibrium,
    thermal_equilibrium_distance,
)
from .uncertainty import (
    check_uncertainty_principle,
    heisenberg_uncertainty,
    information_limit,
    minimum_uncertainty_product,
    optimal_measurement_tradeoff,
    position_momentum_uncertainty,
)

__all__ = [
    # Constants
    "PhysicsConstants",
    # Newton's Laws
    "compute_momentum",
    "compute_force",
    "compute_acceleration",
    "compute_price_velocity",
    "compute_price_acceleration",
    # Gravitation
    "gravitational_force",
    "gravitational_potential",
    "compute_market_gravity",
    "market_gravity_center",
    # Conservation
    "compute_market_energy",
    "compute_market_momentum",
    "check_energy_conservation",
    "check_momentum_conservation",
    # Thermodynamics
    "boltzmann_entropy",
    "compute_market_temperature",
    "compute_free_energy",
    "gibbs_free_energy",
    "thermal_equilibrium_distance",
    "is_thermodynamic_equilibrium",
    # Maxwell's Equations
    "compute_market_field_divergence",
    "compute_market_field_curl",
    "propagate_price_wave",
    "wave_energy",
    # Relativity
    "lorentz_factor",
    "lorentz_transform",
    "relativistic_momentum",
    "compute_relative_time",
    "velocity_addition",
    "time_dilation_factor",
    # Heisenberg Uncertainty
    "heisenberg_uncertainty",
    "minimum_uncertainty_product",
    "position_momentum_uncertainty",
    "check_uncertainty_principle",
    "optimal_measurement_tradeoff",
    "information_limit",
]
