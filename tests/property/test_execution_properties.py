# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st
except ImportError:  # pragma: no cover
    pytest.skip("hypothesis not installed", allow_module_level=True)

from domain import Order, OrderSide, OrderType
from execution.order import position_sizing
from execution.risk import portfolio_heat


class TestPositionSizingProperties:
    """Property-based tests for position sizing."""

    @settings(max_examples=100, deadline=None)
    @given(
        balance=st.floats(min_value=1.0, max_value=1_000_000.0),
        risk=st.floats(min_value=0.0, max_value=1.0),
        price=st.floats(min_value=0.01, max_value=100_000.0),
        max_leverage=st.floats(min_value=1.0, max_value=10.0),
    )
    def test_position_size_never_exceeds_balance_or_leverage(
        self, balance: float, risk: float, price: float, max_leverage: float
    ) -> None:
        """Position size must respect both balance and leverage limits."""
        size = position_sizing(balance, risk, price, max_leverage=max_leverage)

        # Size should be non-negative
        assert size >= 0.0

        # Position notional should not exceed balance * risk
        notional = size * price
        assert notional <= balance * risk * 1.01  # Small tolerance for floating point

        # Position should not exceed leverage cap
        leverage_notional = size * price
        assert leverage_notional <= balance * max_leverage * 1.01

    @settings(max_examples=50, deadline=None)
    @given(
        balance=st.floats(min_value=100.0, max_value=10_000.0),
        price=st.floats(min_value=0.01, max_value=1000.0),
    )
    def test_position_size_increases_with_risk(self, balance: float, price: float) -> None:
        """Higher risk should yield larger position sizes."""
        size_low = position_sizing(balance, 0.1, price)
        size_high = position_sizing(balance, 0.5, price)
        assert size_high >= size_low

    def test_position_sizing_rejects_invalid_price(self) -> None:
        """Negative or zero price should raise ValueError."""
        with pytest.raises(ValueError, match="price must be positive"):
            position_sizing(1000.0, 0.5, 0.0)
        with pytest.raises(ValueError, match="price must be positive"):
            position_sizing(1000.0, 0.5, -10.0)


class TestPortfolioHeatProperties:
    """Property-based tests for portfolio heat calculation."""

    @settings(max_examples=100, deadline=None)
    @given(
        positions=st.lists(
            st.fixed_dictionaries(
                {
                    "qty": st.floats(
                        min_value=-100.0,
                        max_value=100.0,
                        allow_nan=False,
                        allow_infinity=False,
                    ),
                    "price": st.floats(
                        min_value=0.01,
                        max_value=10_000.0,
                        allow_nan=False,
                        allow_infinity=False,
                    ),
                    "risk_weight": st.floats(
                        min_value=0.1,
                        max_value=5.0,
                        allow_nan=False,
                        allow_infinity=False,
                    ),
                    "side": st.sampled_from(["long", "short"]),
                }
            ),
            min_size=0,
            max_size=10,
        )
    )
    def test_heat_is_non_negative(self, positions: list[dict]) -> None:
        """Portfolio heat should always be non-negative."""
        heat = portfolio_heat(positions)
        assert heat >= 0.0

    @settings(max_examples=50, deadline=None)
    @given(
        qty=st.floats(min_value=0.1, max_value=100.0),
        price=st.floats(min_value=1.0, max_value=1000.0),
    )
    def test_heat_doubles_with_doubled_position(self, qty: float, price: float) -> None:
        """Doubling position size should double the heat."""
        single = [{"qty": qty, "price": price, "side": "long"}]
        double = [{"qty": 2 * qty, "price": price, "side": "long"}]

        heat_single = portfolio_heat(single)
        heat_double = portfolio_heat(double)

        assert heat_double == pytest.approx(2 * heat_single, rel=1e-6)

    def test_heat_treats_long_and_short_symmetrically(self) -> None:
        """Heat should be the same for long and short positions of equal size."""
        long_pos = [{"qty": 10.0, "price": 100.0, "side": "long"}]
        short_pos = [{"qty": -10.0, "price": 100.0, "side": "short"}]

        assert portfolio_heat(long_pos) == pytest.approx(portfolio_heat(short_pos), rel=1e-9)


class TestOrderProperties:
    """Property-based tests for Order dataclass."""

    @settings(max_examples=50, deadline=None)
    @given(
        side=st.sampled_from(list(OrderSide)),
        qty=st.floats(min_value=0.001, max_value=1000.0),
        price=st.one_of(st.none(), st.floats(min_value=0.01, max_value=100_000.0)),
        order_type=st.sampled_from(list(OrderType)),
    )
    def test_order_creation_is_consistent(
        self, side: OrderSide, qty: float, price: float | None, order_type: OrderType
    ) -> None:
        """Order should be created with provided fields."""
        kwargs: dict[str, float] = {}
        if order_type is OrderType.ICEBERG:
            visible = max(min(qty, qty * 0.5), 1e-9)
            kwargs["iceberg_visible"] = visible

        order = Order(
            symbol="BTCUSD",
            side=side,
            quantity=qty,
            price=price,
            order_type=order_type,
            **kwargs,
        )
        assert order.side == side
        assert order.quantity == qty
        assert order.price == price
        assert order.order_type == order_type
