# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Central value arbitration — three valuation systems in common currency.

Constructs (Rangel 2008, Ruff & Fehr 2014):
  C01: goal_value            — E[R | a, s] from signal model
  C02: habit_value           — Q(s,a) from RL history (TD update)
  C03: pavlovian_value       — hardwired approach/avoidance gate
  C04: prediction_error      — delta = R_t - V_t (dopaminergic TD signal)
  C23: common_value_currency — normalize heterogeneous signals to one scale
  C26: reward_representation — pre-choice encoding of potential outcomes
  C27: outcome_valuation     — post-choice utility of realized outcome
  C28: three_valuation_systems — parallel Pav/Hab/Goal with weighted arbitration

Closes the loop: delta_t → uncertainty.update() on next tick.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DecisionState:
    v_goal: float
    v_habit: float
    v_pav: float
    v_net: float  # unified normalized value ∈ [-1, 1]
    delta: float  # prediction error → feeds back to uncertainty
    lambda_weights: tuple[float, float, float]  # (pav, hab, goal)


# C28: Regime-dependent system weights
# COHERENT: trust goal-directed (high sync = reliable model)
# METASTABLE: balanced
# DECOHERENT: fall back to habit (model unreliable)
# CRITICAL: pavlovian dominates (protective reflexes)
_REGIME_LAMBDAS: dict[str, tuple[float, float, float]] = {
    "COHERENT": (0.05, 0.15, 0.80),
    "METASTABLE": (0.10, 0.30, 0.60),
    "DECOHERENT": (0.10, 0.60, 0.30),
    "CRITICAL": (0.50, 0.30, 0.20),
    "UNKNOWN": (0.20, 0.50, 0.30),
}


class DecisionCurrency:
    """Three-system value arbitration with common currency normalization.

    Parameters
    ----------
    pav_approach_threshold
        Signal strength above which Pavlovian triggers approach.
    pav_avoid_threshold
        Signal strength below which Pavlovian triggers avoidance.
    """

    def __init__(
        self,
        *,
        pav_approach_threshold: float = 0.3,
        pav_avoid_threshold: float = -0.3,
    ) -> None:
        self.pav_approach = pav_approach_threshold
        self.pav_avoid = pav_avoid_threshold
        self._v_habit: float = 0.0
        self._v_net_prev: float = 0.0

    def update(
        self,
        *,
        goal_value: float,
        signal_strength: float,
        outcome: float,
        alpha: float,
        regime: str,
        policy_delta: float = 0.0,
        drift_bias: float = 0.0,
        effort_gate: float = 1.0,
    ) -> DecisionState:
        """Compute unified decision value from all systems.

        Parameters
        ----------
        goal_value
            E[R | action, state] from signal model (risk_scalar × confidence).
        signal_strength
            Directional signal ∈ [-1, 1] for Pavlovian gate.
        outcome
            Realized reward from last execution.
        alpha
            Adaptive learning rate from uncertainty module.
        regime
            Current market regime for lambda weight selection.
        policy_delta
            Additive shift from context_memory.
        drift_bias
            Prior contribution from prior_integration.
        effort_gate
            E ∈ [0, 1] from control_value. Scales goal vs habit weight.
        """
        # C04: Prediction error (TD signal)
        outcome = outcome if math.isfinite(outcome) else 0.0
        delta = outcome - self._v_net_prev

        # C02: Habit value — TD update
        alpha = max(0.0, min(1.0, alpha if math.isfinite(alpha) else 0.01))
        self._v_habit += alpha * delta
        self._v_habit = max(-1.0, min(1.0, self._v_habit))

        # C01: Goal value — direct from signal model
        v_goal = goal_value if math.isfinite(goal_value) else 0.0

        # C03: Pavlovian — hardwired approach/avoid
        if signal_strength > self.pav_approach:
            v_pav = 0.5
        elif signal_strength < self.pav_avoid:
            v_pav = -0.5
        else:
            v_pav = 0.0

        # C28: Regime-dependent lambda weights
        base_lambdas = _REGIME_LAMBDAS.get(regime, _REGIME_LAMBDAS["UNKNOWN"])

        # Effort gate modulates goal vs habit:
        # High effort → more goal-directed. Low effort → more habitual.
        lam_pav = base_lambdas[0]
        lam_hab = base_lambdas[1] * (1.0 - 0.5 * effort_gate)
        lam_goal = base_lambdas[2] * (0.5 + 0.5 * effort_gate)

        # Renormalize
        total = lam_pav + lam_hab + lam_goal
        if total > 0:
            lam_pav /= total
            lam_hab /= total
            lam_goal /= total

        # C23: Common currency — weighted combination + context + prior
        v_raw = lam_pav * v_pav + lam_hab * self._v_habit + lam_goal * v_goal
        v_net = v_raw + policy_delta + drift_bias * 0.1

        # Normalize to [-1, 1]
        v_net = max(-1.0, min(1.0, v_net))

        self._v_net_prev = v_net

        return DecisionState(
            v_goal=v_goal,
            v_habit=self._v_habit,
            v_pav=v_pav,
            v_net=v_net,
            delta=delta,
            lambda_weights=(round(lam_pav, 3), round(lam_hab, 3), round(lam_goal, 3)),
        )
