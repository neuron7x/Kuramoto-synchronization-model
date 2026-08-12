# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for signal filtering module.

Tests for data and signal filtering functions:
- filter_invalid_values
- filter_by_range
- filter_outliers_zscore
- filter_duplicates
- filter_by_quality
- filter_signals
- filter_dataframe
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.data.signal_filter import (
    FilterResult,
    FilterStrategy,
    SignalFilterConfig,
    SignalFilterConfigError,
    filter_by_quality,
    filter_by_range,
    filter_dataframe,
    filter_duplicates,
    filter_invalid_values,
    filter_outliers_zscore,
    filter_signals,
)


class TestFilterInvalidValues:
    """Tests for filter_invalid_values function."""

    def test_removes_nan_values(self) -> None:
        """NaN values should be removed by default."""
        data = np.array([1.0, np.nan, 2.0, np.nan, 3.0])
        result = filter_invalid_values(data)

        assert isinstance(result, FilterResult)
        assert result.removed_count == 2
        assert result.original_count == 5
        np.testing.assert_array_equal(result.data, [1.0, 2.0, 3.0])

    def test_removes_inf_values(self) -> None:
        """Inf values should be removed by default."""
        data = np.array([1.0, np.inf, 2.0, -np.inf, 3.0])
        result = filter_invalid_values(data)

        assert result.removed_count == 2
        np.testing.assert_array_equal(result.data, [1.0, 2.0, 3.0])

    def test_removes_both_nan_and_inf(self) -> None:
        """Both NaN and Inf values should be removed."""
        data = np.array([1.0, np.nan, 2.0, np.inf, 3.0, -np.inf])
        result = filter_invalid_values(data)

        assert result.removed_count == 3
        np.testing.assert_array_equal(result.data, [1.0, 2.0, 3.0])

    def test_keeps_nan_when_disabled(self) -> None:
        """NaN values should be kept when remove_nan is False."""
        data = np.array([1.0, np.nan, 2.0])
        result = filter_invalid_values(data, remove_nan=False)

        assert result.removed_count == 0
        assert len(result.data) == 3

    def test_keeps_inf_when_disabled(self) -> None:
        """Inf values should be kept when remove_inf is False."""
        data = np.array([1.0, np.inf, 2.0])
        result = filter_invalid_values(data, remove_inf=False)

        assert result.removed_count == 0
        assert len(result.data) == 3

    def test_replace_nan_strategy(self) -> None:
        """REPLACE_NAN strategy should replace invalid values with NaN."""
        data = np.array([1.0, np.inf, 2.0])
        result = filter_invalid_values(data, strategy=FilterStrategy.REPLACE_NAN)

        assert len(result.data) == 3
        assert np.isnan(result.data[1])

    def test_replace_zero_strategy(self) -> None:
        """REPLACE_ZERO strategy should replace invalid values with zero."""
        data = np.array([1.0, np.nan, 2.0])
        result = filter_invalid_values(data, strategy=FilterStrategy.REPLACE_ZERO)

        assert len(result.data) == 3
        assert result.data[1] == 0.0

    def test_replace_previous_strategy(self) -> None:
        """REPLACE_PREVIOUS strategy should forward-fill from previous value."""
        data = np.array([1.0, np.nan, 2.0])
        result = filter_invalid_values(data, strategy=FilterStrategy.REPLACE_PREVIOUS)

        assert len(result.data) == 3
        assert result.data[1] == 1.0  # Forward filled from previous

    def test_empty_array(self) -> None:
        """Empty array should return empty result."""
        data = np.array([])
        result = filter_invalid_values(data)

        assert result.removed_count == 0
        assert result.original_count == 0

    def test_all_invalid_values(self) -> None:
        """All invalid values should result in empty array."""
        data = np.array([np.nan, np.inf, -np.inf])
        result = filter_invalid_values(data)

        assert result.removed_count == 3
        assert len(result.data) == 0

    def test_removal_ratio(self) -> None:
        """Removal ratio should be calculated correctly."""
        data = np.array([1.0, np.nan, 2.0, np.nan, 3.0])
        result = filter_invalid_values(data)

        assert result.removal_ratio == pytest.approx(0.4)  # 2/5


