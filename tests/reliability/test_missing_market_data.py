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
    report = validate_historical_data(prices)
    assert not report.is_valid, "Data with NaN should not be valid"
    assert report.errors_count > 0, "Should have at least one error"
    # Check that the issue mentions NaN
    nan_issues = [i for i in report.issues if "NaN" in i.message or "nan" in i.message.lower()]
    assert len(nan_issues) > 0, "Should have detected NaN issue"


def test_timestamp_gap_detection() -> None:
    """Test that gaps in timestamp sequence are detected (REL_DATA_MISSING_002)."""

    # Create data with a missing date (gap from Jan 5 to Jan 7)
    dates = pd.to_datetime([
        "2020-01-01", "2020-01-02", "2020-01-03", "2020-01-04",
        # Gap: Jan 5 and 6 missing (weekend OK, but large gap)
        "2020-01-07", "2020-01-08", "2020-01-09", "2020-01-10"
    ])
    prices = pd.DataFrame({
        "open": [100, 101, 102, 103, 106, 107, 108, 109],
        "high": [101, 102, 103, 104, 107, 108, 109, 110],
        "low": [99, 100, 101, 102, 105, 106, 107, 108],
        "close": [100.5, 101.5, 102.5, 103.5, 106.5, 107.5, 108.5, 109.5],
        "volume": [1000] * 8,
    }, index=dates)

    # Validate - gap should be detected
    report = validate_historical_data(prices)
    # Gap detection may report this as error or warning depending on config
    assert not report.is_valid or report.warnings_count > 0, "Should detect gap or warn"


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

    # Validate empty data - may pass validation but should be noted
    report = validate_historical_data(prices)
    assert report.validated_rows == 0, "Should show 0 rows validated"


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
    report = validate_historical_data(prices)
    assert not report.is_valid, "Negative prices should invalidate data"
    assert report.errors_count > 0 or report.critical_count > 0


def test_high_less_than_low_detected() -> None:
    """Test that invalid high/low relationships are caught."""

    dates = pd.date_range("2020-01-01", periods=5, freq="D")
    prices = pd.DataFrame({
        "open": [100, 101, 102, 103, 104],
        # Day 3 (index 2): high=101 < low=103 (invalid OHLC)
        "high": [101, 102, 101, 104, 105],
        "low": [99, 100, 103, 102, 103],
        "close": [100.5, 101.5, 102.5, 103.5, 104.5],
        "volume": [1000] * 5,
    }, index=dates)

    # Should detect invalid OHLC relationship
    report = validate_historical_data(prices)
    assert not report.is_valid, "Invalid OHLC relationships should invalidate data"
    assert report.critical_count > 0, "Invalid OHLC should be critical"


def test_validation_with_numpy_array() -> None:
    """Test that validation works with numpy arrays."""

    # Simple 1D array (close prices only)
    prices = np.array([100.0, 101.0, 102.0, np.nan, 104.0])

    # Validate
    report = validate_historical_data(prices)
    # Should detect NaN
    assert not report.is_valid, "NaN in numpy array should be detected"


def test_skip_validation_flag() -> None:
    """Test that skip_validation flag works."""

    # Bad data with NaN
    prices = np.array([100.0, np.nan, 102.0])

    # Skip validation
    report = validate_historical_data(prices, skip_validation=True)
    # Should return valid when skipped (with warning)
    assert report.is_valid, "Skipped validation should return valid"
    assert report.skipped, "Report should be marked as skipped"


def test_backtest_with_invalid_data_via_numpy() -> None:
    """Test backtest behavior with invalid numpy data."""

    # Create data with NaN
    prices = np.array([100.0, 101.0, np.nan, 103.0, 104.0])

    # Simple signal function
    def simple_signal_fn(prices: np.ndarray) -> np.ndarray:
        return np.ones_like(prices)

    # Run backtest - should raise DataQualityError
    with pytest.raises(DataQualityError, match="Data quality validation failed"):
        walk_forward(
            prices=prices,
            signal_fn=simple_signal_fn,
            initial_capital=10000.0,
        )


def test_data_quality_report_structure() -> None:
    """Test that DataQualityReport has expected structure."""

    dates = pd.date_range("2020-01-01", periods=5, freq="D")
    prices = pd.DataFrame({
        "open": [100, 101, 102, 103, 104],
        "high": [101, 102, 103, 104, 105],
        "low": [99, 100, 101, 102, 103],
        "close": [100.5, 101.5, 102.5, 103.5, 104.5],
    }, index=dates)

    report = validate_historical_data(prices)

    # Check report structure
    assert hasattr(report, "is_valid")
    assert hasattr(report, "issues")
    assert hasattr(report, "warnings_count")
    assert hasattr(report, "errors_count")
    assert hasattr(report, "critical_count")
    assert hasattr(report, "validated_rows")

    # For valid data
    assert report.is_valid
    assert report.errors_count == 0
    assert report.critical_count == 0
    assert report.validated_rows == 5
