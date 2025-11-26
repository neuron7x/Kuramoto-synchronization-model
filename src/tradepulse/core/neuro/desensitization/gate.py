from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, Tuple

from .manager import DesensitizationConfig, DesensitizationManager


@dataclass(slots=True)
class DesensitizationGateConfig:
    """High level controls for gate to trading policy."""

    k_temp: float = 0.5
    min_temp_mult: float = 0.5
    max_temp_mult: float = 2.0
    size_gain: float = 1.0
    fail_safe_gate: float = 0.25
    enable_temp: bool = True
    enable_size: bool = True


class DesensitizationGate:
    """Wraps the core manager to produce size and temperature controls."""

    def __init__(
        self,
        *,
        core: DesensitizationManager | None = None,
        core_config: DesensitizationConfig | None = None,
        cfg: DesensitizationGateConfig | None = None,
    ) -> None:
        self.core = core or DesensitizationManager(
            core_config or DesensitizationConfig()
        )
        self.cfg = cfg or DesensitizationGateConfig()

    def step(
        self,
        reward: float,
        *,
        features: Iterable[float],
        drawdown: float,
        vol: float,
        hpa_tone: float = 0.0,
        base_temperature: float | None = None,
    ) -> Tuple[float, float, float, Dict[str, Dict[str, float]]]:
        """Run the desensitization core and derive policy controls."""

        size_gate, state = self.core.step(
            reward,
            features=features,
            drawdown=drawdown,
            vol=vol,
            hpa_tone=hpa_tone,
        )
        shaped_reward = state["reward"]["normalized"]

        sg = size_gate * self.cfg.size_gain if self.cfg.enable_size else 1.0
        if not math.isfinite(sg):
            sg = self.cfg.fail_safe_gate
        sg = max(0.0, min(1.0, sg))

        if self.cfg.enable_temp:
            x = shaped_reward
            tm = math.exp(-self.cfg.k_temp * x)
            tm = max(self.cfg.min_temp_mult, min(self.cfg.max_temp_mult, tm))
        else:
            tm = 1.0

        temp_effect = (base_temperature or 1.0) * tm
        state["combined"].update(
            {
                "size_gate": sg,
                "temp_multiplier": tm,
                "reopen_phase": state["threat"]["reopen_phase"],
            }
        )
        return shaped_reward, sg, temp_effect, state
