"""Discrete Hawkes process environment for risk-sensitive trading."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np


@dataclass
class HawkesConfig:
    mu: float
    alpha: float
    beta: float
    num_steps: int


class HawkesEnv:
    def __init__(self, config: HawkesConfig) -> None:
        self.config = config
        self.step_count = 0
        self.price = 100.0
        self.intensity = config.mu
        self.inventory = 0.0

    def reset(self) -> Dict[str, float | np.ndarray]:
        self.step_count = 0
        self.price = 100.0
        self.intensity = self.config.mu
        self.inventory = 0.0
        return self._state()

    def _state(self) -> Dict[str, float | np.ndarray]:
        obs = np.array(
            [
                self.price,
                self.intensity,
                self.inventory,
                float(self.step_count) / self.config.num_steps,
                np.sin(self.step_count / 10.0),
                np.cos(self.step_count / 10.0),
            ],
            dtype=np.float32,
        )
        return {"state": obs}

    def step(self, action: int) -> Tuple[Dict[str, float | np.ndarray], float, bool]:
        noise = np.random.poisson(self.intensity)
        self.intensity = max(
            1e-3,
            self.config.mu + self.config.alpha * noise + self.config.beta * (np.random.rand() - 0.5),
        )
        price_change = 0.01 * (noise - self.config.mu)
        self.price += price_change
        reward = price_change * (action - 1) - 0.001 * abs(action - 1)
        self.inventory += action - 1
        self.step_count += 1
        done = self.step_count >= self.config.num_steps
        return self._state(), float(reward), done


__all__ = ["HawkesEnv", "HawkesConfig"]
