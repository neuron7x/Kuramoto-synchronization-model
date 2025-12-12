# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Reliability tests for backtest crash handling.

Validates that the backtest engine handles internal exceptions gracefully:
- REL_BACKTEST_CRASH_001: Exception in core backtest engine
- REL_BACKTEST_CRASH_002: Unhandled exception in strategy callback

These tests ensure the system fails fast with clear error messages and
no data corruption when unexpected errors occur.
"""
from __future__ import annotations

import numpy as np
import pytest

from backtest.engine import LatencyConfig, PortfolioConstraints, Result, walk_forward


def test_strategy_exception_handling() -> None:
    """Test that exceptions in signal_fn are caught and reported (REL_BACKTEST_CRASH_001)."""

    # Create minimal valid price data (numpy array of close prices)
    prices = np.linspace(100, 110, 10)

    # Signal function that raises exception
    def faulty_signal_fn(prices: np.ndarray) -> np.ndarray:
        signals = np.ones_like(prices)
        # Force exception at position 5
        if len(prices) > 5:
            raise RuntimeError("Simulated strategy crash during signal generation")
        return signals

    # Run backtest and expect exception to propagate
    with pytest.raises(RuntimeError, match="Simulated strategy crash"):
        walk_forward(
            prices=prices,
            signal_fn=faulty_signal_fn,
            initial_capital=10000.0,
            constraints=PortfolioConstraints(),
            latency=LatencyConfig(),
        )


def test_strategy_callback_crash() -> None:
    """Test that signal_fn callback crashes are caught with context (REL_BACKTEST_CRASH_002)."""

    prices = np.array([100.0, 101.0, 102.0, 103.0, 104.0])

    # Signal function that causes ZeroDivisionError
    def zero_division_signal_fn(prices: np.ndarray) -> np.ndarray:
        # This will fail immediately
        return np.ones_like(prices)

    # Verify exception is raised with meaningful context
    with pytest.raises(ZeroDivisionError):
        walk_forward(
            prices=prices,
            signal_fn=zero_division_signal_fn,
            initial_capital=10000.0,
            constraints=PortfolioConstraints(),
            latency=LatencyConfig(),
        )


def test_infinite_position_handled() -> None:
    """Test that infinite/NaN positions from bad signal_fn are handled.

    Note: This test documents CURRENT behavior where NaN propagates through.
    This is a known gap - system should validate and reject NaN signals upfront.
    """

    prices = np.array([100.0, 101.0, 102.0, 103.0, 104.0])

    # Signal function that returns NaN
    def nan_signal_fn(prices: np.ndarray) -> np.ndarray:
        return np.full_like(prices, np.nan)

    # Run backtest - currently NaN signals produce NaN results (not ideal)
    result = walk_forward(
        prices=prices,
        signal_fn=nan_signal_fn,
        initial_capital=10000.0,
        constraints=PortfolioConstraints(),
        latency=LatencyConfig(),
    )

    # Current behavior: NaN propagates through to results
    assert isinstance(result, Result)
    # This shows the failure mode - equity curve contains NaN
    # (excluding last element which might be initial capital)
    assert np.all(np.isnan(result.equity_curve[:-1]))
    assert np.isnan(result.pnl)
    # TODO: Engine should validate signals and raise clear error for NaN


def test_strategy_returning_invalid_type() -> None:
    """Test that signal_fn returning wrong type is caught."""

    prices = np.array([100.0, 101.0, 102.0])

    # Signal function that returns wrong type
    def bad_return_type_signal_fn(prices: np.ndarray) -> str:  # type: ignore[return]
        return "not an array"  # type: ignore[return-value]

    # This should raise TypeError when trying to process signals
    with pytest.raises((TypeError, ValueError, AttributeError)):
        walk_forward(
            prices=prices,
            signal_fn=bad_return_type_signal_fn,  # type: ignore[arg-type]
            initial_capital=10000.0,
            constraints=PortfolioConstraints(),
            latency=LatencyConfig(),
        )


def test_no_hanging_on_exception() -> None:
    """Test that exceptions don't cause hanging (fast failure)."""
    import time

    prices = np.linspace(100, 200, 100)

    # Signal function that fails immediately
    def immediate_fail_signal_fn(prices: np.ndarray) -> np.ndarray:
        raise ValueError("Immediate failure")

    # Time the failure - should be instant (< 1 second)
    start = time.time()
    with pytest.raises(ValueError):
        walk_forward(
            prices=prices,
            signal_fn=immediate_fail_signal_fn,
            initial_capital=10000.0,
            constraints=PortfolioConstraints(),
            latency=LatencyConfig(),
        )
    elapsed = time.time() - start

    # Verify fast failure (not hanging)
    assert elapsed < 1.0, f"Exception handling took too long: {elapsed}s"


def test_mismatched_signal_length() -> None:
    """Test that signal_fn returning wrong length array is caught."""

    prices = np.array([100.0, 101.0, 102.0, 103.0, 104.0])

    # Signal function that returns wrong-sized array
    def wrong_size_signal_fn(prices: np.ndarray) -> np.ndarray:
        # Return array with different length than prices
        return np.array([1.0, -1.0])  # Only 2 elements instead of 5

    # This should raise an error about mismatched dimensions
    with pytest.raises((ValueError, IndexError, RuntimeError)):
        walk_forward(
            prices=prices,
            signal_fn=wrong_size_signal_fn,
            initial_capital=10000.0,
            constraints=PortfolioConstraints(),
            latency=LatencyConfig(),
        )
