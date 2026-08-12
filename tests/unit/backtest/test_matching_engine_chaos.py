# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import contextlib

import numpy as np
import pytest

from backtest.execution_simulation import (
    HaltMode,
    MarketHalt,
    MatchingEngine,
    Order,
    OrderSide,
    OrderType,
)
from observability.tracing import chaos_span


@pytest.fixture()
def resilient_engine(monkeypatch):
    captured = {}

    def fake_pipeline(stage: str, **attrs):
        captured.setdefault("stages", []).append((stage, attrs))
        return contextlib.nullcontext(None)

    monkeypatch.setattr("observability.tracing.pipeline_span", fake_pipeline)

    def halt_model(symbol: str, timestamp: int) -> MarketHalt | None:
        if symbol == "XBTUSD" and timestamp >= 5:
            return MarketHalt(
                mode=HaltMode.PARTIAL, resume_time=timestamp + 2, liquidity_factor=0.7
            )
        return None

    engine = MatchingEngine(
        latency_model=lambda order: 2 if order.symbol == "XBTUSD" else 0,
        halt_model=halt_model,
    )
    engine.add_passive_liquidity("XBTUSD", OrderSide.SELL, price=100.0, qty=200.0, timestamp=0)
    engine.add_passive_liquidity("XBTUSD", OrderSide.BUY, price=99.5, qty=200.0, timestamp=0)
    return engine, captured


def test_matching_engine_limits_drawdown_under_node_failure(resilient_engine):
    engine, captured = resilient_engine

    order = Order(
        id="ord-chaos",
        symbol="XBTUSD",
        side=OrderSide.BUY,
        qty=100.0,
        timestamp=5,
        order_type=OrderType.LIMIT,
        price=101.0,
    )

    with chaos_span("matching-engine", disruption="node-failure"):
        engine.submit_order(order)
        processed = engine.process_until(10)

    assert processed
    filled = processed[0]
    assert filled.filled_qty == pytest.approx(70.0)
    assert filled.status.name in {"PARTIALLY_FILLED", "FILLED"}

    average_fill = np.mean([report.price for report in filled.executions])
    assert average_fill == pytest.approx(100.0)

    post_shock_price = 99.2
    initial_capital = 5000.0
    pnl = (post_shock_price - average_fill) * filled.filled_qty
    equity_curve = np.array([initial_capital, initial_capital + pnl], dtype=float)
    peaks = np.maximum.accumulate(equity_curve)
    max_drawdown = float((equity_curve - peaks).min())
    drawdown_pct = abs(max_drawdown) / initial_capital

    assert drawdown_pct < 0.02

    stages = captured.get("stages", [])
    assert stages
    stage, attrs = stages[0]
    assert stage == "chaos.matching-engine"
    assert attrs["chaos.experiment"] == "matching-engine"
    assert attrs["disruption"] == "node-failure"
