# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regression: cost basis on a position that flips THROUGH zero.

Bug: the reduce/flip branch discriminated "partial reduction" from "flip" by
magnitude (`abs(net_qty) < abs(previous_qty)`). A flip into a *smaller* opposite
side (long 5 -> sell 8 -> short 3) satisfies that magnitude test and so kept the
stale long entry price, corrupting cost basis and every downstream unrealized/
realized PnL. The discriminator must be the SIGN change, not the magnitude.
"""

from __future__ import annotations

import pytest

from domain.orders import OrderSide
from domain.positions.entity import Position


def test_flip_into_smaller_opposite_side_resets_cost_basis():
    pos = Position("BTCUSD")
    pos.apply_fill(OrderSide.BUY, 5, 100.0)  # long 5 @ 100
    pos.apply_fill(OrderSide.SELL, 8, 120.0)  # sell 8 -> flip to short 3 @ 120

    assert pos.quantity == -3
    # Freshly-opened short at the fill price: entry resets, no unrealized at mark.
    assert pos.entry_price == 120.0
    assert pos.unrealized_pnl == 0.0
    # Realized on the 5 closed longs: (120 - 100) * 5.
    assert pos.realized_pnl == pytest.approx(100.0)


def test_flip_into_larger_opposite_side_resets_cost_basis():
    pos = Position("BTCUSD")
    pos.apply_fill(OrderSide.BUY, 5, 100.0)  # long 5 @ 100
    pos.apply_fill(OrderSide.SELL, 12, 120.0)  # sell 12 -> flip to short 7 @ 120

    assert pos.quantity == -7
    assert pos.entry_price == 120.0
    assert pos.unrealized_pnl == 0.0
    assert pos.realized_pnl == pytest.approx(100.0)


def test_short_flip_into_smaller_long_resets_cost_basis():
    pos = Position("BTCUSD")
    pos.apply_fill(OrderSide.SELL, 5, 100.0)  # short 5 @ 100
    pos.apply_fill(OrderSide.BUY, 8, 80.0)  # buy 8 -> flip to long 3 @ 80

    assert pos.quantity == 3
    assert pos.entry_price == 80.0
    assert pos.unrealized_pnl == 0.0
    # Realized on 5 closed shorts: (80 - 100) * 5 * (-1) = +100.
    assert pos.realized_pnl == pytest.approx(100.0)


def test_same_side_partial_reduction_keeps_entry_price():
    pos = Position("BTCUSD")
    pos.apply_fill(OrderSide.BUY, 5, 100.0)  # long 5 @ 100
    pos.apply_fill(OrderSide.SELL, 3, 120.0)  # sell 3 -> still long 2, entry unchanged

    assert pos.quantity == 2
    assert pos.entry_price == 100.0  # NOT reset — genuine partial reduction
    assert pos.unrealized_pnl == pytest.approx(40.0)  # (120 - 100) * 2
    assert pos.realized_pnl == pytest.approx(60.0)  # (120 - 100) * 3


def test_exact_close_zeroes_cost_basis():
    pos = Position("BTCUSD")
    pos.apply_fill(OrderSide.BUY, 5, 100.0)
    pos.apply_fill(OrderSide.SELL, 5, 120.0)  # flat

    assert pos.quantity == 0
    assert pos.entry_price == 0.0
    assert pos.unrealized_pnl == 0.0
    assert pos.realized_pnl == pytest.approx(100.0)
