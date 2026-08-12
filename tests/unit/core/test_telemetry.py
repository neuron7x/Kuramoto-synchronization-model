# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core.telemetry module - vendor-agnostic metrics interface."""

from __future__ import annotations

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


class TestMetricType:
    """Tests for MetricType enum."""

    def test_values(self) -> None:
        """MetricType should have expected values."""
        assert MetricType.COUNTER.value == "counter"
        assert MetricType.GAUGE.value == "gauge"
        assert MetricType.HISTOGRAM.value == "histogram"
        assert MetricType.SUMMARY.value == "summary"


class TestSamplingConfig:
    """Tests for SamplingConfig."""

    def test_default_values(self) -> None:
        """SamplingConfig should have sensible defaults."""
        config = SamplingConfig()
        assert config.default_rate == 1.0
        assert config.per_metric_rates == {}
        assert config.seed is None

    def test_custom_values(self) -> None:
        """SamplingConfig should accept custom values."""
        config = SamplingConfig(
            default_rate=0.5,
            per_metric_rates={"critical.metric": 1.0},
            seed=42,
        )
        assert config.default_rate == 0.5
        assert config.per_metric_rates["critical.metric"] == 1.0
        assert config.seed == 42

    def test_get_rate_default(self) -> None:
        """get_rate should return default for unknown metrics."""
        config = SamplingConfig(default_rate=0.7)
        assert config.get_rate("unknown.metric") == 0.7

    def test_get_rate_override(self) -> None:
        """get_rate should return override for known metrics."""
        config = SamplingConfig(
            default_rate=0.1,
            per_metric_rates={"important": 1.0},
        )
        assert config.get_rate("important") == 1.0
        assert config.get_rate("other") == 0.1

    def test_invalid_default_rate(self) -> None:
        """SamplingConfig should reject invalid default rates."""
        with pytest.raises(ValueError, match="default_rate"):
            SamplingConfig(default_rate=1.5)

        with pytest.raises(ValueError, match="default_rate"):
            SamplingConfig(default_rate=-0.1)

    def test_invalid_per_metric_rate(self) -> None:
        """SamplingConfig should reject invalid per-metric rates."""
        with pytest.raises(ValueError, match="Rate for bad_metric"):
            SamplingConfig(per_metric_rates={"bad_metric": 2.0})


class TestSampler:
    """Tests for Sampler."""

    def test_always_sample_at_1(self) -> None:
        """Sampler should always sample at rate 1.0."""
        sampler = Sampler(SamplingConfig(default_rate=1.0))
        for _ in range(100):
            assert sampler.should_sample("any.metric") is True

    def test_never_sample_at_0(self) -> None:
        """Sampler should never sample at rate 0.0."""
        sampler = Sampler(SamplingConfig(default_rate=0.0))
        for _ in range(100):
            assert sampler.should_sample("any.metric") is False

    def test_deterministic_with_seed(self) -> None:
        """Sampler should be deterministic with same seed."""
        config = SamplingConfig(default_rate=0.5, seed=12345)
        sampler1 = Sampler(config)
        sampler2 = Sampler(config)

        results1 = [sampler1.should_sample("test") for _ in range(10)]
        results2 = [sampler2.should_sample("test") for _ in range(10)]
        assert results1 == results2

    def test_per_metric_override(self) -> None:
        """Sampler should respect per-metric overrides."""
        config = SamplingConfig(
            default_rate=0.0,
            per_metric_rates={"important": 1.0},
        )
        sampler = Sampler(config)
        assert sampler.should_sample("important") is True
        assert sampler.should_sample("not_important") is False


class TestNoOpBackend:
    """Tests for NoOpBackend."""

    def test_increment_counter(self) -> None:
        """NoOpBackend.increment_counter should not raise."""
        backend = NoOpBackend()
        backend.increment_counter("test", 1.0, {"tag": "value"})

    def test_set_gauge(self) -> None:
        """NoOpBackend.set_gauge should not raise."""
        backend = NoOpBackend()
        backend.set_gauge("test", 42.0, {"tag": "value"})

    def test_observe_histogram(self) -> None:
        """NoOpBackend.observe_histogram should not raise."""
        backend = NoOpBackend()
        backend.observe_histogram("test", 0.5, {"tag": "value"})

    def test_implements_protocol(self) -> None:
        """NoOpBackend should implement MetricsBackend protocol."""
        backend = NoOpBackend()
        assert isinstance(backend, MetricsBackend)


