# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import time

import numpy as np

from core.neuro.amm import AdaptiveMarketMind, AMMConfig

n = 100000
rng = np.random.default_rng(0)
xs = rng.normal(0, 0.001, n).astype(np.float32)
R = np.clip(rng.normal(0.6, 0.05, n), 0, 1).astype(np.float32)
kappa = rng.normal(0.0, 0.1, n).astype(np.float32)

amm = AdaptiveMarketMind(AMMConfig())
t0 = time.perf_counter()
for i in range(n):
    amm.update(float(xs[i]), float(R[i]), float(kappa[i]), None)
dt = time.perf_counter() - t0
print(f"{n} steps in {dt:.4f}s, {n / dt:.0f} steps/s")
