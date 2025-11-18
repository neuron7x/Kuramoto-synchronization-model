import math
from typing import Optional

import pytest

from backtest.execution_simulation import (
    HaltMode,
    MarketHalt,
    MatchingEngine,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
)


@pytest.fixture
def engine():
    return MatchingEngine()


def test_latency_delays_execution(engine):
    engine.latency_model = lambda order: 100
    engine.add_passive_liquidity("BTC-USD", OrderSide.SELL, price=100.0, qty=5.0, timestamp=0)

    order = Order(
        id="o-1",
        symbol="BTC-USD",
        side=OrderSide.BUY,
        qty=5.0,
        timestamp=0,
        order_type=OrderType.MARKET,
    )
    engine.submit_order(order)

    processed = engine.process_until(50)
    assert not processed
    assert order.status == OrderStatus.QUEUED

    engine.process_until(150)
    assert math.isclose(order.filled_qty, 5.0)
    assert order.status == OrderStatus.FILLED


def test_queue_and_partial_fill(engine):
    engine.latency_model = lambda order: 0
    engine.add_passive_liquidity("ETH-USD", OrderSide.SELL, price=100.0, qty=6.0, timestamp=0)

    first = Order(
        id="o-1",
        symbol="ETH-USD",
        side=OrderSide.BUY,
        qty=4.0,
        timestamp=0,
        order_type=OrderType.MARKET,
    )
    second = Order(
        id="o-2",
        symbol="ETH-USD",
        side=OrderSide.BUY,
        qty=4.0,
        timestamp=1,
        order_type=OrderType.MARKET,
    )

    engine.submit_order(first)
    engine.submit_order(second)

    engine.process_until(0)
    assert math.isclose(first.filled_qty, 4.0)
    assert first.status == OrderStatus.FILLED

    engine.process_until(1)
    assert math.isclose(second.filled_qty, 2.0)
    assert second.status == OrderStatus.PARTIALLY_FILLED


def test_market_halt_delay_and_resume():
    resume_time = 200

    def halt_model(symbol: str, timestamp: int) -> Optional[MarketHalt]:
        if timestamp < resume_time:
            return MarketHalt(mode=HaltMode.DELAY, resume_time=resume_time)
        return MarketHalt(mode=HaltMode.OPEN)

    engine = MatchingEngine(latency_model=lambda order: 0, halt_model=halt_model)
    engine.add_passive_liquidity("BTC-USD", OrderSide.SELL, price=50_000, qty=1.0, timestamp=0)

    order = Order(
        id="o-1",
        symbol="BTC-USD",
        side=OrderSide.BUY,
        qty=1.0,
        timestamp=0,
        order_type=OrderType.MARKET,
    )

    engine.submit_order(order)
    engine.process_until(100)
    assert order.status == OrderStatus.QUEUED

    engine.process_until(300)
    assert order.status == OrderStatus.FILLED
    assert math.isclose(order.filled_qty, 1.0)


def test_fok_requires_full_liquidity(engine):
    engine.latency_model = lambda order: 0
    engine.add_passive_liquidity("BTC-USD", OrderSide.SELL, price=25_000, qty=5.0, timestamp=0)

    order = Order(
        id="o-1",
        symbol="BTC-USD",
        side=OrderSide.BUY,
        qty=6.0,
        timestamp=0,
        order_type=OrderType.FOK,
        price=25_000,
    )

    engine.submit_order(order)
    engine.process_until(0)

    assert order.status == OrderStatus.CANCELLED
    assert math.isclose(order.filled_qty, 0.0)
    assert not order.executions


def test_ioc_partial_fill_cancels_remaining(engine):
    engine.latency_model = lambda order: 0
    engine.add_passive_liquidity("BTC-USD", OrderSide.SELL, price=50_000, qty=3.0, timestamp=0)

    order = Order(
        id="o-1",
        symbol="BTC-USD",
        side=OrderSide.BUY,
        qty=5.0,
        timestamp=0,
        order_type=OrderType.IOC,
        price=50_000,
    )

    engine.submit_order(order)
    engine.process_until(0)

    assert order.status == OrderStatus.PARTIALLY_FILLED
    assert math.isclose(order.filled_qty, 3.0)
    assert math.isclose(sum(exec.qty for exec in order.executions), 3.0)


def test_market_order_without_liquidity_is_cancelled(engine):
    engine.latency_model = lambda order: 0

    order = Order(
        id="o-1",
        symbol="ETH-USD",
        side=OrderSide.BUY,
        qty=2.0,
        timestamp=0,
        order_type=OrderType.MARKET,
    )

    engine.submit_order(order)
    engine.process_until(0)

    assert order.status == OrderStatus.CANCELLED
    assert math.isclose(order.filled_qty, 0.0)
    assert not order.executions
