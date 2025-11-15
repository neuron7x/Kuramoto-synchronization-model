"""Thermodynamic energy calculations for system optimization.

This module provides thermodynamic energy functions used by the TACL
(Thermodynamic Autonomic Control Layer) to model and optimize system topology.
It treats the distributed trading system as a physical system where services
are nodes connected by "bonds" with different characteristics.

Key Concepts:
- **Bonds**: Represent communication links between services with types like
  covalent (low-latency), ionic (high-coherency), metallic (high-stability)
- **Free Energy**: Combines internal energy, resource costs, and entropy
- **Thermodynamic Control**: Uses energy descent to optimize system topology

The energy model enables automatic protocol selection, adaptive recovery,
and crisis-aware reconfiguration while maintaining monotonic energy descent
constraints for safety.

Example:
    >>> from core.energy import system_free_energy
    >>> topology = {...}  # Service topology definition
    >>> energy = system_free_energy(topology)
    >>> print(f"System free energy: {energy:.6f}")
"""

from __future__ import annotations

from typing import Dict, Tuple, Literal, TypedDict
import math

import numpy as np

BondType = Literal["covalent", "ionic", "metallic", "vdw", "hydrogen"]


class BondParams(TypedDict):
    base_energy: float
    latency_weight: float
    coherency_weight: float
    stability_bonus: float


BOND_LIBRARY: Dict[BondType, BondParams] = {
    "covalent": {"base_energy": 1.0, "latency_weight": 4.0, "coherency_weight": 2.0, "stability_bonus": 1.5},
    "ionic": {"base_energy": 1.4, "latency_weight": 2.5, "coherency_weight": 4.0, "stability_bonus": 1.2},
    "metallic": {"base_energy": 0.7, "latency_weight": 1.0, "coherency_weight": 1.5, "stability_bonus": 2.5},
    "vdw": {"base_energy": 0.25, "latency_weight": 0.6, "coherency_weight": 0.8, "stability_bonus": 0.2},
    "hydrogen": {"base_energy": 0.5, "latency_weight": 1.8, "coherency_weight": 3.5, "stability_bonus": 3.2},
}

# Thermodynamic constants (dimensionless units for computational stability)
# We use effective thermodynamic units scaled to match the typical magnitude
# of bond energies (order ~1.0) to ensure all terms contribute meaningfully.
K_BOLTZMANN_EFFECTIVE = 1.0  # Effective Boltzmann constant (dimensionless)
SYSTEM_TEMPERATURE_BASE_K = 1.0  # Base temperature in effective units
TEMPERATURE_SCALE_FACTOR = 0.1  # Scaling factor for temperature adaptation

# Heat capacity - affects how quickly system temperature changes
SYSTEM_HEAT_CAPACITY = 10.0  # Higher values = more stable temperature

# We operate on dimensionless, normalised energy units.  The raw contributions
# coming from bond, resource and entropy terms are scaled down to match
# physically plausible magnitudes (≈10⁻¹⁸ J) which keeps numerical derivatives
# stable even when control loops run at sub-millisecond cadence.
ENERGY_SCALE = 1e-18


def bond_internal_energy(
    src: str,
    dst: str,
    kind: BondType,
    latencies: Dict[Tuple[str, str], float],
    coherency: Dict[Tuple[str, str], float],
) -> float:
    params = BOND_LIBRARY[kind]

    latency = float(latencies.get((src, dst), 1.0))
    coherence = float(coherency.get((src, dst), 0.0))

    latency = max(latency, 0.0)
    coherence = float(np.clip(coherence, 0.0, 1.0))

    latency_cost = params["latency_weight"] * math.log(1.0 + latency)
    incoherence_cost = params["coherency_weight"] * (1.0 - coherence) ** 2
    stability_gain = params["stability_bonus"] * coherence

    return params["base_energy"] + latency_cost + incoherence_cost - stability_gain


def system_free_energy(
    bonds: Dict[Tuple[str, str], BondType],
    latencies: Dict[Tuple[str, str], float],
    coherency: Dict[Tuple[str, str], float],
    resource_usage: float,
    entropy: float,
    temperature: float | None = None,
) -> float:
    """Calculate system free energy using Helmholtz formulation.
    
    F = U - TS + resource_costs
    
    where:
        U = internal bond energy
        T = system temperature (adaptive or base)
        S = entropy (diversity of bond types)
        resource_costs = computational overhead
        
    Args:
        bonds: Mapping of edges to bond types
        latencies: Edge latency measurements
        coherency: Edge coherency measurements
        resource_usage: Normalized resource consumption [0, 1]
        entropy: System entropy (bond type diversity)
        temperature: Optional system temperature (uses base if None)
        
    Returns:
        Free energy in scaled units (multiplied by ENERGY_SCALE)
    """
    internal_energy = 0.0
    for (src, dst), kind in bonds.items():
        internal_energy += bond_internal_energy(src, dst, kind, latencies, coherency)

    # Resource term: computational overhead scales with utilization
    # Use adaptive weighting based on resource pressure
    resource_pressure = float(np.clip(resource_usage, 0.0, 1.0))
    resource_term = 2.0 * resource_pressure + 0.5 * (resource_pressure ** 2)

    # Temperature: use provided temperature or base temperature
    T = temperature if temperature is not None else SYSTEM_TEMPERATURE_BASE_K
    
    # Entropy term: -TS (entropy reduces free energy, favoring diversity)
    # Use effective thermodynamic units so entropy contributes meaningfully
    entropy_term = -K_BOLTZMANN_EFFECTIVE * T * max(entropy, 0.0)

    # Helmholtz free energy: F = U - TS + resource_costs
    free_energy = internal_energy + resource_term + entropy_term
    return ENERGY_SCALE * free_energy