class TestFilterByRange:
    """Tests for filter_by_range function."""

    def test_filters_below_min(self) -> None:
        """Values below min should be filtered out."""
        data = np.array([1.0, 5.0, 10.0, 15.0, 20.0])
        result = filter_by_range(data, min_value=5.0)

        np.testing.assert_array_equal(result.data, [5.0, 10.0, 15.0, 20.0])
        assert result.removed_count == 1

    def test_filters_above_max(self) -> None:
        """Values above max should be filtered out."""
        data = np.array([1.0, 5.0, 10.0, 15.0, 20.0])
        result = filter_by_range(data, max_value=15.0)

        np.testing.assert_array_equal(result.data, [1.0, 5.0, 10.0, 15.0])
        assert result.removed_count == 1

    def test_filters_outside_range(self) -> None:
        """Values outside range should be filtered out."""
        data = np.array([1.0, 5.0, 10.0, 15.0, 20.0])
        result = filter_by_range(data, min_value=5.0, max_value=15.0)

        np.testing.assert_array_equal(result.data, [5.0, 10.0, 15.0])
        assert result.removed_count == 2

    def test_exclusive_min(self) -> None:
        """Exclusive min should not include boundary value."""
        data = np.array([5.0, 6.0, 7.0])
        result = filter_by_range(data, min_value=5.0, inclusive_min=False)

        np.testing.assert_array_equal(result.data, [6.0, 7.0])

    def test_exclusive_max(self) -> None:
        """Exclusive max should not include boundary value."""
        data = np.array([5.0, 6.0, 7.0])
        result = filter_by_range(data, max_value=7.0, inclusive_max=False)

        np.testing.assert_array_equal(result.data, [5.0, 6.0])

    def test_no_bounds(self) -> None:
        """No bounds should not filter anything."""
        data = np.array([1.0, 2.0, 3.0])
        result = filter_by_range(data)

        np.testing.assert_array_equal(result.data, [1.0, 2.0, 3.0])
        assert result.removed_count == 0


class TestFilterOutliersZscore:
    """Tests for filter_outliers_zscore function."""

    def test_removes_outliers(self) -> None:
        """Obvious outliers should be removed."""
        # Create data with a clear outlier
        data = np.array([1.0, 1.1, 0.9, 1.0, 1.1, 0.9, 100.0, 1.0, 1.1, 0.9] * 3)
        result = filter_outliers_zscore(data, threshold=2.0, window=5)

        # The 100.0 values should be removed
        assert 100.0 not in result.data
        assert result.removed_count > 0

    def test_keeps_normal_values(self) -> None:
        """Normal values should not be filtered."""
        data = np.array([1.0, 1.1, 0.9, 1.05, 0.95] * 10)
        result = filter_outliers_zscore(data, threshold=3.0, window=5)

        assert result.removed_count == 0

    def test_short_array(self) -> None:
        """Array shorter than window should not filter anything."""
        data = np.array([1.0, 100.0, 1.0])
        result = filter_outliers_zscore(data, threshold=2.0, window=5)

        assert result.removed_count == 0
        assert len(result.data) == 3


class TestFilterDuplicates:
    """Tests for filter_duplicates function."""

    def test_removes_duplicate_rows(self) -> None:
        """Duplicate rows should be removed."""
        df = pd.DataFrame({"a": [1, 1, 2, 2, 3], "b": [1, 1, 2, 3, 3]})
        result = filter_duplicates(df)

        assert len(result.data) == 4  # One full duplicate row removed
        assert result.removed_count == 1

    def test_removes_duplicates_by_subset(self) -> None:
        """Duplicates based on subset should be removed."""
        df = pd.DataFrame({"a": [1, 1, 2], "b": [1, 2, 3]})
        result = filter_duplicates(df, subset="a")

        assert len(result.data) == 2
        assert result.removed_count == 1

    def test_keep_last(self) -> None:
        """Keep='last' should keep the last duplicate."""
        df = pd.DataFrame({"a": [1, 1, 2], "b": [1, 2, 3]})
        result = filter_duplicates(df, subset="a", keep="last")

        # Should keep the second row with a=1
        assert result.data.iloc[0]["b"] == 2

    def test_series_duplicates(self) -> None:
        """Series duplicates should be filtered."""
        series = pd.Series([1, 1, 2, 2, 3])
        result = filter_duplicates(series)

        assert len(result.data) == 3
        assert result.removed_count == 2


class TestFilterByQuality:
    """Tests for filter_by_quality function."""

    def test_filters_low_quality(self) -> None:
        """Rows with quality below threshold should be filtered."""
        df = pd.DataFrame({"value": [1, 2, 3], "quality": [0.3, 0.6, 0.8]})
        result = filter_by_quality(df, "quality", threshold=0.5)

        assert len(result.data) == 2
        assert result.removed_count == 1

    def test_filters_high_quality_when_inverted(self) -> None:
        """Rows with quality above threshold should be filtered when keep_above=False."""
        df = pd.DataFrame({"value": [1, 2, 3], "quality": [0.3, 0.6, 0.8]})
        result = filter_by_quality(df, "quality", threshold=0.5, keep_above=False)

        assert len(result.data) == 1
        assert result.data.iloc[0]["quality"] == 0.3

    def test_missing_column_raises(self) -> None:
        """Missing quality column should raise ValueError."""
        df = pd.DataFrame({"value": [1, 2, 3]})
        with pytest.raises(ValueError, match="Quality column"):
            filter_by_quality(df, "quality", threshold=0.5)


