# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Physics-inspired market modeling framework.

This module provides physics-inspired diagnostics and constants. The
2026-04-30 external audit explicitly **rejects** the framing that
markets obey mechanical conservation laws (no proven mapping
``volume → mass``, ``Δp → velocity``, …). Modules in this package are
therefore organised in two tiers:

* **Anchored physics** — Kuramoto, Lyapunov, Ricci, thermodynamics,
  Landauer, formal-verification kernels. These have invariant ids
  (``INV-K1`` …) bound to peer-reviewed theory and are gated by
  ``physics-kernel-gate.yml``.
* **Volatility / flow proxies** — ``conservation`` (renamed),
  ``newton``, ``gravity``, ``maxwell``, ``relativity``, ``uncertainty``.
  These are interpretive analogies, not physical laws on the market
  state. New code MUST treat their outputs as diagnostics and MUST NOT
  introduce new ``INV-*`` invariants over them without an explicit
  mapping proof. The ``conservation`` module exposes the canonical
  ``*_proxy`` names; the historical ``*_market_*`` / ``*_conservation``
  names remain only as deprecation aliases (see ``conservation.py``).
"""

from .conservation import (
    check_energy_conservation,  # deprecated alias
    check_momentum_conservation,  # deprecated alias
    check_proxy_drift,
    compute_flow_momentum_proxy,
    compute_market_energy,  # deprecated alias
    compute_market_momentum,  # deprecated alias
    compute_volatility_energy_proxy,
)
from .constants import PhysicsConstants

# Physics Engine v2 — T1-T7 modules
from .coulomb import CoulombInteraction

# Research modules — T1-T7 v2
from .diffusion_predictor import BacktestResult as DiffusionBacktestResult
from .diffusion_predictor import DiffusionVolatilityPredictor, VolatilityFrontPrediction
from .engine import GeoSyncPhysicsEngine, PhysicsEngineResult
from .explosive_sync import ESCircuitBreaker, ESProximityResult, ExplosiveSyncDetector
from .forman_ricci import DualTrackRicciMonitor, FormanRicciCurvature, FormanRicciResult
from .free_energy_trading_gate import FreeEnergyTradeDecision, FreeEnergyTradingGate, GateStatistics
from .gravitational_coupling import GravitationalCouplingMatrix
from .gravity import (
    compute_market_gravity,
    gravitational_force,
    gravitational_potential,
    market_gravity_center,
)
from .higher_order_kuramoto import HigherOrderKuramotoEngine, HigherOrderKuramotoResult
from .landauer import (
    K_BOLTZMANN,
    LANDAUER_ENERGY,
    ROOM_TEMPERATURE,
    LandauerInferenceProfiler,
)
from .liquidity_coupling import CouplingBenchmarkResult, LiquidityCouplingMatrix
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
from .newtonian_dynamics import FreeEnergyGate, NewtonianPriceDynamics
from .portfolio_conservation import PortfolioEnergyConservation
from .relativity import (
    compute_relative_time,
    lorentz_factor,
    lorentz_transform,
    relativistic_momentum,
    time_dilation_factor,
    velocity_addition,
)
from .stochastic_thermodynamics import (
    delta_free_energy,
    harmonic_free_energy,
    jarzynski_average,
    langevin_ensemble_step,
    stationary_samples,
    stiffness_ramp_work,
)
from .thermodynamic_risk import ThermodynamicRiskGate
from .thermodynamics import (
    boltzmann_entropy,
    compute_free_energy,
    compute_market_temperature,
    gibbs_free_energy,
    is_thermodynamic_equilibrium,
    thermal_equilibrium_distance,
)
from .tsallis_gate import TsallisGateResult, TsallisRegime, TsallisRiskGate
from .uncertainty import (
    GABOR_LIMIT,
    check_gabor_limit,
    gabor_lower_bound,
    time_frequency_spread,
)
from .wave_propagation import GraphDiffusionEngine

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
    # Volatility / flow proxies (canonical names — NOT conservation laws)
    "compute_volatility_energy_proxy",
    "compute_flow_momentum_proxy",
    "check_proxy_drift",
    # Deprecated aliases — kept for backward compatibility, do not use in new code
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
    # Gabor time-frequency uncertainty limit
    "GABOR_LIMIT",
    "gabor_lower_bound",
    "time_frequency_spread",
    "check_gabor_limit",
    # Physics Engine v2 — T1-T7
    "GravitationalCouplingMatrix",
    "NewtonianPriceDynamics",
    "FreeEnergyGate",
    "PortfolioEnergyConservation",
    "ThermodynamicRiskGate",
    "CoulombInteraction",
    "GraphDiffusionEngine",
    "LandauerInferenceProfiler",
    "K_BOLTZMANN",
    "ROOM_TEMPERATURE",
    "LANDAUER_ENERGY",
    "GeoSyncPhysicsEngine",
    "PhysicsEngineResult",
    # Research modules — T1-T7 v2
    "FormanRicciCurvature",
    "FormanRicciResult",
    "DualTrackRicciMonitor",
    "LiquidityCouplingMatrix",
    "CouplingBenchmarkResult",
    "ExplosiveSyncDetector",
    "ESProximityResult",
    "ESCircuitBreaker",
    "TsallisRiskGate",
    "TsallisGateResult",
    "TsallisRegime",
    "FreeEnergyTradingGate",
    "FreeEnergyTradeDecision",
    "GateStatistics",
    "HigherOrderKuramotoEngine",
    "HigherOrderKuramotoResult",
    "DiffusionVolatilityPredictor",
    "VolatilityFrontPrediction",
    "DiffusionBacktestResult",
    # Stochastic thermodynamics — Jarzynski / equipartition / second law (T8)
    "harmonic_free_energy",
    "delta_free_energy",
    "langevin_ensemble_step",
    "stiffness_ramp_work",
    "stationary_samples",
    "jarzynski_average",
]
