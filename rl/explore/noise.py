# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Exploration noise processes used by FHMC agents."""

from __future__ import annotations

import numpy as np


class OUProcess:
    """Ornstein–Uhlenbeck process for temporally correlated exploration."""

    def __init__(
        self,
        size: int,
        *,
        theta: float = 0.15,
        mu: float = 0.0,
        sigma: float = 0.2,
        dt: float = 1.0,
        rng: np.random.Generator | None = None,
    ) -> None:
        if size <= 0:
            raise ValueError("size must be positive")
        self.size = int(size)
        self.theta = float(theta)
        self.mu = float(mu)
        self.sigma = float(sigma)
        self.dt = float(dt)
        self._rng = rng or np.random.default_rng()
        self.x = np.zeros(self.size, dtype=float)

    def reset(self) -> None:
        self.x.fill(0.0)

    def sample(self) -> np.ndarray:
        noise = self._rng.normal(size=self.x.shape)
        dx = self.theta * (self.mu - self.x) * self.dt + self.sigma * np.sqrt(self.dt) * noise
        self.x = self.x + dx
        return self.x.copy()


class ColoredNoiseAR1:
    """Simple AR(1) coloured noise generator."""

    def __init__(self, size: int, *, rho: float = 0.95, sigma: float = 0.1) -> None:
        if size <= 0:
            raise ValueError("size must be positive")
        self.size = int(size)
        self.rho = float(rho)
        self.sigma = float(sigma)
        self.x = np.zeros(self.size, dtype=float)

    def sample(self) -> np.ndarray:
        noise = np.random.randn(*self.x.shape)
        self.x = self.rho * self.x + self.sigma * noise
        return self.x.copy()
