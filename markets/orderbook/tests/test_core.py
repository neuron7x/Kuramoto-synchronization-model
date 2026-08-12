# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.metrics import (  # noqa: E402  pylint: disable=wrong-import-position
    build_symbol_microstructure_report,
    hasbrouck_information_impulse,
    kyles_lambda,
    queue_imbalance,
)
from markets.orderbook.src import (  # noqa: E402  pylint: disable=wrong-import-position
    LinearImpactModel,
    Order,
    PerUnitBpsSlippage,
    PriceTimeOrderBook,
    QueueAwareSlippage,
    Side,
)


def test_price_time_priority() -> None:
    book = PriceTimeOrderBook()
    book.add_limit_order(Order("o1", Side.SELL, 101.0, 2.0, 0))
    book.add_limit_order(Order("o2", Side.SELL, 101.0, 3.0, 1))
    book.add_limit_order(Order("o3", Side.SELL, 102.0, 5.0, 2))

    trades = book.match_market_order(Side.BUY, 4.0)
    assert [trade.order_id for trade in trades] == ["o1", "o2"]
    assert pytest.approx(sum(t.quantity for t in trades)) == 4.0


def test_queue_depth_levels() -> None:
    book = PriceTimeOrderBook()
    book.add_limit_order(Order("b1", Side.BUY, 99.0, 1.0, 0))
    book.add_limit_order(Order("b2", Side.BUY, 98.5, 2.0, 1))
    book.add_limit_order(Order("b3", Side.BUY, 99.0, 2.5, 2))

    depth = book.depth(Side.BUY)
    assert depth == [(99.0, 3.5), (98.5, 2.0)]


def test_impact_and_slippage_are_applied() -> None:
    impact = LinearImpactModel(0.01)
    slippage = [PerUnitBpsSlippage(10.0), QueueAwareSlippage(5.0)]
    book = PriceTimeOrderBook(impact_model=impact, slippage_modules=slippage)
    book.add_limit_order(Order("s1", Side.SELL, 100.0, 1.5, 0))

    trades = book.match_market_order(Side.BUY, 1.0)
    assert len(trades) == 1
    trade = trades[0]
    assert trade.impacted_price == pytest.approx(100.0 * (1 + 0.01 * 1.0))
    assert trade.slippage > 0.0


def test_queue_imbalance_metric() -> None:
    qi = queue_imbalance([10, 5], [7, 3])
    assert qi == pytest.approx((15 - 10) / 25)


def test_kyles_lambda_regression() -> None:
    returns = np.array([0.01, -0.02, 0.015])
    signed_volume = np.array([100, -120, 110])
    lam = kyles_lambda(returns, signed_volume)
    assert lam != 0.0


def test_hasbrouck_impulse_uses_signed_sqrt_volume() -> None:
    returns = np.array([0.01, -0.02, 0.015, -0.01])
    signed_volume = np.array([100, -120, 110, -90])
    impulse = hasbrouck_information_impulse(returns, signed_volume)
    assert impulse != 0.0


def test_symbol_microstructure_report() -> None:
    data = pd.DataFrame(
        {
            "symbol": ["BTC", "BTC", "ETH", "ETH"],
            "bid_volume": [10, 12, 5, 7],
            "ask_volume": [8, 11, 6, 4],
            "returns": [0.01, -0.015, 0.02, -0.01],
            "signed_volume": [100, -120, 80, -60],
        }
    )

    report = build_symbol_microstructure_report(data)
    assert set(report["symbol"]) == {"BTC", "ETH"}
    assert (report["samples"] == [2, 2]).all()
