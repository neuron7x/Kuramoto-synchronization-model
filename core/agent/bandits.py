# SPDX-License-Identifier: MIT
from __future__ import annotations

from collections.abc import Iterable
import math
import random
from secrets import SystemRandom
from typing import Dict, List, Sequence


Arm = str


def _unique_arms(arms: Iterable[Arm]) -> List[Arm]:
    """Return a list of unique arms preserving their original order."""
    seen = set()
    ordered: List[Arm] = []
    for arm in arms:
        if arm in seen:
            continue
        seen.add(arm)
        ordered.append(arm)
    return ordered


class EpsilonGreedy:
    """Classic epsilon-greedy bandit with cryptographically strong randomness."""

    def __init__(
        self,
        arms: Iterable[Arm],
        *,
        epsilon: float = 0.1,
        rng: random.Random | None = None,
    ) -> None:
        if not 0.0 <= epsilon <= 1.0:
            raise ValueError("epsilon must be within [0, 1]")

        ordered_arms = _unique_arms(arms)
        self._values: Dict[Arm, float] = {arm: 0.0 for arm in ordered_arms}
        self._counts: Dict[Arm, int] = {arm: 0 for arm in ordered_arms}
        self.epsilon = float(epsilon)
        self._rng = rng or SystemRandom()

    @property
    def arms(self) -> Sequence[Arm]:
        """Expose the currently known arms in deterministic order."""
        return tuple(self._values.keys())

    def add_arm(self, arm: Arm) -> None:
        """Register a new arm if it does not already exist."""
        if arm in self._values:
            return
        self._values[arm] = 0.0
        self._counts[arm] = 0

    def remove_arm(self, arm: Arm) -> None:
        """Remove an arm and its associated statistics."""
        if arm not in self._values:
            raise KeyError(f"Unknown arm '{arm}'")
        del self._values[arm]
        del self._counts[arm]

    def select(self) -> Arm:
        """Select the next arm using epsilon-greedy exploration."""
        if not self._values:
            raise ValueError("No arms available")
        arms = list(self._values.keys())
        if self._rng.random() < self.epsilon:
            return self._rng.choice(arms)
        return max(arms, key=lambda arm: self._values[arm])

    def update(self, arm: Arm, reward: float) -> None:
        """Update running averages with an observed reward for an arm."""
        if arm not in self._values:
            raise KeyError(f"Unknown arm '{arm}'")
        self._counts[arm] += 1
        n = self._counts[arm]
        self._values[arm] += (reward - self._values[arm]) / n

    def estimate(self, arm: Arm) -> float:
        """Return the current reward estimate for an arm."""
        if arm not in self._values:
            raise KeyError(f"Unknown arm '{arm}'")
        return self._values[arm]

    def pulls(self, arm: Arm) -> int:
        """Return the number of times an arm has been selected."""
        if arm not in self._counts:
            raise KeyError(f"Unknown arm '{arm}'")
        return self._counts[arm]


class UCB1:
    """Upper Confidence Bound (UCB1) multi-armed bandit implementation."""

    def __init__(self, arms: Iterable[Arm]) -> None:
        ordered_arms = _unique_arms(arms)
        self._values: Dict[Arm, float] = {arm: 0.0 for arm in ordered_arms}
        self._counts: Dict[Arm, int] = {arm: 0 for arm in ordered_arms}
        self._total_pulls = 0

    @property
    def arms(self) -> Sequence[Arm]:
        return tuple(self._values.keys())

    def add_arm(self, arm: Arm) -> None:
        if arm in self._values:
            return
        self._values[arm] = 0.0
        self._counts[arm] = 0

    def select(self) -> Arm:
        if not self._values:
            raise ValueError("No arms available")

        self._total_pulls += 1

        def ucb(arm: Arm) -> float:
            pulls = self._counts[arm]
            if pulls == 0:
                return float("inf")
            exploration = math.sqrt(2.0 * math.log(self._total_pulls) / pulls)
            return self._values[arm] + exploration

        return max(self._values.keys(), key=ucb)

    def update(self, arm: Arm, reward: float) -> None:
        if arm not in self._values:
            raise KeyError(f"Unknown arm '{arm}'")
        self._counts[arm] += 1
        pulls = self._counts[arm]
        self._values[arm] += (reward - self._values[arm]) / pulls

    def estimate(self, arm: Arm) -> float:
        if arm not in self._values:
            raise KeyError(f"Unknown arm '{arm}'")
        return self._values[arm]

    def pulls(self, arm: Arm) -> int:
        if arm not in self._counts:
            raise KeyError(f"Unknown arm '{arm}'")
        return self._counts[arm]
