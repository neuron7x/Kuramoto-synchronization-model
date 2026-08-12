# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for streaming feature extractors (EWMomentum, EWZScore, EWSkewness)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from core.neuro.features import EWMomentum, EWSkewness, EWZScore


def test_momentum_initialization():
    """Test EWMomentum initialization."""
    mom = EWMomentum(fast_span=12, slow_span=26)
    assert mom.momentum == 0.0


def test_momentum_invalid_spans():
    """Test EWMomentum raises on invalid spans."""
    with pytest.raises(ValueError):
        EWMomentum(fast_span=26, slow_span=12)  # fast >= slow

    with pytest.raises(ValueError):
        EWMomentum(fast_span=0, slow_span=26)  # non-positive

    with pytest.raises(ValueError):
        EWMomentum(fast_span=12, slow_span=12)  # equal


def test_momentum_trending_up():
    """Test EWMomentum detects upward trend."""
    mom = EWMomentum(fast_span=5, slow_span=10)

    # Trending up
    for i in range(50):
        mom.update(100.0 + i)

    # Momentum should be positive
    assert mom.momentum > 0.0


def test_momentum_trending_down():
    """Test EWMomentum detects downward trend."""
    mom = EWMomentum(fast_span=5, slow_span=10)

    # Trending down
    for i in range(50):
        mom.update(100.0 - i)

    # Momentum should be negative
    assert mom.momentum < 0.0


def test_momentum_ranging():
    """Test EWMomentum near zero for ranging market."""
    mom = EWMomentum(fast_span=5, slow_span=10)

    # Ranging around 100
    np.random.seed(42)
    for _ in range(100):
        mom.update(100.0 + np.random.normal(0, 0.5))

    # Momentum should be near zero
    assert abs(mom.momentum) < 5.0


def test_momentum_reset():
    """Test EWMomentum reset."""
    mom = EWMomentum()
    for i in range(20):
        mom.update(100.0 + i)

    assert mom.momentum != 0.0

    mom.reset()
    assert mom.momentum == 0.0


def test_zscore_initialization():
    """Test EWZScore initialization."""
    zs = EWZScore(span=50)
    assert zs.mean == 0.0
    assert zs.std == 1.0


def test_zscore_invalid_params():
    """Test EWZScore raises on invalid parameters."""
    with pytest.raises(ValueError):
        EWZScore(span=0)

    with pytest.raises(ValueError):
        EWZScore(span=50, lambda_var=0.0)

    with pytest.raises(ValueError):
        EWZScore(span=50, lambda_var=1.0)

    with pytest.raises(ValueError):
        EWZScore(span=50, eps=-1e-8)


def test_zscore_standardization():
    """Test EWZScore standardizes data."""
    np.random.seed(42)
    data = np.random.normal(5.0, 2.0, 1000)

    zs = EWZScore(span=50)
    zscores = [zs.update(float(x)) for x in data]

    # After many observations, z-scores should have mean ~0, std ~1
    # (for the recent window)
    recent_zscores = zscores[-100:]
    mean_z = np.mean(recent_zscores)
    std_z = np.std(recent_zscores)

    assert abs(mean_z) < 0.3  # Should be near 0
    assert 0.7 < std_z < 1.3  # Should be near 1


def test_zscore_outlier_detection():
    """Test EWZScore detects outliers."""
    np.random.seed(42)

    zs = EWZScore(span=30)

    # Normal data
    for _ in range(100):
        zs.update(np.random.normal(0, 1))

    # Insert outlier
    outlier_z = zs.update(10.0)

    # Should be high z-score
    assert abs(outlier_z) > 3.0


def test_zscore_mean_tracking():
    """Test EWZScore tracks changing mean."""
    zs = EWZScore(span=20)

    # Data around 0
    for _ in range(50):
        zs.update(np.random.normal(0, 1))

    mean_before = zs.mean

    # Data shifts to around 10
    for _ in range(50):
        zs.update(np.random.normal(10, 1))

    mean_after = zs.mean

    # Mean should have increased
    assert mean_after > mean_before + 5.0


def test_zscore_reset():
    """Test EWZScore reset."""
    zs = EWZScore()
    for i in range(20):
        zs.update(float(i))

    assert zs.mean != 0.0

    zs.reset()
    assert zs.mean == 0.0
    assert zs.std == 1.0


def test_skewness_initialization():
    """Test EWSkewness initialization."""
    skew = EWSkewness(span=50)
    assert skew.skewness == 0.0


def test_skewness_invalid_params():
    """Test EWSkewness raises on invalid parameters."""
    with pytest.raises(ValueError):
        EWSkewness(span=0)

    with pytest.raises(ValueError):
        EWSkewness(span=50, lambda_decay=0.0)

    with pytest.raises(ValueError):
        EWSkewness(span=50, lambda_decay=1.0)


def test_skewness_symmetric_data():
    """Test EWSkewness near zero for symmetric data."""
    np.random.seed(42)
    data = np.random.normal(0, 1, 500)

    skew = EWSkewness(span=50)
    for x in data:
        skew.update(float(x))

    # Symmetric data should have near-zero skewness
    assert abs(skew.skewness) < 0.5


def test_skewness_right_skewed():
    """Test EWSkewness detects right skew (positive)."""
    np.random.seed(42)
    # Right-skewed: lognormal
    data = np.random.lognormal(0, 0.5, 500)

    skew = EWSkewness(span=50)
    for x in data:
        skew.update(float(x))

    # Should be positive
    assert skew.skewness > 0.0


def test_skewness_left_skewed():
    """Test EWSkewness detects left skew (negative)."""
    np.random.seed(42)
    # Left-skewed: negative of lognormal
    data = -np.random.lognormal(0, 0.5, 500)

    skew = EWSkewness(span=50)
    for x in data:
        skew.update(float(x))

    # Should be negative
    assert skew.skewness < 0.0


def test_skewness_reset():
    """Test EWSkewness reset."""
    skew = EWSkewness()
    for i in range(50):
        skew.update(float(i * i))  # Squared values have skew

    assert skew.skewness != 0.0

    skew.reset()
    assert skew.skewness == 0.0


def test_all_features_together():
    """Test all streaming features work together."""
    np.random.seed(42)

    mom = EWMomentum(fast_span=10, slow_span=20)
    zs = EWZScore(span=30)
    skew = EWSkewness(span=40)

    # Generate trending data with noise
    for i in range(200):
        value = 100.0 + i * 0.5 + np.random.normal(0, 2.0)

        m = mom.update(value)
        z = zs.update(value)
        s = skew.update(value)

        # All should produce finite values
        assert math.isfinite(m)
        assert math.isfinite(z)
        assert math.isfinite(s)

    # Uptrend should give positive momentum
    assert mom.momentum > 0.0

    # Recent data should be standardized
    assert abs(zs.mean - 100.0 - 200 * 0.5) < 20.0  # Tracking mean

    # Skewness should be roughly symmetric (normal noise)
    # Note: With trending data, some skewness is expected, so use a relaxed threshold
    assert abs(skew.skewness) < 2.0
