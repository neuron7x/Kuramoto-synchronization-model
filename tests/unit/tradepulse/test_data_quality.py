# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unit tests for data quality validation module."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradepulse.data_quality import (
    DataQualityError,
    DataQualityReport,
    IssueSeverity,
    ValidationConfig,
    require_valid_data,
    validate_historical_data,
)


class TestValidateHistoricalData:
    """Tests for validate_historical_data function."""

    def test_valid_data_passes(self) -> None:
        """Normal data with no issues should validate successfully."""
        df = pd.DataFrame(
            {
                "open": [100.0, 101.0, 102.0, 103.0],
                "high": [101.0, 102.0, 103.0, 104.0],
                "low": [99.0, 100.0, 101.0, 102.0],
                "close": [100.5, 101.5, 102.5, 103.5],
            },
            index=pd.date_range("2023-01-01", periods=4, freq="1h"),
        )

        report = validate_historical_data(df)

        assert report.is_valid
        assert report.errors_count == 0
        assert report.critical_count == 0
        assert report.validated_rows == 4

    def test_skip_validation_flag(self) -> None:
        """Skip validation should return valid report without checking."""
        # Create data with obvious issues
        df = pd.DataFrame(
            {"close": [-1.0, 0.0, 100.0]},
            index=pd.date_range("2023-01-01", periods=3, freq="1h"),
        )

        with pytest.warns(UserWarning, match="validation was skipped"):
            report = validate_historical_data(df, skip_validation=True)

        assert report.is_valid
        assert report.skipped
        assert len(report.issues) == 0

    def test_numpy_array_1d_support(self) -> None:
        """1D numpy arrays should be validated as close prices."""
        prices = np.array([100.0, 101.0, 102.0, 103.0])
        report = validate_historical_data(prices)

        assert report.is_valid
        assert report.validated_rows == 4

    def test_numpy_array_2d_support(self) -> None:
        """2D numpy arrays should be validated as OHLC data."""
        ohlc = np.array(
            [
                [100.0, 101.0, 99.0, 100.5],
                [101.0, 102.0, 100.0, 101.5],
                [102.0, 103.0, 101.0, 102.5],
            ]
        )
        report = validate_historical_data(ohlc)

        assert report.is_valid
        assert report.validated_rows == 3


class TestGapDetection:
    """Tests for gap/missing bar detection."""

    def test_detects_gaps_in_timeseries(self) -> None:
        """Large gaps in time series should be flagged."""
        # Create data with a 5-hour gap (5x the expected 1h timestep)
        index = pd.DatetimeIndex(
            [
                "2023-01-01 09:00",
                "2023-01-01 10:00",
                "2023-01-01 11:00",
                "2023-01-01 16:00",  # 5h gap
                "2023-01-01 17:00",
            ]
        )
        df = pd.DataFrame({"close": [100.0, 101.0, 102.0, 107.0, 108.0]}, index=index)

        report = validate_historical_data(df)

        assert not report.is_valid
        gap_issues = [i for i in report.issues if i.code == "GAP_DETECTED"]
        assert len(gap_issues) >= 1
        assert gap_issues[0].severity == IssueSeverity.ERROR

    def test_small_gaps_tolerated(self) -> None:
        """Small gaps within tolerance should not be flagged."""
        # 1-minute variation on 1-hour data should be tolerated
        index = pd.DatetimeIndex(
            [
                "2023-01-01 09:00:00",
                "2023-01-01 10:00:30",  # 30s late
                "2023-01-01 11:00:00",
            ]
        )
        df = pd.DataFrame({"close": [100.0, 101.0, 102.0]}, index=index)

        report = validate_historical_data(df)

        gap_issues = [i for i in report.issues if i.code == "GAP_DETECTED"]
        assert len(gap_issues) == 0


