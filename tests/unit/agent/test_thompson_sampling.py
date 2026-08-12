# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for Thompson Sampling bandit algorithm."""

from __future__ import annotations

import math

import pytest

from core.agent.bandits import ThompsonSampling


def test_thompson_initialization():
    """Test Thompson Sampling initialization."""
    ts = ThompsonSampling(["arm1", "arm2", "arm3"])
    assert len(ts.arms) == 3
    assert "arm1" in ts.arms

    # Initial estimates should be 0.5 (uniform prior Beta(1,1))
    for arm in ts.arms:
        assert math.isclose(ts.estimate(arm), 0.5, abs_tol=1e-6)
        assert ts.pulls(arm) == 0


def test_thompson_invalid_priors():
    """Test Thompson Sampling raises on invalid priors."""
    with pytest.raises(ValueError):
        ThompsonSampling(["a"], alpha_prior=-1.0, beta_prior=1.0)

    with pytest.raises(ValueError):
        ThompsonSampling(["a"], alpha_prior=1.0, beta_prior=0.0)


def test_thompson_selection():
    """Test Thompson Sampling arm selection."""
    ts = ThompsonSampling(["arm1", "arm2"])

    # Should select an arm without error
    arm = ts.select()
    assert arm in ["arm1", "arm2"]


def test_thompson_reward_clamping():
    """Test Thompson Sampling clamps rewards to [0, 1]."""
    ts = ThompsonSampling(["arm1"])

    # Update with out-of-bounds rewards
    ts.update("arm1", 2.0)  # Should clamp to 1.0
    ts.update("arm1", -0.5)  # Should clamp to 0.0

    # Should not raise, estimates should be reasonable
    estimate = ts.estimate("arm1")
    assert 0.0 <= estimate <= 1.0


def test_thompson_credible_interval():
    """Test Thompson Sampling credible interval computation."""
    ts = ThompsonSampling(["arm1"])

    # Add some observations
    for _ in range(10):
        ts.update("arm1", 0.8)

    lower, upper = ts.credible_interval("arm1", confidence=0.95)

    # Interval should contain the estimate
    estimate = ts.estimate("arm1")
    assert lower <= estimate <= upper

    # Bounds should be in [0, 1]
    assert 0.0 <= lower <= 1.0
    assert 0.0 <= upper <= 1.0


def test_thompson_add_remove_arm():
    """Test Thompson Sampling dynamic arm management."""
    ts = ThompsonSampling(["arm1"])
    assert len(ts.arms) == 1

    # Add new arm
    ts.add_arm("arm2")
    assert len(ts.arms) == 2
    assert "arm2" in ts.arms

    # Remove arm
    ts.remove_arm("arm2")
    assert len(ts.arms) == 1

    # Removing unknown arm should raise
    with pytest.raises(KeyError):
        ts.remove_arm("unknown")


def test_thompson_unknown_arm_operations():
    """Test Thompson Sampling raises on unknown arms."""
    ts = ThompsonSampling(["arm1"])

    with pytest.raises(KeyError):
        ts.update("unknown", 0.5)

    with pytest.raises(KeyError):
        ts.estimate("unknown")


def test_thompson_no_arms_raises():
    """Test Thompson Sampling raises when selecting with no arms."""
    ts = ThompsonSampling(["arm1"])
    ts.remove_arm("arm1")

    with pytest.raises(ValueError):
        ts.select()
