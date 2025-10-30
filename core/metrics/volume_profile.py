# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import numpy as np


def cumulative_volume_delta(buys: np.ndarray, sells: np.ndarray) -> np.ndarray:
    return np.cumsum(np.asarray(buys) - np.asarray(sells))


def imbalance(buys: np.ndarray, sells: np.ndarray) -> float:
    b, s = float(np.sum(buys)), float(np.sum(sells))
    if b + s == 0:
        return 0.0
    return (b - s) / (b + s)


def order_aggression(buy_mkt: float, sell_mkt: float) -> float:
    tot = buy_mkt + sell_mkt
    return 0.0 if tot == 0 else (buy_mkt - sell_mkt) / tot