def delta_free_energy(F_prev: float, F_now: float, dt_seconds: float) -> float:
    """Calculate rate of change of free energy.
    
    Args:
        F_prev: Previous free energy
        F_now: Current free energy
        dt_seconds: Time interval in seconds
        
    Returns:
        dF/dt in energy units per second
    """
    if dt_seconds <= 0:
        return 0.0
    return (F_now - F_prev) / dt_seconds


def compute_adaptive_temperature(
    baseline_F: float,
    current_F: float,
    dF_dt: float,
    base_temp: float | None = None,
) -> float:
    """Compute adaptive system temperature based on thermodynamic stress.
    
    Temperature increases when:
    - Free energy is elevated above baseline (system under stress)
    - Free energy is rising rapidly (dF/dt > 0)
    
    This models the system "heating up" during periods of high load,
    instability, or rapid change, which affects the entropy contribution
    to free energy and influences optimization behavior.
    
    Args:
        baseline_F: Baseline (equilibrium) free energy
        current_F: Current free energy
        dF_dt: Rate of change of free energy
        base_temp: Base temperature (uses SYSTEM_TEMPERATURE_BASE_K if None)
        
    Returns:
        Adaptive temperature in effective units
    """
    if base_temp is None:
        base_temp = SYSTEM_TEMPERATURE_BASE_K
    
    # Stress component: temperature rises with free energy above baseline
    stress = max(0.0, current_F - baseline_F)
    stress_contribution = TEMPERATURE_SCALE_FACTOR * stress
    
    # Dynamics component: temperature rises when free energy is increasing
    dynamics_contribution = TEMPERATURE_SCALE_FACTOR * max(0.0, dF_dt)
    
    # Adaptive temperature: T = T_base + stress_effects
    temperature = base_temp + stress_contribution + dynamics_contribution
    
    # Clamp to reasonable bounds (0.1 to 10.0 times base)
    return float(np.clip(temperature, 0.1 * base_temp, 10.0 * base_temp))


def heat_dissipation_rate(
    current_F: float,
    baseline_F: float,
    heat_capacity: float | None = None,
) -> float:
    """Calculate rate at which excess energy dissipates.
    
    Models thermal relaxation: systems naturally cool toward equilibrium.
    Higher heat capacity = slower cooling.
    
    Args:
        current_F: Current free energy
        baseline_F: Equilibrium free energy
        heat_capacity: System heat capacity (uses default if None)
        
    Returns:
        Dissipation rate (positive = cooling toward baseline)
    """
    if heat_capacity is None:
        heat_capacity = SYSTEM_HEAT_CAPACITY
    
    # Newton's law of cooling: dQ/dt ∝ (T - T_ambient)
    # In our model: cooling rate proportional to energy above baseline
    excess_energy = current_F - baseline_F
    
    # Dissipation rate inversely proportional to heat capacity
    dissipation = excess_energy / max(heat_capacity, 1.0)
    
    return float(dissipation)


def thermal_stability_metric(
    temperature: float,
    base_temp: float | None = None,
) -> float:
    """Measure how far system temperature is from baseline.
    
    Returns a value in [0, 1] where:
    - 1.0 = at base temperature (thermally stable)
    - 0.0 = far from base (high thermal stress)
    
    Args:
        temperature: Current temperature
        base_temp: Base temperature (uses default if None)
        
    Returns:
        Stability metric in [0, 1]
    """
    if base_temp is None:
        base_temp = SYSTEM_TEMPERATURE_BASE_K
    
    # Normalized temperature deviation
    temp_ratio = temperature / max(base_temp, 1e-9)
    
    # Stability decreases as temperature deviates from base
    # Use exponential decay for smooth behavior
    stability = math.exp(-abs(temp_ratio - 1.0))
    
    return float(stability)


__all__ = [
    "BondType",
    "BondParams",
    "BOND_LIBRARY",
    "K_BOLTZMANN_EFFECTIVE",
    "SYSTEM_TEMPERATURE_BASE_K",
    "TEMPERATURE_SCALE_FACTOR",
    "SYSTEM_HEAT_CAPACITY",
    "ENERGY_SCALE",
    "bond_internal_energy",
    "system_free_energy",
    "delta_free_energy",
    "compute_adaptive_temperature",
    "heat_dissipation_rate",
    "thermal_stability_metric",
]