class TestFilterSignals:
    """Tests for filter_signals function."""

    def test_comprehensive_filtering(self) -> None:
        """Comprehensive filtering should remove all invalid values."""
        signals = np.array([1.0, np.nan, 2.0, np.inf, 3.0, -np.inf, 100.0])
        config = SignalFilterConfig(
            remove_nan=True,
            remove_inf=True,
            min_value=0.0,
            max_value=10.0,
        )
        result = filter_signals(signals, config)

        np.testing.assert_array_equal(result.data, [1.0, 2.0, 3.0])

    def test_default_config(self) -> None:
        """Default config should remove NaN and Inf."""
        signals = np.array([1.0, np.nan, 2.0, np.inf])
        result = filter_signals(signals)

        np.testing.assert_array_equal(result.data, [1.0, 2.0])

    def test_with_series(self) -> None:
        """Should work with pandas Series."""
        signals = pd.Series([1.0, np.nan, 2.0])
        result = filter_signals(signals)

        np.testing.assert_array_equal(result.data, [1.0, 2.0])

    def test_zscore_filtering(self) -> None:
        """Z-score filtering should remove outliers."""
        signals = np.array([1.0, 1.1, 0.9, 1.0, 1.1, 100.0, 1.0, 1.1, 0.9, 1.0] * 3)
        config = SignalFilterConfig(zscore_threshold=2.0, zscore_window=5)
        result = filter_signals(signals, config)

        assert 100.0 not in result.data

    def test_index_tracking_with_multiple_filters(self) -> None:
        """Indices should map back to original array correctly."""
        # Create array with NaN, out-of-range, and valid values
        # indices: 0=nan, 1=valid, 2=out-of-range, 3=valid, 4=inf
        signals = np.array([np.nan, 1.0, 100.0, 2.0, np.inf])
        config = SignalFilterConfig(min_value=0.0, max_value=10.0)
        result = filter_signals(signals, config)

        # Only indices 1 and 3 should remain (values 1.0 and 2.0)
        np.testing.assert_array_equal(result.data, [1.0, 2.0])
        # Removed indices should be 0, 2, 4 in original array
        assert result.removed_count == 3
        removed_set = set(result.removed_indices.tolist())
        assert 0 in removed_set  # NaN
        assert 2 in removed_set  # out-of-range (100.0)
        assert 4 in removed_set  # Inf


