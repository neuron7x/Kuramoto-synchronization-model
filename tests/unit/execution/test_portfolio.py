# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for execution.portfolio — target uncovered lines."""

from __future__ import annotations

import pytest

from domain import OrderSide
from execution.portfolio import PortfolioAccounting, PortfolioSnapshot


class TestPortfolioAccounting:
    def test_initial_state(self):
        pa = PortfolioAccounting(initial_cash=10000.0)
        assert pa.equity() == 10000.0
        assert pa.realized_pnl() == 0.0
        assert pa.unrealized_pnl() == 0.0
        assert pa.gross_exposure() == 0.0
        assert pa.net_exposure() == 0.0
        assert pa.positions() == {}

    def test_apply_fill_buy(self):
        pa = PortfolioAccounting(initial_cash=10000.0)
        pa.apply_fill("BTC", OrderSide.BUY, 1.0, 100.0)
        assert pa.positions()["BTC"].quantity == 1.0
        assert pa.equity() == 10000.0  # cash - 100 + position 100

    def test_apply_fill_sell(self):
        pa = PortfolioAccounting(initial_cash=10000.0)
        pa.apply_fill("BTC", OrderSide.BUY, 1.0, 100.0)
        pa.apply_fill("BTC", OrderSide.SELL, 1.0, 120.0)
        assert pa.positions()["BTC"].quantity == 0.0
        assert pa.realized_pnl() == 20.0

    def test_apply_fill_with_fees(self):
        pa = PortfolioAccounting(initial_cash=10000.0)
        pa.apply_fill("BTC", OrderSide.BUY, 1.0, 100.0, fees=5.0)
        assert pa.equity() == 10000.0 - 5.0

    def test_apply_fill_negative_fees_raises(self):
        pa = PortfolioAccounting(initial_cash=10000.0)
        with pytest.raises(ValueError, match="fees"):
            pa.apply_fill("BTC", OrderSide.BUY, 1.0, 100.0, fees=-1.0)

    def test_apply_fill_zero_quantity_raises(self):
        pa = PortfolioAccounting(initial_cash=10000.0)
        with pytest.raises(ValueError, match="quantity and price"):
            pa.apply_fill("BTC", OrderSide.BUY, 0.0, 100.0)

    def test_apply_fill_zero_price_raises(self):
        pa = PortfolioAccounting(initial_cash=10000.0)
        with pytest.raises(ValueError, match="quantity and price"):
            pa.apply_fill("BTC", OrderSide.BUY, 1.0, 0.0)

    def test_apply_fill_string_side(self):
        pa = PortfolioAccounting(initial_cash=10000.0)
        pa.apply_fill("BTC", "buy", 1.0, 100.0)
        assert pa.positions()["BTC"].quantity == 1.0

    def test_mark_to_market(self):
        pa = PortfolioAccounting(initial_cash=10000.0)
        pa.apply_fill("BTC", OrderSide.BUY, 1.0, 100.0)
        pa.mark_to_market("BTC", 150.0)
        assert pa.unrealized_pnl() == 50.0

    def test_mark_to_market_zero_price_raises(self):
        pa = PortfolioAccounting(initial_cash=10000.0)
        pa.apply_fill("BTC", OrderSide.BUY, 1.0, 100.0)
        with pytest.raises(ValueError, match="price must be positive"):
            pa.mark_to_market("BTC", 0.0)

    def test_mark_to_market_unknown_symbol_noop(self):
        pa = PortfolioAccounting(initial_cash=10000.0)
        pa.mark_to_market("XYZ", 100.0)  # no position, should be noop

    def test_gross_and_net_exposure(self):
        pa = PortfolioAccounting(initial_cash=50000.0)
        pa.apply_fill("BTC", OrderSide.BUY, 2.0, 100.0)
        pa.apply_fill("ETH", OrderSide.SELL, 3.0, 50.0)
        pa.mark_to_market("BTC", 100.0)
        pa.mark_to_market("ETH", 50.0)
        assert pa.gross_exposure() == 2 * 100 + 3 * 50  # 350
        assert pa.net_exposure() == 2 * 100 + (-3) * 50  # 50

    def test_snapshot(self):
        pa = PortfolioAccounting(initial_cash=10000.0)
        pa.apply_fill("BTC", OrderSide.BUY, 1.0, 100.0, fees=2.0)
        pa.mark_to_market("BTC", 110.0)
        snap = pa.snapshot()
        assert isinstance(snap, PortfolioSnapshot)
        assert snap.fees_paid == 2.0
        assert snap.cash == 10000.0 - 100.0 - 2.0
        assert "BTC" in snap.positions

    def test_multiple_fills_same_symbol(self):
        pa = PortfolioAccounting(initial_cash=50000.0)
        pa.apply_fill("BTC", OrderSide.BUY, 1.0, 100.0)
        pa.apply_fill("BTC", OrderSide.BUY, 1.0, 120.0)
        assert pa.positions()["BTC"].quantity == 2.0

    def test_partial_close(self):
        pa = PortfolioAccounting(initial_cash=50000.0)
        pa.apply_fill("BTC", OrderSide.BUY, 2.0, 100.0)
        pa.apply_fill("BTC", OrderSide.SELL, 1.0, 150.0)
        assert pa.positions()["BTC"].quantity == 1.0
        assert pa.realized_pnl() == 50.0

    def test_short_position(self):
        pa = PortfolioAccounting(initial_cash=50000.0)
        pa.apply_fill("BTC", OrderSide.SELL, 1.0, 100.0)
        assert pa.positions()["BTC"].quantity == -1.0

    def test_equity_includes_market_value(self):
        pa = PortfolioAccounting(initial_cash=10000.0)
        pa.apply_fill("BTC", OrderSide.BUY, 1.0, 100.0)
        pa.mark_to_market("BTC", 200.0)
        # cash = 9900, market_value = 200
        assert pa.equity() == 9900.0 + 200.0
