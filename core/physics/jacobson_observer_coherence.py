# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Jacobson + observer-coherence Clausius witness (P6).

INV-JACOBSON-OBSERVER (P1, conditional, EXTRAPOLATED):
    Jacobson 1995 derived the Einstein field equations from the local
    Clausius relation δQ = T·dS imposed on causal Rindler horizons of
    every uniformly accelerated observer. Equivalently, Einstein
    gravity is the equation of state of spacetime thermodynamics.

    This module operationalizes the contract that any observer-coherence
    correction `c` to the Clausius bookkeeping must satisfy:

        residual = δQ - T·dS - c

    Standard Jacobson recovery: residual ≈ 0 iff c → 0 in the
    decoupled limit (the observer does not shape the local horizon).
    Any non-zero c at observable scale is a falsifiable extension —
    not a redefinition of GR.

Provenance: EXTRAPOLATED.
    - Jacobson, T. (1995). Thermodynamics of spacetime: the Einstein
      equation of state. Phys. Rev. Lett. 75, 1260. arXiv:gr-qc/9504004.
    - Verlinde, E. (2011). On the origin of gravity and the laws of
      Newton. JHEP 04, 029.
    - Padmanabhan, T. (2010). Thermodynamical aspects of gravity:
      new insights. Rep. Prog. Phys. 73, 046901. arXiv:0911.5004.

Jacobson 1995 is settled physics. The observer-coherence correction is
a research direction; this module operationalizes the contract structure
without claiming a particular form of `c`. Truth-coherence ~0.55.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

__all__ = [
    "ClausiusContext",
    "JacobsonObserverWitness",
    "PROVENANCE_TIER",
    "assess_jacobson_observer",
    "clausius_residual",
]

# Discrete provenance tier; see arrow_of_time.py for definition.
PROVENANCE_TIER: Literal["ANCHORED", "EXTRAPOLATED", "SPECULATIVE"] = "EXTRAPOLATED"


@dataclass(frozen=True, slots=True)
class ClausiusContext:
    """A local Clausius accounting context on a causal horizon patch.

    All quantities are in SI:
    - heat_flow_J: δQ flowing across the patch (positive = inflow).
    - unruh_temperature_K: T as seen by the local accelerated observer.
    - entropy_change_J_per_K: dS of the horizon (k_B · ΔA / 4·ℓ_p² in
      natural units; here we accept it as input so the module remains
      a witness, not a derivation engine).
    - observer_coherence_correction_J: `c` — the proposed extension.
      Defaults to 0 (pure Jacobson). Caller supplies any non-zero
      value and must publish a justification.
    """

    heat_flow_J: float
    unruh_temperature_K: float
    entropy_change_J_per_K: float
    observer_coherence_correction_J: float = 0.0


@dataclass(frozen=True, slots=True)
class JacobsonObserverWitness:
    """Diagnostic for INV-JACOBSON-OBSERVER on a single context."""

    context: ClausiusContext
    pure_jacobson_residual_J: float
    observer_extended_residual_J: float
    is_pure_jacobson_consistent: bool
    is_extended_consistent: bool
    reason: str | None


def _check_finite(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(
            f"INV-HPC2 VIOLATED: {name} must be finite, got {value!r}. "
            "Finite inputs → finite outputs is a P0 contract; no silent repair."
        )


def clausius_residual(context: ClausiusContext) -> float:
    """Compute the extended Clausius residual: δQ - T·dS - c.

    For the pure Jacobson 1995 derivation, c = 0 and the residual must
    vanish on a thermal horizon. With observer-coherence c ≠ 0, the
    residual becomes a witness of the extension's compatibility with
    Einstein gravity at observable scale.
    """
    _check_finite(context.heat_flow_J, "heat_flow_J")
    _check_finite(context.unruh_temperature_K, "unruh_temperature_K")
    _check_finite(context.entropy_change_J_per_K, "entropy_change_J_per_K")
    _check_finite(
        context.observer_coherence_correction_J,
        "observer_coherence_correction_J",
    )
    if context.unruh_temperature_K < 0.0:
        raise ValueError(f"unruh_temperature_K must be >= 0, got {context.unruh_temperature_K}")
    pure = context.heat_flow_J - context.unruh_temperature_K * context.entropy_change_J_per_K
    return pure - context.observer_coherence_correction_J


def assess_jacobson_observer(
    context: ClausiusContext,
    *,
    tolerance_J: float = 1e-30,
) -> JacobsonObserverWitness:
    """Witness for INV-JACOBSON-OBSERVER on one Clausius context.

    Reports both the pure-Jacobson residual (c-free) and the extended
    residual (c included). Either residual within `tolerance_J` is
    consistent with the corresponding contract. Tolerance defaults to
    1e-30 J — well below any laboratory-accessible heat flow but
    above float64 noise.
    """
    _check_finite(tolerance_J, "tolerance_J")
    if tolerance_J < 0.0:
        raise ValueError(f"tolerance_J must be non-negative, got {tolerance_J}")
    pure = context.heat_flow_J - context.unruh_temperature_K * context.entropy_change_J_per_K
    extended = pure - context.observer_coherence_correction_J
    pure_consistent = abs(pure) <= tolerance_J
    extended_consistent = abs(extended) <= tolerance_J
    reason: str | None
    if pure_consistent and extended_consistent:
        reason = None
    elif pure_consistent and not extended_consistent:
        reason = (
            "INV-JACOBSON-OBSERVER: pure Clausius δQ = T·dS holds, but the "
            f"observer-coherence correction c={context.observer_coherence_correction_J} J "
            f"introduces a residual {extended} J above tolerance {tolerance_J} J — "
            "the extension does not vanish in the decoupled limit and is "
            "inconsistent with Einstein gravity at observable scale."
        )
    else:
        reason = (
            "INV-JACOBSON-OBSERVER: pure Clausius residual is non-zero "
            f"(pure_residual={pure} J above tolerance {tolerance_J} J); "
            "the input context does not represent a thermal Rindler horizon "
            "to within the supplied tolerance."
        )
    return JacobsonObserverWitness(
        context=context,
        pure_jacobson_residual_J=pure,
        observer_extended_residual_J=extended,
        is_pure_jacobson_consistent=pure_consistent,
        is_extended_consistent=extended_consistent,
        reason=reason,
    )