class TestFilterDataFrame:
    """Tests for filter_dataframe function."""

    def test_filters_invalid_in_value_columns(self) -> None:
        """Invalid values in value columns should be filtered."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=5, freq="1min"),
                "close": [1.0, np.nan, 2.0, np.inf, 3.0],
            }
        )
        config = SignalFilterConfig()
        result = filter_dataframe(df, config, value_columns=["close"])

        assert len(result.data) == 3
        assert result.removed_count == 2

    def test_filters_duplicates(self) -> None:
        """Duplicates should be filtered when configured."""
        df = pd.DataFrame(
            {
                "timestamp": [1, 1, 2, 3],
                "close": [1.0, 1.5, 2.0, 3.0],
            }
        )
        config = SignalFilterConfig(remove_duplicates=True)
        result = filter_dataframe(df, config, timestamp_column="timestamp")

        assert len(result.data) == 3

    def test_filters_by_range(self) -> None:
        """Values outside range should be filtered."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=5, freq="1min"),
                "close": [1.0, 5.0, 10.0, 15.0, 20.0],
            }
        )
        config = SignalFilterConfig(min_value=5.0, max_value=15.0)
        result = filter_dataframe(df, config, value_columns=["close"])

        assert len(result.data) == 3

    def test_filters_by_quality(self) -> None:
        """Low quality rows should be filtered."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=3, freq="1min"),
                "close": [1.0, 2.0, 3.0],
                "quality": [0.3, 0.6, 0.8],
            }
        )
        config = SignalFilterConfig(quality_threshold=0.5)
        result = filter_dataframe(
            df, config, value_columns=["close"], quality_column="quality"
        )

        assert len(result.data) == 2

    def test_empty_dataframe(self) -> None:
        """Empty DataFrame should return empty result."""
        df = pd.DataFrame(columns=["timestamp", "close"])
        config = SignalFilterConfig()
        result = filter_dataframe(df, config, value_columns=["close"])

        assert len(result.data) == 0
        assert result.removed_count == 0


class TestFilterResult:
    """Tests for FilterResult dataclass."""

    def test_removal_ratio(self) -> None:
        """Removal ratio should be calculated correctly."""
        data = np.array([1.0, 2.0, 3.0])
        result = FilterResult(
            data=data,
            removed_count=2,
            removed_indices=np.array([0, 1]),
            original_count=5,
        )

        assert result.removal_ratio == pytest.approx(0.4)

    def test_removal_ratio_zero_original(self) -> None:
        """Removal ratio should be 0 when original count is 0."""
        data = np.array([])
        result = FilterResult(
            data=data,
            removed_count=0,
            removed_indices=np.array([]),
            original_count=0,
        )

        assert result.removal_ratio == 0.0

    def test_retained_count(self) -> None:
        """Retained count should be calculated correctly."""
        data = np.array([1.0, 2.0, 3.0])
        result = FilterResult(
            data=data,
            removed_count=2,
            removed_indices=np.array([0, 1]),
            original_count=5,
        )

        assert result.retained_count == 3


class TestSecurityValidation:
    """Security validation tests for signal filtering module."""

    def test_signal_filter_config_invalid_zscore_window_low(self) -> None:
        """zscore_window must be >= 2."""
        with pytest.raises(SignalFilterConfigError):
            SignalFilterConfig(zscore_window=1)

    def test_signal_filter_config_invalid_zscore_window_high(self) -> None:
        """zscore_window must be <= 10000 to prevent DoS."""
        with pytest.raises(SignalFilterConfigError):
            SignalFilterConfig(zscore_window=20000)

    def test_signal_filter_config_invalid_zscore_threshold(self) -> None:
        """zscore_threshold must be positive."""
        with pytest.raises(SignalFilterConfigError):
            SignalFilterConfig(zscore_threshold=-1.0)

    def test_signal_filter_config_invalid_min_max_range(self) -> None:
        """min_value must be <= max_value."""
        with pytest.raises(SignalFilterConfigError):
            SignalFilterConfig(min_value=10.0, max_value=5.0)

    def test_signal_filter_config_inf_min_value(self) -> None:
        """min_value cannot be infinite."""
        with pytest.raises(SignalFilterConfigError):
            SignalFilterConfig(min_value=np.inf)

    def test_signal_filter_config_nan_zscore_threshold(self) -> None:
        """zscore_threshold cannot be NaN."""
        with pytest.raises(SignalFilterConfigError):
            SignalFilterConfig(zscore_threshold=np.nan)

    def test_filter_by_range_invalid_min_value(self) -> None:
        """filter_by_range should reject infinite min_value."""
        data = np.array([1.0, 2.0, 3.0])
        with pytest.raises(ValueError, match="min_value must be a finite"):
            filter_by_range(data, min_value=np.inf)

    def test_filter_by_range_invalid_max_value(self) -> None:
        """filter_by_range should reject infinite max_value."""
        data = np.array([1.0, 2.0, 3.0])
        with pytest.raises(ValueError, match="max_value must be a finite"):
            filter_by_range(data, max_value=np.inf)

    def test_filter_by_range_invalid_range(self) -> None:
        """filter_by_range should reject min > max."""
        data = np.array([1.0, 2.0, 3.0])
        with pytest.raises(ValueError, match="min_value .* must be <="):
            filter_by_range(data, min_value=10.0, max_value=5.0)

    def test_filter_outliers_zscore_invalid_threshold(self) -> None:
        """filter_outliers_zscore should reject non-positive threshold."""
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        with pytest.raises(ValueError, match="threshold must be positive"):
            filter_outliers_zscore(data, threshold=-1.0)

    def test_filter_outliers_zscore_invalid_window_low(self) -> None:
        """filter_outliers_zscore should reject window < 2."""
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        with pytest.raises(ValueError, match="window must be >= 2"):
            filter_outliers_zscore(data, window=1)

    def test_filter_outliers_zscore_invalid_window_high(self) -> None:
        """filter_outliers_zscore should reject window > 10000."""
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        with pytest.raises(ValueError, match="window must be <= 10000"):
            filter_outliers_zscore(data, window=20000)

    def test_valid_config_passes(self) -> None:
        """Valid config should not raise."""
        config = SignalFilterConfig(
            min_value=0.0,
            max_value=100.0,
            zscore_threshold=3.0,
            zscore_window=20,
        )
        assert config.min_value == 0.0
        assert config.max_value == 100.0
