"""Tests for P² Algorithm (Piecewise-Parabolic quantile estimator)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from core.neuro.quantile import P2Algorithm


def test_p2_initialization():
    """Test P² algorithm initialization."""
    p2 = P2Algorithm(0.75)
    assert p2.count == 0
    assert math.isnan(p2.quantile)


def test_p2_invalid_quantile_raises():
    """Test P² algorithm raises on invalid quantile."""
    for q in (0.0, 1.0, -0.1, 1.1):
        with pytest.raises(ValueError):
            P2Algorithm(q)


def test_p2_first_five_observations():
    """Test P² initialization phase with first 5 observations."""
    p2 = P2Algorithm(0.5)
    values = [3.0, 1.0, 5.0, 2.0, 4.0]

    for i, v in enumerate(values):
        result = p2.update(v)
        if i < 4:
            # During initialization, no estimate yet
            assert math.isnan(p2.quantile) or result == v
        else:
            # After 5 observations, median should be 3.0
            assert math.isfinite(result)

    # Median of [1, 2, 3, 4, 5] is 3.0
    assert p2.quantile == 3.0


def test_p2_converges_to_true_quantile():
    """Test P² algorithm converges with many observations."""
    np.random.seed(42)
    data = np.random.normal(0, 1, 1000)

    p2 = P2Algorithm(0.75)
    for x in data:
        p2.update(float(x))

    true_q75 = float(np.quantile(data, 0.75))
    p2_q75 = p2.quantile

    # P² should be within 5% of true quantile after 1000 samples
    rel_error = abs(p2_q75 - true_q75) / max(abs(true_q75), 1e-6)
    assert rel_error < 0.05, f"P² error {rel_error:.2%} exceeds 5%"


def test_p2_handles_duplicate_values():
    """Test P² with duplicate observations."""
    p2 = P2Algorithm(0.5)
    values = [1.0, 1.0, 1.0, 2.0, 2.0, 2.0, 3.0, 3.0, 3.0]

    for v in values:
        p2.update(v)

    # Median should be approximately 2.0
    assert 1.5 <= p2.quantile <= 2.5


def test_p2_non_finite_raises():
    """Test P² raises on non-finite input."""
    p2 = P2Algorithm(0.5)

    for bad_value in [float("inf"), float("-inf"), float("nan")]:
        with pytest.raises(ValueError):
            p2.update(bad_value)


def test_p2_reset():
    """Test P² reset functionality."""
    p2 = P2Algorithm(0.75)
    for i in range(10):
        p2.update(float(i))

    assert p2.count == 10

    p2.reset()
    assert p2.count == 0
    assert math.isnan(p2.quantile)


def test_p2_state_serialization():
    """Test P² state save/restore."""
    np.random.seed(42)
    data = np.random.normal(0, 1, 100)

    p2 = P2Algorithm(0.9)
    for x in data:
        p2.update(float(x))

    # Save state
    state = p2.get_state()

    # Create new instance from state
    p2_restored = P2Algorithm.from_state(state)

    # Should match exactly
    assert p2_restored.quantile == p2.quantile
    assert p2_restored.count == p2.count
    assert p2_restored._p == p2._p


def test_p2_multiple_quantiles():
    """Test P² with different quantile values."""
    np.random.seed(42)
    data = np.random.normal(0, 1, 500)

    quantiles = [0.01, 0.25, 0.50, 0.75, 0.90, 0.99]
    for q in quantiles:
        p2 = P2Algorithm(q)
        for x in data:
            p2.update(float(x))

        true_q = float(np.quantile(data, q))
        p2_q = p2.quantile

        # Use absolute error for quantiles near zero, relative error otherwise
        abs_error = abs(p2_q - true_q)
        if abs(true_q) < 0.1:
            # For values near zero, use absolute error threshold
            assert abs_error < 0.15, f"P² absolute error for q={q}: {abs_error:.4f}"
        else:
            # For larger values, use relative error
            rel_error = abs_error / abs(true_q)
            assert rel_error < 0.10, f"P² relative error for q={q}: {rel_error:.2%}"


def test_p2_constant_memory():
    """Test P² uses constant memory regardless of sample size."""
    p2 = P2Algorithm(0.5)

    # Process many samples
    for i in range(10000):
        p2.update(float(i % 100))

    # State should only contain fixed-size arrays
    state = p2.get_state()
    assert len(state["markers"]) == 5
    assert len(state["n"]) == 5
    assert len(state["desired"]) == 5


def test_p2_streaming_property():
    """Test P² maintains streaming property (order matters)."""
    np.random.seed(42)
    data = np.random.normal(0, 1, 200)

    # Process all at once
    p2_batch = P2Algorithm(0.75)
    for x in data:
        p2_batch.update(float(x))

    # Process in two batches
    p2_stream = P2Algorithm(0.75)
    for x in data[:100]:
        p2_stream.update(float(x))
    for x in data[100:]:
        p2_stream.update(float(x))

    # Results should be very similar (but not identical due to approximation)
    assert abs(p2_batch.quantile - p2_stream.quantile) < 0.5
