# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the event-driven backtest engine."""

from __future__ import annotations

import math
from datetime import datetime, time
from pathlib import Path

import numpy as np
import pandas as pd

from backtest.engine import (
    LatencyConfig,
    OrderBookConfig,
    SlippageConfig,
    WalkForwardEngine,
)
from backtest.event_driven import (
    CSVChunkDataHandler,
    EventDrivenBacktestEngine,
    Portfolio,
    SimulatedExecutionHandler,
    Strategy,
)
from backtest.events import FillEvent, MarketEvent, OrderEvent, SignalEvent
from backtest.market_calendar import MarketCalendar, SessionHours
from backtest.transaction_costs import (
    BorrowFinancing,
    CompositeTransactionCostModel,
    FixedSlippage,
    FixedSpread,
    PerUnitCommission,
    SquareRootSlippage,
    VolumeProportionalSlippage,
)


def _signal_function(prices: np.ndarray) -> np.ndarray:
    if prices.size == 0:
        return np.array([], dtype=float)
    diffs = np.diff(prices, prepend=prices[0])
    signals = np.where(diffs > 0, 1.0, -1.0)
    signals[0] = 0.0
    return signals


def test_event_engine_matches_walk_forward() -> None:
    prices = np.array([100.0, 101.0, 100.5, 102.0, 101.5, 103.0])
    vector_engine = WalkForwardEngine()
    expected = vector_engine.run(
        prices,
        _signal_function,
        fee=0.0,
        initial_capital=1_000.0,
    )

    engine = EventDrivenBacktestEngine()
    result = engine.run(
        prices,
        _signal_function,
        fee=0.0,
        initial_capital=1_000.0,
        chunk_size=2,
    )

    overlap = min(result.equity_curve.size, expected.equity_curve.size)
    assert np.allclose(result.equity_curve[-overlap:], expected.equity_curve[-overlap:])
    assert np.isclose(result.equity_curve[-1], expected.equity_curve[-1])
    assert result.trades == expected.trades
    assert result.latency_steps == expected.latency_steps
    assert np.isclose(result.pnl, expected.pnl)
    assert np.isclose(result.slippage_cost, expected.slippage_cost)
    assert np.isclose(result.commission_cost, expected.commission_cost)
    assert np.isclose(result.spread_cost, expected.spread_cost)
    assert np.isclose(result.financing_cost, expected.financing_cost)


def test_event_engine_with_latency_matches_walk_forward() -> None:
    prices = np.linspace(100, 110, num=8)
    latency = LatencyConfig(signal_to_order=1, order_to_execution=1, execution_to_fill=1)

    vector_engine = WalkForwardEngine()
    expected = vector_engine.run(
        prices,
        _signal_function,
        fee=0.0,
        initial_capital=500.0,
        latency=latency,
    )

    engine = EventDrivenBacktestEngine()
    result = engine.run(
        prices,
        _signal_function,
        fee=0.0,
        initial_capital=500.0,
        latency=latency,
        chunk_size=3,
    )

    overlap = min(result.equity_curve.size, expected.equity_curve.size)
    assert np.allclose(result.equity_curve[-overlap:], expected.equity_curve[-overlap:])
    assert np.isclose(result.equity_curve[-1], expected.equity_curve[-1])
    assert result.trades == expected.trades
    assert result.latency_steps == expected.latency_steps == latency.total_delay
    assert np.isclose(result.pnl, expected.pnl)
    assert np.isclose(result.slippage_cost, expected.slippage_cost)
    assert np.isclose(result.commission_cost, expected.commission_cost)
    assert np.isclose(result.spread_cost, expected.spread_cost)
    assert np.isclose(result.financing_cost, expected.financing_cost)


def test_csv_chunk_data_handler(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range(datetime(2023, 1, 1), periods=5, freq="1min"),
            "close": np.linspace(100, 104, num=5),
        }
    )
    csv_path = tmp_path / "prices.csv"
    frame.to_csv(csv_path, index=False)

    handler = CSVChunkDataHandler(
        path=str(csv_path),
        price_column="close",
        symbol="TEST",
        chunk_size=2,
        parse_dates=True,
        date_column="timestamp",
    )

    steps: list[int] = []
    timestamps: list[datetime] = []
    total_events = 0
    for chunk in handler.stream():
        total_events += len(chunk)
        steps.extend(event.step for event in chunk)
        timestamps.extend(event.timestamp for event in chunk if event.timestamp is not None)
        assert all(event.symbol == "TEST" for event in chunk)

    assert total_events == len(frame)
    assert steps == list(range(len(frame)))
    assert len(timestamps) == len(frame)


