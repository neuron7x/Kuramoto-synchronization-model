"""Adaptive threshold controller using PID control with anti-windup."""

from dataclasses import dataclass

import numpy as np


@dataclass
class PIDTau:
    """PID controller for adaptive tau threshold with anti-windup."""

    target: float = 0.15
    Kp: float = 0.1
    Ki: float = 0.01
    Kd: float = 0.05
    min_tau: float = 0.5
    max_tau: float = 10.0
    _e_prev: float = 0.0
    _I: float = 0.0

    def update(self, current_ratio: float, tau: float) -> float:
        """
        Update tau based on current forbidden zone ratio.

        Parameters
        ----------
        current_ratio : float
            Current ratio of points in forbidden zone
        tau : float
            Current threshold value

        Returns
        -------
        float
            Updated tau value
        """
        # Error
        e = self.target - float(current_ratio)
        # Anti-windup: clamp integrator
        self._I = float(np.clip(self._I + e, -10.0, 10.0))
        D = e - self._e_prev
        self._e_prev = e
        delta = self.Kp * e + self.Ki * self._I + self.Kd * D
        new_tau = float(np.clip(tau + delta, self.min_tau, self.max_tau))
        return new_tau
