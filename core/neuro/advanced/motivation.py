# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Motivation controller built on fractal market statistics and UCB1."""

from __future__ import annotations

import json
import logging
import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Iterable, List, Mapping, MutableMapping, Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray

from core.neuro.fractal import FractalSummary, summarise_fractal_properties

LOGGER_NAME = "core.neuro.advanced.motivation"


@dataclass
class UCBState:
    """Running statistics for an action under the UCB1 policy."""

    count: int = 0
    value: float = 0.0

    def update(self, reward: float) -> None:
        self.count += 1
        # Incremental mean update to maintain numerical stability.
        self.value += (reward - self.value) / self.count


@dataclass(slots=True)
class FractalSignalTracker:
    """Maintain a rolling window of state vectors and expose fractal metrics."""

    state_dim: int
    max_history: int = 256
    _history: Deque[np.ndarray] = field(init=False, repr=False)
    _latest_summary: FractalSummary | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.state_dim <= 0:
            raise ValueError("state_dim must be positive")
        if self.max_history < 4:
            raise ValueError("max_history must be at least four samples")
        self._history = deque(maxlen=self.max_history)

    def update(self, state: Sequence[float]) -> None:
        array = np.asarray(state, dtype=float)
        if array.ndim != 1:
            raise ValueError("state must be a 1D sequence")
        if array.size != self.state_dim:
            raise ValueError(
                f"state dimension {array.size} does not match tracker state_dim {self.state_dim}"
            )
        self._history.append(array.copy())

    def metrics(self) -> Mapping[str, float]:
        if len(self._history) < 4:
            return self._default_metrics()

        stacked = np.stack(tuple(self._history), axis=0)
        summaries: list[FractalSummary] = []
        for column in stacked.T:
            try:
                summaries.append(summarise_fractal_properties(column))
            except ValueError:
                continue

        if not summaries:
            self._latest_summary = None
            return self._default_metrics()

        hurst = float(np.mean([summary.hurst for summary in summaries]))
        dimension = float(np.mean([summary.fractal_dimension for summary in summaries]))
        volatility = float(np.mean([summary.volatility for summary in summaries]))
        scaling = float(np.mean([summary.scaling_exponent for summary in summaries]))
        stability = float(np.mean([summary.stability for summary in summaries]))
        energy = float(np.mean([summary.energy for summary in summaries]))

        self._latest_summary = FractalSummary(
            hurst=hurst,
            fractal_dimension=dimension,
            volatility=volatility,
            scaling_exponent=scaling,
            stability=stability,
            energy=energy,
        )

        return self._latest_summary.as_mapping()

    def _default_metrics(self) -> Mapping[str, float]:
        return {
            "hurst": 0.5,
            "fractal_dim": 1.5,
            "volatility": 0.0,
            "scaling_exponent": 0.5,
            "stability": 1.0,
            "energy": 0.0,
        }


