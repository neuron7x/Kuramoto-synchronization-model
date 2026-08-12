# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest

from domain import OrderStatus
from execution.order_lifecycle import (
    OrderEvent,
    OrderLifecycle,
    OrderLifecycleStore,
)
from libs.db import DataAccessLayer


@pytest.fixture()
def lifecycle(tmp_path):
    db_path = tmp_path / "orders.db"

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
    return OrderLifecycle(store, clock=lambda: datetime(2024, 1, 1))


def test_deterministic_transitions(lifecycle: OrderLifecycle) -> None:
    first = lifecycle.apply(
        "order-1",
        OrderEvent.SUBMIT,
        correlation_id="c-1",
        metadata={"note": "created"},
    )
    assert first.to_status == OrderStatus.PENDING

    ack = lifecycle.apply("order-1", OrderEvent.ACK, correlation_id="c-2")
    assert ack.from_status == OrderStatus.PENDING
    assert ack.to_status == OrderStatus.OPEN

    partial = lifecycle.apply("order-1", OrderEvent.FILL_PARTIAL, correlation_id="c-3")
    assert partial.from_status == OrderStatus.OPEN
    assert partial.to_status == OrderStatus.PARTIALLY_FILLED

    final = lifecycle.apply("order-1", OrderEvent.FILL_FINAL, correlation_id="c-4")
    assert final.to_status == OrderStatus.FILLED

    history = lifecycle.history("order-1")
    assert [transition.event for transition in history] == [
        OrderEvent.SUBMIT,
        OrderEvent.ACK,
        OrderEvent.FILL_PARTIAL,
        OrderEvent.FILL_FINAL,
    ]


def test_idempotent_correlation_keys(lifecycle: OrderLifecycle) -> None:
    lifecycle.apply("order-2", OrderEvent.ACK, correlation_id="c-ack")
    repeat = lifecycle.apply("order-2", OrderEvent.ACK, correlation_id="c-ack")
    assert repeat.sequence == lifecycle.history("order-2")[0].sequence

    with pytest.raises(ValueError):
        lifecycle.apply("order-2", OrderEvent.CANCEL, correlation_id="c-ack")


def test_invalid_transition_rejected(lifecycle: OrderLifecycle) -> None:
    lifecycle.apply("order-3", OrderEvent.ACK, correlation_id="c-open")
    with pytest.raises(ValueError):
        lifecycle.apply("order-3", OrderEvent.SUBMIT, correlation_id="c-invalid")


def test_recover_active_orders(lifecycle: OrderLifecycle) -> None:
    lifecycle.apply("order-a", OrderEvent.ACK, correlation_id="a-ack")
    lifecycle.apply("order-a", OrderEvent.FILL_PARTIAL, correlation_id="a-partial")

    lifecycle.apply("order-b", OrderEvent.ACK, correlation_id="b-ack")
    lifecycle.apply("order-b", OrderEvent.CANCEL, correlation_id="b-cancel")

    lifecycle.apply("order-c", OrderEvent.ACK, correlation_id="c-ack")

    active = lifecycle.recover_active_orders()
    assert set(active) == {"order-a", "order-c"}
    assert active["order-a"].to_status == OrderStatus.PARTIALLY_FILLED
    assert active["order-c"].to_status == OrderStatus.OPEN


def test_state_survives_restart(tmp_path) -> None:
    db_path = tmp_path / "restart.db"

    def factory() -> sqlite3.Connection:
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        return connection

    dal = DataAccessLayer(factory)
    store = OrderLifecycleStore(dal, schema=None, dialect="sqlite")
    store.ensure_schema()

    lifecycle = OrderLifecycle(store, clock=lambda: datetime(2024, 1, 1))
    lifecycle.apply("order-x", OrderEvent.ACK, correlation_id="x-ack")
    lifecycle.apply("order-x", OrderEvent.FILL_PARTIAL, correlation_id="x-partial")

    restored = OrderLifecycle(store, clock=lambda: datetime(2024, 1, 2))
    assert restored.get_state("order-x") == OrderStatus.PARTIALLY_FILLED
    restored.apply("order-x", OrderEvent.FILL_FINAL, correlation_id="x-final")
    assert restored.get_state("order-x") == OrderStatus.FILLED
