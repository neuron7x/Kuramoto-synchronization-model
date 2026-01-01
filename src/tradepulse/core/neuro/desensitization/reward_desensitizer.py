from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Tuple

from tradepulse.core.neuro.numeric_config import STABILITY_EPSILON


@dataclass(slots=True)
class RewardDesensitizerConfig:
    """Configuration for dopamine-like reward normalization."""

    ewma_alpha: float = 0.02
    setpoint: float = 0.0
    rpe_gain: float = 1.0
    max_abs: float = 8.0
    refractory_ticks: int = 5
    burst_z: float = 2.1
    min_scale: float = 0.3
    max_scale: float = 2.5


class RewardDesensitizer:
    """Tracks reward statistics and produces normalized signals."""

    def __init__(self, cfg: RewardDesensitizerConfig | None = None) -> None:
        self.cfg = cfg or RewardDesensitizerConfig()
        self._mean = 0.0
        self._var = STABILITY_EPSILON
        self._last = 0.0
        self._refractory = 0

    def update(self, reward: float) -> Tuple[float, Dict[str, float]]:
        """Update the state with a new reward sample."""

        delta = reward - self._mean
        self._mean += self.cfg.ewma_alpha * delta
        self._var = (
            1 - self.cfg.ewma_alpha
        ) * self._var + self.cfg.ewma_alpha * delta * delta
        std = max(STABILITY_EPSILON, math.sqrt(self._var))
        z = (reward - self._mean) / std
        rpe = reward - self._last

        if abs(z) >= self.cfg.burst_z:
            self._refractory = self.cfg.refractory_ticks

        gain = self.cfg.rpe_gain
        if self._refractory > 0:
            gain *= 0.5
            self._refractory -= 1

        centered = (reward - self._mean) + (self.cfg.setpoint - self._mean)
        adjusted = centered + gain * rpe
        adjusted = max(-self.cfg.max_abs, min(self.cfg.max_abs, adjusted))

        scale = 1.0 / max(STABILITY_EPSILON, std)
        scale = max(self.cfg.min_scale, min(self.cfg.max_scale, scale))
        normalized = adjusted * scale
        self._last = reward

        return normalized, {
            "mean": self._mean,
            "std": std,
            "z": z,
            "rpe": rpe,
            "gain": gain,
            "scale": scale,
            "refractory": float(self._refractory),
            "normalized": normalized,
        }