class TestPriceValidation:
    """Tests for price column validation."""

    def test_detects_negative_prices(self) -> None:
        """Negative prices should be flagged as critical."""
        df = pd.DataFrame(
            {"close": [100.0, -5.0, 102.0]},
            index=pd.date_range("2023-01-01", periods=3, freq="1h"),
        )

        report = validate_historical_data(df)

        assert not report.is_valid
        assert report.critical_count >= 1
        negative_issues = [i for i in report.issues if i.code == "NON_POSITIVE_PRICES"]
        assert len(negative_issues) >= 1

    def test_detects_zero_prices(self) -> None:
        """Zero prices should be flagged as critical."""
        df = pd.DataFrame(
            {"close": [100.0, 0.0, 102.0]},
            index=pd.date_range("2023-01-01", periods=3, freq="1h"),
        )

        report = validate_historical_data(df)

        assert not report.is_valid
        zero_issues = [i for i in report.issues if i.code == "NON_POSITIVE_PRICES"]
        assert len(zero_issues) >= 1

    def test_detects_nan_prices(self) -> None:
        """NaN prices should be flagged as errors."""
        df = pd.DataFrame(
            {"close": [100.0, np.nan, 102.0]},
            index=pd.date_range("2023-01-01", periods=3, freq="1h"),
        )

        report = validate_historical_data(df)

        assert not report.is_valid
        nan_issues = [i for i in report.issues if i.code == "NAN_PRICES"]
        assert len(nan_issues) >= 1
        assert nan_issues[0].severity == IssueSeverity.ERROR

    def test_detects_large_price_jumps(self) -> None:
        """Unrealistically large price jumps should be flagged as warnings."""
        # 100% price jump
        df = pd.DataFrame(
            {"close": [100.0, 200.0, 201.0]},
            index=pd.date_range("2023-01-01", periods=3, freq="1h"),
        )

        report = validate_historical_data(df)

        # Large jumps are warnings, not errors
        assert report.is_valid
        jump_issues = [i for i in report.issues if i.code == "LARGE_PRICE_JUMP"]
        assert len(jump_issues) >= 1
        assert jump_issues[0].severity == IssueSeverity.WARNING

    def test_normal_price_changes_accepted(self) -> None:
        """Normal price changes within threshold should pass."""
        df = pd.DataFrame(
            {"close": [100.0, 105.0, 110.0, 108.0]},  # 5-10% changes
            index=pd.date_range("2023-01-01", periods=4, freq="1h"),
        )

        report = validate_historical_data(df)

        assert report.is_valid
        jump_issues = [i for i in report.issues if i.code == "LARGE_PRICE_JUMP"]
        assert len(jump_issues) == 0


class TestOHLCValidation:
    """Tests for OHLC relationship validation."""

    def test_detects_high_less_than_low(self) -> None:
        """High < Low should be flagged as critical."""
        df = pd.DataFrame(
            {
                "open": [100.0, 101.0],
                "high": [99.0, 102.0],  # First bar: high < low
                "low": [100.0, 100.0],
                "close": [100.5, 101.5],
            },
            index=pd.date_range("2023-01-01", periods=2, freq="1h"),
        )

        report = validate_historical_data(df)

        assert not report.is_valid
        hl_issues = [i for i in report.issues if i.code == "INVALID_HIGH_LOW"]
        assert len(hl_issues) >= 1
        assert hl_issues[0].severity == IssueSeverity.CRITICAL

    def test_detects_high_less_than_open(self) -> None:
        """High < Open should be flagged as critical."""
        df = pd.DataFrame(
            {
                "open": [105.0, 101.0],  # First bar: open > high
                "high": [104.0, 102.0],
                "low": [99.0, 100.0],
                "close": [100.5, 101.5],
            },
            index=pd.date_range("2023-01-01", periods=2, freq="1h"),
        )

        report = validate_historical_data(df)

        assert not report.is_valid
        high_issues = [i for i in report.issues if i.code == "INVALID_HIGH"]
        assert len(high_issues) >= 1

    def test_detects_low_greater_than_close(self) -> None:
        """Low > Close should be flagged as critical."""
        df = pd.DataFrame(
            {
                "open": [100.0, 101.0],
                "high": [105.0, 102.0],
                "low": [101.0, 100.0],  # First bar: low > close
                "close": [100.0, 101.5],
            },
            index=pd.date_range("2023-01-01", periods=2, freq="1h"),
        )

        report = validate_historical_data(df)

        assert not report.is_valid
        low_issues = [i for i in report.issues if i.code == "INVALID_LOW"]
        assert len(low_issues) >= 1

    def test_valid_ohlc_relationships_pass(self) -> None:
        """Valid OHLC relationships should pass validation."""
        df = pd.DataFrame(
            {
                "open": [100.0, 101.0, 102.0],
                "high": [105.0, 106.0, 107.0],
                "low": [98.0, 99.0, 100.0],
                "close": [102.0, 103.0, 104.0],
            },
            index=pd.date_range("2023-01-01", periods=3, freq="1h"),
        )

        report = validate_historical_data(df)

        assert report.is_valid
        ohlc_issues = [
            i
            for i in report.issues
            if i.code in ("INVALID_HIGH_LOW", "INVALID_HIGH", "INVALID_LOW")
        ]
        assert len(ohlc_issues) == 0


