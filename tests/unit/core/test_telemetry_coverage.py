# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Full coverage tests for core.telemetry — sampling, backends, client,
timer context manager, global singletons."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.telemetry import (
    MetricsBackend,
    MetricType,
    NoOpBackend,
    PrometheusBackend,
    Sampler,
    SamplingConfig,
    TelemetryClient,
    configure_telemetry,
    get_telemetry,
)

# ---------------------------------------------------------------------------
# MetricType enum
# ---------------------------------------------------------------------------


class TestMetricType:
    def test_values(self):
        assert MetricType.COUNTER.value == "counter"
        assert MetricType.GAUGE.value == "gauge"
        assert MetricType.HISTOGRAM.value == "histogram"
        assert MetricType.SUMMARY.value == "summary"


# ---------------------------------------------------------------------------
# SamplingConfig
# ---------------------------------------------------------------------------


class TestSamplingConfig:
    def test_defaults(self):
        sc = SamplingConfig()
        assert sc.default_rate == 1.0
        assert sc.per_metric_rates == {}
        assert sc.seed is None

    def test_invalid_default_rate_low(self):
        with pytest.raises(ValueError, match="default_rate"):
            SamplingConfig(default_rate=-0.1)

    def test_invalid_default_rate_high(self):
        with pytest.raises(ValueError, match="default_rate"):
            SamplingConfig(default_rate=1.1)

    def test_invalid_per_metric_rate(self):
        with pytest.raises(ValueError, match="Rate for"):
            SamplingConfig(per_metric_rates={"foo": 2.0})

    def test_get_rate_default(self):
        sc = SamplingConfig(default_rate=0.5)
        assert sc.get_rate("unknown") == 0.5

    def test_get_rate_override(self):
        sc = SamplingConfig(per_metric_rates={"special": 0.1})
        assert sc.get_rate("special") == 0.1


# ---------------------------------------------------------------------------
# Sampler
# ---------------------------------------------------------------------------


class TestSampler:
    def test_always_sample_at_rate_1(self):
        s = Sampler(SamplingConfig(default_rate=1.0))
        for _ in range(100):
            assert s.should_sample("any") is True

    def test_never_sample_at_rate_0(self):
        s = Sampler(SamplingConfig(default_rate=0.0))
        for _ in range(100):
            assert s.should_sample("any") is False

    def test_deterministic_with_seed(self):
        cfg = SamplingConfig(default_rate=0.5, seed=42)
        s1 = Sampler(cfg)
        s2 = Sampler(cfg)
        results1 = [s1.should_sample("m") for _ in range(20)]
        results2 = [s2.should_sample("m") for _ in range(20)]
        assert results1 == results2

    def test_per_metric_override(self):
        cfg = SamplingConfig(default_rate=1.0, per_metric_rates={"rare": 0.0}, seed=1)
        s = Sampler(cfg)
        assert s.should_sample("rare") is False
        assert s.should_sample("common") is True

    def test_default_config(self):
        s = Sampler()
        assert s.should_sample("anything") is True


# ---------------------------------------------------------------------------
# NoOpBackend
# ---------------------------------------------------------------------------


class TestNoOpBackend:
    def test_all_methods_are_noop(self):
        b = NoOpBackend()
        # These should not raise
        b.increment_counter("c", 1.0, {"t": "v"})
        b.set_gauge("g", 42.0, {"t": "v"})
        b.observe_histogram("h", 1.5, {"t": "v"})

    def test_implements_protocol(self):
        b = NoOpBackend()
        assert isinstance(b, MetricsBackend)


# ---------------------------------------------------------------------------
# PrometheusBackend (mocked — prometheus_client may not be installed)
# ---------------------------------------------------------------------------


class TestPrometheusBackend:
    def test_without_prometheus_client(self):
        with patch.object(PrometheusBackend, "_check_prometheus", return_value=False):
            b = PrometheusBackend()
            assert b._prometheus_available is False
            # All methods should be no-ops
            b.increment_counter("c", 1.0)
            b.set_gauge("g", 1.0)
            b.observe_histogram("h", 1.0)

    def test_get_or_create_counter_no_prometheus(self):
        with patch.object(PrometheusBackend, "_check_prometheus", return_value=False):
            b = PrometheusBackend()
            assert b._get_or_create_counter("test", None) is None

    def test_get_or_create_gauge_no_prometheus(self):
        with patch.object(PrometheusBackend, "_check_prometheus", return_value=False):
            b = PrometheusBackend()
            assert b._get_or_create_gauge("test", None) is None

    def test_get_or_create_histogram_no_prometheus(self):
        with patch.object(PrometheusBackend, "_check_prometheus", return_value=False):
            b = PrometheusBackend()
            assert b._get_or_create_histogram("test", None) is None

    def test_increment_counter_with_tags_no_prom(self):
        with patch.object(PrometheusBackend, "_check_prometheus", return_value=False):
            b = PrometheusBackend()
            b.increment_counter("c", 1.0, {"env": "test"})

    def test_set_gauge_with_tags_no_prom(self):
        with patch.object(PrometheusBackend, "_check_prometheus", return_value=False):
            b = PrometheusBackend()
            b.set_gauge("g", 5.0, {"env": "test"})

    def test_observe_histogram_with_tags_no_prom(self):
        with patch.object(PrometheusBackend, "_check_prometheus", return_value=False):
            b = PrometheusBackend()
            b.observe_histogram("h", 1.0, {"env": "test"})


# ---------------------------------------------------------------------------
# TelemetryClient
# ---------------------------------------------------------------------------


