# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict

import numpy as np

from ..core.params import EKFConfig, Params

log = logging.getLogger(__name__)


@dataclass
class EKFState:
    x: np.ndarray
    P: np.ndarray


class EMHEKF:
    """Extended Kalman Filter over x=[H, M, E, S]."""

    def __init__(self, p: Params, cfg: EKFConfig = EKFConfig(), init_x: np.ndarray | None = None):
        self.p = p
        self.cfg = cfg
        self.st = EKFState(
            x=(init_x if init_x is not None else np.array([0.5, 0.8, 0.1, 0.0], dtype=float)),
            P=np.eye(4, dtype=float) * 1e-2,
        )

    def _d_proxy(self, obs: Dict[str, float]) -> float:
        return float(
            np.clip(
                0.5 * obs.get("dd", 0.0) + 0.3 * obs.get("liq", 0.0) + 0.2 * obs.get("reg", 0.0),
                0.0,
                1.0,
            )
        )

    def f(self, x: np.ndarray, obs: Dict[str, float]) -> np.ndarray:
        H, M, E, _S = x.tolist()
        D = self._d_proxy(obs)
        reward = float(obs.get("reward", 0.0))
        S = np.clip(
            self.p.phi * D + self.p.omega * (1.0 - M / self.p.M0) + self.p.kappa * reward,
            0.0,
            1.0,
        )
        dH = self.p.alpha * S - self.p.beta * H + self.p.gamma * M
        dM = -self.p.delta * M + self.p.theta
        dE = self.p.lambd * (D - M) + self.p.mu * H * S
        Hn = np.clip(H + dH, 0.0, 1.0)
        Mn = np.clip(M + dM, 0.0, 1.0)
        En = np.clip(E + dE, 0.0, 1.0)
        return np.array([Hn, Mn, En, S], dtype=float)

    def h(self, x: np.ndarray, obs: Dict[str, float]) -> np.ndarray:
        Dp = self._d_proxy(obs)
        M_proxy = float(obs.get("m_proxy", x[1]))
        S_proxy = x[3]
        return np.array([Dp, M_proxy, S_proxy], dtype=float)

    def step(self, obs: Dict[str, float]) -> Dict[str, float]:
        F = np.eye(4, dtype=float)
        x_pred = self.f(self.st.x, obs)
        P_pred = F @ self.st.P @ F.T + self.cfg.q * np.eye(4, dtype=float)

        H_j = np.zeros((3, 4), dtype=float)
        H_j[1, 1] = 1.0
        H_j[2, 3] = 1.0

        y_pred = self.h(x_pred, obs)
        y_obs = self.h(x_pred, obs)
        y_obs[1] = float(obs.get("m_proxy", y_pred[1]))

        S_cov = H_j @ P_pred @ H_j.T + self.cfg.r * np.eye(3, dtype=float)
        K = P_pred @ H_j.T @ np.linalg.pinv(S_cov)
        innov = y_obs - y_pred

        x_upd = x_pred + K @ innov
        P_upd = (np.eye(4, dtype=float) - K @ H_j) @ P_pred

        self.st = EKFState(x=np.clip(x_upd, 0.0, 1.0), P=P_upd)

        H_e, M_e, E_e, S_e = self.st.x.tolist()
        return {"H": H_e, "M": M_e, "E": E_e, "S": S_e}