class TestDuplicateDetection:
    """Tests for duplicate detection."""

    def test_detects_duplicate_timestamps(self) -> None:
        """Duplicate timestamps should be flagged as errors."""
        index = pd.DatetimeIndex(
            [
                "2023-01-01 09:00",
                "2023-01-01 10:00",
                "2023-01-01 10:00",  # Duplicate
                "2023-01-01 11:00",
            ]
        )
        df = pd.DataFrame({"close": [100.0, 101.0, 101.5, 102.0]}, index=index)

        report = validate_historical_data(df)

        assert not report.is_valid
        dup_issues = [i for i in report.issues if i.code == "DUPLICATE_TIMESTAMPS"]
        assert len(dup_issues) >= 1
        assert dup_issues[0].severity == IssueSeverity.ERROR

    def test_detects_duplicate_rows(self) -> None:
        """Completely duplicate rows should be flagged as warnings."""
        df = pd.DataFrame(
            {
                "close": [100.0, 101.0, 101.0, 102.0],  # Row 2 and 3 are identical
            },
            index=pd.date_range("2023-01-01", periods=4, freq="1h"),
        )

        report = validate_historical_data(df)

        dup_issues = [i for i in report.issues if i.code == "DUPLICATE_ROWS"]
        assert len(dup_issues) >= 1
        assert dup_issues[0].severity == IssueSeverity.WARNING

    def test_unique_data_passes(self) -> None:
        """Unique data should not trigger duplicate warnings."""
        df = pd.DataFrame(
            {"close": [100.0, 101.0, 102.0, 103.0]},
            index=pd.date_range("2023-01-01", periods=4, freq="1h"),
        )

        report = validate_historical_data(df)

        dup_issues = [
            i
            for i in report.issues
            if i.code in ("DUPLICATE_TIMESTAMPS", "DUPLICATE_ROWS")
        ]
        assert len(dup_issues) == 0


class TestTimezoneIssueDetection:
    """Tests for timezone/DST issue detection."""

    def test_detects_dst_like_jumps(self) -> None:
        """Multiple 1-hour deviations might indicate DST issues."""
        # Create data with multiple 1-hour jumps that look like DST transitions
        index = pd.DatetimeIndex(
            [
                "2023-01-01 09:00",
                "2023-01-01 10:00",
                "2023-01-01 12:00",  # 2h gap (1h deviation)
                "2023-01-01 13:00",
                "2023-01-01 15:00",  # Another 2h gap
                "2023-01-01 16:00",
            ]
        )
        df = pd.DataFrame(
            {"close": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]}, index=index
        )

        report = validate_historical_data(df)

        tz_issues = [i for i in report.issues if i.code == "POSSIBLE_TIMEZONE_ISSUE"]
        assert len(tz_issues) >= 1
        assert tz_issues[0].severity == IssueSeverity.WARNING


