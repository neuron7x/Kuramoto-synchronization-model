"""Tests for Kelly Criterion and Risk Parity functions."""

from __future__ import annotations

import pytest

from core.neuro.sizing import kelly_size, risk_parity_weight


def test_kelly_basic():
    """Test basic Kelly Criterion calculation."""
    # 60% win rate, 2:1 win/loss ratio
    # Kelly = (0.6 * 2 - 0.4) / 2 = 0.4
    size = kelly_size(0.6, 2.0, 1.0, kelly_fraction=1.0, max_leverage=1.0)
    assert abs(size - 0.4) < 1e-6


def test_kelly_fractional():
    """Test fractional Kelly (half-Kelly)."""
    full = kelly_size(0.6, 2.0, 1.0, kelly_fraction=1.0, max_leverage=1.0)
    half = kelly_size(0.6, 2.0, 1.0, kelly_fraction=0.5, max_leverage=1.0)
    assert abs(half - full / 2) < 1e-6


def test_kelly_max_leverage_cap():
    """Test Kelly respects max leverage cap."""
    # Would suggest large position
    size = kelly_size(0.9, 5.0, 1.0, kelly_fraction=1.0, max_leverage=0.5)
    assert size <= 0.5


def test_kelly_zero_when_unfavorable():
    """Test Kelly returns 0 for negative expectancy."""
    # 40% win rate with 1:1 ratio = negative expectancy
    size = kelly_size(0.4, 1.0, 1.0, kelly_fraction=1.0, max_leverage=1.0)
    assert size == 0.0


def test_kelly_invalid_inputs():
    """Test Kelly raises on invalid inputs."""
    with pytest.raises(ValueError):
        kelly_size(0.0, 2.0, 1.0)  # Invalid win_prob

    with pytest.raises(ValueError):
        kelly_size(1.0, 2.0, 1.0)  # Invalid win_prob

    with pytest.raises(ValueError):
        kelly_size(0.6, -1.0, 1.0)  # Negative win_amount

    with pytest.raises(ValueError):
        kelly_size(0.6, 2.0, -1.0)  # Negative loss_amount

    with pytest.raises(ValueError):
        kelly_size(0.6, 2.0, 1.0, kelly_fraction=0.0)  # Invalid fraction

    with pytest.raises(ValueError):
        kelly_size(0.6, 2.0, 1.0, max_leverage=-1.0)  # Negative leverage


def test_risk_parity_basic():
    """Test basic risk parity weighting."""
    vols = [0.10, 0.20, 0.30]
    weights = risk_parity_weight(vols)

    # Should sum to 1.0
    assert abs(sum(weights) - 1.0) < 1e-9

    # Lower vol should get higher weight
    assert weights[0] > weights[1] > weights[2]


def test_risk_parity_equal_vols():
    """Test risk parity with equal volatilities."""
    vols = [0.15, 0.15, 0.15]
    weights = risk_parity_weight(vols)

    # Should be equal weights
    assert all(abs(w - 1 / 3) < 1e-9 for w in weights)


def test_risk_parity_two_assets():
    """Test risk parity with two assets."""
    vols = [0.10, 0.20]
    weights = risk_parity_weight(vols)

    # Lower vol (0.10) should get 2x weight of higher vol (0.20)
    assert abs(weights[0] / weights[1] - 2.0) < 1e-6


def test_risk_parity_invalid_inputs():
    """Test risk parity raises on invalid inputs."""
    with pytest.raises(ValueError):
        risk_parity_weight([])  # Empty list

    with pytest.raises(ValueError):
        risk_parity_weight([0.10, 0.0, 0.20])  # Zero volatility

    with pytest.raises(ValueError):
        risk_parity_weight([0.10, -0.05, 0.20])  # Negative volatility


def test_risk_parity_single_asset():
    """Test risk parity with single asset."""
    vols = [0.15]
    weights = risk_parity_weight(vols)

    # Should be 100%
    assert len(weights) == 1
    assert abs(weights[0] - 1.0) < 1e-9


def test_risk_parity_many_assets():
    """Test risk parity with many assets."""
    vols = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]
    weights = risk_parity_weight(vols)

    # Should sum to 1.0
    assert abs(sum(weights) - 1.0) < 1e-9

    # Should be monotonically decreasing (inverse of vols)
    for i in range(len(weights) - 1):
        assert weights[i] > weights[i + 1]


def test_kelly_and_risk_parity_integration():
    """Test Kelly and risk parity work together for portfolio sizing."""
    # Portfolio with 3 assets
    vols = [0.15, 0.20, 0.10]
    rp_weights = risk_parity_weight(vols)

    # Apply Kelly sizing to each
    win_probs = [0.6, 0.55, 0.65]
    total_size = 0.0

    for weight, prob in zip(rp_weights, win_probs):
        kelly = kelly_size(prob, 2.0, 1.0, kelly_fraction=0.5, max_leverage=1.0)
        sized = weight * kelly
        total_size += sized

    # Total should be reasonable
    assert 0.0 < total_size < 3.0
