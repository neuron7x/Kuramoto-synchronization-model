"""Side-effect-free EKF for the EMH controller."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np

from ..core.emh_engine import EMHSSM, Params


@dataclass
class EKFConfig:
    """Process and observation noise parameters for the EKF."""

    q: float = 1e-3
    r: float = 1e-2

    def __post_init__(self) -> None:
        self.q = float(self.q)
        self.r = float(self.r)


class EMHEKF:
    """Extended Kalman Filter over ``x = [H, M, E, S]``."""

    def __init__(self, params: Params, cfg: EKFConfig = EKFConfig(), x0: list[float] | None = None):
        self.p = params
        self.cfg = cfg
        self.x = np.array(x0 if x0 is not None else [0.5, 0.8, 0.1, 0.0], float)
        self.P = np.eye(4) * 1e-2

    def _d_proxy(self, obs: Dict[str, float]) -> float:
        dd, liq, reg = [float(obs.get(k, 0.0)) for k in ("dd", "liq", "reg")]
        return max(0.0, min(1.0, 0.5 * dd + 0.3 * liq + 0.2 * reg))

    def f(self, x: np.ndarray, obs: Dict[str, float]) -> np.ndarray:
        return EMHSSM.f(x, {**obs, "V": 0.0}, self.p)

    def h(self, x: np.ndarray, obs: Dict[str, float]) -> np.ndarray:
        return np.array([self._d_proxy(obs), float(obs.get("m_proxy", x[1])), x[3]], float)

    def step(self, obs: Dict[str, float]) -> Dict[str, float]:
        F = np.eye(4)
        x_pred = self.f(self.x, obs)
        P_pred = F @ self.P @ F.T + self.cfg.q * np.eye(4)

        H = np.zeros((3, 4))
        H[1, 1] = 1.0
        H[2, 3] = 1.0
        y_pred = self.h(x_pred, obs)
        y_obs = y_pred.copy()
        y_obs[1] = float(obs.get("m_proxy", y_pred[1]))

        S = H @ P_pred @ H.T + self.cfg.r * np.eye(3)
        K = P_pred @ H.T @ np.linalg.pinv(S)
        innov = y_obs - y_pred

        self.x = np.clip(x_pred + K @ innov, 0.0, 1.0)
        self.P = (np.eye(4) - K @ H) @ P_pred
        return {"H": self.x[0], "M": self.x[1], "E": self.x[2], "S": self.x[3]}
