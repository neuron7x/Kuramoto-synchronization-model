# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from collections import deque

import pytest

from domain import Order, OrderSide, OrderType
from execution.connectors import (
    SimulatedExchangeConnector,
    TransientOrderError,
)
from execution.normalization import SymbolSpecification


class DummyConnector(SimulatedExchangeConnector):
    def __init__(self, *, failure_plan: deque[str | Exception] | None = None) -> None:
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
            failure_plan=list(failure_plan or []),
        )


def _order(quantity: float = 0.01) -> Order:
    return Order(
        symbol="BTCUSD",
        side=OrderSide.BUY,
        quantity=quantity,
        price=20000.0,
        order_type=OrderType.LIMIT,
    )


def test_simulated_connector_respects_idempotency_cache() -> None:
    connector = DummyConnector()
    order = _order()
    first = connector.place_order(order, idempotency_key="abc")
    second = connector.place_order(order, idempotency_key="abc")
    assert first is second
    assert first.order_id == second.order_id


@pytest.mark.parametrize(
    "token,expected_exception",
    [
        ("network", TransientOrderError),
        ("429", TransientOrderError),
        ("timeout", TimeoutError),
    ],
)
def test_simulated_connector_failure_plan_tokens(
    token: str, expected_exception: type[BaseException]
) -> None:
    connector = DummyConnector(failure_plan=deque([token]))
    with pytest.raises(expected_exception):
        connector.place_order(_order())


def test_simulated_connector_rejects_unknown_failure_token() -> None:
    connector = DummyConnector(failure_plan=deque(["unknown-token"]))
    with pytest.raises(ValueError, match="Unknown failure token"):
        connector.place_order(_order())


def test_simulated_connector_apply_fill_updates_state() -> None:
    connector = DummyConnector()
    submitted = connector.place_order(_order())
    connector.apply_fill(submitted.order_id, quantity=0.005, price=19950.0)
    cached = connector.fetch_order(submitted.order_id)
    assert cached.filled_quantity == pytest.approx(0.005)
    assert cached.status.value in {"partially_filled", "filled"}


def test_simulated_connector_cancel_unknown_order_returns_false() -> None:
    connector = DummyConnector()
    assert connector.cancel_order("does-not-exist") is False
