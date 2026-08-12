# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from collections import deque
from typing import Deque, Tuple

import numpy as np

from geosync.core.neuro.numeric_config import STABILITY_EPSILON


class DesensitizationModule:
    """Maintains lambda/scale adaptation from energy-imbalance signals."""

    def __init__(
        self,
        lambda_init: float = 0.05,
        mu: float = 0.01,
        sigma_target: float = 0.18,
        reset_eps: float = 0.005,
        ei_window: int = 50,
    ) -> None:
        self.scale = 1.0
        self.lambda_ = float(lambda_init)
        self.mu = float(mu)
        self.sigma_target = float(sigma_target)
        self.reset_eps = float(reset_eps)
        self._ei_hist: Deque[float] = deque(maxlen=ei_window)

    def update(
        self,
        stim: float,
        ei_current: float,
        ht5: float = 0.0,
        bounds: tuple[float, float] = (0.02, 0.08),
    ) -> Tuple[float, float]:
        self._ei_hist.append(ei_current)
        sigma_ei = np.std(self._ei_hist) if len(self._ei_hist) > 10 else self.sigma_target
        if abs(ei_current - 1.0) > self.reset_eps:
            self.lambda_ = float(
                np.clip(self.lambda_ + self.mu * (ei_current - 1.0), bounds[0], bounds[1])
            )
        self.scale = float(self.sigma_target / max(STABILITY_EPSILON, sigma_ei))
        return self.scale, self.lambda_
