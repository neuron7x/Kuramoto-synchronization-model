from __future__ import annotations

from typing import Any, Dict

from ..runtime.controller import NaKController


class NaKHook:
    """Thin integration layer for TradePulse strategy executors."""

    def __init__(self, config_path: str):
        self.ctrl = NaKController(config_path)

    def compute_limits(
        self,
        strategy_id: str,
        local_obs: Dict[str, float],
        global_obs: Dict[str, float],
        risk_per_trade_base: float,
        max_position_base: float,
        cooldown_ms_base: int,
    ) -> Dict[str, Any]:
        out = self.ctrl.step(
            strategy_id,
            local_obs,
            global_obs,
            bases=dict(
                risk_per_trade_base=risk_per_trade_base,
                max_position_base=max_position_base,
                cooldown_ms_base=cooldown_ms_base,
            ),
        )
        # Convert factors to absolute if needed at integration point
        return out
