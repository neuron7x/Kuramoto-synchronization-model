"""Toy data stream for smoke testing the controller."""

from __future__ import annotations

import numpy as np


def toy_stream(steps: int = 500, seed: int = 42):
    rng = np.random.default_rng(seed)
    for t in range(steps):
        vol = np.clip(0.5 + 0.5 * np.sin(t / 30) + 0.2 * rng.standard_normal(), 0, 1)
        dd = np.clip(rng.beta(2, 5) * (0.5 + 0.5 * np.sin(t / 40)), 0, 1)
        liq = np.clip(1 - vol + 0.1 * rng.standard_normal(), 0, 1)
        reg = float(vol > 0.8) * 0.7 + 0.3
        reward = float(np.tanh(0.02 * (1 - vol) - 0.03 * (dd > 0.7)))
        var_breach = bool(vol > 0.9 or dd > 0.75)
        yield dict(dd=dd, vol=vol, liq=liq, reg=reg, reward=reward, var_breach=var_breach)
