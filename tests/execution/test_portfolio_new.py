# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for execution.portfolio module."""

from __future__ import annotations

import pytest

from execution.portfolio import PortfolioAccounting, PortfolioSnapshot


class TestPortfolioAccounting:
    def test_initial_state(self):
        p = PortfolioAccounting(initial_cash=10000.0)
        assert p.realized_pnl() == 0.0
        assert p.unrealized_pnl() == 0.0
        assert p.equity() == 10000.0
        assert p.gross_exposure() == 0.0
        assert p.net_exposure() == 0.0

    def test_default_initial_cash(self):
        p = PortfolioAccounting()
        assert p.equity() == 0.0

    def test_buy_reduces_cash(self):
        p = PortfolioAccounting(initial_cash=10000.0)
        p.apply_fill("BTCUSD", "buy", 1.0, 5000.0)
        # Cash reduced by 5000
        assert p.equity() == pytest.approx(10000.0, abs=0.1)  # equity unchanged at fill price

    def test_sell_increases_cash(self):
        p = PortfolioAccounting(initial_cash=10000.0)
        p.apply_fill("BTCUSD", "buy", 1.0, 5000.0)
        p.apply_fill("BTCUSD", "sell", 1.0, 6000.0)
        # Realized profit = 1000
        assert p.realized_pnl() > 0

    def test_fees_tracked(self):
        p = PortfolioAccounting(initial_cash=10000.0)
        p.apply_fill("BTCUSD", "buy", 1.0, 5000.0, fees=5.0)
        snap = p.snapshot()
        assert snap.fees_paid == 5.0

    def test_negative_fees_raises(self):
        p = PortfolioAccounting(initial_cash=10000.0)
        with pytest.raises(ValueError, match="fees"):
            p.apply_fill("BTC", "buy", 1.0, 5000.0, fees=-5.0)

    def test_zero_quantity_raises(self):
        p = PortfolioAccounting()
        with pytest.raises(ValueError, match="positive"):
            p.apply_fill("BTC", "buy", 0, 100)

    def test_zero_price_raises(self):
        p = PortfolioAccounting()
        with pytest.raises(ValueError, match="positive"):
            p.apply_fill("BTC", "buy", 1.0, 0)

    def test_mark_to_market_unknown_symbol(self):
        p = PortfolioAccounting()
        # Should not raise when symbol unknown
        p.mark_to_market("UNKNOWN", 100.0)

    def test_mark_to_market_zero_price_raises(self):
        p = PortfolioAccounting()
        p.apply_fill("BTC", "buy", 1.0, 5000.0)
        with pytest.raises(ValueError, match="positive"):
            p.mark_to_market("BTC", 0)

    def test_positions_returned_as_copy(self):
        p = PortfolioAccounting()
        p.apply_fill("BTC", "buy", 1.0, 5000.0)
        pos1 = p.positions()
        pos1.clear()
        pos2 = p.positions()
        assert len(pos2) == 1  # Internal state unaffected

    def test_snapshot_captures_all_fields(self):
        p = PortfolioAccounting(initial_cash=10000.0)
        p.apply_fill("BTC", "buy", 1.0, 5000.0, fees=5.0)
        p.mark_to_market("BTC", 5500.0)
        snap = p.snapshot()
        assert isinstance(snap, PortfolioSnapshot)
        assert snap.cash == pytest.approx(10000.0 - 5000.0 - 5.0)
        assert snap.fees_paid == 5.0
        assert "BTC" in snap.positions

    def test_gross_and_net_exposure(self):
        p = PortfolioAccounting(initial_cash=10000.0)
        p.apply_fill("BTC", "buy", 1.0, 5000.0)
        p.mark_to_market("BTC", 5000.0)
        assert p.gross_exposure() == pytest.approx(5000.0)
        assert p.net_exposure() == pytest.approx(5000.0)

    def test_multiple_symbols(self):
        p = PortfolioAccounting(initial_cash=20000.0)
        p.apply_fill("BTC", "buy", 1.0, 5000.0)
        p.apply_fill("ETH", "buy", 2.0, 2000.0)
        assert len(p.positions()) == 2
