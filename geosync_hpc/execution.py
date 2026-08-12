# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Execution cost and fill modeling."""

from __future__ import annotations

import numpy as np


class Execution:
    def __init__(
        self,
        fee_bps: float = 1.0,
        impact_coeff: float = 0.8,
        impact_model: str = "square_root",
        queue_fill_p: float = 0.85,
        seed: int | None = None,
    ) -> None:
        self.fee = fee_bps * 1e-4
        self.impact_coeff = impact_coeff
        self.impact_model = impact_model
        self.queue_fill_p = queue_fill_p
        self._seed = seed
        self._rng = np.random.default_rng(seed)

    def reset_runtime_state(self) -> None:
        """Rewind the fill RNG to its construction seed.

        The ``queue_fill_p`` probabilistic fill advances the RNG on every
        call; without rewinding, a second ``BacktesterCAL.run`` on the same
        instance consumes a different RNG stream and yields different
        fills. Re-seeding from ``self._seed`` guarantees
        run_k(df) == run_j(df) for any k, j on identical input.
        """
        self._rng = np.random.default_rng(self._seed)

    def costs(self, spread_frac: float, vol_proxy: float, notional_frac: float = 1.0) -> float:
        half = 0.5 * spread_frac
        if self.impact_model == "linear":
            impact = self.impact_coeff * vol_proxy * 1e-4 * notional_frac
        elif self.impact_model == "quadratic":
            impact = self.impact_coeff * (vol_proxy**2) * 1e-4 * (notional_frac**2)
        else:
            impact = (
                self.impact_coeff
                * np.sqrt(abs(vol_proxy) + 1e-9)
                * 1e-4
                * np.sqrt(abs(notional_frac))
            )
        return float(self.fee + half + impact)

    def fill(self, mid: float, spread_frac: float, target_pos: float, cur_pos: float) -> float:
        side = np.sign(target_pos - cur_pos)
        slip = 0.5 * spread_frac * mid
        improve = self._rng.random() < self.queue_fill_p
        adj = (-0.25 * spread_frac * mid) if improve else 0.0
        fill_price = mid + side * slip + side * adj
        return float(fill_price)
