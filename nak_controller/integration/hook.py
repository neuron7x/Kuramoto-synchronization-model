"""Integration helpers for embedding the NaK controller into TradePulse.

Copyright (c) 2024 TradePulse Technologies. All rights reserved.
Licensed under the TradePulse Proprietary License Agreement (TPLA).
"""

from __future__ import annotations

from typing import Dict, Mapping, Optional

from ..runtime.controller import BaseLimits, NaKController, NaKStepOutput


class NaKHook:
    """Thin integration layer for TradePulse strategy executors."""

    def __init__(self, config_path: str, *, seed: Optional[int] = None):
        self.ctrl = NaKController(config_path, seed=seed)

    def reset(self, *, seed: Optional[int] = None) -> None:
        """Reset the underlying controller to a clean state."""

        self.ctrl.reset(seed=seed)

    def compute_limits(
        self,
        strategy_id: str,
        local_obs: Mapping[str, float],
        global_obs: Mapping[str, float],
        risk_per_trade_base: float,
        max_position_base: float,
        cooldown_ms_base: int,
    ) -> NaKStepOutput:
        bases: BaseLimits = {
            "risk_per_trade_base": risk_per_trade_base,
            "max_position_base": max_position_base,
            "cooldown_ms_base": cooldown_ms_base,
        }
        return self.ctrl.step(strategy_id, local_obs, global_obs, bases=bases)

    def compute_limits_dict(
        self,
        strategy_id: str,
        local_obs: Mapping[str, float],
        global_obs: Mapping[str, float],
        risk_per_trade_base: float,
        max_position_base: float,
        cooldown_ms_base: int,
    ) -> Dict[str, object]:
        """Compatibility wrapper returning a serialisable dictionary."""

        return self.compute_limits(
            strategy_id,
            local_obs,
            global_obs,
            risk_per_trade_base,
            max_position_base,
            cooldown_ms_base,
        ).as_dict()


__all__ = ["NaKHook"]
