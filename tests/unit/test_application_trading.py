from application.trading import dto_to_signal, order_to_dto, position_to_dto, signal_to_dto
from domain import Order, OrderSide, OrderStatus, OrderType, Position, Signal, SignalAction


def test_signal_dto_round_trip() -> None:
    signal = Signal(symbol="BTCUSD", action=SignalAction.BUY, confidence=0.8)
    dto = signal_to_dto(signal)
    restored = dto_to_signal(dto)
    assert restored.symbol == signal.symbol
    assert restored.action == signal.action
    assert restored.confidence == signal.confidence


def test_order_position_dto_exports() -> None:
    order = Order(
        symbol="ETHUSD",
        side=OrderSide.SELL,
        quantity=1.5,
        order_type=OrderType.LIMIT,
        price=1800.0,
        status=OrderStatus.OPEN,
    )
    order.mark_submitted("OID-1")
    order.record_fill(0.5, 1795.0)
    order_dto = order_to_dto(order)
    assert order_dto["symbol"] == "ETHUSD"
    assert order_dto["status"] == order.status.value

    position = Position(symbol="ETHUSD")
    position.apply_fill(OrderSide.SELL, 1.0, 1800.0)
    position.mark_to_market(1785.0)
    position_dto = position_to_dto(position)
    assert position_dto["quantity"] == position.quantity
    assert position_dto["unrealized_pnl"] == position.unrealized_pnl
