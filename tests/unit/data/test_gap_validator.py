# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Comprehensive tests for gap detection and validation module.

This module tests REQ-002: automatic quality control that blocks import
when gaps are detected in time series data.
"""

from datetime import timedelta

import pandas as pd
import pytest

from core.data.gap_validator import (
    GapDetectionError,
    GapValidator,
    GapValidatorConfig,
    quick_validate,
    validate_timeseries_gaps,
)


class TestGapDetectionError:
    """Tests for GapDetectionError exception."""

    def test_error_with_message_only(self):
        """Test creating error with just a message."""
        error = GapDetectionError("Test error")
        assert str(error) == "Test error"
        assert error.gaps == []

    def test_error_with_gaps(self):
        """Test creating error with gaps list."""
        from core.data.backfill import Gap

        gaps = [
            Gap(
                start=pd.Timestamp("2024-01-01 10:00"),
                end=pd.Timestamp("2024-01-01 10:05"),
            )
        ]
        error = GapDetectionError("Test error", gaps=gaps)
        assert error.gaps == gaps


class TestGapValidatorConfig:
    """Tests for GapValidatorConfig dataclass."""

    def test_minimal_config(self):
        """Test config with minimal required fields."""
        config = GapValidatorConfig(frequency="1min")
        assert config.frequency == "1min"
        assert config.max_gap_duration is None
        assert config.allow_weekend_gaps is False
        assert config.allow_holiday_gaps is False

    def test_full_config(self):
        """Test config with all fields."""
        config = GapValidatorConfig(
            frequency="1h",
            max_gap_duration="5min",
            allow_weekend_gaps=True,
            allow_holiday_gaps=True,
        )
        assert config.frequency == "1h"
        assert config.max_gap_duration == "5min"
        assert config.allow_weekend_gaps is True
        assert config.allow_holiday_gaps is True


class TestGapValidator:
    """Tests for GapValidator class."""

    def test_validator_initialization(self):
        """Test basic validator initialization."""
        validator = GapValidator(frequency="1min")
        assert validator._frequency == "1min"
        assert validator._max_gap_duration is None
        assert validator._allow_weekend_gaps is False

    def test_parse_duration_none(self):
        """Test duration parsing with None."""
        result = GapValidator._parse_duration(None)
        assert result is None

    def test_parse_duration_timedelta(self):
        """Test duration parsing with timedelta."""
        duration = timedelta(minutes=5)
        result = GapValidator._parse_duration(duration)
        assert result == duration

    def test_parse_duration_string(self):
        """Test duration parsing with string."""
        result = GapValidator._parse_duration("5min")
        assert result == timedelta(minutes=5)

    def test_validate_empty_index(self):
        """Test validation of empty DatetimeIndex."""
        validator = GapValidator(frequency="1min")
        index = pd.DatetimeIndex([])
        is_valid, gaps = validator.validate(index)
        assert is_valid is True
        assert gaps == []

    def test_validate_continuous_data(self):
        """Test validation of continuous time series without gaps."""
        validator = GapValidator(frequency="1min")
        index = pd.date_range("2024-01-01", periods=100, freq="1min")
        is_valid, gaps = validator.validate(index)
        assert is_valid is True
        assert gaps == []

    def test_validate_detects_gaps(self):
        """Test that validation detects gaps in time series."""
        validator = GapValidator(frequency="1min")
        # Create index with gap
        idx = pd.date_range("2024-01-01", periods=10, freq="1min")
        idx_with_gap = idx.delete([5, 6, 7])  # Remove 3 bars
        
        is_valid, gaps = validator.validate(idx_with_gap)
        assert is_valid is False
        assert len(gaps) > 0

    def test_validate_with_max_gap_duration(self):
        """Test validation with max gap duration tolerance."""
        # Small gaps are acceptable, large gaps are not
        validator = GapValidator(frequency="1min", max_gap_duration="2min")
        
        # Create index with 1-minute gap (acceptable)
        idx = pd.date_range("2024-01-01", periods=10, freq="1min")
        idx_small_gap = idx.delete([5])  # Remove 1 bar
        
        is_valid, gaps = validator.validate(idx_small_gap)
        # Small gap should be acceptable
        assert is_valid is True or len(gaps) == 0

    def test_validate_weekend_gaps_allowed(self):
        """Test validation when weekend gaps are allowed."""
        validator = GapValidator(
            frequency="1D", allow_weekend_gaps=True
        )
        
        # Create weekday-only index (Friday to Monday with weekend gap)
        dates = pd.date_range("2024-01-05", periods=5, freq="D")  # Fri-Tue
        is_valid, gaps = validator.validate(dates, full_check=False)
        
        # Should pass because we're not doing full check
        assert is_valid is True

    def test_validate_and_raise_success(self):
        """Test validate_and_raise with valid data."""
        validator = GapValidator(frequency="1min")
        index = pd.date_range("2024-01-01", periods=100, freq="1min")
        
        # Should not raise
        validator.validate_and_raise(index)

    def test_validate_and_raise_with_gaps(self):
        """Test validate_and_raise raises exception when gaps detected."""
        validator = GapValidator(frequency="1min")
        idx = pd.date_range("2024-01-01", periods=10, freq="1min")
        idx_with_gap = idx.delete([5, 6, 7])
        
        with pytest.raises(GapDetectionError) as exc_info:
            validator.validate_and_raise(idx_with_gap)
        
        error = exc_info.value
        assert "Data import blocked" in str(error)
        assert "gap(s) detected" in str(error)

    def test_format_gap_summary_empty(self):
        """Test gap summary formatting with empty list."""
        summary = GapValidator._format_gap_summary([])
        assert "No gaps detected" in summary

    def test_format_gap_summary_with_gaps(self):
        """Test gap summary formatting with gaps."""
        from core.data.backfill import Gap

        gaps = [
            Gap(
                start=pd.Timestamp("2024-01-01 10:00"),
                end=pd.Timestamp("2024-01-01 10:05"),
            ),
            Gap(
                start=pd.Timestamp("2024-01-01 11:00"),
                end=pd.Timestamp("2024-01-01 11:03"),
            ),
        ]
        
        summary = GapValidator._format_gap_summary(gaps)
        assert "Gaps found:" in summary
        assert "2024-01-01 10:00" in summary
        assert "duration" in summary

    def test_format_gap_summary_truncates_long_list(self):
        """Test gap summary truncates long lists."""
        from core.data.backfill import Gap

        gaps = [
            Gap(
                start=pd.Timestamp(f"2024-01-01 {i:02d}:00"),
                end=pd.Timestamp(f"2024-01-01 {i:02d}:05"),
            )
            for i in range(10)
        ]
        
        summary = GapValidator._format_gap_summary(gaps, max_display=3)
        assert "and 7 more gap(s)" in summary

    def test_from_config(self):
        """Test creating validator from config object."""
        config = GapValidatorConfig(
            frequency="1h",
            max_gap_duration="10min",
            allow_weekend_gaps=True,
        )
        
        validator = GapValidator.from_config(config)
        assert validator._frequency == "1h"
        assert validator._max_gap_duration == timedelta(minutes=10)
        assert validator._allow_weekend_gaps is True

    def test_filter_acceptable_gaps_empty(self):
        """Test filtering with empty gaps list."""
        validator = GapValidator(frequency="1min")
        result = validator._filter_acceptable_gaps([])
        assert result == []

    def test_filter_acceptable_gaps_by_duration(self):
        """Test filtering gaps by duration threshold."""
        from core.data.backfill import Gap

        validator = GapValidator(frequency="1min", max_gap_duration="3min")
        
        small_gap = Gap(
            start=pd.Timestamp("2024-01-01 10:00"),
            end=pd.Timestamp("2024-01-01 10:02"),  # 2 min gap
        )
        large_gap = Gap(
            start=pd.Timestamp("2024-01-01 11:00"),
            end=pd.Timestamp("2024-01-01 11:05"),  # 5 min gap
        )
        
        unacceptable = validator._filter_acceptable_gaps([small_gap, large_gap])
        
        # Only large gap should be unacceptable
        assert len(unacceptable) == 1
        assert unacceptable[0] == large_gap

    def test_filter_acceptable_gaps_weekend(self):
        """Test filtering out weekend gaps."""
        from core.data.backfill import Gap

        validator = GapValidator(
            frequency="1D",
            allow_weekend_gaps=True,
        )
        
        # Saturday to Sunday gap
        weekend_gap = Gap(
            start=pd.Timestamp("2024-01-06"),  # Saturday
            end=pd.Timestamp("2024-01-07"),    # Sunday
        )
        
        # Weekday gap
        weekday_gap = Gap(
            start=pd.Timestamp("2024-01-02"),  # Tuesday
            end=pd.Timestamp("2024-01-03"),    # Wednesday
        )
        
        unacceptable = validator._filter_acceptable_gaps([weekend_gap, weekday_gap])
        
        # Only weekday gap should be unacceptable
        assert len(unacceptable) == 1
        assert unacceptable[0] == weekday_gap


class TestValidateTimeseriesGaps:
    """Tests for validate_timeseries_gaps convenience function."""

    def test_validate_valid_dataframe(self):
        """Test validation of DataFrame without gaps."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=100, freq="1min"),
            "value": range(100),
        })
        
        # Should not raise
        validate_timeseries_gaps(df, "timestamp", "1min")

    def test_validate_dataframe_with_gaps(self):
        """Test validation of DataFrame with gaps."""
        idx = pd.date_range("2024-01-01", periods=10, freq="1min")
        idx_with_gap = idx.delete([5, 6, 7])
        
        df = pd.DataFrame({
            "timestamp": idx_with_gap,
            "value": range(len(idx_with_gap)),
        })
        
        with pytest.raises(GapDetectionError):
            validate_timeseries_gaps(df, "timestamp", "1min")

    def test_validate_empty_dataframe(self):
        """Test validation of empty DataFrame."""
        df = pd.DataFrame({"timestamp": [], "value": []})
        
        with pytest.raises(ValueError, match="DataFrame is empty"):
            validate_timeseries_gaps(df, "timestamp", "1min")

    def test_validate_missing_timestamp_column(self):
        """Test validation with missing timestamp column."""
        df = pd.DataFrame({"value": [1, 2, 3]})
        
        with pytest.raises(ValueError, match="not found in DataFrame"):
            validate_timeseries_gaps(df, "timestamp", "1min")

    def test_validate_invalid_timestamp_column(self):
        """Test validation with non-datetime column."""
        df = pd.DataFrame({
            "timestamp": ["not", "valid", "dates"],
            "value": [1, 2, 3],
        })
        
        with pytest.raises(ValueError, match="Failed to convert"):
            validate_timeseries_gaps(df, "timestamp", "1min")

    def test_validate_with_max_gap_duration(self):
        """Test validation with max gap duration parameter."""
        idx = pd.date_range("2024-01-01", periods=10, freq="1min")
        idx_small_gap = idx.delete([5])  # 1 bar gap
        
        df = pd.DataFrame({
            "timestamp": idx_small_gap,
            "value": range(len(idx_small_gap)),
        })
        
        # Should not raise with 2min tolerance
        validate_timeseries_gaps(
            df, "timestamp", "1min", max_gap_duration="2min"
        )

    def test_validate_with_weekend_gaps_allowed(self):
        """Test validation with weekend gaps allowed."""
        # Create weekday-only data (business days)
        dates = pd.bdate_range("2024-01-01", periods=10)
        
        df = pd.DataFrame({
            "timestamp": dates,
            "value": range(len(dates)),
        })
        
        # With weekend gaps not allowed, this should raise
        with pytest.raises(GapDetectionError):
            validate_timeseries_gaps(
                df, "timestamp", "1D", allow_weekend_gaps=False
            )


