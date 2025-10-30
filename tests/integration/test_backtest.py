# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import numpy as np
import pytest

from backtest.engine import (
    LatencyConfig,
    OrderBookConfig,
    SlippageConfig,
    walk_forward,
)


def trend_following_signal(prices: np.ndarray) -> np.ndarray:
    signal = np.zeros_like(prices)
    signal[1:] = np.sign(prices[1:] - prices[:-1])
    return signal


def test_walk_forward_trend_following_strategy() -> None:
    prices = np.array([100.0, 101.5, 101.0, 102.5, 103.0])
    result = walk_forward(prices, trend_following_signal, fee=0.0)
    expected_pnl = 4.0
    assert result.pnl == pytest.approx(expected_pnl, rel=1e-12)
    assert result.trades == 3
    assert result.max_dd <= 0


def test_walk_forward_with_latency_and_slippage() -> None:
    prices = np.array([100.0, 101.0, 101.5, 102.0, 103.0, 103.5])

    def long_signal(p: np.ndarray) -> np.ndarray:
        signal = np.ones_like(p)
        signal[0] = 0.0
        return signal

    baseline = walk_forward(prices, long_signal, fee=0.0)
    delayed = walk_forward(
        prices,
        long_signal,
        fee=0.0005,
        latency=LatencyConfig(
            signal_to_order=1, order_to_execution=1, execution_to_fill=1
        ),
        order_book=OrderBookConfig(spread_bps=5.0, depth_profile=(0.5, 0.5)),
        slippage=SlippageConfig(per_unit_bps=10.0, depth_impact_bps=5.0),
    )

    assert delayed.latency_steps == 3
    assert delayed.slippage_cost >= 0.0
    assert delayed.pnl <= baseline.pnl
    assert delayed.equity_curve is not None
