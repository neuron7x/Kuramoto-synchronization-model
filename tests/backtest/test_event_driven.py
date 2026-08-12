# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for backtest.event_driven module."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from backtest.event_driven import (
    ArrayDataHandler,
    MarketDataHandler,
    Portfolio,
    Strategy,
    VectorisedStrategy,
)
from backtest.events import MarketEvent

# ---------------------------------------------------------------------------
# ArrayDataHandler
# ---------------------------------------------------------------------------


class TestArrayDataHandler:
    def test_empty_prices(self):
        handler = ArrayDataHandler(prices=[])
        chunks = list(handler.stream())
        assert chunks == []

    def test_single_chunk(self):
        handler = ArrayDataHandler(prices=[100.0, 101.0, 102.0], symbol="BTC")
        chunks = list(handler.stream())
        assert len(chunks) == 1
        events = chunks[0]
        assert len(events) == 3
        assert events[0].symbol == "BTC"
        assert events[0].price == 100.0

    def test_multiple_chunks(self):
        handler = ArrayDataHandler(prices=list(range(10)), chunk_size=3)
        chunks = list(handler.stream())
        assert len(chunks) == 4  # 3+3+3+1

    def test_chunk_size_equals_total(self):
        handler = ArrayDataHandler(prices=[1.0, 2.0, 3.0], chunk_size=3)
        chunks = list(handler.stream())
        assert len(chunks) == 1

    def test_step_continuity(self):
        handler = ArrayDataHandler(prices=[10.0, 20.0, 30.0, 40.0], chunk_size=2)
        all_events = []
        for chunk in handler.stream():
            all_events.extend(chunk)
        steps = [e.step for e in all_events]
        assert steps == [0, 1, 2, 3]

    def test_negative_chunk_size(self):
        handler = ArrayDataHandler(prices=[1.0, 2.0], chunk_size=-1)
        chunks = list(handler.stream())
        assert len(chunks) == 1

    def test_zero_chunk_size(self):
        handler = ArrayDataHandler(prices=[1.0, 2.0], chunk_size=0)
        chunks = list(handler.stream())
        assert len(chunks) == 1


# ---------------------------------------------------------------------------
# MarketDataHandler
# ---------------------------------------------------------------------------


class TestMarketDataHandler:
    def test_stream_not_implemented(self):
        handler = MarketDataHandler()
        with pytest.raises(NotImplementedError):
            list(handler.stream())


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------


class TestStrategy:
    def test_base_not_implemented(self):
        s = Strategy()
        event = MagicMock(spec=MarketEvent)
        with pytest.raises(NotImplementedError):
            s.on_market_event(event)


# ---------------------------------------------------------------------------
# VectorisedStrategy
# ---------------------------------------------------------------------------


class TestVectorisedStrategy:
    def test_emits_signals(self):
        signals = np.array([0.0, 0.5, -0.5, 1.0, 0.0])
        strat = VectorisedStrategy(signals, symbol="ETH")
        event = MagicMock(spec=MarketEvent, step=0, symbol="ETH")
        result = list(strat.on_market_event(event))
        assert len(result) == 1
        assert result[0].target_position == 0.5

    def test_no_signal_at_boundary(self):
        signals = np.array([0.0, 1.0])
        strat = VectorisedStrategy(signals)
        event = MagicMock(spec=MarketEvent, step=1)
        result = list(strat.on_market_event(event))
        assert result == []

    def test_from_signal_function(self):
        prices = np.array([100.0, 101.0, 99.0, 105.0])

        def fn(p):
            return np.where(np.diff(p, prepend=p[0]) > 0, 1.0, -1.0)

        strat = VectorisedStrategy.from_signal_function(prices, fn)
        assert strat._signals.shape == prices.shape

    def test_from_signal_function_shape_mismatch(self):
        prices = np.array([100.0, 101.0, 99.0])

        def fn(p):
            return np.array([1.0, 2.0])

        with pytest.raises(ValueError, match="same length"):
            VectorisedStrategy.from_signal_function(prices, fn)

    def test_signals_clipped(self):
        prices = np.array([1.0, 2.0, 3.0])

        def fn(p):
            return np.array([5.0, -5.0, 0.0])

        strat = VectorisedStrategy.from_signal_function(prices, fn)
        assert np.all(strat._signals <= 1.0)
        assert np.all(strat._signals >= -1.0)


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------


class TestPortfolio:
    def test_initial_state(self):
        p = Portfolio(symbol="BTC", initial_capital=10000.0, fee_per_unit=0.1)
        assert p.cash == 10000.0
        assert p.position == 0.0
        assert p.trades == 0
        assert p.equity_curve == []

    def test_on_market_event_tracks_equity(self):
        p = Portfolio(symbol="BTC", initial_capital=10000.0, fee_per_unit=0.1)
        e1 = MarketEvent(symbol="BTC", price=100.0, step=0)
        p.on_market_event(e1)
        assert len(p.equity_curve) == 1
        assert p.equity_curve[0] == 10000.0

    def test_position_pnl_updates(self):
        p = Portfolio(symbol="BTC", initial_capital=10000.0, fee_per_unit=0.0)
        p.position = 10.0
        e1 = MarketEvent(symbol="BTC", price=100.0, step=0)
        p.on_market_event(e1)
        e2 = MarketEvent(symbol="BTC", price=110.0, step=1)
        p.on_market_event(e2)
        # Position 10 * delta 10 = +100
        assert p.cash == pytest.approx(10100.0)

    def test_position_history_tracked(self):
        p = Portfolio(symbol="BTC", initial_capital=5000.0, fee_per_unit=0.0)
        e = MarketEvent(symbol="BTC", price=50.0, step=0)
        p.on_market_event(e)
        assert len(p.position_history) == 1

    @pytest.mark.parametrize("capital", [0.0, 1000.0, 1e6])
    def test_various_capitals(self, capital):
        p = Portfolio(symbol="X", initial_capital=capital, fee_per_unit=0.0)
        assert p.cash == capital
