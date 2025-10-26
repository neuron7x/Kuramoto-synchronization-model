"""Conformal quantile regression with exponential weighting."""

from __future__ import annotations

import numpy as np


class ConformalCQR:
    """Weighted CQR + dynamic alpha based on volatility."""

    def __init__(self, alpha: float = 0.1, decay: float = 0.005, window: int = 2000) -> None:
        self.alpha0 = alpha
        self.alpha = alpha
        self.decay = decay
        self.window = window
        self.qhat: float | None = None

    def _weights(self, n: int) -> np.ndarray:
        idx = np.arange(n)
        w = np.exp(-self.decay * (n - 1 - idx))
        w /= w.sum()
        return w

    def fit_calibrate(self, L_cal: np.ndarray, U_cal: np.ndarray, y_cal: np.ndarray):
        if len(y_cal) > self.window:
            L_cal = L_cal[-self.window :]
            U_cal = U_cal[-self.window :]
            y_cal = y_cal[-self.window :]
        s = np.maximum(L_cal - y_cal, y_cal - U_cal)
        n = len(s)
        if n == 0:
            self.qhat = 0.0
            return self
        w = self._weights(n)
        order = np.argsort(s)
        s_sorted = s[order]
        w_sorted = w[order]
        cdf = np.cumsum(w_sorted)
        q = 1.0 - self.alpha
        j = min(np.searchsorted(cdf, q, "left"), n - 1)
        self.qhat = float(s_sorted[j])
        return self

    def dynamic_alpha(
        self, rv: float, rv_ref: float, min_alpha: float = 0.02, max_alpha: float = 0.2
    ) -> float:
        if rv_ref <= 1e-9:
            self.alpha = self.alpha0
            return self.alpha
        ratio = rv / rv_ref
        adj = self.alpha0 / np.sqrt(max(1.0, ratio))
        self.alpha = float(np.clip(adj, min_alpha, max_alpha))
        return self.alpha

    def interval(self, L_pred: float, U_pred: float) -> tuple[float, float]:
        if self.qhat is None:
            return L_pred, U_pred
        # Масштабуємо q̂ на основі поточного рівня α: чим менше α, тим ширший інтервал.
        a = max(self.alpha, 1e-9)
        scale = max(1.0, np.sqrt(self.alpha0 / a))
        q = float(self.qhat * scale)
        return L_pred - q, U_pred + q
