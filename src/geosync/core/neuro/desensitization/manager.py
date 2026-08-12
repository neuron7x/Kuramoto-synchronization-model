# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Tuple

from .reward_desensitizer import RewardDesensitizer, RewardDesensitizerConfig
from .sensory_habituation import SensoryHabituation, SensoryHabituationConfig
from .threat_gating import ThreatGate, ThreatGateConfig


@dataclass(slots=True)
class DesensitizationConfig:
    """Bundle configuration for the desensitization subsystems."""

    reward: RewardDesensitizerConfig = field(default_factory=RewardDesensitizerConfig)
    sensory: SensoryHabituationConfig = field(default_factory=SensoryHabituationConfig)
    threat: ThreatGateConfig = field(default_factory=ThreatGateConfig)


class DesensitizationManager:
    """Co-ordinates reward, sensory and threat modulation."""

    def __init__(self, cfg: DesensitizationConfig | None = None) -> None:
        self.cfg = cfg or DesensitizationConfig()
        self.reward = RewardDesensitizer(self.cfg.reward)
        self.sensory = SensoryHabituation(self.cfg.sensory)
        self.threat = ThreatGate(self.cfg.threat)
        self.last: Dict[str, Dict[str, float]] = {}

    def step(
        self,
        reward: float,
        *,
        features: Iterable[float],
        drawdown: float,
        vol: float,
        hpa_tone: float = 0.0,
    ) -> Tuple[float, Dict[str, Dict[str, float]]]:
        """Update all modules and produce a combined action gate."""

        shaped_reward, r_state = self.reward.update(reward)
        sensitivity, s_state = self.sensory.update(features)
        gate, t_state = self.threat.update(drawdown=drawdown, vol=vol, hpa_tone=hpa_tone)
        combined_gate = max(0.0, min(1.0, gate * (0.5 + 0.5 * sensitivity)))
        self.last = {
            "reward": r_state,
            "sensory": s_state,
            "threat": t_state,
            "combined": {"gate": combined_gate},
        }
        return combined_gate, self.last
