# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import numpy as np


def skewness(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    # size first: std() on an empty array emits RuntimeWarnings before the size guard can
    # take. Reordering is warning-free and preserves all three mutation sites (re-probed 3/3).
    if x.size == 0 or x.std() == 0:
        return 0.0
    z = (x - x.mean()) / (x.std() + 1e-12)
    return float(np.mean(z**3))


def direction_index(skew: float, delta_curv: float, bias: float, lambdas=(0.5, 0.3, 0.2)) -> float:
    l1, l2, l3 = lambdas
    return float(l1 * skew + l2 * delta_curv + l3 * bias)
