# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import numpy as np

from core.neuro.amm import AdaptiveMarketMind, AMMConfig
from core.neuro.calibration import CalibConfig, calibrate_random


def _toy_series(n=2000, seed=0):
    rng = np.random.default_rng(seed)
    x = rng.normal(0, 0.002, n).astype(np.float32)
    x[1000:] += rng.normal(0, 0.01, n - 1000).astype(np.float32)
    R = np.full(n, 0.55, dtype=np.float32)
    R[1000:] = 0.7
    kappa = np.full(n, 0.1, dtype=np.float32)
    kappa[1000:] = -0.1
    return x, R, kappa


def _score(x, R, k, cfg: AMMConfig) -> float:
    amm = AdaptiveMarketMind(cfg)
    vals = []
    for i in range(len(x)):
        o = amm.update(float(x[i]), float(R[i]), float(k[i]), None)
        vals.append(o["amm_pulse"])
    return float(np.mean(vals[-500:]))


def test_calibration_smoke_improves_or_not_worse():
    x, R, k = _toy_series()
    base = AMMConfig()
    s0 = _score(x, R, k, base)
    best = calibrate_random(x, R, k, CalibConfig(iters=25, seed=3))
    s1 = _score(x, R, k, best)
    assert s1 >= s0 * 0.9
