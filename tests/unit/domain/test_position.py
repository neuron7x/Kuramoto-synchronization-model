# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import pytest

from domain import OrderSide, Position


def test_position_open_and_mark_to_market() -> None:
    position = Position(symbol="BTCUSD")
    position.apply_fill(OrderSide.BUY, 1.0, 100.0)
    assert position.quantity == pytest.approx(1.0)
    assert position.entry_price == pytest.approx(100.0)
    assert position.unrealized_pnl == pytest.approx(0.0)

    position.mark_to_market(110.0)
    assert position.unrealized_pnl == pytest.approx(10.0)


def test_position_close_and_realize_pnl() -> None:
    position = Position(symbol="BTCUSD")
    position.apply_fill(OrderSide.BUY, 2.0, 50.0)
    position.apply_fill(OrderSide.SELL, 1.0, 60.0)
    assert position.quantity == pytest.approx(1.0)
    assert position.realized_pnl == pytest.approx(10.0)

    position.apply_fill(OrderSide.SELL, 1.0, 40.0)
    assert position.quantity == pytest.approx(0.0)
    assert position.realized_pnl == pytest.approx(0.0)
    assert position.unrealized_pnl == pytest.approx(0.0)


def test_position_flip_resets_cost_basis() -> None:
    position = Position(symbol="BTCUSD")
    position.apply_fill(OrderSide.SELL, 1.0, 200.0)
    position.apply_fill(OrderSide.BUY, 2.0, 210.0)

    assert position.quantity == pytest.approx(1.0)
    assert position.entry_price == pytest.approx(210.0)
