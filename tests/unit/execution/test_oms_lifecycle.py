"""Lifecycle orchestration integration tests for :mod:`execution.oms`."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from domain import Order, OrderSide, OrderType
from execution.connectors import ExecutionConnector
from execution.oms import OMSConfig, OrderManagementSystem
from execution.order_lifecycle import OrderEvent, OrderLifecycle, OrderLifecycleStore
from interfaces.execution import RiskController
from libs.db import DataAccessLayer


class StubRiskController(RiskController):
    def validate_order(self, symbol: str, side: str, qty: float, price: float) -> None:
        return None

    def register_fill(self, symbol: str, side: str, qty: float, price: float) -> None:
        return None

    def current_position(self, symbol: str) -> float:
        return 0.0

    def current_notional(self, symbol: str) -> float:
        return 0.0

    @property
    def kill_switch(self) -> object | None:
        return None


class DeterministicConnector(ExecutionConnector):
    """Execution connector that issues sequential identifiers for testing."""

    def __init__(self) -> None:
        super().__init__(sandbox=True)
        self._counter = 0

    def place_order(self, order: Order, *, idempotency_key: str | None = None) -> Order:
        if idempotency_key is not None and idempotency_key in self._idempotency_cache:
            return self._idempotency_cache[idempotency_key]
        submitted = replace(order)
        if not submitted.order_id:
            submitted.mark_submitted(f"test-{self._counter:04d}")
        self._counter += 1
        if idempotency_key is not None:
            self._idempotency_cache[idempotency_key] = submitted
        self._orders[submitted.order_id] = submitted
        return submitted


@pytest.fixture()
def lifecycle(tmp_path) -> OrderLifecycle:
    db_path = tmp_path / "lifecycle.db"

    def factory() -> sqlite3.Connection:
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        return connection

    store = OrderLifecycleStore(
        DataAccessLayer(factory),
        schema=None,
        dialect="sqlite",
    )
    store.ensure_schema()
    return OrderLifecycle(
        store, clock=lambda: datetime(2024, 1, 1, tzinfo=timezone.utc)
    )


def _make_oms(tmp_path, lifecycle: OrderLifecycle) -> OrderManagementSystem:
    state_path = tmp_path / "oms-state.json"
    config = OMSConfig(state_path=state_path, auto_persist=False)
    connector = DeterministicConnector()
    risk = StubRiskController()
    return OrderManagementSystem(connector, risk, config, lifecycle=lifecycle)


def test_oms_records_submit_ack_and_fills(tmp_path, lifecycle: OrderLifecycle) -> None:
    oms = _make_oms(tmp_path, lifecycle)

    order = Order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=1.0,
        price=20_000.0,
        order_type=OrderType.LIMIT,
    )

    oms.submit(order, correlation_id="ord-1")
    submitted = oms.process_next()
    assert submitted.order_id is not None

    oms.register_fill(submitted.order_id, 0.4, 19_900.0)
    oms.register_fill(submitted.order_id, 0.6, 20_050.0)

    history = lifecycle.history(submitted.order_id)
    assert [transition.event for transition in history] == [
        OrderEvent.SUBMIT,
        OrderEvent.ACK,
        OrderEvent.FILL_PARTIAL,
        OrderEvent.FILL_FINAL,
    ]


def test_oms_records_cancellation(tmp_path, lifecycle: OrderLifecycle) -> None:
    oms = _make_oms(tmp_path, lifecycle)

    order = Order(
        symbol="ETHUSDT",
        side=OrderSide.SELL,
        quantity=2.0,
        price=1_200.0,
        order_type=OrderType.LIMIT,
    )

    oms.submit(order, correlation_id="ord-cancel")
    submitted = oms.process_next()
    assert submitted.order_id is not None

    assert oms.cancel(submitted.order_id)

    history = lifecycle.history(submitted.order_id)
    assert [transition.event for transition in history] == [
        OrderEvent.SUBMIT,
        OrderEvent.ACK,
        OrderEvent.CANCEL,
    ]
