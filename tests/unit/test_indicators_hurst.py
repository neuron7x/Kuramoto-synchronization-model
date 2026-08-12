# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for Hurst exponent estimation.

This module tests the HurstFeature class and hurst_exponent function,
including their metadata handling. HurstFeature now supports an optional
use_float32 parameter for memory optimization, which is conditionally
included in metadata only when explicitly enabled.

Tests verify:
- Hurst exponent calculations are within expected ranges
- Metadata contains required keys (min_lag, max_lag)
- Optional use_float32 metadata appears only when enabled
- Edge cases like insufficient data are handled properly
- Performance optimizations preserve accuracy
"""

from __future__ import annotations

import numpy as np
import pytest

from core.indicators.hurst import HurstFeature, hurst_exponent


def test_hurst_exponent_of_brownian_motion_near_half(
    brownian_motion: np.ndarray,
) -> None:
    H = hurst_exponent(brownian_motion, min_lag=2, max_lag=40)
    assert 0.45 <= H <= 0.55, f"Hurst exponent {H} deviates from Brownian expectation"


def test_hurst_returns_default_for_short_series() -> None:
    series = np.linspace(0, 1, 10)
    assert hurst_exponent(series, max_lag=20) == 0.5


def test_hurst_clips_to_unit_interval(brownian_motion: np.ndarray) -> None:
    H = hurst_exponent(brownian_motion * 10, min_lag=2, max_lag=80)
    assert 0.0 <= H <= 1.0


def test_hurst_feature_returns_metadata(brownian_motion: np.ndarray) -> None:
    """Test HurstFeature with default parameters produces minimal metadata."""
    feature = HurstFeature(min_lag=3, max_lag=30, name="hurst")
    outcome = feature.transform(brownian_motion)
    assert outcome.name == "hurst"
    # With default parameters, only lag parameters should be in metadata
    assert outcome.metadata == {"min_lag": 3, "max_lag": 30}
    expected = hurst_exponent(brownian_motion, min_lag=3, max_lag=30)
    assert outcome.value == pytest.approx(expected, rel=1e-12)


def test_hurst_feature_metadata_contains_required_keys(
    brownian_motion: np.ndarray,
) -> None:
    """Test that HurstFeature metadata always contains required keys.

    This test verifies that 'min_lag' and 'max_lag' keys are always present,
    regardless of whether optional optimization parameters are used.
    """
    feature = HurstFeature(min_lag=2, max_lag=40)
    outcome = feature.transform(brownian_motion)

    # Required keys must always be present
    assert "min_lag" in outcome.metadata
    assert "max_lag" in outcome.metadata
    assert outcome.metadata["min_lag"] == 2
    assert outcome.metadata["max_lag"] == 40

    # With default settings, only required keys should be present
    assert set(outcome.metadata.keys()) == {"min_lag", "max_lag"}


def test_hurst_feature_with_float32_adds_metadata(brownian_motion: np.ndarray) -> None:
    """Test that use_float32 parameter adds metadata when enabled."""
    feature = HurstFeature(min_lag=2, max_lag=40, use_float32=True)
    outcome = feature.transform(brownian_motion)

    # Required keys
    assert "min_lag" in outcome.metadata
    assert "max_lag" in outcome.metadata

    # Optional optimization flag should be present when enabled
    assert "use_float32" in outcome.metadata
    assert outcome.metadata["use_float32"] is True

    # Verify computation still works correctly
    expected = hurst_exponent(brownian_motion, min_lag=2, max_lag=40, use_float32=True)
    # Hurst is more sensitive to precision, allow larger tolerance
    assert abs(outcome.value - expected) < 0.01


def test_hurst_feature_float32_preserves_accuracy(brownian_motion: np.ndarray) -> None:
    """Test that float32 optimization doesn't significantly change Hurst results."""
    feature_64 = HurstFeature(min_lag=2, max_lag=50, use_float32=False)
    feature_32 = HurstFeature(min_lag=2, max_lag=50, use_float32=True)

    result_64 = feature_64.transform(brownian_motion)
    result_32 = feature_32.transform(brownian_motion)

    # Results should be close (Hurst is more sensitive to precision)
    assert (
        abs(result_64.value - result_32.value) < 0.2
    ), f"Float32 and float64 Hurst values differ too much: {result_64.value} vs {result_32.value}"

    # Both should be in valid range [0, 1]
    assert 0.0 <= result_64.value <= 1.0
    assert 0.0 <= result_32.value <= 1.0


def test_hurst_feature_float32_metadata_not_present_by_default(
    brownian_motion: np.ndarray,
) -> None:
    """Test that use_float32 is not in metadata when using default value."""
    feature = HurstFeature(min_lag=2, max_lag=40, use_float32=False)
    outcome = feature.transform(brownian_motion)

    # use_float32 should not appear in metadata when False (default)
    assert "use_float32" not in outcome.metadata

    # Only lag parameters should be present
    assert set(outcome.metadata.keys()) == {"min_lag", "max_lag"}
