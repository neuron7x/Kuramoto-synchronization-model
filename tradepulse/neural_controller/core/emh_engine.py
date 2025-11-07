"""EMH-inspired bounded state-space dynamics for the neural controller."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp *value* to the inclusive interval [lo, hi]."""

    return lo if value < lo else hi if value > hi else value


@dataclass
class Params:
    """Model coefficients for the EMH state-space model."""

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

    def __post_init__(self) -> None:
        for field in (
            "alpha",
            "beta",
            "gamma",
            "delta",
            "theta",
            "lambd",
            "mu",
            "phi",
            "omega",
            "kappa",
            "psi",
            "eps",
            "eta",
            "M0",
        ):
            setattr(self, field, float(getattr(self, field)))


@dataclass
class State:
    """Mutable EMH state tracked by :class:`EMHSSM`."""

    H: float = 0.5
    M: float = 0.8
    E: float = 0.1
    S: float = 0.0
    V: float = 0.0
    mode: str = "GREEN"

    def __post_init__(self) -> None:
        self.H = float(self.H)
        self.M = float(self.M)
        self.E = float(self.E)
        self.S = float(self.S)
        self.V = float(self.V)


def demand(
    dd: float,
    liq: float,
    reg: float,
    psi: float,
    w_dd: float = 0.5,
    w_liq: float = 0.3,
    w_reg: float = 0.2,
) -> float:
    """Proxy for demand pressure with bounded weights."""

    return clamp(psi * (w_dd * clamp(dd) + w_liq * clamp(liq) + w_reg * clamp(reg)))


def threat_mode(dd: float, var_breach: bool, vol: float) -> str:
    """Return the threat regime based on drawdown, VaR and volatility."""

    if var_breach or dd > 0.7 or vol > 0.9:
        return "RED"
    if dd > 0.4 or vol > 0.7:
        return "AMBER"
    return "GREEN"


class EMHSSM:
    """EMH-inspired bounded SSM with dopamine-style reward prediction error."""

    def __init__(self, params: Params, state: State | None = None):
        self.p = params
        self.s = state or State()

    @staticmethod
    def f(x: np.ndarray, obs: Dict[str, float], params: Params) -> np.ndarray:
        """Pure dynamics step used by the EKF prediction."""

        H, M, E, S = x.tolist()
        dd, liq, reg, vol = [float(obs.get(k, 0.0)) for k in ("dd", "liq", "reg", "vol")]
        D = demand(dd, liq, reg, params.psi)
        reward = float(obs.get("reward", 0.0))
        V = float(obs.get("V", 0.0))
        gamma_rl = 0.9
        delta = reward + gamma_rl * V - V
        S_next = clamp(params.phi * D + params.omega * (1.0 - M / params.M0) + params.kappa * delta)
        dH = params.alpha * S_next - params.beta * H + params.gamma * M
        dM = -params.delta * M + params.theta
        dE = params.lambd * (D - M) + params.mu * H * S_next
        Hn = clamp(H + dH)
        Mn = clamp(M + dM)
        En = clamp(E + dE)
        return np.array([Hn, Mn, En, S_next], float)

    def step(self, obs: Dict[str, float]) -> Dict[str, float]:
        """Update the EMH state with observed market data."""

        dd, liq, reg, vol = [clamp(float(obs.get(k, 0.0))) for k in ("dd", "liq", "reg", "vol")]
        var_breach = bool(obs.get("var_breach", False))
        reward = float(obs.get("reward", 0.0))

        self.s.mode = threat_mode(dd, var_breach, vol)
        D = demand(dd, liq, reg, self.p.psi)

        gamma_rl = 0.9
        delta_rpe = reward + gamma_rl * self.s.V - self.s.V
        self.s.V += 0.1 * delta_rpe

        self.s.S = clamp(
            self.p.phi * D + self.p.omega * (1.0 - self.s.M / self.p.M0) + self.p.kappa * delta_rpe
        )

        dH = self.p.alpha * self.s.S - self.p.beta * self.s.H + self.p.gamma * self.s.M
        dM = -self.p.delta * self.s.M + self.p.theta
        dE = self.p.lambd * (D - self.s.M) + self.p.mu * self.s.H * self.s.S

        self.s.H = clamp(self.s.H + dH)
        self.s.M = clamp(self.s.M + dM)
        self.s.E = clamp(self.s.E + dE)

        if self.s.M < self.p.eps * D:
            self.s.E = clamp(self.s.E + self.p.eta)

        return {
            "H": self.s.H,
            "M": self.s.M,
            "E": self.s.E,
            "S": self.s.S,
            "D": D,
            "RPE": delta_rpe,
            "mode": self.s.mode,
        }
