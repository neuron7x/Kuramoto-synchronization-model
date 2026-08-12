# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Extramedullary hematopoiesis inspired state-space model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from geosync_pro.estimation.belief import VolBelief


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp *x* between *lo* and *hi*."""
    return max(lo, min(hi, x))


@dataclass
class Params:
    """Model parameters."""

    alpha: float = 0.10
    beta: float = 0.05
    gamma: float = 0.05
    delta: float = 0.10
    theta: float = 0.00
    lambd: float = 0.20
    mu: float = 0.05
    phi: float = 0.60
    omega: float = 0.40
    kappa: float = 0.10
    psi: float = 1.0
    eps: float = 0.7
    eta: float = 0.2
    M0: float = 0.8


@dataclass
class State:
    """Container for latent state and metadata."""

    H: float = 0.5
    M: float = 0.8
    E: float = 0.1
    S: float = 0.0
    V: float = 0.0
    mode: str = "GREEN"


def demand(
    dd: float,
    liq: float,
    reg: float,
    psi: float,
    w_dd: float = 0.5,
    w_liq: float = 0.3,
    w_reg: float = 0.2,
) -> float:
    """Aggregate stress demand in the [0, 1] range."""

    x = w_dd * clamp(dd) + w_liq * clamp(liq) + w_reg * clamp(reg)
    return clamp(psi * x)


def threat_mode(dd: float, var_breach: bool, vol: float) -> str:
    """Determine threat mode from drawdown, VaR breach, and volatility."""

    if var_breach or dd > 0.7 or vol > 0.9:
        return "RED"
    if dd > 0.4 or vol > 0.7:
        return "AMBER"
    return "GREEN"


class EMHSSM:
    """State-space model with bounded states and dopamine-linked signal."""

    def __init__(self, p: Params, s: Optional[State] = None) -> None:
        self.p = p
        self.s = s or State()
        self.belief: Optional["VolBelief"] = None

    def step(self, obs: Dict[str, float]) -> Dict[str, Any]:
        """Advance one simulation step and return the updated snapshot."""

        dd = clamp(obs.get("dd", 0.0))
        liq = clamp(obs.get("liq", 0.0))
        reg = clamp(obs.get("reg", 0.0))
        vol = clamp(obs.get("vol", 0.0))
        var_breach = bool(obs.get("var_breach", False))
        reward = float(obs.get("reward", 0.0))

        # Threat mode
        self.s.mode = threat_mode(dd, var_breach, vol)

        # Demand
        D = demand(dd, liq, reg, self.p.psi)

        # Dopamine RPE (TD(0))
        gamma_rl = 0.9
        delta_rpe = reward + gamma_rl * self.s.V - self.s.V
        self.s.V += 0.1 * delta_rpe

        # Belief (optional)
        belief_term = 0.0
        if self.belief is not None:
            B = self.belief.step(vol)  # P(high-vol regime)
            belief_term = 0.05 * (B - 0.5)

        # Aggregate signal S
        self.s.S = clamp(
            self.p.phi * D
            + self.p.omega * (1.0 - self.s.M / self.p.M0)
            + self.p.kappa * delta_rpe
            + belief_term
        )

        # Dynamics
        dH = self.p.alpha * self.s.S - self.p.beta * self.s.H + self.p.gamma * self.s.M
        dM = -self.p.delta * self.s.M + self.p.theta
        dE = self.p.lambd * (D - self.s.M) + self.p.mu * self.s.H * self.s.S

        self.s.H = clamp(self.s.H + dH)
        self.s.M = clamp(self.s.M + dM)
        self.s.E = clamp(self.s.E + dE)

        # EMH trigger
        if self.s.M < self.p.eps * D:
            self.s.E = clamp(self.s.E + self.p.eta)

        return dict(
            H=self.s.H,
            M=self.s.M,
            E=self.s.E,
            S=self.s.S,
            D=D,
            RPE=delta_rpe,
            mode=self.s.mode,
        )
