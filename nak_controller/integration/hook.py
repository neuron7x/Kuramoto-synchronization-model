from __future__ import annotations

import os
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
        self._config_path = Path(config_path)
        resolved_seed = seed
        if resolved_seed is None:
            env_seed = os.getenv("NAK_SEED")
            if env_seed is not None:
                env_seed = env_seed.strip()
                if env_seed:
                    try:
                        resolved_seed = int(env_seed)
                    except ValueError as exc:
                        raise ValueError("NAK_SEED must be an integer") from exc
        self._seed = resolved_seed
        self._controller = NaKController(self._config_path, seed=resolved_seed)

    @property
    def config_path(self) -> Path:
        """Return the resolved configuration path."""
        return self._config_path

    @property
    def seed(self) -> int | None:
        """Return the most recent RNG seed."""
        return self._seed

    def reset(self, *, seed: int | None = None) -> None:
        """Reset the controller state."""
        reseed = seed if seed is not None else self._seed
        if seed is not None:
            self._seed = seed
        self._controller.reset(seed=reseed)

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
