# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for tradepulse.data module public API."""

import numpy as np
import pandas as pd
import pytest


class TestDataModuleImports:
    """Test that all public API imports work correctly."""

    def test_import_validate_ohlcv(self) -> None:
        """Test validate_ohlcv import from tradepulse.data."""
        from tradepulse.data import validate_ohlcv

        assert validate_ohlcv is not None

    def test_import_validate_ohlcv_from_validation(self) -> None:
        """Test validate_ohlcv import from tradepulse.data.validation."""
        from tradepulse.data.validation import validate_ohlcv

        assert validate_ohlcv is not None

    def test_import_ohlcv_validation_result(self) -> None:
        """Test OHLCVValidationResult import from tradepulse.data."""
        from tradepulse.data import OHLCVValidationResult

        assert OHLCVValidationResult is not None

    def test_import_timeseries_validation_config(self) -> None:
        """Test TimeSeriesValidationConfig import from tradepulse.data."""
        from tradepulse.data import TimeSeriesValidationConfig

        assert TimeSeriesValidationConfig is not None

    def test_import_timeseries_validation_error(self) -> None:
        """Test TimeSeriesValidationError import from tradepulse.data."""
        from tradepulse.data import TimeSeriesValidationError

        assert TimeSeriesValidationError is not None

    def test_import_value_column_config(self) -> None:
        """Test ValueColumnConfig import from tradepulse.data."""
        from tradepulse.data import ValueColumnConfig

        assert ValueColumnConfig is not None


class TestValidateOHLCV:
    """Test validate_ohlcv function."""

    def test_validate_valid_data(self) -> None:
        """Test validation of valid OHLCV data."""
        from tradepulse.data.validation import validate_ohlcv

        df = pd.DataFrame(
            {
                "open": [100.0, 101.0, 102.0] * 10,
                "high": [105.0, 106.0, 107.0] * 10,
                "low": [98.0, 99.0, 100.0] * 10,
                "close": [103.0, 104.0, 105.0] * 10,
                "volume": [1000, 1100, 1200] * 10,
            }
        )

        result = validate_ohlcv(df)

        assert result.valid is True
        assert len(result.issues) == 0
        assert result.row_count == 30

    def test_validate_empty_dataframe(self) -> None:
        """Test validation of empty DataFrame."""
        from tradepulse.data.validation import validate_ohlcv

        df = pd.DataFrame()

        result = validate_ohlcv(df)

        assert result.valid is False
        assert "empty" in result.issues[0].lower()

    def test_validate_missing_price_column(self) -> None:
        """Test validation when price column is missing."""
        from tradepulse.data.validation import validate_ohlcv

        df = pd.DataFrame({"volume": [100, 200, 300]})

        result = validate_ohlcv(df)

        assert result.valid is False
        assert any("close" in issue.lower() for issue in result.issues)

    def test_validate_with_nan_values(self) -> None:
        """Test validation with NaN values."""
        from tradepulse.data.validation import validate_ohlcv

        df = pd.DataFrame(
            {
                "close": [100.0, np.nan, 102.0] * 10,
                "volume": [1000, 1100, 1200] * 10,
            }
        )

        result = validate_ohlcv(df)

        # Should have warnings about NaN but may still be valid if below threshold
        assert result.nan_count > 0

    def test_validate_with_negative_prices(self) -> None:
        """Test validation with negative prices."""
        from tradepulse.data.validation import validate_ohlcv

        df = pd.DataFrame(
            {
                "close": [100.0, -50.0, 102.0] * 10,
                "volume": [1000, 1100, 1200] * 10,
            }
        )

        result = validate_ohlcv(df)

        assert result.valid is False
        assert result.negative_count > 0

    def test_validate_with_constant_prices(self) -> None:
        """Test validation with constant prices."""
        from tradepulse.data.validation import validate_ohlcv

        df = pd.DataFrame(
            {
                "close": [100.0] * 30,
                "volume": [1000] * 30,
            }
        )

        result = validate_ohlcv(df)

        assert result.valid is False
        assert any("identical" in issue.lower() for issue in result.issues)

    def test_validate_raises_on_error(self) -> None:
        """Test that raise_on_error=True raises exception."""
        from tradepulse.data.validation import (
            TimeSeriesValidationError,
            validate_ohlcv,
        )

        df = pd.DataFrame()

        with pytest.raises(TimeSeriesValidationError):
            validate_ohlcv(df, raise_on_error=True)

    def test_validate_with_high_low_violations(self) -> None:
        """Test validation catches high < low violations."""
        from tradepulse.data.validation import validate_ohlcv

        df = pd.DataFrame(
            {
                "open": [100.0, 101.0, 102.0] * 10,
                "high": [95.0, 96.0, 97.0] * 10,  # High below low
                "low": [98.0, 99.0, 100.0] * 10,
                "close": [99.0, 98.0, 99.0] * 10,
                "volume": [1000, 1100, 1200] * 10,
            }
        )

        result = validate_ohlcv(df)

        assert result.valid is False
        assert any("high < low" in issue.lower() for issue in result.issues)

    def test_validate_with_negative_volume(self) -> None:
        """Test validation catches negative volume."""
        from tradepulse.data.validation import validate_ohlcv

        df = pd.DataFrame(
            {
                "close": [100.0, 101.0, 102.0] * 10,
                "volume": [1000, -100, 1200] * 10,
            }
        )

        result = validate_ohlcv(df)

        assert result.valid is False
        assert any("negative volume" in issue.lower() for issue in result.issues)


class TestOHLCVValidationResult:
    """Test OHLCVValidationResult class."""

    def test_result_summary(self) -> None:
        """Test OHLCVValidationResult summary method."""
        from tradepulse.data import OHLCVValidationResult

        result = OHLCVValidationResult(
            valid=True,
            row_count=100,
            nan_count=5,
            negative_count=0,
        )

        summary = result.summary()

        assert "PASSED" in summary
        assert "100 rows" in summary

    def test_result_summary_failed(self) -> None:
        """Test OHLCVValidationResult summary for failed validation."""
        from tradepulse.data import OHLCVValidationResult

        result = OHLCVValidationResult(
            valid=False,
            issues=["Empty DataFrame", "Missing column"],
            row_count=0,
        )

        summary = result.summary()

        assert "FAILED" in summary
        assert "2 errors" in summary
