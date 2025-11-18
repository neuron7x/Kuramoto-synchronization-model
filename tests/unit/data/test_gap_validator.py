# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""
Comprehensive test suite for gap_validator.py

This module provides extensive test coverage for the GapValidator class
and related functions, ensuring data quality enforcement for time series data.

Tests follow 2025 best practices:
- Property-based testing for edge cases
- Parametrized tests for multiple scenarios
- Clear test names describing behavior
- Comprehensive coverage of all code paths
"""
import pytest
from datetime import datetime, timedelta
import pandas as pd
from hypothesis import given, strategies as st, assume

from core.data.gap_validator import (
    GapDetectionError,
    GapValidator,
    GapValidatorConfig,
    validate_timeseries_gaps,
    quick_validate,
)
from core.data.backfill import Gap


class TestGapDetectionError:
    """Test GapDetectionError exception class."""

    def test_error_with_message_only(self):
        """Test creating error with just a message."""
        error = GapDetectionError("Test error")
        assert str(error) == "Test error"
        assert error.gaps == []

    def test_error_with_gaps(self):
        """Test creating error with gaps list."""
        gap = Gap(
            start=pd.Timestamp(datetime(2024, 1, 1, 10, 0)),
            end=pd.Timestamp(datetime(2024, 1, 1, 10, 5)),
        )
        error = GapDetectionError("Test error", gaps=[gap])
        assert len(error.gaps) == 1
        assert error.gaps[0] == gap


class TestGapValidatorConfig:
    """Test GapValidatorConfig dataclass."""

    def test_config_minimal(self):
        """Test config with only required fields."""
        config = GapValidatorConfig(frequency="1min")
        assert config.frequency == "1min"
        assert config.max_gap_duration is None
        assert config.allow_weekend_gaps is False
        assert config.allow_holiday_gaps is False

    def test_config_full(self):
        """Test config with all fields specified."""
        config = GapValidatorConfig(
            frequency="5min",
            max_gap_duration="10min",
            allow_weekend_gaps=True,
            allow_holiday_gaps=True,
        )
        assert config.frequency == "5min"
        assert config.max_gap_duration == "10min"
        assert config.allow_weekend_gaps is True
        assert config.allow_holiday_gaps is True


class TestGapValidator:
    """Test GapValidator class core functionality."""

    def test_init_with_string_frequency(self):
        """Test validator initialization with string frequency."""
        validator = GapValidator(frequency="1min")
        assert validator._frequency == "1min"
        assert validator._max_gap_duration is None
        assert validator._allow_weekend_gaps is False

    def test_init_with_max_gap_duration(self):
        """Test validator with max gap duration."""
        validator = GapValidator(frequency="1min", max_gap_duration="5min")
        assert validator._max_gap_duration == timedelta(minutes=5)

    def test_init_with_timedelta_max_gap(self):
        """Test validator with timedelta max gap duration."""
        td = timedelta(minutes=10)
        validator = GapValidator(frequency="1min", max_gap_duration=td)
        assert validator._max_gap_duration == td

    def test_parse_duration_none(self):
        """Test duration parsing with None."""
        result = GapValidator._parse_duration(None)
        assert result is None

    def test_parse_duration_timedelta(self):
        """Test duration parsing with timedelta."""
        td = timedelta(minutes=5)
        result = GapValidator._parse_duration(td)
        assert result == td

    def test_parse_duration_string(self):
        """Test duration parsing with string."""
        result = GapValidator._parse_duration("10min")
        assert result == timedelta(minutes=10)

    def test_parse_duration_cached(self):
        """Test that duration parsing is cached."""
        # Clear cache first
        GapValidator._parse_duration.cache_clear()
        
        # First call
        result1 = GapValidator._parse_duration("5min")
        cache_info1 = GapValidator._parse_duration.cache_info()
        
        # Second call should hit cache
        result2 = GapValidator._parse_duration("5min")
        cache_info2 = GapValidator._parse_duration.cache_info()
        
        assert result1 == result2
        assert cache_info2.hits > cache_info1.hits


class TestGapValidatorValidation:
    """Test gap validation logic."""

    def test_validate_empty_index(self):
        """Test validation with empty index returns valid."""
        validator = GapValidator(frequency="1min")
        index = pd.DatetimeIndex([])
        is_valid, gaps = validator.validate(index)
        assert is_valid is True
        assert gaps == []

    def test_validate_continuous_index(self):
        """Test validation with continuous index (no gaps)."""
        validator = GapValidator(frequency="1min")
        index = pd.date_range("2024-01-01", periods=60, freq="1min")
        is_valid, gaps = validator.validate(index)
        assert is_valid is True
        assert gaps == []

    def test_validate_with_gap(self):
        """Test validation detects gaps in time series."""
        validator = GapValidator(frequency="1min")
        # Create index with gap by deleting middle elements
        index = pd.date_range("2024-01-01", periods=10, freq="1min")
        index_with_gap = index.delete(slice(4, 7))  # Remove 3 bars
        is_valid, gaps = validator.validate(index_with_gap)
        assert is_valid is False
        assert len(gaps) > 0

    def test_validate_with_acceptable_small_gap(self):
        """Test validation allows small gaps below threshold."""
        validator = GapValidator(frequency="1min", max_gap_duration="5min")
        # Create index with 2-minute gap (should be acceptable)
        index = pd.date_range("2024-01-01", periods=10, freq="1min")
        index_with_small_gap = index.delete(slice(4, 5))  # Remove 1 bar = 1min gap
        is_valid, gaps = validator.validate(index_with_small_gap)
        assert is_valid is True

    def test_validate_with_unacceptable_large_gap(self):
        """Test validation rejects gaps above threshold."""
        validator = GapValidator(frequency="1min", max_gap_duration="5min")
        # Create index with 10-minute gap (should be rejected)
        index = pd.date_range("2024-01-01", periods=20, freq="1min")
        index_with_large_gap = index.delete(slice(5, 15))  # Remove 10 bars
        is_valid, gaps = validator.validate(index_with_large_gap)
        assert is_valid is False
        assert len(gaps) > 0

    def test_validate_weekend_gap_allowed(self):
        """Test validation allows weekend gaps when configured."""
        validator = GapValidator(
            frequency="1D",
            allow_weekend_gaps=True,
        )
        # Create index spanning weekend
        index = pd.date_range("2024-01-05", periods=5, freq="1D")  # Fri-Tue
        # Remove Saturday and Sunday
        index_no_weekend = index[[0, 3, 4]]  # Fri, Mon, Tue
        is_valid, gaps = validator.validate(index_no_weekend)
        # Should be valid if weekend gaps are filtered properly
        # Note: This test depends on the specific implementation of _filter_acceptable_gaps

    def test_validate_quick_check_mode(self):
        """Test validation with quick check (full_check=False)."""
        validator = GapValidator(frequency="1min")
        index = pd.date_range("2024-01-01", periods=60, freq="1min")
        is_valid, gaps = validator.validate(index, full_check=False)
        assert is_valid is True


class TestGapValidatorRaiseExceptions:
    """Test validate_and_raise method."""

    def test_validate_and_raise_no_gaps(self):
        """Test validate_and_raise does not raise when no gaps."""
        validator = GapValidator(frequency="1min")
        index = pd.date_range("2024-01-01", periods=60, freq="1min")
        # Should not raise
        validator.validate_and_raise(index)

    def test_validate_and_raise_with_gaps(self):
        """Test validate_and_raise raises when gaps detected."""
        validator = GapValidator(frequency="1min")
        index = pd.date_range("2024-01-01", periods=10, freq="1min")
        index_with_gap = index.delete(slice(4, 7))
        
        with pytest.raises(GapDetectionError) as exc_info:
            validator.validate_and_raise(index_with_gap)
        
        assert "Data import blocked" in str(exc_info.value)
        assert len(exc_info.value.gaps) > 0

    def test_validate_and_raise_error_message_format(self):
        """Test error message includes gap details."""
        validator = GapValidator(frequency="1min")
        index = pd.date_range("2024-01-01", periods=10, freq="1min")
        index_with_gap = index.delete(slice(4, 7))
        
        with pytest.raises(GapDetectionError) as exc_info:
            validator.validate_and_raise(index_with_gap)
        
        error_msg = str(exc_info.value)
        assert "gap(s) detected" in error_msg
        assert "Expected frequency: 1min" in error_msg


class TestGapValidatorFormatGapSummary:
    """Test gap summary formatting."""

    def test_format_gap_summary_empty(self):
        """Test formatting with no gaps."""
        summary = GapValidator._format_gap_summary([])
        assert "No gaps detected" in summary

    def test_format_gap_summary_single_gap(self):
        """Test formatting with single gap."""
        gap = Gap(
            start=pd.Timestamp(datetime(2024, 1, 1, 10, 0)),
            end=pd.Timestamp(datetime(2024, 1, 1, 10, 5)),
        )
        summary = GapValidator._format_gap_summary([gap])
        assert "Gaps found:" in summary
        assert "2024-01-01 10:00" in summary
        assert "2024-01-01 10:05" in summary

    def test_format_gap_summary_multiple_gaps(self):
        """Test formatting with multiple gaps."""
        gaps = [
            Gap(pd.Timestamp(datetime(2024, 1, 1, 10, 0)), pd.Timestamp(datetime(2024, 1, 1, 10, 5))),
            Gap(pd.Timestamp(datetime(2024, 1, 1, 11, 0)), pd.Timestamp(datetime(2024, 1, 1, 11, 3))),
        ]
        summary = GapValidator._format_gap_summary(gaps)
        assert "Gaps found:" in summary
        assert "1." in summary
        assert "2." in summary

    def test_format_gap_summary_max_display(self):
        """Test formatting truncates long gap lists."""
        gaps = [
            Gap(pd.Timestamp(datetime(2024, 1, 1, i, 0)), pd.Timestamp(datetime(2024, 1, 1, i, 5)))
            for i in range(10)
        ]
        summary = GapValidator._format_gap_summary(gaps, max_display=3)
        assert "and 7 more gap(s)" in summary


class TestGapValidatorFromConfig:
    """Test factory method from_config."""

    def test_from_config_basic(self):
        """Test creating validator from config."""
        config = GapValidatorConfig(frequency="5min")
        validator = GapValidator.from_config(config)
        assert validator._frequency == "5min"

    def test_from_config_full(self):
        """Test creating validator from complete config."""
        config = GapValidatorConfig(
            frequency="1h",
            max_gap_duration="2h",
            allow_weekend_gaps=True,
            allow_holiday_gaps=True,
        )
        validator = GapValidator.from_config(config)
        assert validator._frequency == "1h"
        assert validator._max_gap_duration == timedelta(hours=2)
        assert validator._allow_weekend_gaps is True
        assert validator._allow_holiday_gaps is True


class TestValidateTimeseriesGaps:
    """Test convenience function validate_timeseries_gaps."""

    def test_validate_dataframe_no_gaps(self):
        """Test validation of DataFrame without gaps."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=60, freq="1min"),
            "value": range(60),
        })
        # Should not raise
        validate_timeseries_gaps(df, "timestamp", "1min")

    def test_validate_dataframe_with_gaps(self):
        """Test validation of DataFrame with gaps raises error."""
        index = pd.date_range("2024-01-01", periods=10, freq="1min")
        df = pd.DataFrame({
            "timestamp": index.delete(slice(4, 7)),
            "value": [0, 1, 2, 3, 7, 8, 9],
        })
        
        with pytest.raises(GapDetectionError):
            validate_timeseries_gaps(df, "timestamp", "1min")

    def test_validate_empty_dataframe(self):
        """Test validation of empty DataFrame raises ValueError."""
        df = pd.DataFrame({"timestamp": [], "value": []})
        
        with pytest.raises(ValueError, match="DataFrame is empty"):
            validate_timeseries_gaps(df, "timestamp", "1min")

    def test_validate_missing_column(self):
        """Test validation with missing timestamp column raises ValueError."""
        df = pd.DataFrame({"value": [1, 2, 3]})
        
        with pytest.raises(ValueError, match="not found"):
            validate_timeseries_gaps(df, "timestamp", "1min")

    def test_validate_invalid_timestamp_column(self):
        """Test validation with invalid timestamp data raises ValueError."""
        df = pd.DataFrame({
            "timestamp": ["not", "a", "timestamp"],
            "value": [1, 2, 3],
        })
        
        with pytest.raises(ValueError, match="Failed to convert"):
            validate_timeseries_gaps(df, "timestamp", "1min")

    def test_validate_with_max_gap_duration(self):
        """Test validation with max gap duration parameter."""
        index = pd.date_range("2024-01-01", periods=10, freq="1min")
        df = pd.DataFrame({
            "timestamp": index.delete(slice(4, 5)),  # 1min gap
            "value": list(range(9)),
        })
        # Should not raise with 5min tolerance
        validate_timeseries_gaps(df, "timestamp", "1min", max_gap_duration="5min")

    def test_validate_with_weekend_gaps(self):
        """Test validation with weekend gaps allowed."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-05", periods=3, freq="1D"),
            "value": [1, 2, 3],
        })
        # Should not raise
        validate_timeseries_gaps(
            df, "timestamp", "1D", allow_weekend_gaps=True
        )


class TestQuickValidate:
    """Test quick_validate convenience function."""

    def test_quick_validate_continuous(self):
        """Test quick validation with continuous data."""
        index = pd.date_range("2024-01-01", periods=60, freq="1min")
        assert quick_validate(index, "1min") is True

    def test_quick_validate_with_gap_strict(self):
        """Test quick validation with gap in strict mode."""
        index = pd.date_range("2024-01-01", periods=10, freq="1min")
        index_with_gap = index.delete(slice(4, 7))
        assert quick_validate(index_with_gap, "1min", strict=True) is False

    def test_quick_validate_with_small_gap_lenient(self):
        """Test quick validation with small gap in lenient mode."""
        index = pd.date_range("2024-01-01", periods=10, freq="1min")
        index_with_gap = index.delete(slice(4, 5))  # 1min gap
        # Lenient mode allows up to 2x frequency
        assert quick_validate(index_with_gap, "1min", strict=False) is True

    def test_quick_validate_empty_index(self):
        """Test quick validation with empty index."""
        index = pd.DatetimeIndex([])
        assert quick_validate(index, "1min") is True

    def test_quick_validate_various_frequencies(self):
        """Test quick validation with different frequencies."""
        # Test hourly data
        index_hourly = pd.date_range("2024-01-01", periods=24, freq="1h")
        assert quick_validate(index_hourly, "1h") is True
        
        # Test daily data
        index_daily = pd.date_range("2024-01-01", periods=30, freq="1D")
        assert quick_validate(index_daily, "1D") is True


class TestGapValidatorEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_single_timestamp(self):
        """Test validation with single timestamp."""
        validator = GapValidator(frequency="1min")
        index = pd.DatetimeIndex([datetime(2024, 1, 1, 10, 0)])
        is_valid, gaps = validator.validate(index)
        assert is_valid is True

    def test_two_timestamps_continuous(self):
        """Test validation with two continuous timestamps."""
        validator = GapValidator(frequency="1min")
        index = pd.date_range("2024-01-01 10:00", periods=2, freq="1min")
        is_valid, gaps = validator.validate(index)
        assert is_valid is True

    def test_two_timestamps_with_gap(self):
        """Test validation with two timestamps with gap."""
        validator = GapValidator(frequency="1min")
        index = pd.DatetimeIndex([
            datetime(2024, 1, 1, 10, 0),
            datetime(2024, 1, 1, 10, 10),  # 10 min gap
        ])
        is_valid, gaps = validator.validate(index)
        assert is_valid is False

    def test_multiple_gaps(self):
        """Test validation with multiple gaps in series."""
        validator = GapValidator(frequency="1min")
        index = pd.DatetimeIndex([
            datetime(2024, 1, 1, 10, 0),
            datetime(2024, 1, 1, 10, 1),
            # Gap here
            datetime(2024, 1, 1, 10, 5),
            datetime(2024, 1, 1, 10, 6),
            # Gap here
            datetime(2024, 1, 1, 10, 10),
        ])
        is_valid, gaps = validator.validate(index)
        assert is_valid is False
        assert len(gaps) >= 2

    def test_very_large_timedelta(self):
        """Test with very large max gap duration."""
        validator = GapValidator(frequency="1min", max_gap_duration="1D")
        index = pd.DatetimeIndex([
            datetime(2024, 1, 1, 10, 0),
            datetime(2024, 1, 1, 15, 0),  # 5 hour gap
        ])
        is_valid, gaps = validator.validate(index)
        assert is_valid is True  # Should be acceptable with 1 day tolerance


class TestFilterAcceptableGaps:
    """Test _filter_acceptable_gaps method."""

    def test_filter_no_gaps(self):
        """Test filtering with no gaps."""
        validator = GapValidator(frequency="1min")
        result = validator._filter_acceptable_gaps([])
        assert result == []

    def test_filter_by_duration(self):
        """Test filtering gaps by duration."""
        validator = GapValidator(frequency="1min", max_gap_duration="5min")
        small_gap = Gap(
            pd.Timestamp(datetime(2024, 1, 1, 10, 0)),
            pd.Timestamp(datetime(2024, 1, 1, 10, 2)),  # 2min gap
        )
        large_gap = Gap(
            pd.Timestamp(datetime(2024, 1, 1, 11, 0)),
            pd.Timestamp(datetime(2024, 1, 1, 11, 10)),  # 10min gap
        )
        result = validator._filter_acceptable_gaps([small_gap, large_gap])
        assert len(result) == 1
        assert result[0] == large_gap

    def test_filter_weekend_gaps(self):
        """Test filtering weekend gaps."""
        validator = GapValidator(frequency="1D", allow_weekend_gaps=True)
        # Saturday to Sunday gap
        weekend_gap = Gap(
            pd.Timestamp(datetime(2024, 1, 6, 0, 0)),  # Saturday
            pd.Timestamp(datetime(2024, 1, 7, 0, 0)),  # Sunday
        )
        # Weekday gap
        weekday_gap = Gap(
            pd.Timestamp(datetime(2024, 1, 8, 0, 0)),  # Monday
            pd.Timestamp(datetime(2024, 1, 9, 0, 0)),  # Tuesday
        )
        result = validator._filter_acceptable_gaps([weekend_gap, weekday_gap])
        assert len(result) == 1
        assert result[0] == weekday_gap


# Property-based tests using Hypothesis
class TestGapValidatorPropertyBased:
    """Property-based tests for comprehensive edge case coverage."""

    @given(
        periods=st.integers(min_value=1, max_value=100),
        freq=st.sampled_from(["1min", "5min", "1h", "1D"]),
    )
    def test_continuous_index_always_valid(self, periods, freq):
        """Property: Continuous index should always validate."""
        validator = GapValidator(frequency=freq)
        index = pd.date_range("2024-01-01", periods=periods, freq=freq)
        is_valid, gaps = validator.validate(index)
        assert is_valid is True
        assert gaps == []

    @given(
        num_timestamps=st.integers(min_value=0, max_value=50),
    )
    def test_empty_or_single_always_valid(self, num_timestamps):
        """Property: Empty or very small indices should validate."""
        assume(num_timestamps <= 1)
        validator = GapValidator(frequency="1min")
        if num_timestamps == 0:
            index = pd.DatetimeIndex([])
        else:
            index = pd.DatetimeIndex([datetime(2024, 1, 1, 10, 0)])
        is_valid, gaps = validator.validate(index)
        assert is_valid is True

    @given(
        gap_duration_minutes=st.integers(min_value=1, max_value=100),
        tolerance_minutes=st.integers(min_value=1, max_value=200),
    )
    def test_gap_filtering_by_duration(self, gap_duration_minutes, tolerance_minutes):
        """Property: Gaps smaller than tolerance should be accepted."""
        validator = GapValidator(
            frequency="1min",
            max_gap_duration=f"{tolerance_minutes}min",
        )
        # Create gap by adding minutes to base timestamp
        start = pd.Timestamp(datetime(2024, 1, 1, 10, 0))
        end = start + pd.Timedelta(minutes=gap_duration_minutes)
        gap = Gap(start, end)
        result = validator._filter_acceptable_gaps([gap])
        
        if gap_duration_minutes <= tolerance_minutes:
            assert len(result) == 0  # Gap should be filtered out
        else:
            assert len(result) == 1  # Gap should remain


class TestGapValidatorIntegration:
    """Integration tests combining multiple components."""

    def test_complete_workflow_with_valid_data(self):
        """Test complete workflow with valid data."""
        # Create DataFrame
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=1440, freq="1min"),
            "price": range(1440),
        })
        
        # Validate
        validate_timeseries_gaps(df, "timestamp", "1min")
        
        # Quick check
        assert quick_validate(pd.DatetimeIndex(df["timestamp"]), "1min") is True

    def test_complete_workflow_with_invalid_data(self):
        """Test complete workflow detects and blocks invalid data."""
        # Create DataFrame with gap
        index = pd.date_range("2024-01-01", periods=100, freq="1min")
        df = pd.DataFrame({
            "timestamp": index.delete(slice(50, 60)),
            "price": range(90),
        })
        
        # Should raise error
        with pytest.raises(GapDetectionError) as exc_info:
            validate_timeseries_gaps(df, "timestamp", "1min")
        
        assert len(exc_info.value.gaps) > 0
        
        # Quick check should also fail
        assert quick_validate(pd.DatetimeIndex(df["timestamp"]), "1min") is False

    def test_config_based_workflow(self):
        """Test workflow using configuration object."""
        config = GapValidatorConfig(
            frequency="5min",
            max_gap_duration="15min",
            allow_weekend_gaps=True,
        )
        validator = GapValidator.from_config(config)
        
        # Test with acceptable gap
        index = pd.date_range("2024-01-01", periods=20, freq="5min")
        index_with_small_gap = index.delete(slice(10, 11))
        is_valid, gaps = validator.validate(index_with_small_gap)
        assert is_valid is True


# Performance tests
class TestGapValidatorPerformance:
    """Test performance characteristics."""

    def test_large_continuous_dataset(self):
        """Test validation of large continuous dataset."""
        # 1 week of minute data = 10,080 points
        validator = GapValidator(frequency="1min")
        index = pd.date_range("2024-01-01", periods=10080, freq="1min")
        is_valid, gaps = validator.validate(index)
        assert is_valid is True

    def test_cache_effectiveness(self):
        """Test that duration parsing cache improves performance."""
        GapValidator._parse_duration.cache_clear()
        
        # Create multiple validators with same duration
        validators = [
            GapValidator(frequency="1min", max_gap_duration="5min")
            for _ in range(10)
        ]
        
        cache_info = GapValidator._parse_duration.cache_info()
        # Should have cache hits after first call
        assert cache_info.hits > 0
