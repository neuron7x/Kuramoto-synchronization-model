"""Integration surface for embedding the NaK controller into TradePulse."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, cast

from ..runtime.controller import NaKController


@dataclass(slots=True)
class LimitBases:
    """Base scalar limits used to scale controller outputs."""

    risk_per_trade: float
    max_position: float
    cooldown_ms: float


class NaKHook:
    """Thin adapter around :class:`NaKController` suitable for strategy hooks."""

    def __init__(self, config_path: str | Path, *, seed: int | None = None) -> None:
        self._controller = NaKController(config_path, seed=seed)
        self._config_path = Path(config_path)

    @property
    def config_path(self) -> Path:
        """Return the resolved configuration path."""
        return self._config_path

    def reset(self) -> None:
        """Reset the controller state."""
        self._controller.reset()

    def compute_limits(
        self,
        strategy_id: str,
        local_obs: Mapping[str, float],
        global_obs: Mapping[str, float],
        base_risk_per_trade: float,
        base_max_position: float,
        base_cooldown_ms: float,
    ) -> dict[str, object]:
        """Compute scaled limits for the provided observations."""
        bases = LimitBases(
            risk_per_trade=base_risk_per_trade,
            max_position=base_max_position,
            cooldown_ms=base_cooldown_ms,
        )
        response = self._controller.step(
            strategy_id,
            local_obs,
            global_obs,
            {"cooldown_ms_base": bases.cooldown_ms},
        )
        risk_factor = cast(float, response["risk_per_trade_factor"])
        max_position_factor = cast(float, response["max_position_factor"])
        enriched: dict[str, Any] = dict(response)
        enriched["risk_per_trade"] = risk_factor * bases.risk_per_trade
        enriched["max_position"] = max_position_factor * bases.max_position
        return enriched


__all__ = ["NaKHook", "LimitBases"]
