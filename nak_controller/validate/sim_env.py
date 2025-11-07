"""Synthetic simulation environments used for validation and tests.

Copyright (c) 2024 TradePulse Technologies. All rights reserved.
Licensed under the TradePulse Proprietary License Agreement (TPLA).
"""

from __future__ import annotations

from typing import Iterator, TypedDict

import numpy as np


class RegimeObservation(TypedDict):
    regime: str
    ret: float
    global_vol: float
    portfolio_dd_proxy: float


def multi_regime_stream(steps: int, seed: int) -> Iterator[RegimeObservation]:
    rng = np.random.default_rng(seed)
    regime_len = 200
    regimes = ["normal", "volatile", "crash"]
    for t in range(steps):
        reg = regimes[(t // regime_len) % len(regimes)]
        if reg == "normal":
            drift, vol = 0.0004, 0.01
        elif reg == "volatile":
            drift, vol = 0.0006, 0.03
        else:  # crash
            drift, vol = -0.0012, 0.05
        ret = drift + vol * rng.standard_normal()
        yield {
            "regime": reg,
            "ret": ret,
            "global_vol": min(1.0, abs(vol * 30)),
            "portfolio_dd_proxy": 0.0,
        }
