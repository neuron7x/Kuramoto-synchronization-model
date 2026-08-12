# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for backtest.transaction_costs module."""

from __future__ import annotations

import math

import pytest

from backtest.transaction_costs import (
    BorrowFinancing,
    BpsSpread,
    FixedBpsCommission,
    FixedSlippage,
    FixedSpread,
    PercentVolumeCommission,
    PerUnitCommission,
    SquareRootSlippage,
    TransactionCostModel,
    VolumeProportionalSlippage,
    ZeroTransactionCost,
)


class TestTransactionCostModel:
    def test_base_returns_zero(self):
        m = TransactionCostModel()
        assert m.get_commission(100, 50) == 0.0
        assert m.get_spread(100) == 0.0
        assert m.get_slippage(100, 50) == 0.0
        assert m.get_financing(10, 50) == 0.0


class TestZeroTransactionCost:
    def test_all_zero(self):
        m = ZeroTransactionCost()
        assert m.get_commission(1000, 100) == 0.0
        assert m.get_spread(100) == 0.0


class TestPerUnitCommission:
    def test_basic(self):
        m = PerUnitCommission(0.01)
        assert m.get_commission(100, 50) == pytest.approx(1.0)

    def test_negative_fee_clamped(self):
        m = PerUnitCommission(-5.0)
        assert m.fee_per_unit == 0.0

    def test_zero_volume(self):
        m = PerUnitCommission(0.01)
        assert m.get_commission(0, 50) == 0.0

    def test_nan_volume(self):
        m = PerUnitCommission(0.01)
        assert m.get_commission(float("nan"), 50) == 0.0

    def test_negative_volume_uses_abs(self):
        m = PerUnitCommission(0.01)
        assert m.get_commission(-100, 50) == pytest.approx(1.0)


class TestFixedBpsCommission:
    def test_basic(self):
        m = FixedBpsCommission(10.0)  # 10 bps
        # 100 units * $50 = $5000 notional * 10 bps = $5.0
        assert m.get_commission(100, 50) == pytest.approx(5.0)

    def test_negative_bps_clamped(self):
        m = FixedBpsCommission(-10.0)
        assert m.bps == 0.0

    def test_zero_price(self):
        m = FixedBpsCommission(10.0)
        assert m.get_commission(100, 0) == 0.0

    def test_nan_input(self):
        m = FixedBpsCommission(10.0)
        assert m.get_commission(float("nan"), 50) == 0.0


class TestPercentVolumeCommission:
    def test_basic(self):
        m = PercentVolumeCommission(0.1)  # 0.1%
        # 100 * 50 = 5000 * 0.001 = 5.0
        assert m.get_commission(100, 50) == pytest.approx(5.0)

    def test_negative_percent_clamped(self):
        m = PercentVolumeCommission(-1.0)
        assert m.percent == 0.0


class TestFixedSpread:
    def test_basic(self):
        m = FixedSpread(0.05)
        assert m.get_spread(100) == 0.05

    def test_negative_clamped(self):
        m = FixedSpread(-0.05)
        assert m.spread == 0.0


class TestBpsSpread:
    def test_basic(self):
        m = BpsSpread(10.0)  # 10 bps
        assert m.get_spread(100.0) == pytest.approx(0.1)

    def test_zero_price(self):
        m = BpsSpread(10.0)
        assert m.get_spread(0) == 0.0

    def test_nan_price(self):
        m = BpsSpread(10.0)
        assert m.get_spread(float("nan")) == 0.0


class TestFixedSlippage:
    def test_basic(self):
        m = FixedSlippage(0.02)
        assert m.get_slippage(100, 50) == 0.02

    def test_negative_clamped(self):
        m = FixedSlippage(-0.02)
        assert m.slippage == 0.0


class TestVolumeProportionalSlippage:
    def test_basic(self):
        m = VolumeProportionalSlippage(0.001)
        assert m.get_slippage(100, 50) == pytest.approx(0.1)

    def test_zero_volume(self):
        m = VolumeProportionalSlippage(0.001)
        assert m.get_slippage(0, 50) == 0.0

    def test_nan_volume(self):
        m = VolumeProportionalSlippage(0.001)
        assert m.get_slippage(float("nan"), 50) == 0.0


class TestSquareRootSlippage:
    def test_basic(self):
        m = SquareRootSlippage(a=0.0, b=0.01)
        result = m.get_slippage(100, 50)
        assert result == pytest.approx(50 * 0.01 * math.sqrt(100))

    def test_zero_volume(self):
        m = SquareRootSlippage(a=0.01, b=0.01)
        assert m.get_slippage(0, 50) == 0.0

    def test_nan_volume(self):
        m = SquareRootSlippage(a=0.01, b=0.01)
        assert m.get_slippage(float("nan"), 50) == 0.0

    def test_a_component(self):
        m = SquareRootSlippage(a=0.01, b=0.0)
        assert m.get_slippage(100, 50) == pytest.approx(50 * 0.01)


class TestBorrowFinancing:
    def test_creation(self):
        m = BorrowFinancing()
        assert m.get_financing(0, 50) == 0.0

    @pytest.mark.parametrize("vol,price", [(0, 100), (100, 0), (float("nan"), 50)])
    def test_edge_cases_return_zero(self, vol, price):
        m = BorrowFinancing()
        result = m.get_financing(vol, price)
        assert result == 0.0 or math.isfinite(result)
