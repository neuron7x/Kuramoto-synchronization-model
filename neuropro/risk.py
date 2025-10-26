"""Risk guardrails used during backtests."""

from __future__ import annotations

import numpy as np


class Guardrails:
    def __init__(
        self,
        intraday_dd_limit: float = 0.02,
        loss_streak_cooldown: int = 4,
        vola_spike_mult: float = 2.5,
        exposure_cap: float = 1.0,
    ) -> None:
        self.dd_limit = intraday_dd_limit
        self.cooldown_streak = loss_streak_cooldown
        self.vola_mult = vola_spike_mult
        self.exposure_cap = exposure_cap
        self.peak = 0.0
        self.cooldown = 0

    def check(
        self,
        equity_curve: list[float],
        vola: float,
        vola_avg: float,
        loss_streak: int,
        proposed_pos: float,
    ) -> dict[str, float | bool]:
        if len(equity_curve) == 0:
            return {
                "halt": False,
                "throttle": 1.0,
                "pos_cap": np.clip(proposed_pos, -self.exposure_cap, self.exposure_cap),
            }
        eq = float(equity_curve[-1])
        self.peak = max(self.peak, eq)
        dd = (self.peak - eq) / (1e-9 + self.peak)
        halt = dd > self.dd_limit or loss_streak >= self.cooldown_streak
        throttle = 0.5 if vola > self.vola_mult * max(1e-9, vola_avg) else 1.0
        if halt:
            self.cooldown = 60
        if self.cooldown > 0:
            self.cooldown -= 1
            throttle = 0.0
        pos_cap = float(np.clip(proposed_pos, -self.exposure_cap, self.exposure_cap))
        return {"halt": halt, "throttle": throttle, "pos_cap": pos_cap}
