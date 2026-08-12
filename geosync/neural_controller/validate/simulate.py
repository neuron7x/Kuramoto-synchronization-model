# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from typing import Dict, Iterator

import numpy as np


def toy_stream(steps: int = 500, seed: int = 42) -> Iterator[Dict[str, float]]:
    rng = np.random.default_rng(seed)
    for t in range(steps):
        vol = float(np.clip(0.5 + 0.5 * np.sin(t / 30) + 0.2 * rng.standard_normal(), 0.0, 1.0))
        dd = float(np.clip(rng.beta(2, 5) * (0.5 + 0.5 * np.sin(t / 40)), 0.0, 1.0))
        liq = float(np.clip(1 - vol + 0.1 * rng.standard_normal(), 0.0, 1.0))
        reg = float(0.7 if vol > 0.8 else 0.3)
        reward = float(0.02 * (1 - vol) - 0.03 * (dd > 0.7))
        var_breach = bool(vol > 0.9 or dd > 0.75)
        yield dict(dd=dd, vol=vol, liq=liq, reg=reg, reward=reward, var_breach=var_breach)
