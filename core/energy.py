# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Operational-cost energy for TACL system-topology optimization.

This module provides the energy functions used by the TACL (Thermodynamic
Autonomic Control Layer) to model and optimize *system topology*. It treats the
distributed system as a physical analogue where services are nodes connected by
"bonds" with different characteristics.

ONTOLOGY CONTRACT (two distinct energies — do not conflate)
-----------------------------------------------------------
1. ``operational_cost_energy`` (this module's optimization objective):
   a *cost functional* over a service-bond topology. It is the quantity TACL
   minimizes via :func:`~runtime.thermo_controller.gradient_descent_step`.
   Here entropy/disorder is a **penalty that RAISES the objective** — the more
   disordered the topology, the higher the cost. This is the correct sign for a
   minimization target and is NOT the thermodynamic Helmholtz/Gibbs free energy.

2. ``thermo_free_energy`` (canonical physics, INV-FE2): F = U − T·S, where
   raising entropy S *LOWERS* F. This matches
   :pyattr:`core.validation.physics_validator.ThermodynamicState.gibbs_energy`
   and the CLAUDE.md canon. F itself may be either sign.

The historical name ``system_free_energy`` conflated these two opposite-sign
conventions (a free energy whose entropy term ADDED). It is retained as a
backward-compatible alias of :func:`operational_cost_energy`; new code should
call the intent-revealing name.

UNIT CONTRACT
-------------
Outputs are **dimensionless** operational-cost units (``ENERGY_UNITS``).
``K_BOLTZMANN_EFFECTIVE`` and ``SYSTEM_TEMPERATURE_K`` are a *fixed normalization
convention borrowed from physics* to keep the entropy term's magnitude bounded;
they do NOT make the output an energy measured in joules. No Joule claim is made
or implied by this module.

Example:
    >>> from core.energy import operational_cost_energy
    >>> cost = operational_cost_energy(bonds, latencies, coherency, 0.0, 0.0)
    >>> print(f"Operational cost: {cost:.3e} (dimensionless)")
"""

from __future__ import annotations

import math
from typing import Dict, Final, Literal, Tuple, TypedDict

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

# Fixed normalization convention (NOT a joule claim — see UNIT CONTRACT in the
# module docstring). These constants only bound the magnitude of the entropy
# penalty in the dimensionless operational-cost objective.
K_BOLTZMANN_EFFECTIVE: Final[float] = 1.38e-23
SYSTEM_TEMPERATURE_K: Final[float] = 300.0

# Pre-compute the kT product since it's used in every cost calculation
_KT_PRODUCT: Final[float] = K_BOLTZMANN_EFFECTIVE * SYSTEM_TEMPERATURE_K

# Output is dimensionless operational cost, scaled for numerical-derivative
# stability when control loops run at sub-millisecond cadence.
ENERGY_SCALE: Final[float] = 1e-18

# Explicit unit declaration so downstream code/tests can assert the boundary.
ENERGY_UNITS: Final[str] = "dimensionless"


def bond_internal_energy(
    src: str,
    dst: str,
    kind: BondType,
    latencies: Dict[Tuple[str, str], float],
    coherency: Dict[Tuple[str, str], float],
) -> float:
    """Compute internal energy for a single bond.

    Optimized with direct attribute access and reduced function calls.
    """
    params = BOND_LIBRARY[kind]

    latency = latencies.get((src, dst), 1.0)
    coherence = coherency.get((src, dst), 0.0)

    # Inline bounds checking to avoid function call overhead
    if latency < 0.0:
        latency = 0.0
    if coherence < 0.0:
        coherence = 0.0
    elif coherence > 1.0:
        coherence = 1.0

    # Use math.log1p for better numerical stability with small latencies
    latency_cost = params["latency_weight"] * math.log1p(latency)
    incoherence = 1.0 - coherence
    incoherence_cost = params["coherency_weight"] * (incoherence * incoherence)
    stability_gain = params["stability_bonus"] * coherence

    return params["base_energy"] + latency_cost + incoherence_cost - stability_gain


def operational_cost_energy(
    bonds: Dict[Tuple[str, str], BondType],
    latencies: Dict[Tuple[str, str], float],
    coherency: Dict[Tuple[str, str], float],
    resource_usage: float,
    entropy: float,
) -> float:
    """Dimensionless operational-cost objective minimized by TACL.

    This is a *cost functional* over a service-bond topology, NOT the
    thermodynamic free energy. By construction entropy is a disorder **penalty**:
    ``∂/∂entropy ≥ 0`` (more disorder ⇒ higher cost). For the canonical
    physics free energy F = U − T·S, use :func:`thermo_free_energy`.

    Returns a dimensionless value (``ENERGY_UNITS``); see the module UNIT
    CONTRACT — no joule claim is made.
    """
    internal_energy = 0.0
    for (src, dst), kind in bonds.items():
        internal_energy += bond_internal_energy(src, dst, kind, latencies, coherency)

    # Inline clip operation to avoid numpy overhead for single values
    if resource_usage < 0.0:
        resource_clipped = 0.0
    elif resource_usage > 1.0:
        resource_clipped = 1.0
    else:
        resource_clipped = resource_usage

    resource_term = 2.0 * resource_clipped
    # Disorder penalty: raises the cost objective (correct sign for a
    # minimization target — opposite to the −T·S term of thermo_free_energy).
    entropy_term = _KT_PRODUCT * (entropy if entropy > 0.0 else 0.0)

    cost = internal_energy + resource_term + entropy_term
    return ENERGY_SCALE * cost


# Backward-compatible alias. ``system_free_energy`` historically named the
# operational-cost objective "free energy", which collided with the canonical
# F = U − T·S sign convention. New code should call ``operational_cost_energy``.
system_free_energy = operational_cost_energy


def thermo_free_energy(internal_energy: float, temperature: float, entropy: float) -> float:
    """Canonical thermodynamic free energy F = U − T·S (INV-FE2).

    Mirrors :pyattr:`core.validation.physics_validator.ThermodynamicState.gibbs_energy`.
    Unlike :func:`operational_cost_energy`, raising entropy *lowers* F here:
    ``∂F/∂entropy = −temperature ≤ 0``. F may be either sign; only the
    components (U, T, S) carry non-negativity guarantees (INV-FE2).
    """
    return internal_energy - temperature * entropy


def delta_free_energy(F_prev: float, F_now: float, dt_seconds: float) -> float:
    """Compute free energy derivative with respect to time."""
    if dt_seconds <= 0.0:
        return 0.0
    return (F_now - F_prev) / dt_seconds


__all__ = [
    "BondType",
    "BondParams",
    "BOND_LIBRARY",
    "K_BOLTZMANN_EFFECTIVE",
    "SYSTEM_TEMPERATURE_K",
    "ENERGY_SCALE",
    "ENERGY_UNITS",
    "bond_internal_energy",
    "operational_cost_energy",
    "system_free_energy",
    "thermo_free_energy",
    "delta_free_energy",
]
