# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unit tests for numeric constants and helper functions."""

from __future__ import annotations

import math

import numpy as np
import pytest

from core.utils.numeric_constants import (
    BINARY_PROB_MIN,
    DIV_SAFE_MIN,
    FLOAT32_EPS,
    FLOAT64_EPS,
    FLOAT_ABS_TOL,
    FLOAT_REL_TOL,
    LOG_SAFE_MIN,
    PROB_CLIP_MAX,
    PROB_CLIP_MIN,
    VARIANCE_SAFE_MIN,
    VOLATILITY_SAFE_MIN,
    ZERO_TOL,
    clip_probability,
    is_effectively_zero,
    safe_divide,
    safe_log,
    safe_sqrt,
)


class TestNumericConstants:
    """Test that numeric constants have sensible values."""

    def test_machine_epsilon_constants(self) -> None:
        """Verify machine epsilon values match NumPy."""
        assert FLOAT64_EPS == pytest.approx(np.finfo(np.float64).eps)
        assert FLOAT32_EPS == pytest.approx(np.finfo(np.float32).eps)
        assert FLOAT32_EPS > FLOAT64_EPS

    def test_safe_min_ordering(self) -> None:
        """Verify safe minimums are properly ordered."""
        # LOG_SAFE_MIN should be smaller as log is more tolerant
        assert LOG_SAFE_MIN < DIV_SAFE_MIN
        assert VARIANCE_SAFE_MIN <= DIV_SAFE_MIN
        assert VOLATILITY_SAFE_MIN >= VARIANCE_SAFE_MIN

    def test_probability_bounds(self) -> None:
        """Verify probability bounds are valid."""
        assert 0 < PROB_CLIP_MIN < 0.5
        assert 0.5 < PROB_CLIP_MAX < 1.0
        assert PROB_CLIP_MIN + PROB_CLIP_MAX == pytest.approx(1.0)
        assert BINARY_PROB_MIN >= PROB_CLIP_MIN

    def test_tolerance_ordering(self) -> None:
        """Verify tolerance constants are properly ordered."""
        assert FLOAT_ABS_TOL <= FLOAT_REL_TOL
        assert ZERO_TOL <= FLOAT_ABS_TOL


class TestSafeDivide:
    """Test safe_divide function."""

    def test_normal_division(self) -> None:
        """Normal division works correctly."""
        assert safe_divide(10.0, 2.0) == pytest.approx(5.0)
        assert safe_divide(-6.0, 3.0) == pytest.approx(-2.0)

    def test_zero_denominator_returns_default(self) -> None:
        """Division by zero returns default value."""
        assert safe_divide(10.0, 0.0) == 0.0
        assert safe_divide(10.0, 0.0, default=-1.0) == -1.0

    def test_small_denominator_returns_default(self) -> None:
        """Very small denominator triggers default."""
        assert safe_divide(10.0, 1e-15) == 0.0
        assert safe_divide(10.0, 1e-15, default=999.0) == 999.0

    def test_custom_min_denom(self) -> None:
        """Custom minimum denominator threshold works."""
        # With default min_denom (1e-12), 1e-14 should return default
        assert safe_divide(10.0, 1e-14) == 0.0
        # With smaller min_denom, division should proceed
        assert safe_divide(10.0, 1e-14, min_denom=1e-15) == pytest.approx(1e15)


class TestSafeLog:
    """Test safe_log function."""

    def test_normal_log(self) -> None:
        """Normal logarithm works correctly."""
        assert safe_log(1.0) == pytest.approx(0.0)
        assert safe_log(math.e) == pytest.approx(1.0)
        assert safe_log(10.0) == pytest.approx(math.log(10.0))

    def test_zero_input_returns_safe_value(self) -> None:
        """Log of zero returns log of minimum value."""
        result = safe_log(0.0)
        assert math.isfinite(result)
        assert result < 0  # log of small positive number is negative

    def test_negative_input_returns_safe_value(self) -> None:
        """Log of negative returns log of minimum value."""
        result = safe_log(-5.0)
        assert math.isfinite(result)
        assert result == safe_log(0.0)

    def test_custom_min_value(self) -> None:
        """Custom minimum value works."""
        result = safe_log(0.0, min_value=0.001)
        expected = math.log(0.001)
        assert result == pytest.approx(expected)


class TestSafeSqrt:
    """Test safe_sqrt function."""

    def test_normal_sqrt(self) -> None:
        """Normal square root works correctly."""
        assert safe_sqrt(4.0) == pytest.approx(2.0)
        assert safe_sqrt(9.0) == pytest.approx(3.0)

    def test_zero_input(self) -> None:
        """Sqrt of zero is zero."""
        assert safe_sqrt(0.0) == 0.0

    def test_negative_input_clamped(self) -> None:
        """Negative input is clamped to zero."""
        assert safe_sqrt(-1.0) == 0.0
        assert safe_sqrt(-100.0) == 0.0

    def test_custom_min_value(self) -> None:
        """Custom minimum value works."""
        result = safe_sqrt(-5.0, min_value=4.0)
        assert result == pytest.approx(2.0)


class TestClipProbability:
    """Test clip_probability function."""

    def test_valid_probability_unchanged(self) -> None:
        """Valid probabilities in middle range are unchanged."""
        assert clip_probability(0.5) == pytest.approx(0.5)
        assert clip_probability(0.3) == pytest.approx(0.3)
        assert clip_probability(0.8) == pytest.approx(0.8)

    def test_zero_clipped(self) -> None:
        """Zero is clipped to PROB_CLIP_MIN."""
        assert clip_probability(0.0) == pytest.approx(PROB_CLIP_MIN)

    def test_one_clipped(self) -> None:
        """One is clipped to PROB_CLIP_MAX."""
        assert clip_probability(1.0) == pytest.approx(PROB_CLIP_MAX)

    def test_negative_clipped(self) -> None:
        """Negative values are clipped to PROB_CLIP_MIN."""
        assert clip_probability(-0.5) == pytest.approx(PROB_CLIP_MIN)

    def test_greater_than_one_clipped(self) -> None:
        """Values > 1 are clipped to PROB_CLIP_MAX."""
        assert clip_probability(1.5) == pytest.approx(PROB_CLIP_MAX)


class TestIsEffectivelyZero:
    """Test is_effectively_zero function."""

    def test_zero_is_zero(self) -> None:
        """Actual zero is effectively zero."""
        assert is_effectively_zero(0.0) is True

    def test_small_values_are_zero(self) -> None:
        """Very small values are effectively zero."""
        assert is_effectively_zero(1e-15) is True
        assert is_effectively_zero(-1e-15) is True

    def test_larger_values_not_zero(self) -> None:
        """Larger values are not effectively zero."""
        assert is_effectively_zero(0.001) is False
        assert is_effectively_zero(-0.001) is False

    def test_custom_tolerance(self) -> None:
        """Custom tolerance works."""
        assert is_effectively_zero(0.001, tol=0.01) is True
        assert is_effectively_zero(0.1, tol=0.01) is False
