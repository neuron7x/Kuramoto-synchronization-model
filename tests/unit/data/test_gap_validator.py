# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for core/data/gap_validator.py module.

This module provides comprehensive tests for the GapValidator class
which implements time series gap detection and validation for data import blocking.
"""

from __future__ import annotations

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
    """Tests for GapDetectionError exception class."""

    def test_gap_detection_error_message(self) -> None:
        """Test error message is properly stored."""
        error = GapDetectionError("Test error message")
        assert str(error) == "Test error message"
        assert error.gaps == []

    def test_gap_detection_error_with_gaps(self) -> None:
        """Test error stores gaps list."""
        from core.data.backfill import Gap

        gaps = [
            Gap(
                start=pd.Timestamp("2024-01-01 10:00"),
                end=pd.Timestamp("2024-01-01 10:05"),
            )
        ]
        error = GapDetectionError("Gap detected", gaps=gaps)
        assert len(error.gaps) == 1
        assert error.gaps[0].start == pd.Timestamp("2024-01-01 10:00")


class TestGapValidatorConfig:
    """Tests for GapValidatorConfig dataclass."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = GapValidatorConfig(frequency="1min")
        assert config.frequency == "1min"
        assert config.max_gap_duration is None
        assert config.allow_weekend_gaps is False
        assert config.allow_holiday_gaps is False

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
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

    def test_validate_empty_index(self) -> None:
        """Test validation of empty index returns True."""
        validator = GapValidator(frequency="1min")
        is_valid, gaps = validator.validate(pd.DatetimeIndex([]))
        assert is_valid is True
        assert gaps == []

    def test_validate_continuous_index(self) -> None:
        """Test validation of continuous index without gaps."""
        validator = GapValidator(frequency="1min")
        index = pd.date_range("2024-01-01 10:00", periods=60, freq="1min")
        is_valid, gaps = validator.validate(index)
        assert is_valid is True
        assert gaps == []

    def test_validate_with_gap(self) -> None:
        """Test validation detects gaps in the time series."""
        validator = GapValidator(frequency="1min")
        # Create index with a gap (remove 5 minutes)
        full_index = pd.date_range("2024-01-01 10:00", periods=20, freq="1min")
        gapped_index = full_index.delete(slice(5, 10))  # Remove bars 5-9

        is_valid, gaps = validator.validate(gapped_index)
        assert is_valid is False
        assert len(gaps) > 0

    def test_validate_with_max_gap_duration(self) -> None:
        """Test that small gaps within threshold are acceptable."""
        validator = GapValidator(frequency="1min", max_gap_duration="5min")
        # Create index with a 3-minute gap (acceptable)
        full_index = pd.date_range("2024-01-01 10:00", periods=20, freq="1min")
        gapped_index = full_index.delete(slice(5, 7))  # Remove 2 bars

        is_valid, gaps = validator.validate(gapped_index)
        # Small gap should be acceptable
        assert is_valid is True

    def test_validate_with_weekend_gaps_allowed(self) -> None:
        """Test that weekend gaps are allowed when configured."""
        validator = GapValidator(frequency="1D", allow_weekend_gaps=True)
        # Create a weekday-only index using business day frequency
        # The "B" freq automatically skips weekends
        index = pd.date_range("2024-01-01", periods=5, freq="B")  # Business days only

        is_valid, gaps = validator.validate(index)
        assert is_valid is True

    def test_validate_and_raise_passes_for_valid(self) -> None:
        """Test validate_and_raise doesn't raise for valid data."""
        validator = GapValidator(frequency="1min")
        index = pd.date_range("2024-01-01 10:00", periods=10, freq="1min")
        # Should not raise
        validator.validate_and_raise(index)

    def test_validate_and_raise_raises_for_gaps(self) -> None:
        """Test validate_and_raise raises GapDetectionError for gapped data."""
        validator = GapValidator(frequency="1min")
        full_index = pd.date_range("2024-01-01 10:00", periods=20, freq="1min")
        gapped_index = full_index.delete(slice(5, 15))  # Remove 10 bars

        with pytest.raises(GapDetectionError) as exc_info:
            validator.validate_and_raise(gapped_index)

        assert "Data import blocked" in str(exc_info.value)
        assert "gap(s) detected" in str(exc_info.value)

    def test_from_config(self) -> None:
        """Test creating validator from config object."""
        config = GapValidatorConfig(
            frequency="5min",
            max_gap_duration="15min",
            allow_weekend_gaps=True,
        )
        validator = GapValidator.from_config(config)
        assert validator._frequency == "5min"
        assert validator._allow_weekend_gaps is True

    def test_parse_duration_with_string(self) -> None:
        """Test duration parsing from string."""
        validator = GapValidator(frequency="1min", max_gap_duration="10min")
        assert validator._max_gap_duration == timedelta(minutes=10)

    def test_parse_duration_with_timedelta(self) -> None:
        """Test duration parsing from timedelta."""
        duration = timedelta(hours=1)
        validator = GapValidator(frequency="1min", max_gap_duration=duration)
        assert validator._max_gap_duration == duration

    def test_parse_duration_with_none(self) -> None:
        """Test duration parsing with None (zero tolerance)."""
        validator = GapValidator(frequency="1min", max_gap_duration=None)
        assert validator._max_gap_duration is None

    def test_format_gap_summary_empty(self) -> None:
        """Test gap summary formatting with no gaps."""
        summary = GapValidator._format_gap_summary([])
        assert summary == "No gaps detected."

    def test_format_gap_summary_with_gaps(self) -> None:
        """Test gap summary formatting with gaps."""
        from core.data.backfill import Gap

        gaps = [
            Gap(
                start=pd.Timestamp("2024-01-01 10:00"),
                end=pd.Timestamp("2024-01-01 10:05"),
            )
        ]
        summary = GapValidator._format_gap_summary(gaps)
        assert "Gaps found:" in summary
        assert "2024-01-01" in summary

    def test_format_gap_summary_truncates_many_gaps(self) -> None:
        """Test that gap summary truncates when many gaps."""
        from core.data.backfill import Gap

        gaps = [
            Gap(
                start=pd.Timestamp(f"2024-01-0{i} 10:00"),
                end=pd.Timestamp(f"2024-01-0{i} 10:05"),
            )
            for i in range(1, 8)
        ]
        summary = GapValidator._format_gap_summary(gaps, max_display=3)
        assert "... and 4 more gap(s)" in summary

    def test_validate_no_full_check(self) -> None:
        """Test validation without full index generation."""
        validator = GapValidator(frequency="1min")
        index = pd.date_range("2024-01-01 10:00", periods=10, freq="1min")
        is_valid, gaps = validator.validate(index, full_check=False)
        assert is_valid is True


