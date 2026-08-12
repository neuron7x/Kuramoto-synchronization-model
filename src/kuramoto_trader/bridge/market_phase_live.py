"""Market → phase bridge using rolling Hilbert transform."""

from __future__ import annotations

from collections import deque

import numpy as np
import pandas as pd
from scipy.signal import hilbert


class MarketPhaseLive:
    def __init__(self, window: int = 256, fs: float = 1 / 3600):
        self.window = int(window)
        self.fs = float(fs)
        self._prices: deque[float] = deque(maxlen=self.window)
        self._ts: list[pd.Timestamp] = []
        self._phase_vals: list[float] = []

    def update(self, new_price: float, ts: pd.Timestamp) -> float | None:
        self._prices.append(float(new_price))
        self._ts.append(pd.Timestamp(ts))
        if len(self._prices) < self.window:
            self._phase_vals.append(np.nan)
            return None

        arr = np.asarray(self._prices, dtype=float)
        centered = arr - np.mean(arr)
        analytic = hilbert(centered)
        phase = float(np.angle(analytic[-1]))
        phase = float(np.clip(phase, -np.pi, np.pi))
        self._phase_vals.append(phase)
        return phase

    def phase_series(self) -> pd.Series:
        return pd.Series(self._phase_vals, index=pd.DatetimeIndex(self._ts), name="phase")
