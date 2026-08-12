# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""V(O) — integral value function for the semantic sieve.

Formal form (operationalised, discrete time):

    V(O) = G_v(O) · Σ_t (α·I + β·F + γ·S + δ·X + ε·A + ζ·R + η·P
                         − λ·N − μ·H − ν·C) · Δt

* ``G_v(O)`` is a fail-closed gate. Any of the conditions below
  collapses the score to zero:
    - no falsification contract attached;
    - no executable verification recorded;
    - the artifact never reached the VERIFICATION stage.
* The integral is approximated by a sum over recorded ``StageRecord``
  samples (one per stage transition); ``Δt`` defaults to 1 so the
  cycle behaves as a discrete state machine.
* Each component is bounded in [0, 1]. Negative-weighted terms (N, H,
  C) are subtracted before the gate is applied.

The function is **deterministic**: same components → same score, no
floating-point jitter beyond IEEE-754 double precision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True)
class ValueWeights:
    """Coefficients for the V(O) sum.

    Default weights match the user contract:
    * positive components (I, F, S, X, A, R, P) sum to 0.7;
    * penalty components (N, H, C) sum to 0.3.
    Customising the weights is allowed but they MUST stay non-negative
    and the positive sum MUST exceed the penalty sum, otherwise the
    function would not reward signal over noise.
    """

    alpha: float = 0.16  # I — invariance
    beta: float = 0.14  # F — falsifiability
    gamma: float = 0.12  # S — stability
    delta: float = 0.08  # X — cross-domain transfer
    epsilon: float = 0.10  # A — operational actionability
    zeta: float = 0.06  # R — reproducibility
    eta: float = 0.04  # P — productivity
    lam: float = 0.12  # N — noise penalty
    mu: float = 0.10  # H — hallucination dependency penalty
    nu: float = 0.08  # C — cognitive cost penalty

    def __post_init__(self) -> None:
        for name, value in self._items():
            if value < 0:
                raise ValueError(f"weight {name} must be non-negative; got {value}")
        positive = sum(v for n, v in self._items() if n not in {"lam", "mu", "nu"})
        penalty = self.lam + self.mu + self.nu
        if positive <= penalty:
            raise ValueError(
                "positive weights must exceed penalty weights; "
                f"positive={positive:.4f} penalty={penalty:.4f}"
            )

    def _items(self) -> tuple[tuple[str, float], ...]:
        return (
            ("alpha", self.alpha),
            ("beta", self.beta),
            ("gamma", self.gamma),
            ("delta", self.delta),
            ("epsilon", self.epsilon),
            ("zeta", self.zeta),
            ("eta", self.eta),
            ("lam", self.lam),
            ("mu", self.mu),
            ("nu", self.nu),
        )


DEFAULT_WEIGHTS: Final[ValueWeights] = ValueWeights()


class ValueComponents(BaseModel):
    """One sample of the V(O) integrand.

    All fields are clamped at the schema layer to [0, 1]; the cycle
    orchestrator emits one of these per stage transition.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    invariance: float = Field(ge=0.0, le=1.0)
    falsifiability: float = Field(ge=0.0, le=1.0)
    stability: float = Field(ge=0.0, le=1.0)
    cross_domain: float = Field(ge=0.0, le=1.0)
    actionability: float = Field(ge=0.0, le=1.0)
    reproducibility: float = Field(ge=0.0, le=1.0)
    productivity: float = Field(ge=0.0, le=1.0)
    noise: float = Field(ge=0.0, le=1.0)
    hallucination: float = Field(ge=0.0, le=1.0)
    cognitive_cost: float = Field(ge=0.0, le=1.0)

    def integrand(self, weights: ValueWeights = DEFAULT_WEIGHTS) -> float:
        positive = (
            weights.alpha * self.invariance
            + weights.beta * self.falsifiability
            + weights.gamma * self.stability
            + weights.delta * self.cross_domain
            + weights.epsilon * self.actionability
            + weights.zeta * self.reproducibility
            + weights.eta * self.productivity
        )
        penalty = (
            weights.lam * self.noise
            + weights.mu * self.hallucination
            + weights.nu * self.cognitive_cost
        )
        return positive - penalty


@dataclass(frozen=True)
class GvCondition:
    """Fail-closed clauses for the verification gate G_v(O)."""

    has_falsification_contract: bool
    has_verification_evidence: bool
    completed_audit: bool

    def passes(self) -> bool:
        return (
            self.has_falsification_contract
            and self.has_verification_evidence
            and self.completed_audit
        )


def integrate_value(
    samples: tuple[ValueComponents, ...],
    *,
    weights: ValueWeights = DEFAULT_WEIGHTS,
    gv: GvCondition,
    dt: float = 1.0,
) -> float:
    """Compute V(O).

    Returns 0.0 fail-closed when ``gv.passes()`` is false. Otherwise
    returns the dt-weighted sum of integrand contributions, normalised
    so the maximum reachable value equals the positive weight sum
    (i.e. an artifact with all positive components at 1.0 and zero
    penalties scores ``Σ positive_weights``, not the sample count).
    """
    if dt <= 0:
        raise ValueError("dt must be positive")
    if not gv.passes():
        return 0.0
    if not samples:
        return 0.0
    raw = sum(sample.integrand(weights) for sample in samples) * dt
    normaliser = float(len(samples)) * dt
    return raw / normaliser


__all__ = [
    "DEFAULT_WEIGHTS",
    "GvCondition",
    "ValueComponents",
    "ValueWeights",
    "integrate_value",
]