class TestTelemetryClient:
    def test_default_backend_is_noop(self):
        tc = TelemetryClient()
        assert isinstance(tc._backend, NoOpBackend)

    def test_enabled_by_default(self):
        tc = TelemetryClient()
        assert tc.enabled is True

    def test_disable_enable(self):
        tc = TelemetryClient()
        tc.disable()
        assert tc.enabled is False
        tc.enable()
        assert tc.enabled is True

    def test_increment_calls_backend(self):
        backend = MagicMock()
        tc = TelemetryClient(backend=backend, prefix="test")
        tc.increment("counter", 2.0, tags={"k": "v"})
        backend.increment_counter.assert_called_once_with("test.counter", 2.0, {"k": "v"})

    def test_gauge_calls_backend(self):
        backend = MagicMock()
        tc = TelemetryClient(backend=backend, prefix="test")
        tc.gauge("mem", 42.0, tags={"k": "v"})
        backend.set_gauge.assert_called_once_with("test.mem", 42.0, {"k": "v"})

    def test_histogram_calls_backend(self):
        backend = MagicMock()
        tc = TelemetryClient(backend=backend, prefix="test")
        tc.histogram("latency", 1.5, tags={"k": "v"})
        backend.observe_histogram.assert_called_once_with("test.latency", 1.5, {"k": "v"})

    def test_disabled_skips_increment(self):
        backend = MagicMock()
        tc = TelemetryClient(backend=backend)
        tc.disable()
        tc.increment("counter")
        backend.increment_counter.assert_not_called()

    def test_disabled_skips_gauge(self):
        backend = MagicMock()
        tc = TelemetryClient(backend=backend)
        tc.disable()
        tc.gauge("g", 1.0)
        backend.set_gauge.assert_not_called()

    def test_disabled_skips_histogram(self):
        backend = MagicMock()
        tc = TelemetryClient(backend=backend)
        tc.disable()
        tc.histogram("h", 1.0)
        backend.observe_histogram.assert_not_called()

    def test_sampling_filters(self):
        backend = MagicMock()
        cfg = SamplingConfig(default_rate=0.0)
        tc = TelemetryClient(backend=backend, sampling=cfg, prefix="p")
        tc.increment("counter")
        tc.gauge("g", 1.0)
        tc.histogram("h", 1.0)
        backend.increment_counter.assert_not_called()
        backend.set_gauge.assert_not_called()
        backend.observe_histogram.assert_not_called()

    def test_no_prefix(self):
        backend = MagicMock()
        tc = TelemetryClient(backend=backend, prefix="")
        tc.increment("raw_name")
        backend.increment_counter.assert_called_once()
        args = backend.increment_counter.call_args
        assert args[0][0] == "raw_name"

    def test_full_name_with_prefix(self):
        tc = TelemetryClient(prefix="geo")
        assert tc._full_name("metric") == "geo.metric"

    def test_full_name_without_prefix(self):
        tc = TelemetryClient(prefix="")
        assert tc._full_name("metric") == "metric"


# ---------------------------------------------------------------------------
# Timer context manager
# ---------------------------------------------------------------------------


class TestTelemetryTimer:
    def test_timer_records_on_success(self):
        backend = MagicMock()
        tc = TelemetryClient(backend=backend, prefix="t")
        with tc.timer("op", tags={"env": "test"}) as ctx:
            ctx["data"] = 42
        backend.observe_histogram.assert_called_once()
        call_args = backend.observe_histogram.call_args
        assert call_args[0][0] == "t.op"
        tags = call_args[0][2]
        assert tags["status"] == "success"
        assert tags["env"] == "test"

    def test_timer_records_on_error(self):
        backend = MagicMock()
        tc = TelemetryClient(backend=backend, prefix="t")
        with pytest.raises(ValueError):
            with tc.timer("op") as ctx:
                raise ValueError("boom")
        backend.observe_histogram.assert_called_once()
        tags = backend.observe_histogram.call_args[0][2]
        assert tags["status"] == "error"

    def test_timer_no_record_on_error_when_disabled(self):
        backend = MagicMock()
        tc = TelemetryClient(backend=backend, prefix="t")
        with pytest.raises(ValueError):
            with tc.timer("op", record_on_error=False):
                raise ValueError("boom")
        backend.observe_histogram.assert_not_called()

    def test_timer_no_tags(self):
        backend = MagicMock()
        tc = TelemetryClient(backend=backend, prefix="t")
        with tc.timer("op"):
            pass
        tags = backend.observe_histogram.call_args[0][2]
        assert tags == {"status": "success"}


# ---------------------------------------------------------------------------
# Global singletons
# ---------------------------------------------------------------------------


class TestGlobalTelemetry:
    def test_get_telemetry_creates_singleton(self):
        import core.telemetry as mod

        old = mod._telemetry
        try:
            mod._telemetry = None
            t = get_telemetry()
            assert t is not None
            t2 = get_telemetry()
            assert t2 is t
        finally:
            mod._telemetry = old

    def test_configure_telemetry_replaces(self):
        import core.telemetry as mod

        old = mod._telemetry
        try:
            t1 = configure_telemetry(prefix="a")
            t2 = configure_telemetry(prefix="b")
            assert t1 is not t2
            assert mod._telemetry is t2
        finally:
            mod._telemetry = old

    def test_configure_with_backend(self):
        import core.telemetry as mod

        old = mod._telemetry
        try:
            backend = MagicMock()
            t = configure_telemetry(backend=backend, prefix="test")
            assert t._backend is backend
        finally:
            mod._telemetry = old

    def test_get_telemetry_with_params(self):
        import core.telemetry as mod

        old = mod._telemetry
        try:
            mod._telemetry = None
            backend = MagicMock()
            t = get_telemetry(backend=backend)
            assert t._backend is backend
        finally:
            mod._telemetry = old
