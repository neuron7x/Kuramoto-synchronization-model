"""Synthetic simulator to exercise the NaK controller."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterator, Tuple

import numpy as np


@dataclass(slots=True)
class SimulatedEnvironment:
    """Generate deterministic observation streams for validation."""

    seed: int
    steps: int
    _rng: np.random.Generator = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)

    def iter_steps(self) -> Iterator[Tuple[Dict[str, float], Dict[str, float]]]:
        """Yield ``(local_obs, global_obs)`` tuples for each step."""

        for _ in range(self.steps):
            trades = float(self._rng.uniform(0.0, 1.0))
            pnl = float(self._rng.normal(0.0, 0.002))
            local_vol = float(self._rng.uniform(0.05, 1.0))
            local_dd = float(self._rng.uniform(0.0, 1.0))
            tech_errors = float(self._rng.uniform(0.0, 0.4))
            latency = float(self._rng.uniform(0.0, 0.6))
            slippage = float(self._rng.normal(0.0, 0.001))
            glial = float(self._rng.uniform(0.0, 0.5))

            local = {
                "trades": trades,
                "pnl": pnl,
                "pnl_scale": 0.01,
                "local_vol": local_vol,
                "local_dd": local_dd,
                "tech_errors": tech_errors,
                "latency": latency,
                "slippage": slippage,
                "glial_support": glial,
            }

            global_vol = float(self._rng.uniform(0.0, 1.0))
            portfolio_dd = float(self._rng.uniform(0.0, 1.0))
            exposure = float(self._rng.uniform(0.5, 1.0))
            unexpected_reward = float(self._rng.normal(0.0, 0.5))

            global_obs = {
                "global_vol": global_vol,
                "portfolio_dd": portfolio_dd,
                "exposure": exposure,
                "unexpected_reward": unexpected_reward,
            }
            yield local, global_obs


__all__ = ["SimulatedEnvironment"]
