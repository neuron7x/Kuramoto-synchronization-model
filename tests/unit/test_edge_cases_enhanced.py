# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Edge case tests for numerical stability in indicators and calculations.

This module validates that indicators and numerical computations handle
edge cases gracefully without producing NaN, Inf, or incorrect results.

Test Coverage:
- Zero variance (constant prices)
- Extreme values (near overflow)
- Minimal data (single/few points)
- Empty datasets
- Negative values (where invalid)
- Division by zero scenarios

These tests complement the main unit tests by focusing specifically on
boundary conditions and numerical edge cases that could cause instability
in production.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.indicators.kuramoto import kuramoto_order
from execution.order import position_sizing
from execution.risk import portfolio_heat


class TestNumericalEdgeCases:
    """Test suite for numerical stability edge cases."""

    def test_kuramoto_order_handles_constant_prices(self) -> None:
        """Test that kuramoto_order handles zero-variance phase series.

        Constant phases can cause issues in synchronization calculations.
        The function should handle this gracefully.

        Validates:
        - No NaN in output
        - No Inf in output
        - Reasonable default behavior
        """
        phases = np.ones(100) * np.pi / 2  # Constant phase
        result = kuramoto_order(phases)

        assert not np.isnan(result), "Result should not be NaN"
        assert not np.isinf(result), "Result should not be Inf"
        assert 0.0 <= result <= 1.0, "Order parameter should be in [0, 1]"

    def test_kuramoto_order_handles_single_phase(self) -> None:
        """Test kuramoto_order with single phase value.

        Validates behavior with minimal input.
        """
        phases = np.array([np.pi / 4])
        result = kuramoto_order(phases)

        assert not np.isnan(result), "Result should not be NaN"
        assert not np.isinf(result), "Result should not be Inf"
        # Single oscillator should have perfect order
        assert result == pytest.approx(1.0, abs=0.01)

    def test_position_sizing_with_zero_balance(self) -> None:
        """Test that position sizing handles zero balance gracefully.

        Zero balance should result in zero position size, not division error.
        """
        size = position_sizing(balance=0.0, risk=0.1, price=100.0)
        assert size == 0.0, "Zero balance should produce zero size"
        assert not np.isnan(size), "Result should not be NaN"

    def test_position_sizing_with_very_high_price(self) -> None:
        """Test position sizing with prices near numerical limits.

        Very high prices could cause overflow in notional calculations.
        """
        size = position_sizing(balance=1000.0, risk=0.1, price=1e10)
        assert size >= 0.0, "Size should be non-negative"
        assert not np.isinf(size), "Size should not be infinite"
        assert size * 1e10 <= 1000.0 * 0.1 * 1.01, "Cost should not exceed risk capital"

    def test_position_sizing_with_very_low_price(self) -> None:
        """Test position sizing with very small prices.

        Very low prices could cause precision loss in calculations.
        """
        size = position_sizing(balance=1000.0, risk=0.1, price=0.001)
        assert size >= 0.0, "Size should be non-negative"
        assert not np.isinf(size), "Size should not be infinite"
        # With low price, size could be large but cost should be bounded
        assert size * 0.001 <= 1000.0 * 0.1 * 1.01, "Cost should not exceed risk capital"

    def test_portfolio_heat_with_empty_positions(self) -> None:
        """Test portfolio heat calculation with no positions.

        Empty portfolio should produce zero heat, not an error.
        """
        heat = portfolio_heat([])
        assert heat == 0.0, "Empty portfolio should have zero heat"
        assert not np.isnan(heat), "Result should not be NaN"

    def test_portfolio_heat_with_zero_quantities(self) -> None:
        """Test portfolio heat with zero-quantity positions.

        Zero quantities should contribute zero to portfolio heat.
        """
        positions = [
            {"qty": 0.0, "price": 100.0},
            {"qty": 0.0, "price": 50.0},
        ]
        heat = portfolio_heat(positions)
        assert heat == 0.0, "Zero quantities should produce zero heat"

    def test_portfolio_heat_with_extreme_prices(self) -> None:
        """Test portfolio heat doesn't overflow with extreme prices.

        Very large positions * prices should not cause overflow.
        """
        positions = [
            {"qty": 1e6, "price": 1e6},  # 1 trillion notional
        ]
        heat = portfolio_heat(positions)
        assert not np.isinf(heat), "Heat should not be infinite"
        assert heat > 0, "Heat should be positive"


class TestBoundaryConditions:
    """Test suite for boundary conditions and minimal inputs."""

    def test_kuramoto_order_with_two_phases(self) -> None:
        """Test kuramoto_order with minimal number of oscillators.

        Validates behavior at the minimum viable input length.
        """
        phases = np.array([0.0, np.pi])  # Opposite phases
        result = kuramoto_order(phases)

        # Two opposite phases should have low order parameter
        assert not np.isnan(result)
        assert 0.0 <= result <= 1.0
        assert result < 0.5, "Opposite phases should have low synchronization"

    def test_position_sizing_at_risk_extremes(self) -> None:
        """Test position sizing at risk percentage boundaries.

        Validates behavior at 0% risk (minimum) and 100% risk (maximum).
        """
        balance = 1000.0
        price = 100.0

        # Zero risk should produce zero or minimal size
        size_zero = position_sizing(balance, risk=0.0, price=price)
        assert size_zero >= 0.0, "Size should be non-negative"
        assert size_zero * price <= balance * 0.01, "Should allocate minimal capital"

        # Full risk should use entire balance
        size_full = position_sizing(balance, risk=1.0, price=price)
        assert size_full > 0, "Size should be positive"
        assert size_full * price <= balance * 1.01, "Should not exceed balance"


class TestErrorConditions:
    """Test suite for error handling and invalid inputs."""

    def test_kuramoto_order_handles_empty_array(self) -> None:
        """Test that kuramoto_order handles empty input gracefully.

        Empty array should either return a sensible default or raise
        an appropriate error.
        """
        phases = np.array([])
        try:
            result = kuramoto_order(phases)
            # If it doesn't raise, result should be sensible
            assert not np.isnan(result) or result == 0.0
        except (ValueError, IndexError):
            # It's also acceptable to raise an error
            pass

    def test_position_sizing_rejects_negative_balance(self) -> None:
        """Test that negative balance is rejected.

        Balance must be non-negative.
        """
        with pytest.raises(ValueError, match="[Bb]alance.*non-negative"):
            position_sizing(balance=-100.0, risk=0.1, price=100.0)

    def test_position_sizing_rejects_negative_price(self) -> None:
        """Test that negative price is rejected.

        Prices must be positive.
        """
        with pytest.raises(ValueError, match="[Pp]rice.*positive"):
            position_sizing(balance=1000.0, risk=0.1, price=-100.0)

    def test_position_sizing_clamps_invalid_risk_percentage(self) -> None:
        """Test that invalid risk percentages are clamped to valid range.

        Risk percentage is automatically clipped to [0, 1] range for safety
        rather than raising an error, as documented in calculate_position_size.
        """
        # Risk > 1.0 should be clamped to 1.0
        size_high = position_sizing(balance=1000.0, risk=1.5, price=100.0)
        size_normal = position_sizing(balance=1000.0, risk=1.0, price=100.0)
        assert size_high == size_normal, "Risk > 1.0 should be clamped to 1.0"

        # Risk < 0.0 should be clamped to 0.0
        size_negative = position_sizing(balance=1000.0, risk=-0.1, price=100.0)
        assert size_negative == 0.0, "Negative risk should be clamped to 0.0"
