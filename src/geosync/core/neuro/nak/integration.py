# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable

from ..desensitization.gate import DesensitizationGate, DesensitizationGateConfig
from ..desensitization.manager import DesensitizationConfig
from .controller import NaKConfig, NaKControllerV4_2


@dataclass(slots=True)
class AdapterOutput:
    reward: float
    gate: float
    effective_size: float
    temperature: float
    controller_log: Dict[str, float]
    gate_state: Dict[str, Dict[str, float]]


class NaKAdapter:
    """Adapter combining NaK controller output with desensitization gating."""

    def __init__(
        self,
        strategy_id: int,
        *,
        controller_config: NaKConfig | None = None,
        gate_config: DesensitizationGateConfig | None = None,
        core_config: DesensitizationConfig | None = None,
    ) -> None:
        self.controller = NaKControllerV4_2(strategy_id, controller_config)
        self.gate = DesensitizationGate(core_config=core_config, cfg=gate_config)

    def step(
        self,
        *,
        p: float,
        v: float,
        drawdown: float,
        features: Iterable[float] | None = None,
        p_exp_for_stim: float | None = None,
        hpa_tone: float = 0.0,
        base_temperature: float = 1.0,
        size_hint: float = 1.0,
    ) -> AdapterOutput:
        reward, ctrl_log = self.controller.update(
            p=p,
            v=v,
            drawdown=drawdown,
            features=features,
            p_exp_for_stim=p_exp_for_stim,
            hpa_tone=hpa_tone,
        )
        shaped_reward, size_gate, temp_effect, gate_state = self.gate.step(
            reward,
            features=features or [v],
            drawdown=max(0.0, -drawdown),
            vol=v,
            hpa_tone=hpa_tone,
            base_temperature=base_temperature,
        )
        gate_state["combined"]["lambda"] = ctrl_log.get(
            "lambda_", gate_state["combined"].get("lambda", 0.05)
        )
        effective_size = max(0.0, min(1.0, size_hint * size_gate))
        return AdapterOutput(
            reward=reward,
            gate=size_gate,
            effective_size=effective_size,
            temperature=temp_effect,
            controller_log=ctrl_log | {"shaped_reward": shaped_reward, "size_hint": size_hint},
            gate_state=gate_state,
        )
