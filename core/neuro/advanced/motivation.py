"""Fractal motivation controller inspired by neurobiological principles.

This module implements a motivation controller that combines intrinsic
reinforcement-learning signals (reward prediction error, information gain,
and pink ``1/f`` noise) with an Upper Confidence Bound (UCB1) action
selection policy.  The design mirrors dopamine-driven exploration dynamics
observed in the brain while remaining grounded in empirically validated
mathematical models.
"""

from __future__ import annotations

import json
import logging
import math
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, MutableMapping, Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray

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


class VossNoiseGenerator:
    """Pink-noise (``1/f``) generator using the Voss–McCartney algorithm.

    The generator maintains ``dimensions`` independent white-noise sources and
    replaces sources when the binary representation of the sample counter flips
    from ``1`` to ``0``.  The sum of the sources approximates pink noise with a
    Hurst exponent in the ``0.7–0.8`` range that has been reported in EEG
    studies.
    """

    def __init__(self, dimensions: int = 8, *, rng: np.random.Generator | None = None) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be a positive integer")
        self._dimensions = dimensions
        self._rng = rng or np.random.default_rng()
        self._sources = self._rng.normal(size=dimensions)
        self._counter = 0

    def sample(self) -> float:
        """Return the next pink-noise sample."""

        if self._counter == 0:
            self._sources[0] = self._rng.normal()
        else:
            idx = 0
            counter = self._counter
            while counter % 2 == 0:
                idx += 1
                counter //= 2
            if idx < self._dimensions:
                self._sources[idx] = self._rng.normal()

        value = float(self._sources.sum() / math.sqrt(self._dimensions))
        self._counter = (self._counter + 1) % (1 << self._dimensions)
        return value


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
        weight_array = np.asarray(value_weights if value_weights is not None else self._rng.normal(size=3), dtype=float)
        if weight_array.ndim != 1:
            raise ValueError("value_weights must be a 1D array-like object")
        self._value_weights: NDArray[np.float64] = weight_array

        self._states: MutableMapping[str, UCBState] = defaultdict(UCBState)
        self._total_count = 0
        self._pink_noise = VossNoiseGenerator(rng=self._rng)

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

    def compute_intrinsic_reward(self, state: Sequence[float], next_state: Sequence[float]) -> float:
        """Intrinsic reward composed of RPE, information gain, and pink noise."""

        predicted = self.predict_value(state)
        actual = self.predict_value(next_state)
        reward_prediction_error = float(actual - predicted)
        info_gain = float(np.linalg.norm(np.asarray(next_state, dtype=float) - np.asarray(state, dtype=float)))
        pink_noise = 0.01 * self._pink_noise.sample()
        return reward_prediction_error + 0.1 * info_gain + pink_noise

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

    def get_recommended_action(self, state: Sequence[float], signals: Mapping[str, float | bool]) -> str:
        """Return the next action recommendation based on the provided signals."""

        risk_ok = bool(signals.get("risk_ok", True))
        compliance_ok = bool(signals.get("compliance_ok", True))
        timestamp = time.time()

        if not risk_ok or not compliance_ok:
            payload = {
                "timestamp": timestamp,
                "state": list(state),
                "signals": dict(signals),
                "recommended": "pause_and_audit",
                "reason": "guardrail_violation",
            }
            self._audit_logger.warning(json.dumps(payload))
            return "pause_and_audit"

        base_rewards: Dict[str, float] = {}
        pnl = float(signals.get("PnL", 0.0) or 0.0)
        hazard = bool(signals.get("hazard", False))

        for action in self._actions:
            penalty = -10.0 if hazard and action in {"open_long", "open_short"} else 0.0
            simulated_next = np.asarray(state, dtype=float) + self._rng.normal(scale=0.1, size=self._value_weights.size)
            intrinsic = self.compute_intrinsic_reward(state, simulated_next)
            base_rewards[action] = pnl + penalty + intrinsic

        # Choose an action using the current UCB statistics prior to applying
        # any updates so that only the reward for the executed action is
        # incorporated into the running statistics.
        scores = self.ucb_scores()
        recommended = max(scores, key=scores.get)

        observed_reward = base_rewards[recommended]
        self.update(recommended, observed_reward)

        payload = {
            "timestamp": timestamp,
            "state": list(state),
            "signals": dict(signals),
            "ucb_scores": scores,
            "base_rewards": base_rewards,
            "recommended": recommended,
        }
        self._logger.info(json.dumps(payload))
        return recommended

