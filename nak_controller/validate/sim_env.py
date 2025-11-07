"""Synthetic simulation environment used for validation routines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

import numpy as np


@dataclass(slots=True)
class SimulationEnvironment:
    """Produce synthetic observations for validation loops."""

    seed: int
    cooldown_ms_base: float = 2000.0

    _rng: np.random.Generator = field(init=False, repr=False)
    _step: int = field(init=False, repr=False, default=0)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_rng", np.random.default_rng(self.seed))
        object.__setattr__(self, "_step", 0)

    def step(self) -> tuple[Dict[str, float], Dict[str, float], Dict[str, float]]:
        """Return local observations, global observations and base scalars."""
        self._step += 1
        seasonal = 0.5 + 0.5 * np.sin(self._step / 10.0)
        noise = self._rng.normal(0.0, 0.1, size=6)

        local = {
            "trades": float(np.clip(0.5 + 0.4 * seasonal + noise[0], 0.0, 1.0)),
            "pnl": float(self._rng.normal(0.0, 0.005)),
            "pnl_scale": 0.01,
            "local_vol": float(np.clip(0.3 + 0.5 * seasonal + noise[1], 0.0, 1.0)),
            "local_dd": float(np.clip(0.1 + 0.3 * seasonal + noise[2], 0.0, 1.0)),
            "tech_errors": float(np.clip(0.05 + abs(noise[3]), 0.0, 1.0)),
            "latency": float(np.clip(0.2 + abs(noise[4]), 0.0, 1.0)),
            "slippage": float(np.clip(0.0005 + 0.0005 * noise[5], 0.0, 0.005)),
            "glial_support": float(np.clip(0.4 + 0.2 * seasonal, 0.0, 1.0)),
        }

        global_obs = {
            "global_vol": float(
                np.clip(0.4 + 0.4 * seasonal + self._rng.normal(0.0, 0.1), 0.0, 1.0)
            ),
            "portfolio_dd": float(
                np.clip(0.2 + 0.5 * seasonal + self._rng.normal(0.0, 0.1), 0.0, 1.0)
            ),
            "exposure": float(np.clip(0.5 + 0.3 * seasonal, 0.0, 1.0)),
            "unexpected_reward": float(self._rng.normal(0.0, 0.5)),
        }

        bases = {
            "risk_per_trade": 0.002,
            "max_position": 1.0,
            "cooldown_ms_base": self.cooldown_ms_base,
        }
        return local, global_obs, bases


__all__ = ["SimulationEnvironment"]