def test_simulated_execution_partial_fill() -> None:
    handler = SimulatedExecutionHandler(
        OrderBookConfig(spread_bps=0.0, depth_profile=(0.5,), infinite_depth=False),
        SlippageConfig(),
        fee_per_unit=0.0,
    )
    handler.on_market_event(MarketEvent(symbol="TEST", price=100.0, step=0))
    fill = handler.execute(OrderEvent(symbol="TEST", quantity=1.0, step=0), current_step=0)
    assert math.isclose(fill.quantity, 0.5)
    assert math.isclose(fill.slippage, 0.0)
    assert math.isclose(fill.spread_cost, 0.0)


def test_simulated_execution_applies_fixed_slippage_model() -> None:
    cost_model = CompositeTransactionCostModel(slippage_model=FixedSlippage(0.05))
    handler = SimulatedExecutionHandler(
        OrderBookConfig(spread_bps=0.0, depth_profile=(10.0,), infinite_depth=True),
        SlippageConfig(),
        fee_per_unit=0.0,
        transaction_cost_model=cost_model,
    )
    handler.on_market_event(MarketEvent(symbol="TEST", price=100.0, step=0))
    fill = handler.execute(OrderEvent(symbol="TEST", quantity=1.0, step=0), current_step=0)
    assert math.isclose(fill.price, 100.05)
    assert math.isclose(fill.slippage, 0.05)


def test_simulated_execution_applies_volume_slippage_model() -> None:
    cost_model = CompositeTransactionCostModel(slippage_model=VolumeProportionalSlippage(0.02))
    handler = SimulatedExecutionHandler(
        OrderBookConfig(spread_bps=0.0, depth_profile=(10.0,), infinite_depth=True),
        SlippageConfig(),
        fee_per_unit=0.0,
        transaction_cost_model=cost_model,
    )
    handler.on_market_event(MarketEvent(symbol="TEST", price=100.0, step=0))
    fill = handler.execute(OrderEvent(symbol="TEST", quantity=2.0, step=0), current_step=0)
    assert math.isclose(fill.price, 100.04)
    assert math.isclose(fill.slippage, 0.08)


def test_simulated_execution_applies_square_root_slippage_model() -> None:
    cost_model = CompositeTransactionCostModel(slippage_model=SquareRootSlippage(a=0.001, b=0.01))
    handler = SimulatedExecutionHandler(
        OrderBookConfig(spread_bps=0.0, depth_profile=(10.0,), infinite_depth=True),
        SlippageConfig(),
        fee_per_unit=0.0,
        transaction_cost_model=cost_model,
    )
    handler.on_market_event(MarketEvent(symbol="TEST", price=100.0, step=0))
    fill = handler.execute(OrderEvent(symbol="TEST", quantity=4.0, step=0), current_step=0)
    expected_adjustment = 100.0 * (0.001 + 0.01 * math.sqrt(4.0))
    assert math.isclose(fill.price, 100.0 + expected_adjustment)
    assert math.isclose(fill.slippage, expected_adjustment * 4.0)


class _BuyOnceStrategy(Strategy):
    def __init__(self) -> None:
        self._emitted = False

    def on_market_event(self, event: MarketEvent):
        if not self._emitted:
            self._emitted = True
            return (SignalEvent(symbol=event.symbol, target_position=1.0, step=event.step),)
        return ()


def test_event_engine_transaction_cost_breakdown() -> None:
    prices = np.array([100.0, 101.0, 102.0])
    strategy = _BuyOnceStrategy()
    financing_model = BorrowFinancing(long_rate_bps=50, short_rate_bps=50, periods_per_year=2)
    cost_model = CompositeTransactionCostModel(
        commission_model=PerUnitCommission(0.1),
        spread_model=FixedSpread(0.02),
        slippage_model=FixedSlippage(0.03),
        financing_model=financing_model,
    )
    engine = EventDrivenBacktestEngine()
    result = engine.run(
        prices,
        _signal_function,
        fee=0.0,
        initial_capital=1_000.0,
        strategy=strategy,
        transaction_cost_model=cost_model,
    )
    assert math.isclose(result.commission_cost, 0.1)
    assert math.isclose(result.spread_cost, 0.02)
    assert math.isclose(result.slippage_cost, 0.03)
    expected_financing = float(financing_model.get_financing(1.0, float(prices[1])))
    assert math.isclose(result.financing_cost, expected_financing)


