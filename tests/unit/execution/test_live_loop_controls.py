# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests exercising lifecycle controls in :mod:`execution.live_loop`."""

from __future__ import annotations

from typing import Tuple

import pytest

from domain import Order, OrderSide, OrderStatus, OrderType
from execution.connectors import BinanceConnector
from execution.live_loop import LiveExecutionLoop, LiveLoopConfig
from execution.risk import RiskLimits, RiskManager
from execution.session_snapshot import SessionSnapshotError


@pytest.fixture()
def loop_env(tmp_path) -> Tuple[LiveExecutionLoop, BinanceConnector]:
    """Provide a fresh loop and connector for lifecycle tests."""

    config = LiveLoopConfig(state_dir=tmp_path / "state")
    risk_manager = RiskManager(RiskLimits(max_notional=1_000_000, max_position=100))
    connector = BinanceConnector()
    loop = LiveExecutionLoop({"binance": connector}, risk_manager, config=config)
    return loop, connector


def _adopt_order(loop: LiveExecutionLoop, connector: BinanceConnector) -> Order:
    order = Order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=0.25,
        price=20_000,
        order_type=OrderType.LIMIT,
    )
    placed = connector.place_order(order)
    assert placed.order_id is not None
    context = loop._contexts["binance"]
    context.oms.adopt_open_order(placed, correlation_id="corr-1")
    return placed


def test_cancel_order_discovers_context_when_not_cached(loop_env) -> None:
    loop, connector = loop_env
    order = _adopt_order(loop, connector)

    assert order.order_id not in loop._order_connector
    assert loop.cancel_order(order.order_id)
    assert order.order_id not in loop._order_connector
    assert order.order_id not in loop._last_reported_fill
    assert connector.fetch_order(order.order_id).status is OrderStatus.CANCELLED


def test_cancel_all_outstanding_clears_tracking(loop_env) -> None:
    loop, connector = loop_env
    order = _adopt_order(loop, connector)

    order_id = order.order_id
    assert order_id is not None

    loop._order_connector[order_id] = "binance"
    loop._last_reported_fill[order_id] = 0.1

    loop._cancel_all_outstanding(reason="unit-test")

    assert not list(loop._contexts["binance"].oms.outstanding())
    assert order_id not in loop._order_connector
    assert order_id not in loop._last_reported_fill
    assert connector.fetch_order(order_id).status is OrderStatus.CANCELLED


def test_cancel_all_outstanding_logs_rejections(monkeypatch, loop_env) -> None:
    loop, connector = loop_env
    order = _adopt_order(loop, connector)
    context = loop._contexts["binance"]

    order_id = order.order_id
    assert order_id is not None

    loop._order_connector[order_id] = "binance"
    loop._last_reported_fill[order_id] = 0.2

    cancellations: list[str] = []

    def fake_cancel(cancel_id: str) -> bool:
        cancellations.append(cancel_id)
        return False

    monkeypatch.setattr(context.oms, "cancel", fake_cancel)

    loop._cancel_all_outstanding(reason="rejected")

    assert cancellations == [order_id]
    assert list(context.oms.outstanding())[0].order_id == order_id
    assert loop._order_connector[order_id] == "binance"
    assert loop._last_reported_fill[order_id] == 0.2


def test_start_requires_snapshot(loop_env) -> None:
    loop, _ = loop_env

    class FailingSnapshotter:
        def capture(self, connectors, *, preloaded=None):  # type: ignore[unused-argument]
            raise SessionSnapshotError("boom")

    loop._session_snapshotter = FailingSnapshotter()  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="snapshot"):
        loop.start(cold_start=True)

    assert not loop.started