class TestValidateTimeseriesGaps:
    """Tests for validate_timeseries_gaps function."""

    def test_validates_valid_dataframe(self) -> None:
        """Test validation passes for DataFrame without gaps."""
        index = pd.date_range("2024-01-01 10:00", periods=60, freq="1min")
        df = pd.DataFrame({"timestamp": index, "price": range(60)})

        # Should not raise
        validate_timeseries_gaps(df, "timestamp", "1min")

    def test_raises_for_empty_dataframe(self) -> None:
        """Test raises ValueError for empty DataFrame."""
        df = pd.DataFrame(columns=["timestamp", "price"])

        with pytest.raises(ValueError, match="DataFrame is empty"):
            validate_timeseries_gaps(df, "timestamp", "1min")

    def test_raises_for_missing_column(self) -> None:
        """Test raises ValueError for missing timestamp column."""
        df = pd.DataFrame({"price": [1, 2, 3]})

        with pytest.raises(ValueError, match="not found in DataFrame"):
            validate_timeseries_gaps(df, "timestamp", "1min")

    def test_raises_for_invalid_timestamp(self) -> None:
        """Test raises ValueError for non-convertible timestamps."""
        df = pd.DataFrame({"timestamp": ["not", "valid", "dates"], "price": [1, 2, 3]})

        with pytest.raises(ValueError, match="Failed to convert"):
            validate_timeseries_gaps(df, "timestamp", "1min")

    def test_raises_gap_detection_error(self) -> None:
        """Test raises GapDetectionError when gaps detected."""
        full_index = pd.date_range("2024-01-01 10:00", periods=30, freq="1min")
        gapped_index = full_index.delete(slice(10, 20))
        df = pd.DataFrame(
            {"timestamp": gapped_index, "price": range(len(gapped_index))}
        )

        with pytest.raises(GapDetectionError):
            validate_timeseries_gaps(df, "timestamp", "1min")


class TestQuickValidate:
    """Tests for quick_validate function."""

    def test_quick_validate_valid_strict(self) -> None:
        """Test quick validation in strict mode for valid data."""
        index = pd.date_range("2024-01-01 10:00", periods=60, freq="1min")
        assert quick_validate(index, "1min", strict=True) is True

    def test_quick_validate_invalid_strict(self) -> None:
        """Test quick validation in strict mode detects gaps."""
        full_index = pd.date_range("2024-01-01 10:00", periods=20, freq="1min")
        gapped_index = full_index.delete(slice(5, 10))
        assert quick_validate(gapped_index, "1min", strict=True) is False

    def test_quick_validate_relaxed(self) -> None:
        """Test quick validation in non-strict mode allows small gaps."""
        index = pd.date_range("2024-01-01 10:00", periods=10, freq="1min")
        # Non-strict mode should allow small gaps
        assert quick_validate(index, "1min", strict=False) is True


class TestGapValidatorEdgeCases:
    """Edge case tests for GapValidator."""

    def test_single_timestamp_index(self) -> None:
        """Test validation of single-element index."""
        validator = GapValidator(frequency="1min")
        index = pd.DatetimeIndex([pd.Timestamp("2024-01-01 10:00")])
        is_valid, gaps = validator.validate(index)
        assert is_valid is True

    def test_two_timestamp_index_no_gap(self) -> None:
        """Test validation of two consecutive timestamps."""
        validator = GapValidator(frequency="1min")
        index = pd.DatetimeIndex(
            [pd.Timestamp("2024-01-01 10:00"), pd.Timestamp("2024-01-01 10:01")]
        )
        is_valid, gaps = validator.validate(index)
        assert is_valid is True

    def test_hourly_frequency(self) -> None:
        """Test validation with hourly frequency."""
        validator = GapValidator(frequency="1h")
        index = pd.date_range("2024-01-01 10:00", periods=24, freq="1h")
        is_valid, gaps = validator.validate(index)
        assert is_valid is True

    def test_daily_frequency(self) -> None:
        """Test validation with daily frequency."""
        validator = GapValidator(frequency="1D")
        index = pd.date_range("2024-01-01", periods=30, freq="1D")
        is_valid, gaps = validator.validate(index)
        assert is_valid is True

    def test_filter_acceptable_gaps_empty(self) -> None:
        """Test filtering with empty gaps list."""
        validator = GapValidator(frequency="1min")
        result = validator._filter_acceptable_gaps([])
        assert result == []
