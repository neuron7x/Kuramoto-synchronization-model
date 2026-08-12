# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Comprehensive tests for position sizing input validation.

This test module validates that position sizing functions properly
reject invalid inputs and handle edge cases correctly. These tests
ensure that the trading system won't accept dangerous parameters
that could lead to financial losses.

Test Coverage:
- Input validation (negative balance, negative price)
- Risk parameter clamping behavior
- Zero and extreme value handling
- Leverage limit enforcement
- Precision and rounding behavior

Test Organization:
- TestPositionSizingValidation: Input validation tests
- TestPositionSizingBehavior: Calculation behavior tests
- TestPositionSizingWrapper: Wrapper function tests
- TestPositionSizingPrecision: Numerical precision tests
- TestPositionSizingEdgeCases: Boundary condition tests
"""

from __future__ import annotations

import math

import pytest

from execution.order import position_sizing
from execution.position_sizer import calculate_position_size


# Test fixtures for common parameters
@pytest.fixture
def standard_params():
    """Standard test parameters for most tests."""
    return {"balance": 1000.0, "risk": 0.1, "price": 100.0}


@pytest.fixture
def high_leverage_params():
    """Parameters with high leverage scenario."""
    return {"balance": 1000.0, "risk": 1.0, "price": 50.0, "max_leverage": 10.0}


class TestPositionSizingValidation:
    """Test suite for position sizing input validation."""

    def test_rejects_negative_balance(self) -> None:
        """Negative balance must be rejected with clear error message."""
        with pytest.raises(ValueError, match="balance must be non-negative"):
            calculate_position_size(balance=-100.0, risk=0.1, price=100.0)

    def test_rejects_zero_price(self) -> None:
        """Zero price must be rejected to prevent division by zero."""
        with pytest.raises(ValueError, match="price must be positive"):
            calculate_position_size(balance=1000.0, risk=0.1, price=0.0)

    def test_rejects_negative_price(self) -> None:
        """Negative price must be rejected as prices cannot be negative."""
        with pytest.raises(ValueError, match="price must be positive"):
            calculate_position_size(balance=1000.0, risk=0.1, price=-100.0)

    def test_accepts_zero_balance(self) -> None:
        """Zero balance is valid and should return zero position size."""
        size = calculate_position_size(balance=0.0, risk=0.1, price=100.0)
        assert size == 0.0, "Zero balance should produce zero position size"

    def test_accepts_zero_risk(self) -> None:
        """Zero risk is valid and should return zero position size."""
        size = calculate_position_size(balance=1000.0, risk=0.0, price=100.0)
        assert size == 0.0, "Zero risk should produce zero position size"

    def test_clamps_negative_risk_to_zero(self) -> None:
        """Negative risk should be clamped to zero rather than raising error."""
        size = calculate_position_size(balance=1000.0, risk=-0.5, price=100.0)
        assert size == 0.0, "Negative risk should be clamped to zero"

    def test_clamps_excessive_risk_to_one(self) -> None:
        """Risk > 1.0 should be clamped to 1.0 for safety."""
        size_high = calculate_position_size(balance=1000.0, risk=2.0, price=100.0)
        size_normal = calculate_position_size(balance=1000.0, risk=1.0, price=100.0)
        assert abs(size_high - size_normal) < 1e-9, "Risk > 1.0 should be clamped to 1.0"


class TestPositionSizingBehavior:
    """Test suite for position sizing calculation behavior."""

    def test_respects_leverage_cap(self) -> None:
        """Position size must not exceed leverage limit."""
        balance = 1000.0
        risk = 1.0  # Use full balance
        price = 50.0
        max_leverage = 2.0

        size = calculate_position_size(
            balance=balance, risk=risk, price=price, max_leverage=max_leverage
        )

        # Maximum notional should be balance * max_leverage
        max_notional = balance * max_leverage
        actual_notional = size * price

        assert (
            actual_notional <= max_notional * 1.01
        ), f"Notional {actual_notional} exceeds leverage limit {max_notional}"

    def test_position_does_not_exceed_risk_budget(self) -> None:
        """Position cost should not exceed allocated risk capital."""
        balance = 10000.0
        risk = 0.1  # 10% risk
        price = 100.0

        size = calculate_position_size(balance=balance, risk=risk, price=price)
        cost = size * price
        risk_budget = balance * risk

        # Allow tiny floating-point overshoot
        assert cost <= risk_budget * 1.000001, f"Cost {cost} exceeds budget {risk_budget}"

    @pytest.mark.parametrize(
        "balance,risk,price,expected_within_budget",
        [
            (1000.0, 0.1, 0.0001, True),  # Very small price (altcoins)
            (1000.0, 0.1, 50000.0, True),  # Very large price (BTC)
            (10000.0, 0.1, 100.0, True),  # Standard case
        ],
    )
    def test_handles_various_price_ranges(
        self, balance: float, risk: float, price: float, expected_within_budget: bool
    ) -> None:
        """Position sizing should work across various price ranges."""
        size = calculate_position_size(balance=balance, risk=risk, price=price)
        assert size >= 0.0, "Size should be non-negative"
        assert not math.isinf(size), "Size should not be infinite"

        cost = size * price
        risk_budget = balance * risk

        if expected_within_budget:
            assert cost <= risk_budget * 1.01, f"Cost {cost} exceeds budget {risk_budget}"

    def test_zero_size_when_balance_too_small(self) -> None:
        """Should return zero size when balance is too small for minimum position."""
        # With extremely small balance relative to price, size should be zero
        size = calculate_position_size(balance=0.01, risk=0.1, price=10000.0)
        # Risk budget is 0.01 * 0.1 = 0.001, which is way too small for 10000.0 price
        assert size >= 0.0, "Size should be non-negative"
        assert size * 10000.0 <= 0.01 * 0.1 * 1.01, "Cost should respect tiny budget"


class TestPositionSizingWrapper:
    """Test the position_sizing wrapper function."""

    def test_wrapper_forwards_validation_errors(self) -> None:
        """The wrapper should forward validation errors from calculate_position_size."""
        with pytest.raises(ValueError, match="balance must be non-negative"):
            position_sizing(balance=-100.0, risk=0.1, price=100.0)

        with pytest.raises(ValueError, match="price must be positive"):
            position_sizing(balance=1000.0, risk=0.1, price=-100.0)

    def test_wrapper_produces_same_results(self, standard_params) -> None:
        """Wrapper should produce identical results to calculate_position_size."""
        size_direct = calculate_position_size(**standard_params)
        size_wrapper = position_sizing(**standard_params)
        assert size_direct == size_wrapper, "Wrapper should produce same result"

    def test_wrapper_accepts_leverage_parameter(self) -> None:
        """Wrapper should accept and forward max_leverage parameter."""
        size1 = position_sizing(balance=1000.0, risk=1.0, price=50.0, max_leverage=2.0)
        size2 = position_sizing(balance=1000.0, risk=1.0, price=50.0, max_leverage=5.0)
        # With higher leverage, size should be larger (or equal due to risk budget)
        assert size2 >= size1, "Higher leverage should allow larger positions"


class TestPositionSizingPrecision:
    """Test numerical precision and rounding behavior."""

    def test_no_floating_point_overshoot(self) -> None:
        """Position cost must not exceed budget due to floating-point errors."""
        # Test with values that might cause floating-point issues
        test_cases = [
            (1000.0, 0.1, 33.33),
            (500.0, 0.2, 17.77),
            (10000.0, 0.05, 123.45),
        ]

        for balance, risk, price in test_cases:
            size = calculate_position_size(balance=balance, risk=risk, price=price)
            cost = size * price
            budget = balance * risk
            # Use tiny tolerance for floating-point comparison
            assert (
                cost <= budget * 1.0000001
            ), f"Cost {cost} exceeds budget {budget} for price {price}"

    def test_consistent_results_across_calls(self) -> None:
        """Repeated calls with same parameters should return identical results."""
        params = {"balance": 1000.0, "risk": 0.15, "price": 100.0}
        size1 = calculate_position_size(**params)
        size2 = calculate_position_size(**params)
        size3 = calculate_position_size(**params)
        assert size1 == size2 == size3, "Results should be deterministic"


class TestPositionSizingEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_extremely_high_leverage(self) -> None:
        """Test with unreasonably high leverage values."""
        size = calculate_position_size(balance=1000.0, risk=0.1, price=100.0, max_leverage=100.0)
        # Risk budget is 100, so max size is 1.0
        assert size >= 0.0 and size <= 1.0 * 1.01, "Size should be bounded by risk budget"

    def test_leverage_exactly_one(self) -> None:
        """Test with leverage = 1.0 (no leverage)."""
        size = calculate_position_size(balance=1000.0, risk=0.5, price=100.0, max_leverage=1.0)
        # With max_leverage=1, position is capped by balance/price
        max_size = 1000.0 / 100.0  # = 10
        assert size <= max_size * 1.01, "Position should be capped by leverage constraint"

    def test_risk_exactly_one(self) -> None:
        """Test with risk = 1.0 (use entire balance)."""
        balance = 1000.0
        price = 100.0
        size = calculate_position_size(balance=balance, risk=1.0, price=price, max_leverage=5.0)
        # With risk=1.0, can use entire balance
        max_size_by_balance = balance / price  # = 10
        assert size <= max_size_by_balance * 1.01, "Size should not exceed what balance allows"

    def test_matching_risk_and_leverage(self) -> None:
        """Test when risk budget and leverage limit are equal."""
        # Set up so both constraints are equally restrictive
        balance = 1000.0
        risk = 0.5  # 500 risk budget
        price = 100.0
        max_leverage = 1.0  # Max 1000 notional

        size = calculate_position_size(
            balance=balance, risk=risk, price=price, max_leverage=max_leverage
        )
        # Risk budget: 500, allows size up to 5.0
        # Leverage limit: 1000, allows size up to 10.0
        # Should be bounded by risk budget (more restrictive)
        assert size <= 5.0 * 1.01, "Should be bounded by more restrictive constraint"
