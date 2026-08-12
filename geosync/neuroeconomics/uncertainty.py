# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Uncertainty classification and adaptive learning rate.

Constructs (Rushworth 2008, Yu & Dayan 2005, Behrens 2007):
  C05-C10: risk, ambiguity, expected/unexpected uncertainty,
  volatility, adaptive learning rate.

Performance: Welford's online algorithm — O(1) per tick, not O(n).
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass


class UncertaintyType(enum.Enum):
    RISK = "RISK"
    AMBIGUITY = "AMBIGUITY"
    EXPECTED = "EXPECTED"
    UNEXPECTED = "UNEXPECTED"


@dataclass(frozen=True)
class UncertaintyState:
    sigma_risk: float
    sigma_ambiguity: float
    sigma_eu: float
    surprise: float
    omega: float
    alpha: float
    uncertainty_type: UncertaintyType

    @property
    def epistemic(self) -> float:
        """Compat: sigma_ambiguity as epistemic uncertainty proxy."""
        return min(1.0, self.sigma_ambiguity * 5.0)

    @property
    def ambiguity_index(self) -> float:
        """Compat: log-space ratio to avoid singularity near sigma_eu -> 0."""
        return math.exp(
            math.log1p(max(0.0, self.sigma_ambiguity)) - math.log1p(max(0.0, self.sigma_eu))
        )


class _WelfordAccumulator:
    """Welford's online algorithm for streaming mean/variance in O(1)."""

    __slots__ = ("_n", "_mean", "_m2", "_maxn")

    def __init__(self, maxn: int = 50) -> None:
        self._n: int = 0
        self._mean: float = 0.0
        self._m2: float = 0.0
        self._maxn = maxn

    def push(self, x: float) -> None:
        # Bounded: decay oldest contribution when window full
        if self._n >= self._maxn:
            # Exponential decay approximation for bounded window
            decay = 1.0 - 1.0 / self._maxn
            self._mean *= decay
            self._m2 *= decay
            # Don't increment n past maxn
        else:
            self._n += 1
        delta = x - self._mean
        self._mean += delta / max(self._n, 1)
        delta2 = x - self._mean
        self._m2 += delta * delta2

    @property
    def variance(self) -> float:
        if self._n < 2:
            return 0.0
        return max(0.0, self._m2 / (self._n - 1))

    @property
    def std(self) -> float:
        return math.sqrt(self.variance)

    @property
    def mean(self) -> float:
        return self._mean

    @property
    def count(self) -> int:
        return self._n


class UncertaintyController:
    """Classifies uncertainty and adapts learning rate to volatility.

    O(1) per tick via Welford accumulators (not O(n) deque loops).
    """

    def __init__(
        self,
        *,
        alpha_min: float = 0.01,
        alpha_max: float = 0.5,
        tau_omega: float = 0.1,
        window: int = 50,
    ) -> None:
        self.alpha_min = alpha_min
        self.alpha_max = alpha_max
        self.tau_omega = tau_omega
        self._delta_acc = _WelfordAccumulator(window)
        self._outcome_acc = _WelfordAccumulator(window)
        self._abs_delta_acc = _WelfordAccumulator(window)

    def update(self, delta_t: float | dict[str, object], outcome: float = 0.0) -> UncertaintyState:  # type: ignore[override]
        """O(1) per tick. Accepts float (flow_controller) or dict (epistemic_action)."""
        if isinstance(delta_t, dict):
            # Signal-dict API: extract delta proxy from signal
            risk = delta_t.get("risk_scalar", 0)
            delta_t = (
                float(risk)
                if isinstance(risk, (int, float)) and math.isfinite(float(risk))
                else 0.0
            )
        delta = delta_t if isinstance(delta_t, (int, float)) and math.isfinite(delta_t) else 0.0
        out = outcome if math.isfinite(outcome) else 0.0

        self._delta_acc.push(delta)
        self._outcome_acc.push(out)
        self._abs_delta_acc.push(abs(delta))

        # C09: Volatility = Var(recent deltas) — O(1)
        omega = self._delta_acc.variance

        # C10: Adaptive learning rate
        alpha = self.alpha_min + (self.alpha_max - self.alpha_min) * _sigmoid(
            omega / max(self.tau_omega, 1e-9)
        )

        # C07: Expected uncertainty = std of deltas — O(1)
        sigma_eu = self._delta_acc.std if self._delta_acc.count >= 3 else 1.0

        # C08: Surprise = |delta| / sigma_eu
        surprise = abs(delta) / max(sigma_eu, 1e-9)

        # C05: Risk = std of outcomes — O(1)
        sigma_risk = self._outcome_acc.std if self._outcome_acc.count >= 3 else 0.0

        # C06: Ambiguity = variance of |deltas| — O(1)
        sigma_ambiguity = self._abs_delta_acc.variance if self._abs_delta_acc.count >= 5 else 0.0

        # Classification
        if surprise > 2.0:
            utype = UncertaintyType.UNEXPECTED
        elif sigma_ambiguity > sigma_risk and sigma_ambiguity > 0.01:
            utype = UncertaintyType.AMBIGUITY
        elif sigma_risk > sigma_eu:
            utype = UncertaintyType.RISK
        else:
            utype = UncertaintyType.EXPECTED

        return UncertaintyState(
            sigma_risk=sigma_risk,
            sigma_ambiguity=sigma_ambiguity,
            sigma_eu=sigma_eu,
            surprise=surprise,
            omega=omega,
            alpha=alpha,
            uncertainty_type=utype,
        )

    def kelly_discount(self, estimate: UncertaintyState) -> float:
        """Compat: discount factor for Kelly fraction [0.1, 1.0]."""
        total = max(estimate.epistemic, estimate.sigma_risk)
        return max(0.1, 1.0 - 0.9 * min(1.0, total))

    def is_ambiguity_zone(self, estimate: UncertaintyState) -> bool:
        """Compat: True if 2nd-order uncertainty dominates."""
        return estimate.ambiguity_index > 1.0


def _sigmoid(x: float) -> float:
    if x > 20:
        return 1.0
    if x < -20:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


# Aliases for bridge layer compat
UncertaintyEstimator = UncertaintyController
UncertaintyEstimate = UncertaintyState
