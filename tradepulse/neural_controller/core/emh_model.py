from __future__ import annotations

import logging
import math
from typing import Dict

from .params import NeuromodulationMixConfig, Params
from .state import EMHState, clamp

log = logging.getLogger(__name__)


def _demand(
    dd: float,
    liq: float,
    reg: float,
    psi: float,
    w_dd: float = 0.5,
    w_liq: float = 0.3,
    w_reg: float = 0.2,
) -> float:
    return clamp(psi * (w_dd * clamp(dd) + w_liq * clamp(liq) + w_reg * clamp(reg)))


def _threat_mode(dd: float, var_breach: bool, vol: float) -> str:
    if var_breach or dd > 0.7 or vol > 0.9:
        return "RED"
    if dd > 0.4 or vol > 0.7:
        return "AMBER"
    return "GREEN"


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def mix_prediction_rpe(
    prediction_error: float,
    rpe: float,
    *,
    volatility: float,
    confidence: float,
    config: NeuromodulationMixConfig,
    prev_weight: float | None = None,
) -> tuple[float, float]:
    drive = max(clamp(volatility), 1.0 - clamp(confidence))
    target = _sigmoid(config.volatility_slope * (drive - config.volatility_midpoint))
    target = clamp(target, config.min_weight, config.max_weight)
    base_weight = config.normalized_prediction_weight()
    current = base_weight if prev_weight is None else prev_weight
    weight = current + config.anneal_rate * (target - current)
    weight = clamp(weight, config.min_weight, config.max_weight)
    mixed = weight * prediction_error + (1.0 - weight) * rpe
    return mixed, weight


class EMHSSM:
    """EMH-inspired bounded state-space model."""

    def __init__(self, p: Params, s: EMHState | None = None):
        self.p = p
        self.s = s or EMHState()
        self.belief_term_gain = 0.05
        self.mix_weight = self.p.neuromodulation_mix.normalized_prediction_weight()

    def step(self, obs: Dict[str, float]) -> Dict[str, float]:
        dd = clamp(float(obs.get("dd", 0.0)))
        liq = clamp(float(obs.get("liq", 0.0)))
        reg = clamp(float(obs.get("reg", 0.0)))
        vol = clamp(float(obs.get("vol", 0.0)))
        var_breach = bool(obs.get("var_breach", False))
        reward = float(obs.get("reward", 0.0))
        belief_term = float(obs.get("belief_term", 0.0))
        prediction_error = float(obs.get("prediction_error", 0.0))
        sensory_confidence = clamp(float(obs.get("sensory_confidence", 1.0)))
        confidence_weight = max(
            0.0,
            (1.0 - self.p.sensory_confidence_gain)
            + self.p.sensory_confidence_gain * sensory_confidence,
        )
        prediction_error *= confidence_weight

        self.s.mode = _threat_mode(dd, var_breach, vol)
        D = _demand(dd, liq, reg, self.p.psi)

        gamma_rl = 0.9
        delta_rpe = reward + gamma_rl * self.s.V - self.s.V
        self.s.V += 0.1 * delta_rpe
        scaled_rpe = self.p.kappa * delta_rpe
        scaled_prediction = self.p.prediction_gain * prediction_error
        mixed_error, self.mix_weight = mix_prediction_rpe(
            scaled_prediction,
            scaled_rpe,
            volatility=vol,
            confidence=sensory_confidence,
            config=self.p.neuromodulation_mix,
            prev_weight=self.mix_weight,
        )

        self.s.S = clamp(
            self.p.phi * D
            + self.p.omega * (1.0 - self.s.M / self.p.M0)
            + self.belief_term_gain * belief_term
            + mixed_error
        )

        dH = self.p.alpha * self.s.S - self.p.beta * self.s.H + self.p.gamma * self.s.M
        dM = -self.p.delta * self.s.M + self.p.theta
        dE = self.p.lambd * (D - self.s.M) + self.p.mu * self.s.H * self.s.S

        self.s.H = clamp(self.s.H + dH)
        self.s.M = clamp(self.s.M + dM)
        self.s.E = clamp(self.s.E + dE)

        if self.s.M < self.p.eps * D:
            self.s.E = clamp(self.s.E + self.p.eta)

        out = dict(
            H=self.s.H,
            M=self.s.M,
            E=self.s.E,
            S=self.s.S,
            D=D,
            RPE=delta_rpe,
            mode=self.s.mode,
        )
        return out
