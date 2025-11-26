from __future__ import annotations

from typing import List

import pytest

from domain import Order, OrderSide, OrderStatus, OrderType
from execution.connectors import SimulatedExchangeConnector
from execution.normalization import SymbolSpecification
from execution.paper_trading import (
    DeterministicLatencyModel,
    PaperTradingEngine,
    TelemetryEvent,
)


class _DummyConnector(SimulatedExchangeConnector):
    def __init__(self) -> None:
        specs = {
            "BTCUSD": SymbolSpecification(
                "BTCUSD",
                min_qty=0.001,
                min_notional=10.0,
                step_size=0.001,
                tick_size=0.5,
            )
        }
        super().__init__(
            sandbox=True,
            symbol_map={"BTCUSD": "BTCUSD"},
            specifications=specs,
        )


def _order(quantity: float = 0.01) -> Order:
    return Order(
        symbol="BTCUSD",
        side=OrderSide.BUY,
        quantity=quantity,
        price=20000.0,
        order_type=OrderType.LIMIT,
    )


def test_execute_order_records_latency_and_pnl() -> None:
    connector = _DummyConnector()
    captured: List[TelemetryEvent] = []
    engine = PaperTradingEngine(
        connector,
        latency_model=DeterministicLatencyModel(ack_delay=0.1, fill_delay=0.4),
        clock=lambda: 1_000.0,
        telemetry_listeners=[captured.append],
    )

    report = engine.execute_order(
        _order(),
        execution_price=20_010.0,
        ideal_price=20_000.0,
        metadata={"run": "experiment-42"},
    )

    assert report.latency.ack_delay == pytest.approx(0.1)
    assert report.latency.fill_delay == pytest.approx(0.4)
    assert report.latency.total_delay == pytest.approx(0.5)

    assert len(report.telemetry) == 3
    assert [event.event for event in report.telemetry] == [
        "order.submit",
        "order.ack",
        "order.fill",
    ]
    assert report.telemetry[-1].timestamp == pytest.approx(1_000.5)

    assert report.order.status is OrderStatus.FILLED
    assert not report.stability_issues

    assert report.pnl.deviation == pytest.approx(report.pnl.implementation_shortfall)
    assert report.pnl.deviation == pytest.approx(0.1)

    assert captured == list(report.telemetry)


def test_partial_fill_flags_stability_issue() -> None:
    connector = _DummyConnector()
    engine = PaperTradingEngine(
        connector,
        latency_model=DeterministicLatencyModel(ack_delay=0.0, fill_delay=0.0),
        clock=lambda: 0.0,
    )

    quantity = 0.02
    report = engine.execute_order(
        _order(quantity=quantity),
        execution_price=20_000.0,
        executed_quantity=quantity / 2,
    )

    assert report.order.status is OrderStatus.PARTIALLY_FILLED
    assert report.stability_issues
    assert "status partially_filled" in report.stability_issues[0]


def test_execute_order_defaults_to_normalized_quantity() -> None:
    connector = _DummyConnector()
    engine = PaperTradingEngine(
        connector,
        latency_model=DeterministicLatencyModel(ack_delay=0.0, fill_delay=0.0),
        clock=lambda: 0.0,
    )

    order = _order(quantity=0.0012)

    report = engine.execute_order(
        order,
        execution_price=20_000.0,
    )

    assert report.order.quantity == pytest.approx(0.001)
    assert report.order.filled_quantity == pytest.approx(0.001)
    assert report.order.status is OrderStatus.FILLED
    assert not report.stability_issues


@pytest.mark.parametrize(
    "execution_price,executed_quantity",
    [(-1.0, 0.01), (10.0, 0.0), (10.0, 0.02)],
)
def test_execute_order_validation(
    execution_price: float, executed_quantity: float
) -> None:
    connector = _DummyConnector()
    engine = PaperTradingEngine(connector)
    order = _order()

    if executed_quantity > order.quantity:
        with pytest.raises(ValueError, match="executed_quantity"):
            engine.execute_order(
                order,
                execution_price=execution_price,
                executed_quantity=executed_quantity,
            )
    elif execution_price <= 0:
        with pytest.raises(ValueError, match="execution_price"):
            engine.execute_order(
                order,
                execution_price=execution_price,
            )
    else:
        with pytest.raises(ValueError, match="executed_quantity"):
            engine.execute_order(
                order,
                execution_price=execution_price,
                executed_quantity=executed_quantity,
            )
