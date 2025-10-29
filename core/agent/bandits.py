# SPDX-License-Identifier: MIT
from __future__ import annotations

import math
from secrets import SystemRandom
from typing import List


class EpsilonGreedy:
    def __init__(self, arms: List[str], epsilon: float = 0.1):
        self.Q = {a: 0.0 for a in arms}
        self.N = {a: 0 for a in arms}
        self.epsilon = epsilon
        self._rng = SystemRandom()

    def select(self) -> str:
        arms = list(self.Q.keys())
        if not arms:
            raise ValueError("No arms available")
        if self._rng.random() < self.epsilon:
            return self._rng.choice(arms)
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
