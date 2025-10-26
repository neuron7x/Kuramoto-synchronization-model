import pytest

from domain import Order, OrderSide, OrderStatus, OrderType


def test_order_rejects_invalid_quantity() -> None:
    with pytest.raises(ValueError, match="quantity must be positive"):
        Order(symbol="BTCUSD", side=OrderSide.BUY, quantity=0.0)


def test_order_fill_progression() -> None:
    order = Order(
        symbol="BTCUSD",
        side=OrderSide.BUY,
        quantity=2.0,
        order_type=OrderType.LIMIT,
        price=100.0,
    )
    order.mark_submitted("abc")
    assert order.status == OrderStatus.OPEN

    order.record_fill(1.0, 99.0)
    assert order.status == OrderStatus.PARTIALLY_FILLED
    assert order.filled_quantity == pytest.approx(1.0)
    assert order.remaining_quantity == pytest.approx(1.0)

    order.record_fill(1.0, 98.0)
    assert order.status == OrderStatus.FILLED
    assert order.remaining_quantity == 0.0
    assert order.average_price == pytest.approx(98.5)


def test_order_cancel_and_reject() -> None:
    order = Order(symbol="BTCUSD", side=OrderSide.SELL, quantity=1.0)
    order.cancel()
    assert order.status == OrderStatus.CANCELLED

    order.reject("venue rejected")
    assert order.status == OrderStatus.REJECTED
    assert getattr(order, "rejection_reason") == "venue rejected"


def test_order_accepts_iceberg_type() -> None:
    order = Order(
        symbol="BTCUSD",
        side=OrderSide.BUY,
        quantity=1.0,
        price=100.0,
        order_type=OrderType.ICEBERG,
        iceberg_visible=0.25,
    )
    assert order.order_type is OrderType.ICEBERG


def test_iceberg_requires_visible_quantity() -> None:
    with pytest.raises(ValueError, match="iceberg orders require iceberg_visible"):
        Order(
            symbol="BTCUSD",
            side=OrderSide.BUY,
            quantity=1.0,
            price=100.0,
            order_type=OrderType.ICEBERG,
        )

    with pytest.raises(ValueError, match="cannot exceed total order quantity"):
        Order(
            symbol="BTCUSD",
            side=OrderSide.BUY,
            quantity=1.0,
            price=100.0,
            order_type=OrderType.ICEBERG,
            iceberg_visible=2.0,
        )
