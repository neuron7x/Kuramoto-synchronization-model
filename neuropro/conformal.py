"""Conformal quantile regression with exponential weighting."""

from __future__ import annotations

from collections import deque
from typing import Iterable

import numpy as np


class ConformalCQR:
    """Weighted CQR + dynamic alpha; optional online updates without leakage."""

    def __init__(
        self,
        alpha: float = 0.1,
        decay: float = 0.005,
        window: int = 2000,
        online_window: int = 2000,
    ) -> None:
        self.alpha0 = alpha
        self.alpha = alpha
        self.decay = decay
        self.window = window
        self.qhat: float | None = None
        self._qhat_alpha: float = alpha
        self.online_window = int(online_window)
        self._resid: deque[float] = deque(maxlen=self.online_window)

    def _weights(self, n: int) -> np.ndarray:
        idx = np.arange(n)
        w = np.exp(-self.decay * (n - 1 - idx))
        w /= w.sum()
        return w

    def fit_calibrate(
        self, L_cal: Iterable[float], U_cal: Iterable[float], y_cal: Iterable[float]
    ):
        L_arr = np.asarray(L_cal, dtype=float)
        U_arr = np.asarray(U_cal, dtype=float)
        y_arr = np.asarray(y_cal, dtype=float)
        if len(y_arr) > self.window:
            L_arr = L_arr[-self.window :]
            U_arr = U_arr[-self.window :]
            y_arr = y_arr[-self.window :]
        s = np.maximum(L_arr - y_arr, y_arr - U_arr)
        n = len(s)
        if n == 0:
            self.qhat = 0.0
            return self
        w = self._weights(n)
        order = np.argsort(s)
        s_sorted = s[order]
        w_sorted = w[order]
        cdf = np.cumsum(w_sorted)
        q = 1.0 - self.alpha0
        j = min(np.searchsorted(cdf, q, "left"), n - 1)
        self.qhat = float(s_sorted[j])
        self._qhat_alpha = self.alpha0
        self._resid.clear()
        self._resid.extend(float(val) for val in s[max(0, n - self.online_window) :])
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

    def update_online(self, L_pred: float, U_pred: float, y_true: float):
        s = float(max(L_pred - y_true, y_true - U_pred))
        self._resid.append(s)
        if not self._resid:
            return self
        s_arr = np.asarray(self._resid)
        n = len(s_arr)
        w = self._weights(n)
        order = np.argsort(s_arr)
        s_sorted = s_arr[order]
        w_sorted = w[order]
        cdf = np.cumsum(w_sorted)
        q = 1.0 - self.alpha0
        j = min(np.searchsorted(cdf, q, "left"), n - 1)
        self.qhat = float(s_sorted[j])
        self._qhat_alpha = self.alpha0
        return self

    def interval(self, L_pred: float, U_pred: float) -> tuple[float, float]:
        if self.qhat is None:
            return L_pred, U_pred
        # Масштабуємо q̂ на основі поточного рівня α: чим менше α, тим ширший інтервал.
        alpha_eff = max(self.alpha, 1e-9)
        alpha_ref = max(self._qhat_alpha, 1e-9)
        scale = 1.0
        if alpha_eff < alpha_ref:
            scale = float(np.sqrt(alpha_ref / alpha_eff))
        q = float(self.qhat * scale)
        return L_pred - q, U_pred + q