class TestValidationConfig:
    """Tests for custom validation configuration."""

    def test_custom_max_price_jump(self) -> None:
        """Custom max_price_jump_pct should be respected."""
        df = pd.DataFrame(
            {"close": [100.0, 160.0, 162.0]},  # 60% jump (exceeds default 50%)
            index=pd.date_range("2023-01-01", periods=3, freq="1h"),
        )

        # Default config flags this
        report_default = validate_historical_data(df)
        jump_issues = [i for i in report_default.issues if i.code == "LARGE_PRICE_JUMP"]
        assert len(jump_issues) >= 1

        # Custom config with higher threshold
        config = ValidationConfig(max_price_jump_pct=100.0)
        report_custom = validate_historical_data(df, config=config)
        jump_issues = [i for i in report_custom.issues if i.code == "LARGE_PRICE_JUMP"]
        assert len(jump_issues) == 0

    def test_custom_price_columns(self) -> None:
        """Custom price_columns should be validated."""
        df = pd.DataFrame(
            {
                "bid": [100.0, -1.0, 102.0],  # Negative value in custom column
                "ask": [101.0, 102.0, 103.0],
            },
            index=pd.date_range("2023-01-01", periods=3, freq="1h"),
        )

        config = ValidationConfig(price_columns=("bid", "ask"))
        report = validate_historical_data(df, config=config)

        assert not report.is_valid
        negative_issues = [i for i in report.issues if i.code == "NON_POSITIVE_PRICES"]
        assert len(negative_issues) >= 1
        assert negative_issues[0].details["column"] == "bid"


class TestRequireValidData:
    """Tests for require_valid_data function."""

    def test_raises_on_invalid_data(self) -> None:
        """Should raise DataQualityError on invalid data."""
        df = pd.DataFrame(
            {"close": [-1.0, 100.0, 102.0]},
            index=pd.date_range("2023-01-01", periods=3, freq="1h"),
        )

        with pytest.raises(DataQualityError) as exc_info:
            require_valid_data(df)

        assert "validation failed" in str(exc_info.value)
        assert exc_info.value.report.critical_count >= 1

    def test_returns_report_on_valid_data(self) -> None:
        """Should return report on valid data."""
        df = pd.DataFrame(
            {"close": [100.0, 101.0, 102.0]},
            index=pd.date_range("2023-01-01", periods=3, freq="1h"),
        )

        report = require_valid_data(df)

        assert isinstance(report, DataQualityReport)
        assert report.is_valid

    def test_allow_warnings_flag(self) -> None:
        """allow_warnings=False should raise on warnings too."""
        # Create data with a large but valid price jump (warning)
        df = pd.DataFrame(
            {"close": [100.0, 200.0, 201.0]},
            index=pd.date_range("2023-01-01", periods=3, freq="1h"),
        )

        # With allow_warnings=True (default), should pass
        report = require_valid_data(df, allow_warnings=True)
        assert report.warnings_count >= 1

        # With allow_warnings=False, should raise
        with pytest.raises(DataQualityError) as exc_info:
            require_valid_data(df, allow_warnings=False)

        assert "warnings" in str(exc_info.value)


class TestDataQualityReportSerialization:
    """Tests for DataQualityReport serialization."""

    def test_as_dict_serializable(self) -> None:
        """as_dict should return JSON-serializable dictionary."""
        import json

        df = pd.DataFrame(
            {"close": [100.0, -1.0, 102.0]},
            index=pd.date_range("2023-01-01", periods=3, freq="1h"),
        )

        report = validate_historical_data(df)
        report_dict = report.as_dict()

        # Should be JSON serializable
        json_str = json.dumps(report_dict)
        assert isinstance(json_str, str)

        # Should contain expected fields
        assert "is_valid" in report_dict
        assert "issues" in report_dict
        assert "warnings_count" in report_dict
        assert "errors_count" in report_dict
        assert "critical_count" in report_dict
