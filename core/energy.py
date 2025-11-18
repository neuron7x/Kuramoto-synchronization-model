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

import math
from typing import Dict, Literal, Tuple, TypedDict

import numpy as np

BondType = Literal["covalent", "ionic", "metallic", "vdw", "hydrogen"]


class BondParams(TypedDict):
    base_energy: float
    latency_weight: float
    coherency_weight: float
    stability_bonus: float


BOND_LIBRARY: Dict[BondType, BondParams] = {
    "covalent": {
        "base_energy": 1.0,
        "latency_weight": 4.0,
        "coherency_weight": 2.0,
        "stability_bonus": 1.5,
    },
    "ionic": {
        "base_energy": 1.4,
        "latency_weight": 2.5,
        "coherency_weight": 4.0,
        "stability_bonus": 1.2,
    },
    "metallic": {
        "base_energy": 0.7,
        "latency_weight": 1.0,
        "coherency_weight": 1.5,
        "stability_bonus": 2.5,
    },
    "vdw": {
        "base_energy": 0.25,
        "latency_weight": 0.6,
        "coherency_weight": 0.8,
        "stability_bonus": 0.2,
    },
    "hydrogen": {
        "base_energy": 0.5,
        "latency_weight": 1.8,
        "coherency_weight": 3.5,
        "stability_bonus": 3.2,
    },
}

K_BOLTZMANN_EFFECTIVE = 1.38e-23
SYSTEM_TEMPERATURE_K = 300.0

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
) -> float:
    internal_energy = 0.0
    for (src, dst), kind in bonds.items():
        internal_energy += bond_internal_energy(src, dst, kind, latencies, coherency)

    resource_term = 2.0 * float(np.clip(resource_usage, 0.0, 1.0))
    entropy_term = (K_BOLTZMANN_EFFECTIVE * SYSTEM_TEMPERATURE_K) * max(entropy, 0.0)

    free_energy = internal_energy + resource_term + entropy_term
    return ENERGY_SCALE * free_energy


def delta_free_energy(F_prev: float, F_now: float, dt_seconds: float) -> float:
    if dt_seconds <= 0:
        return 0.0
    return (F_now - F_prev) / dt_seconds


__all__ = [
    "BondType",
    "BondParams",
    "BOND_LIBRARY",
    "K_BOLTZMANN_EFFECTIVE",
    "SYSTEM_TEMPERATURE_K",
    "ENERGY_SCALE",
    "bond_internal_energy",
    "system_free_energy",
    "delta_free_energy",
]