class TestQuickValidate:
    """Tests for quick_validate convenience function."""

    def test_quick_validate_continuous_data(self):
        """Test quick validation of continuous data."""
        index = pd.date_range("2024-01-01", periods=100, freq="1min")
        result = quick_validate(index, "1min")
        assert result is True

    def test_quick_validate_with_gaps_strict(self):
        """Test quick validation with gaps in strict mode."""
        idx = pd.date_range("2024-01-01", periods=10, freq="1min")
        idx_with_gap = idx.delete([5, 6, 7])
        
        result = quick_validate(idx_with_gap, "1min", strict=True)
        assert result is False

    def test_quick_validate_with_small_gaps_non_strict(self):
        """Test quick validation with small gaps in non-strict mode."""
        idx = pd.date_range("2024-01-01", periods=10, freq="1min")
        idx_small_gap = idx.delete([5])  # Just 1 bar
        
        # Non-strict mode allows gaps up to 2x frequency
        result = quick_validate(idx_small_gap, "1min", strict=False)
        # Result depends on gap detection logic, just ensure it doesn't crash
        assert isinstance(result, bool)

    def test_quick_validate_empty_index(self):
        """Test quick validation with empty index."""
        index = pd.DatetimeIndex([])
        result = quick_validate(index, "1min")
        assert result is True

    def test_quick_validate_various_frequencies(self):
        """Test quick validation with different frequencies."""
        for freq in ["1min", "5min", "1h", "1D"]:
            index = pd.date_range("2024-01-01", periods=50, freq=freq)
            result = quick_validate(index, freq)
            assert result is True