def test_portfolio_updates_history_on_fill() -> None:
    portfolio = Portfolio(symbol="TEST", initial_capital=1_000.0, fee_per_unit=0.0)
    first_event = MarketEvent(symbol="TEST", price=100.0, step=0)
    second_event = MarketEvent(symbol="TEST", price=101.0, step=1)
    portfolio.on_market_event(first_event)
    assert portfolio.position_history is not None
    assert portfolio.position_history[-1] == 0.0

    fill = FillEvent(symbol="TEST", quantity=1.5, price=100.0, fee=0.0, slippage=0.0, step=0)
    portfolio.on_fill(fill)

    assert portfolio.position == 1.5
    # Position history still reflects the last market mark until the next event is processed.
    assert portfolio.position_history[-1] == 0.0

    # Finalising without a subsequent market event should capture the latest position.
    portfolio.finalise_history()
    assert portfolio.position_history[-1] == 1.5

    # A later market event keeps the history consistent.
    portfolio.on_market_event(second_event)
    assert portfolio.position_history[-1] == 1.5


def test_event_engine_random_seed_controls_slippage() -> None:
    prices = np.linspace(100, 105, num=20)
    slippage_cfg = SlippageConfig(stochastic_bps=50.0)
    engine = EventDrivenBacktestEngine()

    seeded_one = engine.run(
        prices,
        _signal_function,
        fee=0.0,
        initial_capital=1_000.0,
        slippage=slippage_cfg,
        random_seed=42,
    )
    seeded_two = engine.run(
        prices,
        _signal_function,
        fee=0.0,
        initial_capital=1_000.0,
        slippage=slippage_cfg,
        random_seed=42,
    )
    different_seed = engine.run(
        prices,
        _signal_function,
        fee=0.0,
        initial_capital=1_000.0,
        slippage=slippage_cfg,
        random_seed=7,
    )

    assert np.allclose(seeded_one.equity_curve, seeded_two.equity_curve)
    assert not np.allclose(seeded_one.equity_curve, different_seed.equity_curve)


def test_event_engine_financing_cost_matches_walk_forward() -> None:
    prices = np.linspace(50.0, 55.0, num=6)
    vector_engine = WalkForwardEngine()
    vector_cost_model = CompositeTransactionCostModel(
        commission_model=PerUnitCommission(0.05),
        financing_model=BorrowFinancing(long_rate_bps=120, short_rate_bps=80, periods_per_year=4),
    )
    expected = vector_engine.run(
        prices,
        _signal_function,
        fee=0.0,
        initial_capital=500.0,
        cost_model=vector_cost_model,
    )

    engine = EventDrivenBacktestEngine()
    event_cost_model = CompositeTransactionCostModel(
        commission_model=PerUnitCommission(0.05),
        financing_model=BorrowFinancing(long_rate_bps=120, short_rate_bps=80, periods_per_year=4),
    )
    result = engine.run(
        prices,
        _signal_function,
        fee=0.0,
        initial_capital=500.0,
        transaction_cost_model=event_cost_model,
    )

    assert np.isclose(result.financing_cost, expected.financing_cost)
    assert np.isclose(result.pnl, expected.pnl)
    assert np.isclose(result.equity_curve[-1], expected.equity_curve[-1])


def test_event_engine_respects_market_calendar() -> None:
    calendar = MarketCalendar(
        timezone="America/New_York",
        regular_hours={idx: SessionHours(time(9, 30), time(16, 0)) for idx in range(5)},
        holidays={datetime(2023, 1, 2).date()},
    )

    timestamps = [
        datetime(2022, 12, 30, 14, 30),  # open session
        datetime(2023, 1, 2, 14, 30),  # holiday
        datetime(2023, 1, 3, 14, 30),  # open session
    ]
    prices = np.array([100.0, 101.0, 102.0])
    events = [
        MarketEvent(symbol="TEST", price=float(price), step=idx, timestamp=ts)
        for idx, (price, ts) in enumerate(zip(prices, timestamps, strict=True))
    ]

    class _StaticHandler(CSVChunkDataHandler):
        def __init__(self, events):
            self._events = events
            self.symbol = "TEST"

        def stream(self):
            yield self._events

    handler = _StaticHandler(events)
    engine = EventDrivenBacktestEngine()
    result = engine.run(
        prices,
        _signal_function,
        fee=0.0,
        initial_capital=1_000.0,
        data_handler=handler,
        calendar=calendar,
    )

    # Only two sessions should contribute to the equity curve because the holiday event is skipped.
    assert result.equity_curve.size == 2
