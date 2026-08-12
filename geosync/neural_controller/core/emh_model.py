# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import logging
from typing import Dict, Iterable

from .params import Params
from .s_modulators import SModulator, load_s_modulators
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


class EMHSSM:
    """EMH-inspired bounded state-space model."""

    def __init__(
        self,
        p: Params,
        s: EMHState | None = None,
        s_modulators: Iterable[SModulator] | None = None,
    ):
        self.p = p
        self.s = s or EMHState()
        self.belief_term_gain = 0.05
        self.S_modulators = list(s_modulators or load_s_modulators())

    def step(self, obs: Dict[str, float]) -> Dict[str, float]:
        dd = clamp(float(obs.get("dd", 0.0)))
        liq = clamp(float(obs.get("liq", 0.0)))
        reg = clamp(float(obs.get("reg", 0.0)))
        vol = clamp(float(obs.get("vol", 0.0)))
        var_breach = bool(obs.get("var_breach", False))
        reward = float(obs.get("reward", 0.0))
        belief_term = float(obs.get("belief_term", 0.0))
        self.s.mode = _threat_mode(dd, var_breach, vol)
        D = _demand(dd, liq, reg, self.p.psi)

        gamma_rl = 0.9
        delta_rpe = reward + gamma_rl * self.s.V - self.s.V
        self.s.V += 0.1 * delta_rpe

        base_S = (
            self.p.phi * D
            + self.p.omega * (1.0 - self.s.M / self.p.M0)
            + self.p.kappa * delta_rpe
            + self.belief_term_gain * belief_term
        )
        modulation = sum(modulator(self, obs) for modulator in self.S_modulators)
        self.s.S = clamp(base_S + modulation)

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
