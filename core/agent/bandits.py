# SPDX-License-Identifier: MIT
from __future__ import annotations

import math
import random
from typing import List, Protocol, Sequence


class _ArmRandom(Protocol):
    """Protocol describing the minimal interface required for RNG hooks."""

    def random(self) -> float:
        """Return a float in the interval [0.0, 1.0)."""

    def choice(self, seq: Sequence[str]) -> str:
        """Select an element from the provided sequence."""


class EpsilonGreedy:
    def __init__(
        self,
        arms: List[str],
        epsilon: float = 0.1,
        rng: _ArmRandom | None = None,
    ):
        self.Q = {a: 0.0 for a in arms}
        self.N = {a: 0 for a in arms}
        self.epsilon = epsilon
        self._rng: _ArmRandom = rng or random.SystemRandom()

    @property
    def rng(self) -> _ArmRandom:
        """Expose the RNG to allow deterministic injection for testing."""

        return self._rng

    @rng.setter
    def rng(self, rng: _ArmRandom) -> None:
        self._rng = rng

    def select(self) -> str:
        if self._rng.random() < self.epsilon:
            return self._rng.choice(list(self.Q.keys()))
        arms = list(self.Q.keys())
        if not arms:
            raise ValueError("No arms available")
        return max(arms, key=lambda a: self.Q[a])

    def update(self, arm: str, reward: float):
        self.N[arm] += 1
        n = self.N[arm]
        self.Q[arm] += (reward - self.Q[arm]) / n


class UCB1:
    def __init__(self, arms: List[str]):
        self.Q = {a: 0.0 for a in arms}
        self.N = {a: 0 for a in arms}
        self.t = 0

    def select(self) -> str:
        self.t += 1

        def ucb(a):
            n = self.N[a]
            if n == 0:
                return float("inf")
            return self.Q[a] + math.sqrt(2 * math.log(self.t) / n)

        return max(self.Q.keys(), key=ucb)

    def update(self, arm: str, reward: float):
        self.N[arm] += 1
        n = self.N[arm]
        self.Q[arm] += (reward - self.Q[arm]) / n
