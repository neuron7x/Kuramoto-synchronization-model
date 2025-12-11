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
import pandas as pd
import pytest

from backtest.engine import (
    LatencyConfig,
    PortfolioConstraints,
    Result,
    walk_forward,
)


def test_strategy_exception_handling() -> None:
    """Test that exceptions in strategy are caught and reported (REL_BACKTEST_CRASH_001)."""
    
    # Create minimal valid price data
    dates = pd.date_range("2020-01-01", periods=10, freq="D")
    prices = pd.DataFrame({
        "open": np.linspace(100, 110, 10),
        "high": np.linspace(101, 111, 10),
        "low": np.linspace(99, 109, 10),
        "close": np.linspace(100.5, 110.5, 10),
        "volume": np.ones(10) * 1000,
    }, index=dates)
    
    # Strategy that raises exception on bar 5
    def faulty_strategy(prices: pd.DataFrame, i: int) -> float:
        if i == 5:
            raise RuntimeError("Simulated strategy crash on bar 5")
        return 1.0 if i % 2 == 0 else -1.0
    
    # Run backtest and expect exception to propagate
    with pytest.raises(RuntimeError, match="Simulated strategy crash on bar 5"):
        walk_forward(
            prices=prices,
            strategy=faulty_strategy,
            constraints=PortfolioConstraints(),
            latency=LatencyConfig(),
        )


def test_strategy_callback_crash() -> None:
    """Test that strategy callback crashes are caught with context (REL_BACKTEST_CRASH_002)."""
    
    dates = pd.date_range("2020-01-01", periods=5, freq="D")
    prices = pd.DataFrame({
        "open": [100, 101, 102, 103, 104],
        "high": [101, 102, 103, 104, 105],
        "low": [99, 100, 101, 102, 103],
        "close": [100.5, 101.5, 102.5, 103.5, 104.5],
        "volume": [1000] * 5,
    }, index=dates)
    
    # Strategy that causes ZeroDivisionError
    def zero_division_strategy(prices: pd.DataFrame, i: int) -> float:
        # This will fail on bar 0
        return 1.0 / (i - 0)
    
    # Verify exception is raised with meaningful context
    with pytest.raises(ZeroDivisionError):
        walk_forward(
            prices=prices,
            strategy=zero_division_strategy,
            constraints=PortfolioConstraints(),
            latency=LatencyConfig(),
        )


def test_infinite_position_handled() -> None:
    """Test that infinite/NaN positions from bad strategy are detected."""
    
    dates = pd.date_range("2020-01-01", periods=5, freq="D")
    prices = pd.DataFrame({
        "open": [100, 101, 102, 103, 104],
        "high": [101, 102, 103, 104, 105],
        "low": [99, 100, 101, 102, 103],
        "close": [100.5, 101.5, 102.5, 103.5, 104.5],
        "volume": [1000] * 5,
    }, index=dates)
    
    # Strategy that returns NaN
    def nan_strategy(prices: pd.DataFrame, i: int) -> float:
        return float("nan")
    
    # Run backtest - NaN positions should be handled
    result = walk_forward(
        prices=prices,
        strategy=nan_strategy,
        constraints=PortfolioConstraints(),
        latency=LatencyConfig(),
    )
    
    # Verify result is valid (engine should handle NaN gracefully)
    assert isinstance(result, Result)
    # NaN signals should result in zero positions (no trades)
    assert not np.any(np.isnan(result.positions)) or np.all(result.positions == 0)


def test_strategy_returning_invalid_type() -> None:
    """Test that strategy returning wrong type is caught."""
    
    dates = pd.date_range("2020-01-01", periods=3, freq="D")
    prices = pd.DataFrame({
        "open": [100, 101, 102],
        "high": [101, 102, 103],
        "low": [99, 100, 101],
        "close": [100.5, 101.5, 102.5],
        "volume": [1000] * 3,
    }, index=dates)
    
    # Strategy that returns a string instead of float
    def bad_return_type_strategy(prices: pd.DataFrame, i: int) -> str:  # type: ignore[return]
        return "not a number"  # type: ignore[return-value]
    
    # This should raise TypeError when trying to convert to position
    with pytest.raises((TypeError, ValueError)):
        walk_forward(
            prices=prices,
            strategy=bad_return_type_strategy,  # type: ignore[arg-type]
            constraints=PortfolioConstraints(),
            latency=LatencyConfig(),
        )


def test_no_hanging_on_exception() -> None:
    """Test that exceptions don't cause hanging (fast failure)."""
    import time
    
    dates = pd.date_range("2020-01-01", periods=100, freq="D")
    prices = pd.DataFrame({
        "open": np.linspace(100, 200, 100),
        "high": np.linspace(101, 201, 100),
        "low": np.linspace(99, 199, 100),
        "close": np.linspace(100.5, 200.5, 100),
        "volume": np.ones(100) * 1000,
    }, index=dates)
    
    # Strategy that fails immediately
    def immediate_fail_strategy(prices: pd.DataFrame, i: int) -> float:
        raise ValueError("Immediate failure")
    
    # Time the failure - should be instant (< 1 second)
    start = time.time()
    with pytest.raises(ValueError):
        walk_forward(
            prices=prices,
            strategy=immediate_fail_strategy,
            constraints=PortfolioConstraints(),
            latency=LatencyConfig(),
        )
    elapsed = time.time() - start
    
    # Verify fast failure (not hanging)
    assert elapsed < 1.0, f"Exception handling took too long: {elapsed}s"
