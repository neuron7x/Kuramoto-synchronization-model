# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Property-based regression tests for execution adapter parsing helpers."""

from __future__ import annotations

import pytest

try:  # pragma: no cover - optional dependency
    from hypothesis import HealthCheck, given, settings
    from hypothesis import strategies as st
except ImportError:  # pragma: no cover - executed when hypothesis missing
    pytest.skip("hypothesis not installed", allow_module_level=True)

from domain import Order
from execution.adapters.binance import BinanceRESTConnector
from execution.adapters.coinbase import CoinbaseRESTConnector
from execution.adapters.kraken import KrakenRESTConnector

_FLOATS = st.floats(min_value=-1e12, max_value=1e12, allow_nan=False, allow_infinity=False)
_INTS = st.integers(min_value=-1_000_000_000, max_value=1_000_000_000)
_NUMERIC_TEXT = st.one_of(
    _FLOATS.map(lambda value: f"  {value} \t"),
    _INTS.map(lambda value: f"\n{value}  "),
)
_BASE_SCALARS = st.one_of(
    st.none(),
    st.booleans(),
    _FLOATS,
    _INTS,
    _NUMERIC_TEXT,
    st.text(min_size=0, max_size=20),
)

_VALUE_TREE = st.recursive(
    _BASE_SCALARS,
    lambda children: st.lists(children, max_size=4)
    | st.dictionaries(st.text(min_size=1, max_size=12), children, max_size=4),
    max_leaves=20,
)

_MISSING = object()


def _payload_strategy(
    keys: list[str], *, special: dict[str, st.SearchStrategy[object]] | None = None
) -> st.SearchStrategy[dict[str, object]]:
    """Build a payload strategy with optional overrides per key."""

    special = special or {}
    base_fields: dict[str, st.SearchStrategy[object]] = {}
    for key in keys:
        value_strategy = special.get(key, _VALUE_TREE)
        base_fields[key] = st.one_of(value_strategy, st.just(_MISSING))

    core = st.fixed_dictionaries(base_fields) if base_fields else st.just({})
    extras = st.dictionaries(
        st.text(min_size=1, max_size=12),
        _VALUE_TREE,
        max_size=6,
    )
    return st.builds(
        lambda extra, base: {
            **extra,
            **{key: value for key, value in base.items() if value is not _MISSING},
        },
        extras,
        core,
    )


_BINANCE_ORDER_KEYS = [
    "symbol",
    "side",
    "S",
    "type",
    "o",
    "orderId",
    "i",
    "order_id",
    "origQty",
    "q",
    "price",
    "p",
    "executedQty",
    "z",
    "filledQty",
    "cummulativeQuoteQty",
    "Z",
    "cumulativeQuoteQty",
    "avgPrice",
    "ap",
    "status",
    "X",
]

_COINBASE_ORDER_KEYS = [
    "product_id",
    "side",
    "order_type",
    "type",
    "order_id",
    "id",
    "orderId",
    "size",
    "base_size",
    "filled_size",
    "executed_value",
    "price",
    "limit_price",
    "average_filled_price",
    "average_price",
    "status",
]

_COINBASE_ORDER_PAYLOAD = _payload_strategy(_COINBASE_ORDER_KEYS)

_KRAKEN_ORDER_KEYS = [
    "pair",
    "symbol",
    "type",
    "side",
    "ordertype",
    "ordertxid",
    "order_id",
    "txid",
    "vol",
    "volume",
    "vol_exec",
    "filled",
    "price",
    "limitprice",
    "avg_price",
    "status",
    "state",
]

_BINANCE_POSITIONS_PAYLOAD = _payload_strategy(["balances"])
_COINBASE_POSITIONS_PAYLOAD = _payload_strategy(["accounts"])
_KRAKEN_POSITIONS_PAYLOAD = _payload_strategy(["result"])


@settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(payload=_payload_strategy(_BINANCE_ORDER_KEYS))
def test_binance_parse_order_is_resilient(payload: dict[str, object]) -> None:
    connector = BinanceRESTConnector()
    try:
        order = connector._parse_order(payload)
    except ValueError:
        return
    assert isinstance(order, Order)


@settings(max_examples=150, deadline=None)
@given(payload=_BINANCE_POSITIONS_PAYLOAD)
def test_binance_parse_positions_handles_noise(payload: dict[str, object]) -> None:
    connector = BinanceRESTConnector()
    positions = connector._parse_positions(payload)
    assert isinstance(positions, list)
    for position in positions:
        assert isinstance(position, dict)
        assert position["symbol"].strip()
        assert position["qty"] >= 0


@settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    payload=_payload_strategy(
        _COINBASE_ORDER_KEYS + ["order"],
        special={"order": st.one_of(_COINBASE_ORDER_PAYLOAD, _VALUE_TREE)},
    )
)
def test_coinbase_parse_order_is_resilient(payload: dict[str, object]) -> None:
    connector = CoinbaseRESTConnector()
    try:
        order = connector._parse_order(payload)
    except ValueError:
        return
    assert isinstance(order, Order)


@settings(max_examples=150, deadline=None)
@given(payload=_COINBASE_POSITIONS_PAYLOAD)
def test_coinbase_parse_positions_handles_noise(payload: dict[str, object]) -> None:
    connector = CoinbaseRESTConnector()
    positions = connector._parse_positions(payload)
    assert isinstance(positions, list)
    for position in positions:
        assert isinstance(position, dict)
        assert position["symbol"].strip()
        assert position["qty"] >= 0


@settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(payload=_payload_strategy(_KRAKEN_ORDER_KEYS))
def test_kraken_parse_order_is_resilient(payload: dict[str, object]) -> None:
    connector = KrakenRESTConnector()
    try:
        order = connector._parse_order(payload)
    except ValueError:
        return
    assert isinstance(order, Order)


@settings(max_examples=150, deadline=None)
@given(payload=_KRAKEN_POSITIONS_PAYLOAD)
def test_kraken_parse_positions_handles_noise(payload: dict[str, object]) -> None:
    connector = KrakenRESTConnector()
    positions = connector._parse_positions(payload)
    assert isinstance(positions, list)
    for position in positions:
        assert isinstance(position, dict)
        assert position["symbol"].strip()
        assert position["qty"] >= 0
