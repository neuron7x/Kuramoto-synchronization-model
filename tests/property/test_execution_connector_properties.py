# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Property-based checks for simulated execution connectors."""

from __future__ import annotations

import pytest

try:
    from hypothesis import HealthCheck, assume, given, settings
    from hypothesis import strategies as st
except ImportError:  # pragma: no cover
    pytest.skip("hypothesis not installed", allow_module_level=True)

from domain import Order, OrderSide, OrderType
from execution.connectors import BinanceConnector, KrakenConnector
from tests.tolerances import FLOAT_ABS_TOL, FLOAT_REL_TOL


def _limit_order(symbol: str, quantity: float, price: float) -> Order:
    return Order(
        symbol=symbol,
        side=OrderSide.BUY,
        quantity=quantity,
        price=price,
        order_type=OrderType.LIMIT,
    )


@settings(
    max_examples=75,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    quantity=st.floats(min_value=0.0001, max_value=5.0, allow_nan=False, allow_infinity=False),
    price=st.floats(min_value=50.0, max_value=80_000.0, allow_nan=False, allow_infinity=False),
)
def test_binance_connector_respects_step_sizes(quantity: float, price: float) -> None:
    """Placed orders should be rounded to Binance lot/tick sizes."""
    connector = BinanceConnector()
    spec = connector.normalizer.specification("BTCUSDT")
    assert spec is not None

    assume(quantity >= spec.min_qty)
    assume(quantity * price >= spec.min_notional)

    placed = connector.place_order(_limit_order("BTCUSDT", quantity, price))

    expected_qty = connector.normalizer.round_quantity("BTCUSDT", quantity)
    expected_price = connector.normalizer.round_price("BTCUSDT", price)

    assert placed.quantity == pytest.approx(expected_qty, rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL)
    assert placed.price is not None
    assert placed.price == pytest.approx(expected_price, rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL)
    assert placed.order_id is not None and placed.order_id.startswith("BinanceConnector-")
    assert connector.fetch_order(placed.order_id) is placed


@settings(
    max_examples=75,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    quantity=st.floats(min_value=0.0001, max_value=3.0, allow_nan=False, allow_infinity=False),
    price=st.floats(min_value=50.0, max_value=50_000.0, allow_nan=False, allow_infinity=False),
)
def test_kraken_connector_normalizes_symbols(quantity: float, price: float) -> None:
    """Kraken connector should round quantities according to mapped symbol specs."""
    connector = KrakenConnector()
    spec = connector.normalizer.specification("BTCUSD")
    assert spec is not None

    assume(quantity >= spec.min_qty)
    assume(quantity * price >= spec.min_notional)

    placed = connector.place_order(_limit_order("BTCUSD", quantity, price))

    expected_qty = connector.normalizer.round_quantity("BTCUSD", quantity)
    expected_price = connector.normalizer.round_price("BTCUSD", price)

    assert placed.quantity == pytest.approx(expected_qty, rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL)
    assert placed.price is not None
    assert placed.price == pytest.approx(expected_price, rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL)
    assert connector.normalizer.exchange_symbol("BTCUSD") == "XBTUSD"
    assert placed.order_id is not None
