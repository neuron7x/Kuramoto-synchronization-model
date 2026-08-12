# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Context memory with regime tracking and pessimism bias.

Constructs (Kuhnen 2025, Rangel 2008):
  C14: context_effect     — regime shifts decision policy
  C15: experience_effect  — history-dependent bias from prior outcomes
  C16: pessimism_bias     — alpha_loss > alpha_gain (asymmetric learning)
  C25: regime_context     — market regime as explicit state variable
  C30: history_dependence — EWA of outcomes with decay
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContextState:
    regime: str  # current market regime
    history_score: float  # EWA of outcomes
    experience_weight: float  # sigmoid(beta * history_score)
    effective_alpha: float  # asymmetric: alpha_loss if loss, alpha_gain if gain
    policy_delta: float  # additive shift from context


class ContextMemory:
    """Regime-aware experience memory with pessimism bias.

    Parameters
    ----------
    alpha_gain
        Learning rate for positive outcomes.
    alpha_loss
        Learning rate for negative outcomes (> alpha_gain = pessimism bias).
    decay
        Exponential decay for history score.
    beta_exp
        Steepness of experience weight sigmoid.
    context_weight
        Scaling of regime context → policy_delta.
    """

    def __init__(
        self,
        *,
        alpha_gain: float = 0.05,
        alpha_loss: float = 0.15,
        decay: float = 0.95,
        beta_exp: float = 2.0,
        context_weight: float = 0.1,
    ) -> None:
        self.alpha_gain = alpha_gain
        self.alpha_loss = alpha_loss
        self.decay = decay
        self.beta_exp = beta_exp
        self.context_weight = context_weight
        self._history_score: float = 0.0
        self._last_regime: str = "UNKNOWN"

    def update(
        self,
        *,
        regime: str,
        outcome: float,
    ) -> ContextState:
        """Update context memory with new regime and outcome.

        Parameters
        ----------
        regime
            Current market regime classification.
        outcome
            Realized reward from last action.
        """
        outcome = outcome if math.isfinite(outcome) else 0.0

        # C16: Pessimism bias — losses update faster
        eff_alpha = self.alpha_loss if outcome < 0 else self.alpha_gain

        # C30: History dependence — EWA with decay
        self._history_score = self.decay * self._history_score + (1.0 - self.decay) * outcome

        # C15: Experience weight
        exp_weight = _sigmoid(self.beta_exp * self._history_score)

        # C14: Context effect — regime shift → policy delta
        regime_value = _REGIME_VALUES.get(regime, 0.0)
        policy_delta = self.context_weight * regime_value * exp_weight

        self._last_regime = regime

        return ContextState(
            regime=regime,
            history_score=self._history_score,
            experience_weight=exp_weight,
            effective_alpha=eff_alpha,
            policy_delta=policy_delta,
        )


# Regime → scalar value for policy modulation
_REGIME_VALUES: dict[str, float] = {
    "COHERENT": 0.5,
    "METASTABLE": 0.0,
    "DECOHERENT": -0.5,
    "CRITICAL": -1.0,
    "UNKNOWN": -0.3,
}


def _sigmoid(x: float) -> float:
    if x > 20:
        return 1.0
    if x < -20:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))
