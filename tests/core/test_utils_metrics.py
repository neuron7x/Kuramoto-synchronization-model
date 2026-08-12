# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core.utils.metrics module."""

from __future__ import annotations

import pytest

from core.utils.metrics import (
    MetricsCollector,
    _fallback_quantiles,
    get_metrics_collector,
)


class TestFallbackQuantiles:
    def test_empty_values(self):
        assert _fallback_quantiles([], (0.5,)) == {}

    def test_single_value(self):
        result = _fallback_quantiles([42.0], (0.5,))
        assert result[0.5] == pytest.approx(42.0)

    def test_median(self):
        result = _fallback_quantiles([1.0, 2.0, 3.0, 4.0, 5.0], (0.5,))
        assert result[0.5] == pytest.approx(3.0)

    def test_quartiles(self):
        values = list(range(101))
        result = _fallback_quantiles([float(v) for v in values], (0.25, 0.5, 0.75))
        assert result[0.25] == pytest.approx(25.0)
        assert result[0.5] == pytest.approx(50.0)
        assert result[0.75] == pytest.approx(75.0)

    def test_min_max_quantiles(self):
        values = [1.0, 2.0, 3.0]
        result = _fallback_quantiles(values, (0.0, 1.0))
        assert result[0.0] == pytest.approx(1.0)
        assert result[1.0] == pytest.approx(3.0)

    def test_out_of_range_quantile_skipped(self):
        values = [1.0, 2.0]
        result = _fallback_quantiles(values, (-0.1, 1.1))
        assert -0.1 not in result
        assert 1.1 not in result

    def test_interpolation(self):
        values = [10.0, 20.0]
        result = _fallback_quantiles(values, (0.5,))
        assert result[0.5] == pytest.approx(15.0)

    @pytest.mark.parametrize("q", [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0])
    def test_various_quantiles(self, q):
        values = [float(i) for i in range(100)]
        result = _fallback_quantiles(values, (q,))
        assert q in result
        assert 0.0 <= result[q] <= 99.0


class TestMetricsCollector:
    def test_singleton_pattern(self):
        mc1 = get_metrics_collector()
        mc2 = get_metrics_collector()
        assert mc1 is mc2

    def test_singleton_has_api_metrics(self):
        mc = get_metrics_collector()
        if mc._enabled:
            assert hasattr(mc, "api_request_latency")
            assert hasattr(mc, "api_requests_total")
            assert hasattr(mc, "api_requests_in_flight")


class TestGetMetricsCollector:
    def test_returns_metrics_collector(self):
        mc = get_metrics_collector()
        assert isinstance(mc, MetricsCollector)

    def test_idempotent(self):
        mc1 = get_metrics_collector()
        mc2 = get_metrics_collector()
        assert mc1 is mc2
