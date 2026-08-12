# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import numpy as np


class HomeostaticModule:
    """Sigmoid pressure when metabolic reserve M drops below target."""

    def __init__(self, M_target: float = 0.8, k_sigmoid: float = 5.0):
        self.M_target = float(M_target)
        self.k = float(k_sigmoid)

    def pressure(self, M_current: float) -> float:
        deficit = max(0.0, self.M_target - float(M_current))
        return float(1.0 / (1.0 + np.exp(-self.k * deficit)))
