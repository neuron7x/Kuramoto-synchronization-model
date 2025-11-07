from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

from ..runtime.controller import NaKController

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "conf" / "nak.yaml"


@dataclass(slots=True)
class NaKHook:
    """User-facing wrapper exposing a simple ``compute_limits`` API."""

    config_path: str = str(DEFAULT_CONFIG)
    _controller: NaKController = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._controller = NaKController(self.config_path)

    def reset(self) -> None:
        """Reset the underlying controller state."""

        self._controller.reset()

    def compute_limits(
        self,
        strategy_id: str,
        local_obs: Dict[str, float],
        global_obs: Dict[str, float],
        base_risk_per_trade: float,
        base_max_position: float,
        base_cooldown_ms: float,
    ) -> Dict[str, Any]:
        """Return control outputs for a strategy."""

        bases = {
            "risk_per_trade_base": base_risk_per_trade,
            "max_position_base": base_max_position,
            "cooldown_ms_base": base_cooldown_ms,
        }
        result = self._controller.step(strategy_id, local_obs, global_obs, bases)
        risk = result["risk_per_trade_factor"] * base_risk_per_trade
        max_position = result["max_position_factor"] * base_max_position
        enriched = dict(result)
        enriched["risk_per_trade"] = risk
        enriched["max_position"] = max_position
        return enriched


__all__ = ["NaKHook"]
