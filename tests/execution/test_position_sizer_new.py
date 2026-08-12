# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for execution.position_sizer module."""

from __future__ import annotations

import math

import pytest

from execution.position_sizer import calculate_position_size


class TestCalculatePositionSize:
    def test_basic(self):
        qty = calculate_position_size(10000, 0.1, 100)
        assert qty == pytest.approx(10.0)

    def test_zero_balance(self):
        assert calculate_position_size(0, 0.5, 100) == 0.0

    def test_zero_risk(self):
        assert calculate_position_size(10000, 0.0, 100) == 0.0

    def test_full_risk(self):
        qty = calculate_position_size(10000, 1.0, 100)
        assert qty > 0

    def test_risk_clipped_above_one(self):
        q1 = calculate_position_size(10000, 1.0, 100)
        q2 = calculate_position_size(10000, 2.0, 100)
        assert q1 == q2

    def test_risk_clipped_below_zero(self):
        assert calculate_position_size(10000, -0.5, 100) == 0.0

    def test_leverage_cap(self):
        qty = calculate_position_size(1000, 1.0, 10, max_leverage=2.0)
        assert qty <= 1000 * 2.0 / 10

    def test_negative_balance_raises(self):
        with pytest.raises(ValueError, match="balance"):
            calculate_position_size(-100, 0.1, 100)

    def test_zero_price_raises(self):
        with pytest.raises(ValueError, match="price"):
            calculate_position_size(10000, 0.1, 0)

    def test_negative_price_raises(self):
        with pytest.raises(ValueError, match="price"):
            calculate_position_size(10000, 0.1, -50)

    def test_precision_safety(self):
        qty = calculate_position_size(10000, 0.1, 100)
        assert qty * 100 <= 10000 * 0.1

    @pytest.mark.parametrize("risk", [0.01, 0.05, 0.1, 0.5, 1.0])
    def test_various_risks(self, risk):
        qty = calculate_position_size(10000, risk, 50)
        assert qty >= 0

    def test_infinite_balance_fails_closed(self):
        """+inf balance must collapse to a flat position, not an infinite one.

        Regression for a fail-open defect: balance=+inf previously produced an
        infinite quantity (it passes ``balance < 0`` and ``notional <= 0.0``).
        """
        qty = calculate_position_size(math.inf, 0.1, 100)
        assert math.isfinite(qty)
        assert qty == 0.0

    def test_nan_balance_fails_closed(self):
        """NaN balance must collapse to a flat position."""
        qty = calculate_position_size(math.nan, 0.1, 100)
        assert math.isfinite(qty)
        assert qty == 0.0

    def test_nan_price_fails_closed(self):
        """NaN price must collapse to a flat position (non-finite guard)."""
        qty = calculate_position_size(10000, 0.1, math.nan)
        assert math.isfinite(qty)
        assert qty == 0.0
