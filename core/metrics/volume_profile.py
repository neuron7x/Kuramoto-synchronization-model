# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Volume profile analysis and order flow metrics.

This module provides functions for analyzing volume distribution and order flow
dynamics, which are critical for understanding market microstructure:

- **Cumulative Volume Delta (CVD)**: Tracks the net volume pressure (buys - sells)
- **Volume Imbalance**: Measures the ratio of buying to selling pressure
- **Order Aggression**: Quantifies the aggressiveness of market orders
- **Volume Profile**: Price-volume distribution analysis

These metrics help identify areas of strong buying/selling interest, support/resistance
levels based on volume, and potential market turning points.

Example:
    >>> import numpy as np
    >>> from core.metrics.volume_profile import cumulative_volume_delta, imbalance
    >>> buys = np.array([100, 150, 200])
    >>> sells = np.array([80, 120, 180])
    >>> cvd = cumulative_volume_delta(buys, sells)
    >>> imb = imbalance(buys, sells)
"""

from __future__ import annotations

import numpy as np


def cumulative_volume_delta(buys: np.ndarray, sells: np.ndarray) -> np.ndarray:
    """Calculate cumulative volume delta (CVD) from buy and sell volumes.

    CVD tracks the net volume pressure over time by computing the running sum
    of (buy_volume - sell_volume). Positive CVD indicates buying pressure,
    negative indicates selling pressure.

    Args:
        buys: Array of buy volumes for each period.
        sells: Array of sell volumes for each period.

    Returns:
        Array of cumulative volume deltas.

    Raises:
        ValueError: If arrays have mismatched shapes.

    Example:
        >>> buys = np.array([100, 150, 200])
        >>> sells = np.array([80, 120, 180])
        >>> cvd = cumulative_volume_delta(buys, sells)
        >>> cvd
        array([ 20,  50,  70])
    """
    buys_arr = np.asarray(buys, dtype=float)
    sells_arr = np.asarray(sells, dtype=float)

    if buys_arr.shape != sells_arr.shape:
        raise ValueError(
            f"Buy and sell arrays must have the same shape: "
            f"buys {buys_arr.shape} vs sells {sells_arr.shape}"
        )

    return np.cumsum(buys_arr - sells_arr)


def imbalance(buys: np.ndarray, sells: np.ndarray) -> float:
    """Calculate volume imbalance ratio.

    Computes the normalized difference between total buy and sell volumes:
    imbalance = (total_buys - total_sells) / (total_buys + total_sells)

    Result ranges from -1 (all sells) to +1 (all buys).

    Args:
        buys: Array of buy volumes.
        sells: Array of sell volumes.

    Returns:
        Imbalance ratio in range [-1.0, 1.0]. Returns 0.0 if total volume is zero.

    Example:
        >>> buys = np.array([100, 150, 200])
        >>> sells = np.array([80, 120, 180])
        >>> imb = imbalance(buys, sells)
        >>> round(imb, 3)
        0.085
    """
    b = float(np.sum(np.asarray(buys, dtype=float)))
    s = float(np.sum(np.asarray(sells, dtype=float)))

    total = b + s
    if np.isclose(total, 0.0):
        return 0.0

    return (b - s) / total


def order_aggression(buy_mkt: float, sell_mkt: float) -> float:
    """Calculate order flow aggression score.

    Measures the aggressiveness of market orders by comparing buy-side and
    sell-side market order volumes. Aggressive buyers (market takers lifting
    offers) indicate bullish pressure; aggressive sellers indicate bearish pressure.

    Args:
        buy_mkt: Volume of market buy orders.
        sell_mkt: Volume of market sell orders.

    Returns:
        Aggression score in range [-1.0, 1.0]:
        - +1.0: All market buys (maximum bullish aggression)
        - 0.0: Balanced market orders
        - -1.0: All market sells (maximum bearish aggression)

    Example:
        >>> agg = order_aggression(buy_mkt=150.0, sell_mkt=100.0)
        >>> round(agg, 3)
        0.2
    """
    total = float(buy_mkt) + float(sell_mkt)

    if np.isclose(total, 0.0):
        return 0.0

    return (float(buy_mkt) - float(sell_mkt)) / total