class FractalMotivationController:
    """Action-selection controller that fuses intrinsic and extrinsic rewards."""

    def __init__(
        self,
        actions: Iterable[str],
        *,
        exploration_coef: float = 1.0,
        value_weights: ArrayLike | None = None,
        rng: np.random.Generator | None = None,
        logger: logging.Logger | None = None,
        audit_logger: logging.Logger | None = None,
    ) -> None:
        self._actions: List[str] = list(actions)
        if not self._actions:
            raise ValueError("actions must not be empty")

        self._exploration_coef = float(exploration_coef)
        if self._exploration_coef < 0:
            raise ValueError("exploration_coef must be non-negative")

        self._rng = rng or np.random.default_rng()
        weight_array = np.asarray(
            value_weights if value_weights is not None else np.full(3, 1.0), dtype=float
        )
        if weight_array.ndim != 1:
            raise ValueError("value_weights must be a 1D array-like object")
        self._value_weights: NDArray[np.float64] = weight_array

        self._states: MutableMapping[str, UCBState] = defaultdict(UCBState)
        self._total_count = 0
        self._tracker = FractalSignalTracker(state_dim=self._value_weights.size)

        self._logger = logger or logging.getLogger(LOGGER_NAME)
        self._audit_logger = audit_logger or logging.getLogger(f"{LOGGER_NAME}.audit")

    @property
    def total_count(self) -> int:
        """Total number of action updates processed."""

        return self._total_count

    def ucb_scores(self) -> Dict[str, float]:
        """Compute the current UCB1 score for each action."""

        scores: Dict[str, float] = {}
        if self._total_count == 0:
            for action in self._actions:
                scores[action] = float("inf")
            return scores

        log_total = math.log(self._total_count)
        for action in self._actions:
            state = self._states[action]
            if state.count == 0:
                scores[action] = float("inf")
            else:
                bonus = self._exploration_coef * math.sqrt((2.0 * log_total) / state.count)
                scores[action] = state.value + bonus
        return scores

    def update(self, action: str, reward: float) -> None:
        """Update running statistics for ``action`` with ``reward``."""

        if action not in self._actions:
            raise KeyError(f"Unknown action '{action}'")
        self._states[action].update(reward)
        self._total_count += 1

    def compute_intrinsic_reward(
        self,
        state: Sequence[float],
        signals: Mapping[str, float | bool],
        metrics: Mapping[str, float],
    ) -> float:
        """Intrinsic reward composed of reward prediction error and fractal metrics."""

        predicted = self.predict_value(state)
        next_state = self._project_next_state(np.asarray(state, dtype=float), signals, metrics)
        actual = self.predict_value(next_state)
        reward_prediction_error = float(actual - predicted)
        info_gain = float(np.linalg.norm(next_state - np.asarray(state, dtype=float)))
        energy = float(metrics.get("energy", 0.0))
        stability = float(metrics.get("stability", 1.0))
        return reward_prediction_error + 0.1 * info_gain + 0.05 * energy + 0.02 * stability

    def predict_value(self, state: Sequence[float]) -> float:
        """Predict the value of ``state`` using the linear value function."""

        state_array = np.asarray(state, dtype=float)
        if state_array.ndim != 1:
            raise ValueError("state must be a 1D sequence")
        if state_array.size != self._value_weights.size:
            raise ValueError(
                f"state dimension {state_array.size} does not match value_weights {self._value_weights.size}"
            )
        return float(self._value_weights @ state_array)

    def get_recommended_action(
        self, state: Sequence[float], signals: Mapping[str, float | bool]
    ) -> str:
        """Return the next action recommendation based on the provided signals."""

        risk_ok = bool(signals.get("risk_ok", True))
        compliance_ok = bool(signals.get("compliance_ok", True))
        timestamp = time.time()
        state_array = np.asarray(state, dtype=float)
        if state_array.size != self._value_weights.size:
            raise ValueError(
                f"state dimension {state_array.size} does not match value_weights {self._value_weights.size}"
            )
        self._tracker.update(state_array)

        if not risk_ok or not compliance_ok:
            payload = {
                "timestamp": timestamp,
                "state": state_array.tolist(),
                "signals": dict(signals),
                "recommended": "pause_and_audit",
                "reason": "guardrail_violation",
            }
            self._audit_logger.warning(json.dumps(payload))
            return "pause_and_audit"

        base_rewards: Dict[str, float] = {}
        pnl = float(signals.get("PnL", 0.0) or 0.0)
        hazard = bool(signals.get("hazard", False))
        metrics = self._tracker.metrics()

        for action in self._actions:
            penalty = -10.0 if hazard and action in {"open_long", "open_short"} else 0.0
            intrinsic = self.compute_intrinsic_reward(state_array, signals, metrics)
            directional_bias = 0.0
            if action in {"open_long", "open_short"}:
                persistence = float(metrics.get("scaling_exponent", 0.5) - 0.5)
                direction = np.sign(pnl if pnl != 0.0 else persistence)
                if direction == 0.0:
                    direction = 1.0
                if action == "open_short":
                    direction *= -1.0
                directional_bias = 0.05 * direction
            elif action == "hold":
                directional_bias = -0.02 * abs(metrics.get("energy", 0.0))
            base_rewards[action] = pnl + penalty + intrinsic + directional_bias

        # Choose an action using the current UCB statistics prior to applying
        # any updates so that only the reward for the executed action is
        # incorporated into the running statistics.
        scores = self.ucb_scores()
        recommended = max(scores, key=scores.get)

        observed_reward = base_rewards[recommended]
        self.update(recommended, observed_reward)

        payload = {
            "timestamp": timestamp,
            "state": state_array.tolist(),
            "signals": dict(signals),
            "ucb_scores": scores,
            "base_rewards": base_rewards,
            "recommended": recommended,
        }
        self._logger.info(json.dumps(payload))
        return recommended

    def _project_next_state(
        self,
        state: np.ndarray,
        signals: Mapping[str, float | bool],
        metrics: Mapping[str, float],
    ) -> np.ndarray:
        pnl = float(signals.get("PnL", 0.0) or 0.0)
        hazard = bool(signals.get("hazard", False))
        energy = float(metrics.get("energy", 0.0))
        persistence = float(metrics.get("hurst", 0.5) - 0.5)
        direction = np.sign(pnl if pnl != 0.0 else persistence)
        if direction == 0.0:
            direction = 1.0

        scale = 0.5 * energy + 0.2 * persistence
        adjustment = direction * scale
        if hazard:
            adjustment -= abs(adjustment) * 0.5

        weights = np.linspace(1.0, 0.5, state.size, dtype=float)
        delta = weights * adjustment
        return state + delta


__all__ = [
    "FractalMotivationController",
    "FractalSignalTracker",
    "UCBState",
]
