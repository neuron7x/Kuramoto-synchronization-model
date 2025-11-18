from __future__ import annotations

from core.events.models import (
    BarEvent,
    FillEvent,
    FillLiquidity,
    FillStatus,
    OrderEvent,
    OrderSide,
    OrderType,
    SignalDirection,
    SignalEvent,
    TickEvent,
    TickMicrostructure,
    TimeInForce,
)


def test_event_dataclasses_support_expected_fields() -> None:
    bar = BarEvent(
        event_id="evt-bar",
        schema_version="1.0.0",
        symbol="AAPL",
        timestamp=1,
        interval="1m",
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=1000.0,
        vwap=1.2,
        trade_count=10,
    )

    fill = FillEvent(
        event_id="evt-fill",
        schema_version="1.0.0",
        symbol="AAPL",
        timestamp=1,
        order_id="ord-1",
        fill_id="fill-1",
        status=FillStatus.FILLED,
        filled_qty=10.0,
        fill_price=101.0,
        fees=0.1,
        liquidity=FillLiquidity.MAKER,
        metadata={"venue": "TEST"},
    )

    order = OrderEvent(
        event_id="evt-order",
        schema_version="1.0.0",
        symbol="AAPL",
        timestamp=1,
        order_id="ord-1",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=10.0,
        price=101.0,
        time_in_force=TimeInForce.DAY,
        routing="NYSE",
    )

    signal = SignalEvent(
        event_id="evt-signal",
        schema_version="1.0.0",
        symbol="AAPL",
        timestamp=1,
        signal_type="mean-reversion",
        strength=0.7,
        direction=SignalDirection.BUY,
        ttl_seconds=60,
        metadata={"model": "ricci"},
    )

    tick = TickEvent(
        event_id="evt-tick",
        schema_version="1.0.0",
        symbol="AAPL",
        timestamp=1,
        bid_price=100.0,
        ask_price=100.5,
        last_price=100.2,
        volume=1,
        microstructure=TickMicrostructure(bid_size=10, ask_size=12, trade_condition="@"),
    )

    assert bar.vwap == 1.2
    assert fill.liquidity is FillLiquidity.MAKER
    assert order.time_in_force is TimeInForce.DAY
    assert signal.metadata["model"] == "ricci"
    assert tick.microstructure.trade_condition == "@"
