# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for dopamine TD backtesting module."""

import numpy as np
import pandas as pd
import pytest

from backtest.dopamine_td import (
    DopamineTDParams,
    dopamine_td_signal,
    run_dopamine_backtest,
    run_vectorized_dopamine_td,
)


@pytest.fixture
def sample_prices():
    """Generate sample price data for testing."""
    np.random.seed(42)
    # Generate a random walk price series
    returns = np.random.normal(0, 0.01, 1000)
    prices = 100.0 * np.cumprod(1 + returns)
    return prices


@pytest.fixture
def sample_df():
    """Generate sample DataFrame for testing."""
    np.random.seed(42)
    returns = np.random.normal(0, 0.01, 1000)
    prices = 100.0 * np.cumprod(1 + returns)
    df = pd.DataFrame({"close": prices}, index=pd.date_range("2023-01-01", periods=1000, freq="1h"))
    return df


@pytest.fixture
def default_config():
    """Return default configuration."""
    return DopamineTDParams()


def test_dopamine_td_params_defaults():
    """Test that DopamineTDParams has reasonable defaults."""
    config = DopamineTDParams()
    assert 0 < config.discount_gamma <= 1
    assert config.learning_rate_v > 0
    assert config.decay_rate > 0
    assert config.burst_factor > 0
    assert config.k > 0
    assert 0 <= config.theta <= 1
    assert config.c_novelty >= 0


def test_run_vectorized_dopamine_td_basic(sample_df, default_config):
    """Test basic execution of run_vectorized_dopamine_td."""
    result = run_vectorized_dopamine_td(sample_df, default_config)

    # Check output structure
    assert isinstance(result, pd.DataFrame)
    assert len(result) == len(sample_df)
    assert "close" in result.columns
    assert "returns" in result.columns
    assert "rpe" in result.columns
    assert "tonic" in result.columns
    assert "phasic" in result.columns
    assert "dopamine" in result.columns

    # Check value ranges
    assert np.all(np.isfinite(result["dopamine"]))
    assert np.all(result["dopamine"] >= 0)
    assert np.all(result["dopamine"] <= 1)
    assert np.all(result["tonic"] >= 0)
    assert np.all(result["tonic"] <= 1)
    assert np.all(result["phasic"] >= 0)


def test_run_vectorized_dopamine_td_with_novelty(sample_df, default_config):
    """Test run_vectorized_dopamine_td with novelty scores."""
    # Add novelty column
    sample_df["novelty"] = np.random.uniform(0, 0.5, len(sample_df))

    result = run_vectorized_dopamine_td(sample_df, default_config)

    # Check that it runs successfully
    assert isinstance(result, pd.DataFrame)
    assert len(result) == len(sample_df)
    assert "dopamine" in result.columns


def test_dopamine_td_signal_shape(sample_prices, default_config):
    """Test that dopamine_td_signal returns correct shape."""
    signal = dopamine_td_signal(sample_prices, default_config)

    assert isinstance(signal, np.ndarray)
    assert len(signal) == len(sample_prices)
    assert signal.dtype == np.float64


def test_dopamine_td_signal_range(sample_prices, default_config):
    """Test that dopamine_td_signal returns values in [-1, 1] range."""
    signal = dopamine_td_signal(sample_prices, default_config)

    assert np.all(signal >= -1.0)
    assert np.all(signal <= 1.0)
    assert np.all(np.isfinite(signal))


def test_dopamine_td_signal_default_config(sample_prices):
    """Test that dopamine_td_signal works with default config."""
    signal = dopamine_td_signal(sample_prices)

    assert isinstance(signal, np.ndarray)
    assert len(signal) == len(sample_prices)
    assert np.all(signal >= -1.0)
    assert np.all(signal <= 1.0)


def test_run_dopamine_backtest_basic(sample_prices):
    """Test basic execution of run_dopamine_backtest."""
    result = run_dopamine_backtest(sample_prices)

    # Check that result is returned
    assert result is not None

    # Check for expected attributes from Result dataclass
    assert hasattr(result, "pnl")
    assert hasattr(result, "max_dd")
    assert hasattr(result, "trades")
    assert hasattr(result, "equity_curve")


def test_run_dopamine_backtest_with_config(sample_prices):
    """Test run_dopamine_backtest with custom configuration."""
    config = DopamineTDParams(
        discount_gamma=0.95,
        learning_rate_v=0.02,
        k=10.0,
        theta=0.6,
    )

    result = run_dopamine_backtest(sample_prices, config=config, fee=0.001)

    assert result is not None
    assert hasattr(result, "equity_curve")
    assert result.equity_curve is not None


def test_run_dopamine_backtest_with_kwargs(sample_prices):
    """Test run_dopamine_backtest passes kwargs to walk_forward."""
    from backtest.engine import LatencyConfig

    latency = LatencyConfig(signal_to_order=1)

    result = run_dopamine_backtest(
        sample_prices, fee=0.0005, latency=latency, initial_capital=10000.0
    )

    assert result is not None
    assert hasattr(result, "latency_steps")


def test_dopamine_td_signal_deterministic(sample_prices, default_config):
    """Test that dopamine_td_signal is deterministic."""
    signal1 = dopamine_td_signal(sample_prices, default_config)
    signal2 = dopamine_td_signal(sample_prices, default_config)

    np.testing.assert_array_equal(signal1, signal2)


def test_dopamine_td_with_different_params(sample_prices):
    """Test that different parameters produce different signals."""
    config1 = DopamineTDParams(k=5.0)
    config2 = DopamineTDParams(k=10.0)

    signal1 = dopamine_td_signal(sample_prices, config1)
    signal2 = dopamine_td_signal(sample_prices, config2)

    # Signals should be different with different parameters
    assert not np.allclose(signal1, signal2)


def test_run_vectorized_dopamine_td_preserves_index(sample_df, default_config):
    """Test that run_vectorized_dopamine_td preserves the input index."""
    result = run_vectorized_dopamine_td(sample_df, default_config)

    pd.testing.assert_index_equal(result.index, sample_df.index)


def test_dopamine_td_signal_short_series():
    """Test dopamine_td_signal with very short price series."""
    prices = np.array([100.0, 101.0, 99.0, 102.0])
    signal = dopamine_td_signal(prices)

    assert len(signal) == len(prices)
    assert np.all(np.isfinite(signal))
    assert np.all(signal >= -1.0)
    assert np.all(signal <= 1.0)


def test_run_dopamine_backtest_numerical_stability(sample_prices):
    """Test that backtest handles numerical edge cases gracefully."""
    # Add some extreme values
    prices_with_spike = sample_prices.copy()
    prices_with_spike[500] = prices_with_spike[500] * 1.5  # 50% spike

    result = run_dopamine_backtest(prices_with_spike)

    # Should still produce valid results
    assert result is not None
    assert np.isfinite(result.pnl)
    assert np.isfinite(result.max_dd)
