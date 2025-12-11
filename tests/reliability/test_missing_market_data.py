# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Reliability tests for missing/invalid market data handling.

Validates data validation and error handling:
- REL_DATA_MISSING_001: NaN values in price data
- REL_DATA_MISSING_002: Gaps in timestamp sequence
- REL_DATA_MISSING_003: Empty dataset

These tests ensure data quality issues are caught early and reported clearly.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.engine import (
    LatencyConfig,
    PortfolioConstraints,
    walk_forward,
)
from tradepulse.data_quality import (
    DataQualityError,
    validate_historical_data,
)


def test_nan_price_detection() -> None:
    """Test that NaN values in price data are detected (REL_DATA_MISSING_001)."""
    
    dates = pd.date_range("2020-01-01", periods=10, freq="D")
    prices = pd.DataFrame({
        "open": [100, 101, np.nan, 103, 104, 105, 106, 107, 108, 109],  # NaN on day 3
        "high": [101, 102, 103, 104, 105, 106, 107, 108, 109, 110],
        "low": [99, 100, 101, 102, 103, 104, 105, 106, 107, 108],
        "close": [100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5, 107.5, 108.5, 109.5],
        "volume": [1000] * 10,
    }, index=dates)
    
    # Validate data - should detect NaN
    with pytest.raises(DataQualityError, match="NaN|null|missing"):
        validate_historical_data(prices)


def test_timestamp_gap_detection() -> None:
    """Test that gaps in timestamp sequence are detected (REL_DATA_MISSING_002)."""
    
    # Create data with a missing date (gap from Jan 5 to Jan 7)
    dates = pd.to_datetime([
        "2020-01-01", "2020-01-02", "2020-01-03", "2020-01-04",
        # Gap: Jan 5 and 6 missing
        "2020-01-07", "2020-01-08", "2020-01-09", "2020-01-10"
    ])
    prices = pd.DataFrame({
        "open": [100, 101, 102, 103, 106, 107, 108, 109],
        "high": [101, 102, 103, 104, 107, 108, 109, 110],
        "low": [99, 100, 101, 102, 105, 106, 107, 108],
        "close": [100.5, 101.5, 102.5, 103.5, 106.5, 107.5, 108.5, 109.5],
        "volume": [1000] * 8,
    }, index=dates)
    
    # Validate with strict gap detection
    with pytest.raises(DataQualityError, match="gap|missing|discontinuous"):
        validate_historical_data(prices, allow_gaps=False)


def test_empty_dataset_handling() -> None:
    """Test that empty datasets are rejected clearly (REL_DATA_MISSING_003)."""
    
    # Create empty DataFrame with correct columns
    prices = pd.DataFrame({
        "open": [],
        "high": [],
        "low": [],
        "close": [],
        "volume": [],
    })
    
    # Validate empty data
    with pytest.raises((DataQualityError, ValueError), match="empty|no data"):
        validate_historical_data(prices)


def test_all_nan_column() -> None:
    """Test that columns with all NaN values are detected."""
    
    dates = pd.date_range("2020-01-01", periods=5, freq="D")
    prices = pd.DataFrame({
        "open": [100, 101, 102, 103, 104],
        "high": [101, 102, 103, 104, 105],
        "low": [99, 100, 101, 102, 103],
        "close": [100.5, 101.5, 102.5, 103.5, 104.5],
        "volume": [np.nan] * 5,  # All volume values are NaN
    }, index=dates)
    
    # Should detect that volume is completely missing
    with pytest.raises(DataQualityError, match="NaN|null|missing|volume"):
        validate_historical_data(prices)


def test_negative_prices_detected() -> None:
    """Test that negative prices are flagged as invalid."""
    
    dates = pd.date_range("2020-01-01", periods=5, freq="D")
    prices = pd.DataFrame({
        "open": [100, 101, -102, 103, 104],  # Negative price
        "high": [101, 102, 103, 104, 105],
        "low": [99, 100, 101, 102, 103],
        "close": [100.5, 101.5, 102.5, 103.5, 104.5],
        "volume": [1000] * 5,
    }, index=dates)
    
    # Should detect negative price
    with pytest.raises(DataQualityError, match="negative|invalid|price"):
        validate_historical_data(prices)


def test_high_less_than_low_detected() -> None:
    """Test that invalid high/low relationships are caught."""
    
    dates = pd.date_range("2020-01-01", periods=5, freq="D")
    prices = pd.DataFrame({
        "open": [100, 101, 102, 103, 104],
        "high": [101, 102, 101, 104, 105],  # high < low on day 3
        "low": [99, 100, 103, 102, 103],
        "close": [100.5, 101.5, 102.5, 103.5, 104.5],
        "volume": [1000] * 5,
    }, index=dates)
    
    # Should detect invalid OHLC relationship
    with pytest.raises(DataQualityError, match="high|low|invalid|OHLC"):
        validate_historical_data(prices)


def test_zero_volume_warning() -> None:
    """Test that zero volume is detected (warning or error depending on config)."""
    
    dates = pd.date_range("2020-01-01", periods=5, freq="D")
    prices = pd.DataFrame({
        "open": [100, 101, 102, 103, 104],
        "high": [101, 102, 103, 104, 105],
        "low": [99, 100, 101, 102, 103],
        "close": [100.5, 101.5, 102.5, 103.5, 104.5],
        "volume": [1000, 0, 1000, 0, 1000],  # Zero volume on some bars
    }, index=dates)
    
    # Zero volume might be a warning rather than hard error
    # Depending on config, this might pass or warn
    try:
        validate_historical_data(prices, allow_zero_volume=True)
        # If it passes, verify we can still backtest with it
        def simple_strategy(prices: pd.DataFrame, i: int) -> float:
            return 1.0
        
        result = walk_forward(
            prices=prices,
            strategy=simple_strategy,
            constraints=PortfolioConstraints(),
            latency=LatencyConfig(),
        )
        assert result is not None
    except DataQualityError:
        # If validation is strict, zero volume should be caught
        pass


def test_missing_required_columns() -> None:
    """Test that missing required columns are detected."""
    
    dates = pd.date_range("2020-01-01", periods=5, freq="D")
    # Missing 'close' column
    prices = pd.DataFrame({
        "open": [100, 101, 102, 103, 104],
        "high": [101, 102, 103, 104, 105],
        "low": [99, 100, 101, 102, 103],
        "volume": [1000] * 5,
    }, index=dates)
    
    # Should detect missing required column
    with pytest.raises((DataQualityError, KeyError), match="close|column|missing"):
        validate_historical_data(prices)
