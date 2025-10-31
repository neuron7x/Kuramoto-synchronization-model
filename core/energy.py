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

K_BOLTZMANN_EFFECTIVE = 1.38e-23
SYSTEM_TEMPERATURE_K = 300.0

# We operate on dimensionless, normalised energy units.  The raw contributions
# coming from bond, resource and entropy terms are scaled down to match
# physically plausible magnitudes (≈10⁻¹⁸ J) which keeps numerical derivatives
# stable even when control loops run at sub-millisecond cadence.
ENERGY_SCALE = 1e-18


def _bond_energy(
    src: str,
    dst: str,
    kind: BondType,
    latencies: Dict[Tuple[str, str], float],
    coherency: Dict[Tuple[str, str], float],
) -> float:
    """Compute the (dimensionless) contribution for a single directed bond.

    The inputs are defensive against partially populated latency/coherency maps
    by falling back to conservative defaults.  Values are clipped to the
    physically meaningful range to avoid runaway gradients when operators feed
    noisy telemetry into the controller.
    """

    params = BOND_LIBRARY[kind]

    latency = float(latencies.get((src, dst), 1.0))
    coherence = float(coherency.get((src, dst), 0.0))

    if not math.isfinite(latency):
        latency = 1.0
    if not math.isfinite(coherence):
        coherence = 0.0

    latency = max(latency, 0.0)
    coherence = float(np.clip(coherence, 0.0, 1.0))

    latency_cost = params["latency_weight"] * math.log1p(latency)
    incoherence_cost = params["coherency_weight"] * (1.0 - coherence) ** 2
    stability_gain = params["stability_bonus"] * coherence

    return params["base_energy"] + latency_cost + incoherence_cost - stability_gain


def _bounded_resource_usage(value: float) -> float:
    if not math.isfinite(value):
        return 1.0
    return float(np.clip(value, 0.0, 1.0))


def _bounded_entropy(value: float) -> float:
    if not math.isfinite(value) or value < 0.0:
        return 0.0
    return value


def system_free_energy(
    bonds: Dict[Tuple[str, str], BondType],
    latencies: Dict[Tuple[str, str], float],
    coherency: Dict[Tuple[str, str], float],
    resource_usage: float,
    entropy: float,
) -> float:
    """Compute the scaled Helmholtz free energy for the runtime graph."""

    internal_energy = math.fsum(
        _bond_energy(src, dst, kind, latencies, coherency)
        for (src, dst), kind in bonds.items()
    )

    resource_term = 2.0 * _bounded_resource_usage(resource_usage)
    entropy_term = (K_BOLTZMANN_EFFECTIVE * SYSTEM_TEMPERATURE_K) * _bounded_entropy(entropy)

    free_energy = internal_energy + resource_term + entropy_term
    return ENERGY_SCALE * free_energy


def delta_free_energy(F_prev: float, F_now: float, dt_seconds: float) -> float:
    """Return the time derivative of the free energy, guarding against dt→0."""

    if dt_seconds <= 0 or not math.isfinite(dt_seconds):
        return 0.0
    return (F_now - F_prev) / dt_seconds


__all__ = [
    "BondType",
    "BondParams",
    "BOND_LIBRARY",
    "K_BOLTZMANN_EFFECTIVE",
    "SYSTEM_TEMPERATURE_K",
    "ENERGY_SCALE",
    "system_free_energy",
    "delta_free_energy",
]
