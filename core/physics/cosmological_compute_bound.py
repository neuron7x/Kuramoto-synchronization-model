# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Cosmological compute bound on a causal diamond (P4).

INV-COSMOLOGICAL-COMPUTE (P1, statistical, EXTRAPOLATED):
    I ≤ A / (4 · ℓ_p² · ln 2) bits per Bekenstein-Hawking 1973.
    Caller-side discounting is the caller's responsibility; this
    module ships only the holographic ceiling. The previous
    `efficiency` parameter was dropped in chore/inflaw-5 because
    for ε ≤ 1 the inequality reduced to a tautology (any number of
    useful bits ≤ holographic ceiling is trivially satisfied by the
    Bekenstein-Hawking bound itself, and ε had no operational
    definition or first-principles derivation in this module).

    where A is the horizon area and ℓ_p is the Planck length. The
    Bekenstein-Hawking formula gives I_max = A / (4 · ℓ_p²) nats =
    A / (4 · ℓ_p² · ln 2) bits.

Provenance: EXTRAPOLATED.
    - Bekenstein 1973 (PRD 7, 2333): black-hole entropy ∝ horizon area.
    - 't Hooft 1993 (gr-qc/9310026): dimensional reduction.
    - Susskind 1995 (J. Math. Phys. 36, 6377): holographic principle.
    - Susskind 2014 (Fortschr. Phys. 64, 24, arXiv:1402.5674):
      computational complexity and black-hole horizons.

The holographic-bound side is settled physics. The interpretation as
a hard ceiling on cosmological computation is a research direction;
truth-coherence ~0.5.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from core.physics.thermodynamic_budget import LANDAUER_LN2

__all__ = [
    "BH_BIT_COEFF",
    "CausalDiamond",
    "ComputeBudgetWitness",
    "ComputeBudget",
    "PLANCK_LENGTH_M",
    "PROVENANCE_TIER",
    "assess_compute_claim",
    "diamond_compute_budget",
    "holographic_bit_capacity",
]

# Discrete provenance tier; see arrow_of_time.py for definition.
PROVENANCE_TIER: Literal["ANCHORED", "EXTRAPOLATED", "SPECULATIVE"] = "EXTRAPOLATED"

# CODATA 2018 Planck length (square root of ℏ·G/c³).
PLANCK_LENGTH_M: float = 1.616_255e-35
# Bekenstein-Hawking bit coefficient: I_max = A · BH_BIT_COEFF [bits, A in m²].
# = 1 / (4 · ℓ_p² · ln 2)
BH_BIT_COEFF: float = 1.0 / (4.0 * (PLANCK_LENGTH_M**2) * LANDAUER_LN2)


@dataclass(frozen=True, slots=True)
class CausalDiamond:
    """A causal diamond defined by its horizon area or a derived radius.

    horizon_area_m2 must be finite and non-negative. The diamond's
    interior bulk volume is not needed for the holographic bound.
    """

    horizon_area_m2: float


@dataclass(frozen=True, slots=True)
class ComputeBudget:
    """Holographic compute budget of a causal diamond.

    `holographic_max_bits` is the Bekenstein-Hawking ceiling for the
    diamond's horizon area. No `efficiency`/`useful_max_bits` split is
    exposed — caller-side discounting belongs in the caller.
    """

    diamond: CausalDiamond
    holographic_max_bits: float


@dataclass(frozen=True, slots=True)
class ComputeBudgetWitness:
    """Diagnostic for INV-COSMOLOGICAL-COMPUTE on a single claim."""

    budget: ComputeBudget
    claimed_bits: float
    margin_bits: float
    is_within_budget: bool
    reason: str | None


def _check_finite(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(
            f"INV-HPC2 VIOLATED: {name} must be finite, got {value!r}. "
            "Finite inputs → finite outputs is a P0 contract; no silent repair."
        )


def _check_non_negative(value: float, name: str) -> None:
    if value < 0.0:
        raise ValueError(f"{name} must be non-negative, got {value}")


def holographic_bit_capacity(area_m2: float) -> float:
    """Bekenstein-Hawking bit count for a horizon of area `area_m2`.

    I_max = A / (4 · ℓ_p² · ln 2) bits. Returns 0.0 for area = 0.
    Fail-closed on negative or non-finite inputs.
    """
    _check_finite(area_m2, "area_m2")
    _check_non_negative(area_m2, "area_m2")
    bits: float = BH_BIT_COEFF * area_m2
    _check_finite(bits, "holographic_bit_capacity")
    return bits


def diamond_compute_budget(diamond: CausalDiamond) -> ComputeBudget:
    """Compute the holographic budget for a causal diamond.

    Returns the Bekenstein-Hawking ceiling A / (4 · ℓ_p² · ln 2) for
    the diamond's horizon area. Caller-side discounting (de Sitter
    complexity efficiency) is intentionally not exposed here — see
    module docstring.
    """
    holographic = holographic_bit_capacity(diamond.horizon_area_m2)
    return ComputeBudget(
        diamond=diamond,
        holographic_max_bits=holographic,
    )


def assess_compute_claim(
    diamond: CausalDiamond,
    claimed_bits: float,
) -> ComputeBudgetWitness:
    """Witness for INV-COSMOLOGICAL-COMPUTE on one claim.

    Returns a non-raising witness; caller fail-closes on
    `is_within_budget is False`.
    """
    _check_finite(claimed_bits, "claimed_bits")
    _check_non_negative(claimed_bits, "claimed_bits")
    budget = diamond_compute_budget(diamond)
    margin = budget.holographic_max_bits - claimed_bits
    within = claimed_bits <= budget.holographic_max_bits
    reason: str | None
    if within:
        reason = None
    else:
        reason = (
            "INV-COSMOLOGICAL-COMPUTE: claim exceeds budget; "
            f"claimed_bits={claimed_bits} > "
            f"holographic_max_bits={budget.holographic_max_bits}"
        )
    return ComputeBudgetWitness(
        budget=budget,
        claimed_bits=claimed_bits,
        margin_bits=margin,
        is_within_budget=within,
        reason=reason,
    )
