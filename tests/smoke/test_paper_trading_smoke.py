# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Smoke tests validating the happy-path behaviour of the paper trading engine."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from domain import Order, OrderSide, OrderStatus
from execution.connectors import SimulatedExchangeConnector
from execution.paper_trading import (
    DeterministicLatencyModel,
    PaperTradingEngine,
)


@pytest.mark.smoke
def test_paper_trading_engine_executes_market_order() -> None:
    """Ensure a market order can be executed end-to-end in the simulator."""

    connector = SimulatedExchangeConnector()
    engine = PaperTradingEngine(
        connector,
        latency_model=DeterministicLatencyModel(ack_delay=0.0, fill_delay=0.0),
        clock=lambda: 42.0,
    )

    order = Order(symbol="ETH-USD", side=OrderSide.BUY, quantity=2.0)
    report = engine.execute_order(order, execution_price=2015.25)

    assert report.order.status is OrderStatus.FILLED
    assert report.order.filled_quantity == pytest.approx(2.0)
    assert report.latency.total_delay == pytest.approx(0.0)
    assert report.pnl.realized_value == pytest.approx(2.0 * 2015.25, rel=1e-9)
    assert not report.stability_issues
    assert any(event.event == "order.submit" for event in report.telemetry)


@pytest.mark.smoke
def test_paper_trading_engine_respects_ideal_price_override() -> None:
    """Verify execution analytics reflect an explicitly provided ideal price."""

    connector = SimulatedExchangeConnector()
    engine = PaperTradingEngine(
        connector,
        latency_model=DeterministicLatencyModel(ack_delay=0.1, fill_delay=0.2),
        clock=lambda: datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp(),
    )

    order = Order(symbol="BTC-USD", side=OrderSide.SELL, quantity=0.75)
    report = engine.execute_order(
        order,
        execution_price=38123.0,
        ideal_price=38100.0,
        executed_quantity=0.75,
    )

    assert report.order.status is OrderStatus.FILLED
    assert report.latency.total_delay == pytest.approx(0.3)
    assert report.pnl.deviation == pytest.approx(-17.25)
    assert report.pnl.ideal_value == pytest.approx(-0.75 * 38100.0)
    assert report.order.filled_quantity == pytest.approx(0.75)
    assert report.telemetry[0].event == "order.submit"
    assert report.telemetry[-1].event == "order.fill"
