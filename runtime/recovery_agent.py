"""Adaptive recovery agent for crisis mitigation."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RecoveryState:
    """Compact representation of the controller state."""

    F_current: float
    F_baseline: float
    latency_spike: float
    steps_in_crisis: int


class RecoveryAction:
    """Discrete recovery actions."""

    SLOW = "slow"
    MEDIUM = "medium"
    FAST = "fast"
    ALL = (SLOW, MEDIUM, FAST)


class AdaptiveRecoveryAgent:
    """Minimal Q-learning implementation for recovery planning."""

    def __init__(
        self,
        *,
        alpha: float = 0.1,
        gamma: float = 0.95,
        epsilon: float = 0.1,
        state_bins: int = 10,
        rng: np.random.Generator | None = None,
    ) -> None:
        self.alpha = alpha
        self.gamma = gamma
        self.epsilon = epsilon
        self.state_bins = max(state_bins, 1)
        self._rng = rng or np.random.default_rng()

        self.Q: Dict[Tuple[Tuple[int, int, int], str], float] = defaultdict(float)
        self.episode_count = 0
        self.total_reward = 0.0
        self.action_history: list[Dict[str, object]] = []

        logger.debug(
            "AdaptiveRecoveryAgent initialised alpha=%s gamma=%s epsilon=%s",
            alpha,
            gamma,
            epsilon,
        )

    # State handling -----------------------------------------------------
    def discretize_state(self, state: RecoveryState) -> Tuple[int, int, int]:
        deviation = (
            0.0
            if state.F_baseline == 0
            else ((state.F_current - state.F_baseline) / state.F_baseline)
        )
        F_bin = int(np.clip(deviation * 100, 0, 2 * self.state_bins - 1))
        spike_bin = int(np.clip(state.latency_spike - 1.0, 0, 2 * self.state_bins - 1))
        duration_bin = int(
            np.clip(
                state.steps_in_crisis / max(self.state_bins, 1), 0, self.state_bins - 1
            )
        )
        return F_bin, spike_bin, duration_bin

    # Policy -------------------------------------------------------------
    def choose_action(self, state: RecoveryState) -> str:
        discrete_state = self.discretize_state(state)
        if self._rng.random() < self.epsilon:
            action = self._rng.choice(RecoveryAction.ALL)
            logger.debug("Exploration step: action=%s state=%s", action, discrete_state)
        else:
            values = {
                action: self.Q[(discrete_state, action)]
                for action in RecoveryAction.ALL
            }
            action = max(values, key=values.get)
            logger.debug(
                "Exploitation step: action=%s q=%.6f state=%s",
                action,
                values[action],
                discrete_state,
            )
        self.action_history.append({"state": discrete_state, "action": action})
        return action

    def update(
        self,
        state: RecoveryState,
        action: str,
        reward: float,
        next_state: RecoveryState,
    ) -> None:
        s = self.discretize_state(state)
        s_next = self.discretize_state(next_state)

        current = self.Q[(s, action)]
        max_next = max(self.Q[(s_next, a)] for a in RecoveryAction.ALL)
        new_value = current + self.alpha * (reward + self.gamma * max_next - current)
        self.Q[(s, action)] = new_value
        self.total_reward += reward

        logger.debug(
            "Q update state=%s action=%s reward=%.6f value=%.6f -> %.6f",
            s,
            action,
            reward,
            current,
            new_value,
        )

    def end_episode(self) -> None:
        count = len(self.action_history) or 1
        average_reward = self.total_reward / count
        self.episode_count += 1
        logger.info(
            "Episode %s finished average_reward=%.6f actions=%s",
            self.episode_count,
            average_reward,
            count,
        )
        self.action_history.clear()
        self.total_reward = 0.0

    # Utilities ----------------------------------------------------------
    def get_recovery_params(self, action: str) -> Dict[str, float]:
        mapping = {
            RecoveryAction.SLOW: {
                "mutation_rate": 0.1,
                "recovery_speed": 1.05,
                "generations": 10,
            },
            RecoveryAction.MEDIUM: {
                "mutation_rate": 0.3,
                "recovery_speed": 1.15,
                "generations": 30,
            },
            RecoveryAction.FAST: {
                "mutation_rate": 0.5,
                "recovery_speed": 1.30,
                "generations": 50,
            },
        }
        return mapping[action]

    def save_q_table(self, path: str) -> None:
        import pickle

        with open(path, "wb") as fh:
            pickle.dump(dict(self.Q), fh)
        logger.info("Saved Q-table entries=%s path=%s", len(self.Q), path)

    def load_q_table(self, path: str) -> None:
        import builtins
        import pickle

        # CWE-502: Use restricted unpickler to prevent arbitrary code execution
        # The Q-table only contains primitive types (dict, tuple, str, float)
        class RestrictedUnpickler(pickle.Unpickler):
            """Restricted unpickler that only allows safe types for Q-table."""

            SAFE_BUILTINS = frozenset({"dict", "tuple", "list", "str", "int", "float"})

            def find_class(self, module: str, name: str) -> type:
                if module == "builtins" and name in self.SAFE_BUILTINS:
                    return getattr(builtins, name)
                raise pickle.UnpicklingError(
                    f"Unsafe class: {module}.{name} - only primitive types are allowed for Q-table"
                )

        with open(path, "rb") as fh:
            data = RestrictedUnpickler(
                fh
            ).load()  # nosec B301 - guarded by restricted unpickler
        self.Q = defaultdict(float, data)
        logger.info("Loaded Q-table entries=%s path=%s", len(self.Q), path)


__all__ = ["AdaptiveRecoveryAgent", "RecoveryState", "RecoveryAction"]