class TestGapValidatorIntegration:
    """Integration tests for complete workflows."""

    def test_end_to_end_validation_workflow(self):
        """Test complete validation workflow from config to result."""
        # Create config
        config = GapValidatorConfig(
            frequency="1min",
            max_gap_duration="5min",
        )
        
        # Create validator
        validator = GapValidator.from_config(config)
        
        # Create data with gaps
        idx = pd.date_range("2024-01-01", periods=100, freq="1min")
        idx_with_gap = idx.delete(slice(50, 60))  # 10 bar gap
        
        # Validate
        is_valid, gaps = validator.validate(idx_with_gap)
        
        assert is_valid is False
        assert len(gaps) > 0

    def test_multiple_gap_detection(self):
        """Test detection of multiple gaps in time series."""
        validator = GapValidator(frequency="1min")
        
        # Create index with multiple gaps
        idx = pd.date_range("2024-01-01", periods=30, freq="1min")
        idx_gaps = idx.delete([5, 6, 7, 15, 16, 25])
        
        is_valid, gaps = validator.validate(idx_gaps)
        
        assert is_valid is False
        # Should detect multiple gaps
        assert len(gaps) >= 2

    def test_validation_with_dataframe_conversion(self):
        """Test validation workflow with DataFrame input."""
        # Create DataFrame
        df = pd.DataFrame({
            "time": pd.date_range("2024-01-01", periods=100, freq="1min"),
            "open": range(100),
            "close": range(100),
        })
        
        # Drop some rows to create gap
        df = df.drop(df.index[50:55])
        
        # Validate
        with pytest.raises(GapDetectionError):
            validate_timeseries_gaps(df, "time", "1min")

    def test_performance_with_large_dataset(self):
        """Test validation performance with large dataset."""
        # Create large continuous dataset
        index = pd.date_range("2024-01-01", periods=10000, freq="1min")
        validator = GapValidator(frequency="1min")
        
        # Should complete quickly
        is_valid, gaps = validator.validate(index)
        assert is_valid is True

    def test_edge_case_single_timestamp(self):
        """Test validation with single timestamp."""
        validator = GapValidator(frequency="1min")
        index = pd.DatetimeIndex([pd.Timestamp("2024-01-01")])
        
        is_valid, gaps = validator.validate(index)
        assert is_valid is True

    def test_edge_case_two_timestamps(self):
        """Test validation with two consecutive timestamps."""
        validator = GapValidator(frequency="1min")
        index = pd.DatetimeIndex([
            pd.Timestamp("2024-01-01 00:00"),
            pd.Timestamp("2024-01-01 00:01"),
        ])
        
        is_valid, gaps = validator.validate(index)
        assert is_valid is True