class TestTelemetryClient:
    """Tests for TelemetryClient."""

    def test_default_creation(self) -> None:
        """TelemetryClient should work with defaults."""
        client = TelemetryClient()
        assert client.enabled is True

    def test_with_prefix(self) -> None:
        """TelemetryClient should use prefix."""
        backend = MockBackend()
        client = TelemetryClient(backend=backend, prefix="myapp")
        client.increment("requests")
        assert backend.counters[-1][0] == "myapp.requests"

    def test_increment(self) -> None:
        """increment should call backend.increment_counter."""
        backend = MockBackend()
        client = TelemetryClient(backend=backend)
        client.increment("test.counter", 5.0, {"env": "prod"})
        assert len(backend.counters) == 1
        name, value, tags = backend.counters[0]
        assert "test.counter" in name
        assert value == 5.0
        assert tags["env"] == "prod"

    def test_gauge(self) -> None:
        """gauge should call backend.set_gauge."""
        backend = MockBackend()
        client = TelemetryClient(backend=backend)
        client.gauge("test.gauge", 42.0, {"host": "server1"})
        assert len(backend.gauges) == 1
        name, value, tags = backend.gauges[0]
        assert "test.gauge" in name
        assert value == 42.0
        assert tags["host"] == "server1"

    def test_histogram(self) -> None:
        """histogram should call backend.observe_histogram."""
        backend = MockBackend()
        client = TelemetryClient(backend=backend)
        client.histogram("test.latency", 0.125, {"route": "/api"})
        assert len(backend.histograms) == 1
        name, value, tags = backend.histograms[0]
        assert "test.latency" in name
        assert value == 0.125
        assert tags["route"] == "/api"

    def test_timer_success(self) -> None:
        """timer should record duration on success."""
        backend = MockBackend()
        client = TelemetryClient(backend=backend)
        with client.timer("test.duration", tags={"op": "query"}) as ctx:
            ctx["result"] = "ok"
        assert len(backend.histograms) == 1
        name, value, tags = backend.histograms[0]
        assert "test.duration" in name
        assert value >= 0
        assert tags["status"] == "success"
        assert tags["op"] == "query"

    def test_timer_error(self) -> None:
        """timer should record duration on error."""
        backend = MockBackend()
        client = TelemetryClient(backend=backend)
        with pytest.raises(ValueError):
            with client.timer("test.duration"):
                raise ValueError("Test error")
        assert len(backend.histograms) == 1
        _, _, tags = backend.histograms[0]
        assert tags["status"] == "error"

    def test_timer_no_record_on_error(self) -> None:
        """timer with record_on_error=False should not record on error."""
        backend = MockBackend()
        client = TelemetryClient(backend=backend)
        with pytest.raises(ValueError):
            with client.timer("test.duration", record_on_error=False):
                raise ValueError("Test error")
        assert len(backend.histograms) == 0

    def test_disable_enable(self) -> None:
        """disable/enable should control metric collection."""
        backend = MockBackend()
        client = TelemetryClient(backend=backend)

        client.increment("test1")
        assert len(backend.counters) == 1

        client.disable()
        client.increment("test2")
        assert len(backend.counters) == 1  # Not incremented

        client.enable()
        client.increment("test3")
        assert len(backend.counters) == 2

    def test_sampling(self) -> None:
        """TelemetryClient should respect sampling config."""
        backend = MockBackend()
        sampling = SamplingConfig(default_rate=0.0)  # Never sample
        client = TelemetryClient(backend=backend, sampling=sampling)

        for _ in range(100):
            client.increment("test")

        assert len(backend.counters) == 0


class TestConfigureTelemetry:
    """Tests for configure_telemetry function."""

    def test_configure_returns_client(self) -> None:
        """configure_telemetry should return a TelemetryClient."""
        client = configure_telemetry(prefix="test")
        assert isinstance(client, TelemetryClient)

    def test_get_telemetry_returns_same(self) -> None:
        """get_telemetry should return global instance."""
        configure_telemetry(prefix="global_test")
        client1 = get_telemetry()
        client2 = get_telemetry()
        assert client1 is client2


class TestPrometheusBackend:
    """Tests for PrometheusBackend."""

    def test_creation(self) -> None:
        """PrometheusBackend should be creatable."""
        backend = PrometheusBackend()
        # Should not raise even if prometheus_client not installed
        assert backend is not None

    def test_implements_protocol(self) -> None:
        """PrometheusBackend should implement MetricsBackend protocol."""
        backend = PrometheusBackend()
        assert isinstance(backend, MetricsBackend)


class MockBackend:
    """Mock backend for testing TelemetryClient."""

    def __init__(self) -> None:
        self.counters: list[tuple[str, float, dict[str, str]]] = []
        self.gauges: list[tuple[str, float, dict[str, str]]] = []
        self.histograms: list[tuple[str, float, dict[str, str]]] = []

    def increment_counter(
        self,
        name: str,
        value: float = 1.0,
        tags: dict[str, str] | None = None,
    ) -> None:
        self.counters.append((name, value, dict(tags or {})))

    def set_gauge(
        self,
        name: str,
        value: float,
        tags: dict[str, str] | None = None,
    ) -> None:
        self.gauges.append((name, value, dict(tags or {})))

    def observe_histogram(
        self,
        name: str,
        value: float,
        tags: dict[str, str] | None = None,
    ) -> None:
        self.histograms.append((name, value, dict(tags or {})))
