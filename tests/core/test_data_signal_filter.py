# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core.data.signal_filter module."""

from __future__ import annotations

import numpy as np
import pytest

from core.data.signal_filter import (
    FilterResult,
    FilterStrategy,
    SignalFilterConfig,
    SignalFilterConfigError,
    filter_invalid_values,
)


class TestFilterStrategy:
    def test_values(self):
        assert FilterStrategy.REMOVE.value == "remove"
        assert FilterStrategy.REPLACE_NAN.value == "replace_nan"
        assert FilterStrategy.REPLACE_ZERO.value == "replace_zero"
        assert FilterStrategy.REPLACE_PREVIOUS.value == "replace_previous"


class TestFilterResult:
    def test_removal_ratio_empty(self):
        r = FilterResult(
            data=np.array([]),
            removed_count=0,
            removed_indices=np.array([], dtype=np.intp),
            original_count=0,
        )
        assert r.removal_ratio == 0.0

    def test_removal_ratio(self):
        r = FilterResult(
            data=np.array([1.0, 3.0]),
            removed_count=1,
            removed_indices=np.array([1], dtype=np.intp),
            original_count=3,
        )
        assert r.removal_ratio == pytest.approx(1 / 3)

    def test_retained_count(self):
        r = FilterResult(
            data=np.array([1.0]),
            removed_count=2,
            removed_indices=np.array([0, 2], dtype=np.intp),
            original_count=3,
        )
        assert r.retained_count == 1


class TestSignalFilterConfig:
    def test_defaults(self):
        cfg = SignalFilterConfig()
        assert cfg.remove_nan is True
        assert cfg.remove_inf is True
        assert cfg.strategy == FilterStrategy.REMOVE

    def test_zscore_window_too_small(self):
        with pytest.raises(SignalFilterConfigError, match="zscore_window"):
            SignalFilterConfig(zscore_window=1)

    def test_zscore_window_too_large(self):
        with pytest.raises(SignalFilterConfigError, match="10000"):
            SignalFilterConfig(zscore_window=20000)

    def test_zscore_threshold_negative(self):
        with pytest.raises(SignalFilterConfigError, match="positive"):
            SignalFilterConfig(zscore_threshold=-1.0)

    def test_zscore_threshold_inf(self):
        with pytest.raises(SignalFilterConfigError, match="finite"):
            SignalFilterConfig(zscore_threshold=np.inf)

    def test_quality_threshold_inf(self):
        with pytest.raises(SignalFilterConfigError, match="finite"):
            SignalFilterConfig(quality_threshold=np.inf)

    def test_min_value_inf(self):
        with pytest.raises(SignalFilterConfigError, match="finite"):
            SignalFilterConfig(min_value=np.inf)

    def test_min_exceeds_max(self):
        with pytest.raises(SignalFilterConfigError, match="min_value"):
            SignalFilterConfig(min_value=10.0, max_value=5.0)

    def test_valid_config(self):
        cfg = SignalFilterConfig(
            min_value=0.0,
            max_value=100.0,
            zscore_threshold=3.0,
            zscore_window=50,
        )
        assert cfg.min_value == 0.0


class TestFilterInvalidValues:
    def test_remove_nan(self):
        data = np.array([1.0, np.nan, 3.0])
        result = filter_invalid_values(data)
        assert result.removed_count == 1
        assert len(result.data) == 2
        np.testing.assert_array_equal(result.data, [1.0, 3.0])

    def test_remove_inf(self):
        data = np.array([1.0, np.inf, -np.inf, 4.0])
        result = filter_invalid_values(data)
        assert result.removed_count == 2

    def test_no_removal(self):
        data = np.array([1.0, 2.0, 3.0])
        result = filter_invalid_values(data)
        assert result.removed_count == 0
        assert result.original_count == 3

    def test_all_invalid(self):
        data = np.array([np.nan, np.inf, -np.inf])
        result = filter_invalid_values(data)
        assert result.removed_count == 3
        assert len(result.data) == 0

    def test_empty_array(self):
        data = np.array([])
        result = filter_invalid_values(data)
        assert result.removed_count == 0
        assert result.original_count == 0

    def test_replace_nan_strategy(self):
        data = np.array([1.0, np.nan, 3.0])
        result = filter_invalid_values(data, strategy=FilterStrategy.REPLACE_NAN)
        assert len(result.data) == 3
        assert np.isnan(result.data[1])

    def test_replace_zero_strategy(self):
        data = np.array([1.0, np.nan, 3.0])
        result = filter_invalid_values(data, strategy=FilterStrategy.REPLACE_ZERO)
        assert len(result.data) == 3
        assert result.data[1] == 0.0

    def test_max_size_exceeded(self):
        data = np.zeros(10)
        with pytest.raises(ValueError, match="exceeds"):
            filter_invalid_values(data, max_size=5)

    def test_keep_nan_flag(self):
        data = np.array([1.0, np.nan, 3.0])
        result = filter_invalid_values(data, remove_nan=False)
        assert result.removed_count == 0

    def test_keep_inf_flag(self):
        data = np.array([1.0, np.inf, 3.0])
        result = filter_invalid_values(data, remove_inf=False)
        assert result.removed_count == 0

    @pytest.mark.parametrize("n", [10, 100, 1000])
    def test_various_sizes(self, n):
        rng = np.random.default_rng(42)
        data = rng.standard_normal(n)
        data[rng.choice(n, n // 10, replace=False)] = np.nan
        result = filter_invalid_values(data)
        assert result.removed_count == n // 10
        assert result.retained_count == n - n // 10
