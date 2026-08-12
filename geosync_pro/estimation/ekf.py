# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Extended Kalman Filter for the EMH latent state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np

from ..models.emh import EMHSSM


@dataclass
class EKFConfig:
    """Configuration for the EKF."""

    q: float = 1e-3  # process noise scalar
    r: float = 1e-2  # observation noise scalar


class EMHEKF:
    """Extended Kalman Filter on the EMH state (x=[H,M,E,S])."""

    def __init__(self, model: EMHSSM, cfg: EKFConfig | None = None) -> None:
        self.model = model
        self.cfg = cfg or EKFConfig()
        self.x = np.array([model.s.H, model.s.M, model.s.E, model.s.S], dtype=float)
        self.P = np.eye(4) * 1e-2

    def _D_proxy(self, obs: Dict[str, float]) -> float:
        return float(np.clip(0.5 * obs["dd"] + 0.3 * obs["liq"] + 0.2 * obs["reg"], 0.0, 1.0))

    def f(self, x: np.ndarray, obs: Dict[str, float]) -> np.ndarray:
        H, M, E, _ = x.tolist()
        D = self._D_proxy(obs)
        reward = float(obs.get("reward", 0.0))
        p = self.model.p
        S_next = float(np.clip(p.phi * D + p.omega * (1.0 - M / p.M0) + p.kappa * reward, 0.0, 1.0))
        dH = p.alpha * S_next - p.beta * H + p.gamma * M
        dM = -p.delta * M + p.theta
        dE = p.lambd * (D - M) + p.mu * H * S_next
        Hn = float(np.clip(H + dH, 0.0, 1.0))
        Mn = float(np.clip(M + dM, 0.0, 1.0))
        En = float(np.clip(E + dE, 0.0, 1.0))
        return np.array([Hn, Mn, En, S_next], dtype=float)

    def h(self, x: np.ndarray, obs: Dict[str, float]) -> np.ndarray:
        D_proxy = self._D_proxy(obs)
        M_proxy = float(obs.get("m_proxy", x[1]))
        S_proxy = x[3]
        return np.array([D_proxy, M_proxy, S_proxy], dtype=float)

    def step(self, obs: Dict[str, float]) -> Dict[str, float]:
        F = np.eye(4)
        x_pred = self.f(self.x, obs)
        P_pred = F @ self.P @ F.T + self.cfg.q * np.eye(4)

        H_jac = np.zeros((3, 4))
        H_jac[1, 1] = 1.0
        H_jac[2, 3] = 1.0

        y_pred = self.h(x_pred, obs)
        m_proxy_raw = obs.get("m_proxy")
        has_measurement = True

        if m_proxy_raw is None:
            has_measurement = False
        else:
            try:
                m_proxy_val = float(m_proxy_raw)
            except (TypeError, ValueError):
                has_measurement = False
            else:
                if np.isnan(m_proxy_val):
                    has_measurement = False

        if not has_measurement:
            x_upd = x_pred
            P_upd = P_pred
        else:
            y_obs = y_pred.copy()
            y_obs[1] = m_proxy_val

            S_cov = H_jac @ P_pred @ H_jac.T + self.cfg.r * np.eye(3)
            K = P_pred @ H_jac.T @ np.linalg.pinv(S_cov)
            innov = y_obs - y_pred

            x_upd = x_pred + K @ innov
            P_upd = (np.eye(4) - K @ H_jac) @ P_pred

        self.x = np.clip(x_upd, 0.0, 1.0)
        self.P = P_upd
        return dict(
            H=float(self.x[0]),
            M=float(self.x[1]),
            E=float(self.x[2]),
            S=float(self.x[3]),
        )
