# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Quantile regression ensemble for conditional intervals."""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor


class QuantileModels:
    def __init__(self, low_q: float = 0.2, high_q: float = 0.8, seed: int = 7) -> None:
        self.low = GradientBoostingRegressor(loss="quantile", alpha=low_q, random_state=seed)
        # Використовуємо 0.5-квантиль для медіани задля узгодженості з CQR
        self.med = GradientBoostingRegressor(loss="quantile", alpha=0.5, random_state=seed)
        self.high = GradientBoostingRegressor(loss="quantile", alpha=high_q, random_state=seed)
        self.cols: list[str] | None = None
        self.fitted = False

    def fit(self, X, y):
        self.cols = list(X.columns)
        self.low.fit(X, y)
        self.med.fit(X, y)
        self.high.fit(X, y)
        self.fitted = True
        return self

    def predict_all(self, x_row: dict[str, float]) -> tuple[float, float, float]:
        if not self.cols:
            raise ValueError("QuantileModels must be fitted before prediction.")
        x = np.array([x_row.get(c, 0.0) for c in self.cols]).reshape(1, -1)
        low = float(self.low.predict(x)[0])
        med = float(self.med.predict(x)[0])
        high = float(self.high.predict(x)[0])
        return low, med, high
