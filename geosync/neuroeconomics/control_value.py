# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Value of information and control allocation.

Constructs (Rushworth 2008):
  C11: value_of_information — E[ΔH | action] (expected uncertainty reduction)
  C12: action_cost          — compute/latency/resource cost
  C13: control_allocation   — meta-decision: invest processing or use heuristic
  C29: exploration_bonus    — κ/√(N+1) for underexplored actions

Decides: is it worth deliberating, or should we fast-path?
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ControlState:
    voi: float  # value of information
    action_cost: float  # cost of deliberation
    effort_gate: float  # E ∈ [0, 1]: 0=heuristic, 1=full deliberation
    exploration_bonus: float  # κ/√(N+1) for least-visited action


class ControlValueGate:
    """Meta-decision: invest computation or fast-path.

    Parameters
    ----------
    temperature
        Softness of sigmoid effort gate.
    kappa
        Exploration bonus coefficient.
    latency_cost_per_ms
        Cost per millisecond of deliberation.
    """

    def __init__(
        self,
        *,
        temperature: float = 0.1,
        kappa: float = 0.5,
        latency_cost_per_ms: float = 0.001,
    ) -> None:
        self.temperature = max(temperature, 1e-9)
        self.kappa = kappa
        self.latency_cost_per_ms = latency_cost_per_ms
        self._visit_counts: dict[str, int] = defaultdict(int)

    def compute(
        self,
        *,
        prior_entropy: float,
        expected_posterior_entropy: float,
        latency_ms: float,
        action: str = "TRADE",
    ) -> ControlState:
        """Compute control allocation.

        Parameters
        ----------
        prior_entropy
            H(prior) before deliberation.
        expected_posterior_entropy
            E[H(posterior)] after deliberation.
        latency_ms
            Estimated deliberation time in milliseconds.
        action
            Action being considered (for visit counting).
        """
        # C11: VOI = expected uncertainty reduction
        voi = max(0.0, prior_entropy - expected_posterior_entropy)

        # C12: Action cost
        cost = latency_ms * self.latency_cost_per_ms

        # C13: Effort gate = sigmoid((VOI - C) / T)
        effort = _sigmoid((voi - cost) / self.temperature)

        # C29: Exploration bonus
        self._visit_counts[action] += 1
        n = self._visit_counts[action]
        bonus = self.kappa / math.sqrt(n + 1)

        return ControlState(
            voi=voi,
            action_cost=cost,
            effort_gate=effort,
            exploration_bonus=bonus,
        )

    def v_net(self, base_value: float, state: ControlState) -> float:
        """Net value after cost and bonus: V_net = V - C + bonus."""
        return base_value - state.action_cost + state.exploration_bonus


def _sigmoid(x: float) -> float:
    if x > 20:
        return 1.0
    if x < -20:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))
