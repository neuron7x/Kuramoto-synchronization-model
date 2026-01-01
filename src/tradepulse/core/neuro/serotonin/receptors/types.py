from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass(slots=True)
class ReceptorContext:
    volatility_norm: float
    drawdown_norm: float
    novelty_norm: float
    shock_norm: float
    impulse_pressure_norm: float
    regime_entropy_norm: float
    circadian_phase: Optional[float] = None
    temperature_floor: float = 0.0


@dataclass(slots=True)
class ParamDeltas:
    cooldown_s: float = 0.0
    temperature_floor_delta: float = 0.0
    pos_mult_cap_delta: float = 0.0
    hold_hysteresis_delta: float = 0.0
    phasic_weight_delta: float = 0.0
    tonic_weight_delta: float = 0.0
    veto_bias: float = 0.0
    force_veto: bool = False

    def combine(self, other: "ParamDeltas") -> "ParamDeltas":
        return ParamDeltas(
            cooldown_s=min(max(self.cooldown_s + other.cooldown_s, 0.0), 600.0),
            temperature_floor_delta=min(
                max(self.temperature_floor_delta + other.temperature_floor_delta, -0.5),
                0.5,
            ),
            pos_mult_cap_delta=min(self.pos_mult_cap_delta + other.pos_mult_cap_delta, 0.0),
            hold_hysteresis_delta=min(
                max(self.hold_hysteresis_delta + other.hold_hysteresis_delta, 0.0), 0.2
            ),
            phasic_weight_delta=max(self.phasic_weight_delta + other.phasic_weight_delta, -0.9),
            tonic_weight_delta=min(self.tonic_weight_delta + other.tonic_weight_delta, 1.0),
            veto_bias=min(max(self.veto_bias + other.veto_bias, -0.2), 0.5),
            force_veto=self.force_veto or other.force_veto,
        )

    def to_dict(self) -> Dict[str, float | bool]:
        return {
            "cooldown_s": self.cooldown_s,
            "temperature_floor_delta": self.temperature_floor_delta,
            "pos_mult_cap_delta": self.pos_mult_cap_delta,
            "hold_hysteresis_delta": self.hold_hysteresis_delta,
            "phasic_weight_delta": self.phasic_weight_delta,
            "tonic_weight_delta": self.tonic_weight_delta,
            "veto_bias": self.veto_bias,
            "force_veto": self.force_veto,
        }


@dataclass(slots=True)
class ReceptorState:
    prev_activation: float = 0.0
    latched: bool = False


ReceptorActivation = Dict[str, float]
