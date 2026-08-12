# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Comprehensive tests for cortex service refactor."""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import StaticPool

os.environ.setdefault("CORTEX__DATABASE__URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("CORTEX__DATABASE__POOL_SIZE", "1")
os.environ.setdefault("CORTEX__DATABASE__POOL_TIMEOUT", "30")

from cortex_service.app.api import create_app
from cortex_service.app.config import (
    ConfigurationError,
    CortexSettings,
    DatabaseSettings,
    RegimeSettings,
    RiskSettings,
    ServiceMeta,
    SignalSettings,
)
from cortex_service.app.core.signals import FeatureObservation, compute_signal
from cortex_service.app.decorators import with_retry
from cortex_service.app.errors import (
    DatabaseError,
)
from cortex_service.app.ethics.risk import compute_risk
from cortex_service.app.services.regime_service import (
    BayesianShadowSampler,
    CacheCoherenceStatus,
    HybridLogicalClock,
    HybridLogicalTimestamp,
    RegimeCache,
    RegimeService,
)


def _test_settings() -> CortexSettings:
    return CortexSettings(
        service=ServiceMeta(),
        database=DatabaseSettings(
            url="sqlite+pysqlite:///:memory:", pool_size=1, pool_timeout=30, echo=False
        ),
        signals=SignalSettings(
            smoothing_factor=0.2,
            rescale_min=-1.0,
            rescale_max=1.0,
            volatility_floor=1e-6,
        ),
        risk=RiskSettings(
            max_absolute_exposure=2.0,
            var_confidence=0.95,
            stress_scenarios=(0.8, 0.5),
        ),
        regime=RegimeSettings(decay=0.2, min_valence=-1.0, max_valence=1.0, confidence_floor=0.1),
    )


def _sqlite_engine():
    return create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )


class TestErrorHandlers:
    """Test global exception handlers."""

    def test_cortex_error_handler(self):
        settings = _test_settings()
        engine = _sqlite_engine()
        app = create_app(settings=settings, engine=engine)
        client = TestClient(app)

        # Trigger NotFoundError
        response = client.get("/memory/nonexistent")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert "message" in data
        assert "request_id" in data

    def test_validation_error_handler(self):
        settings = _test_settings()
        engine = _sqlite_engine()
        app = create_app(settings=settings, engine=engine)
        client = TestClient(app)

        # Send invalid request (missing required fields)
        response = client.post("/signals", json={"as_of": "not-a-date"})
        assert response.status_code in (400, 422)

    def test_request_id_propagation(self):
        settings = _test_settings()
        engine = _sqlite_engine()
        app = create_app(settings=settings, engine=engine)
        client = TestClient(app)

        # Send request with custom request ID
        custom_id = "test-request-123"
        response = client.get("/health", headers={"X-Request-ID": custom_id})
        assert response.status_code == 200
        assert response.headers.get("X-Request-ID") == custom_id

        # Send request without request ID (should generate one)
        response = client.get("/health")
        assert response.status_code == 200
        assert "X-Request-ID" in response.headers


class TestReadinessEndpoint:
    """Test /ready endpoint."""

    def test_readiness_check_success(self):
        settings = _test_settings()
        engine = _sqlite_engine()
        app = create_app(settings=settings, engine=engine)
        client = TestClient(app)

        response = client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert "ready" in data
        assert "checks" in data
        assert data["checks"]["database"] is True


class TestSignalEdgeCases:
    """Test signal computation edge cases."""

    def test_signal_zero_std(self):
        settings = SignalSettings()
        features = [
            FeatureObservation(
                instrument="TEST",
                name="feature1",
                value=1.0,
                mean=0.5,
                std=0.0,  # Zero std
                weight=1.0,
            )
        ]
        signal = compute_signal(features, settings)
        assert signal.instrument == "TEST"
        assert -1.0 <= signal.strength <= 1.0

    def test_signal_none_std(self):
        settings = SignalSettings()
        features = [
            FeatureObservation(
                instrument="TEST",
                name="feature1",
                value=1.0,
                mean=0.5,
                std=None,  # None std
                weight=1.0,
            )
        ]
        signal = compute_signal(features, settings)
        assert signal.instrument == "TEST"

    def test_signal_empty_bundle_raises(self):
        settings = SignalSettings()
        with pytest.raises(ValueError, match="cannot be empty"):
            compute_signal([], settings)


class TestRiskEdgeCases:
    """Test risk assessment edge cases."""

    def test_risk_invalid_confidence(self):
        # Now caught at config level
        with pytest.raises(ConfigurationError, match="between 0 and 1"):
            RiskSettings(var_confidence=1.5)

    def test_risk_zero_confidence(self):
        # Now caught at config level
        with pytest.raises(ConfigurationError, match="between 0 and 1"):
            RiskSettings(var_confidence=0.0)

    def test_risk_empty_exposures(self):
        settings = RiskSettings()
        assessment = compute_risk([], settings)
        assert assessment.score == 0.0
        assert assessment.value_at_risk == 0.0
        assert len(assessment.breached) == 0


class TestConfigurationValidation:
    """Test configuration validation."""

    def test_stress_scenarios_must_be_unique(self):
        with pytest.raises(ConfigurationError, match="unique"):
            RiskSettings(stress_scenarios=(0.8, 0.8, 0.5))

    def test_stress_scenarios_must_be_positive(self):
        with pytest.raises(ConfigurationError, match="positive"):
            RiskSettings(stress_scenarios=(0.8, -0.5))

    def test_stress_scenarios_cannot_be_empty(self):
        with pytest.raises(ConfigurationError, match="cannot be empty"):
            RiskSettings(stress_scenarios=())

    def test_var_confidence_range(self):
        with pytest.raises(ConfigurationError, match="between 0 and 1"):
            RiskSettings(var_confidence=1.5)


class TestRetryDecorator:
    """Test retry/backoff decorator."""

    def test_retry_on_operational_error(self):
        attempt_count = 0

        @with_retry(max_attempts=3, initial_delay=0.01, max_delay=0.1)
        def failing_function():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise OperationalError("db error", None, None)
            return "success"

        result = failing_function()
        assert result == "success"
        assert attempt_count == 3

    def test_retry_exhausted_raises_database_error(self):
        @with_retry(max_attempts=2, initial_delay=0.01)
        def always_failing():
            raise OperationalError("db error", None, None)

        with pytest.raises(DatabaseError, match="after 2 attempts"):
            always_failing()


class TestRegimeCache:
    """Test regime caching."""

    def test_cache_miss_returns_none(self):
        cache = RegimeCache()
        assert cache.get() is None

    def test_cache_hit_returns_state(self):
        from cortex_service.app.modulation.regime import RegimeState

        cache = RegimeCache()
        state = RegimeState(
            label="bullish", valence=0.7, confidence=0.8, as_of=datetime.now(timezone.utc)
        )
        cache.write_through(state, version=10)
        retrieved = cache.get()
        assert retrieved is not None
        assert retrieved.state.label == "bullish"
        assert retrieved.version == 10

    def test_cache_miss_for_insufficient_version(self):
        from cortex_service.app.modulation.regime import RegimeState

        cache = RegimeCache()
        state = RegimeState(
            label="bullish", valence=0.7, confidence=0.8, as_of=datetime.now(timezone.utc)
        )
        cache.write_through(state, version=3)
        assert cache.get(min_version=4) is None

    def test_cache_invalidate(self):
        from cortex_service.app.modulation.regime import RegimeState

        cache = RegimeCache()
        state = RegimeState(
            label="bullish", valence=0.7, confidence=0.8, as_of=datetime.now(timezone.utc)
        )
        cache.write_through(state, version=5)
        cache.invalidate()
        assert cache.get() is None

    def test_write_through_restores_coherent_status(self):
        from cortex_service.app.modulation.regime import RegimeState

        cache = RegimeCache()
        cache.mark_divergent()
        assert cache.status is CacheCoherenceStatus.DIVERGENT

        state = RegimeState(
            label="neutral", valence=0.0, confidence=0.9, as_of=datetime.now(timezone.utc)
        )
        cache.write_through(state, version=6)
        assert cache.status is CacheCoherenceStatus.COHERENT

    def test_hlc_receive_is_monotonic(self):
        clock = HybridLogicalClock(wall_clock_ms=lambda: 1_000)
        first = clock.send()
        second = clock.receive(HybridLogicalTimestamp(wall_time_ms=2_000, logical=4))
        assert second.wall_time_ms >= first.wall_time_ms
        assert second.to_version() > first.to_version()

    def test_bayesian_sampler_escalates_rate_on_divergence(self):
        sampler = BayesianShadowSampler(base_rate=0.05)
        initial_rate = sampler.sample_rate()
        for _ in range(6):
            sampler.observe(divergent=True)
        assert sampler.sample_rate() > initial_rate

    def test_coherence_entropy_signal_scales_with_volatility(self):
        service = RegimeService(RegimeSettings())
        low = service._coherence_entropy_signal(volatility=0.1)  # noqa: SLF001
        high = service._coherence_entropy_signal(volatility=0.9)  # noqa: SLF001
        assert high >= low

    def test_hlc_backwards_drift_marks_cache_critical(self):
        service = RegimeService(
            RegimeSettings(),
            max_hlc_backwards_drift_ms=1,
        )

        class _FakeHlc:
            @property
            def last_wall_time_ms(self):
                return 10_000

            def wall_now_ms(self):
                return 0

            def receive(self, remote):
                return remote

        service._hlc = _FakeHlc()  # noqa: SLF001
        _ = service._compute_version(datetime.now(timezone.utc))  # noqa: SLF001
        assert service._cache.status is CacheCoherenceStatus.CRITICAL_DIVERGENT  # noqa: SLF001

    def test_rcu_snapshot_stress_readers_and_writer(self):
        from cortex_service.app.modulation.regime import RegimeState

        cache = RegimeCache()
        stop = threading.Event()
        failures: list[str] = []

        def writer() -> None:
            for idx in range(2_000):
                state = RegimeState(
                    label="neutral" if idx % 2 == 0 else "bullish",
                    valence=float(idx % 10) / 10.0,
                    confidence=0.9,
                    as_of=datetime.now(timezone.utc),
                )
                cache.write_through(state, version=idx + 1)
            stop.set()

        def reader() -> None:
            while not stop.is_set():
                entry = cache.get()
                if entry is None:
                    continue
                try:
                    assert isinstance(entry.state.label, str)
                    assert isinstance(entry.version, int)
                    assert entry.version >= 1
                except AssertionError as exc:  # pragma: no cover - defensive capture
                    failures.append(str(exc))
                    stop.set()

        threads = [threading.Thread(target=reader) for _ in range(10)]
        writer_thread = threading.Thread(target=writer)
        for thread in threads:
            thread.start()
        writer_thread.start()
        writer_thread.join(timeout=10)
        stop.set()
        for thread in threads:
            thread.join(timeout=10)

        assert not failures

    def test_state_compare_epsilon_handles_rounding_noise(self):
        from cortex_service.app.modulation.regime import RegimeState

        service = RegimeService(RegimeSettings(), state_compare_epsilon=1e-9)
        left = RegimeState(
            label="neutral",
            valence=1.0,
            confidence=0.9999999991,
            as_of=datetime.now(timezone.utc),
        )
        right = RegimeState(
            label="neutral",
            valence=0.9999999992,
            confidence=1.0,
            as_of=left.as_of,
        )

        assert service._state_equals(left, right)  # noqa: SLF001

    def test_entropy_driven_sampling_increases_with_injected_drift(self):
        sampler = BayesianShadowSampler(base_rate=0.05)
        baseline_rate = sampler.sample_rate()

        for _ in range(20):
            sampler.observe(divergent=True)
        drifted_rate = sampler.sample_rate()

        assert drifted_rate > baseline_rate

    def test_bayesian_sampler_decay_preserves_adaptivity(self):
        sampler = BayesianShadowSampler(base_rate=0.05, decay=0.99, decay_interval=10)
        for _ in range(200):
            sampler.observe(divergent=True)
        high_rate = sampler.sample_rate()
        for _ in range(200):
            sampler.observe(divergent=False)
        cooled_rate = sampler.sample_rate()
        assert 0.01 <= cooled_rate <= 1.0
        assert cooled_rate < high_rate

    def test_hlc_send_monotonic_under_backwards_clock_fuzz(self):
        timeline = [10_000, 9_000, 8_000, 12_000, 11_000, 20_000]
        index = {"i": 0}

        def _wall() -> int:
            i = min(index["i"], len(timeline) - 1)
            value = timeline[i]
            index["i"] += 1
            return value

        clock = HybridLogicalClock(wall_clock_ms=_wall)
        last_version = clock.send().to_version()
        for _ in range(10):
            current = clock.send().to_version()
            assert current > last_version
            last_version = current

    def test_get_current_regime_uses_cache_fast_path(self):
        from cortex_service.app.modulation.regime import RegimeState

        service = RegimeService(RegimeSettings())
        state = RegimeState(
            label="neutral",
            valence=0.2,
            confidence=0.9,
            as_of=datetime.now(timezone.utc),
        )
        service._cache.write_through(state, version=1)  # noqa: SLF001

        class _Repo:
            def latest_regime(self):
                return None

        resolved = service.get_current_regime(_Repo())  # type: ignore[arg-type]
        assert resolved.label == state.label

    def test_get_current_regime_raises_on_empty_repository(self):
        from cortex_service.app.errors import ValidationError as CortexValidationError

        service = RegimeService(RegimeSettings())

        class _Repo:
            def latest_regime(self):
                return None

        with pytest.raises(CortexValidationError, match="No regime state found"):
            service.get_current_regime(_Repo())  # type: ignore[arg-type]


class TestRegimeExtreme:
    """Test regime transitions under extreme conditions."""

    def test_extreme_volatility(self):
        settings = _test_settings()
        engine = _sqlite_engine()
        app = create_app(settings=settings, engine=engine)
        client = TestClient(app)

        # Very high volatility should lead to low confidence
        response = client.post(
            "/regime",
            json={
                "feedback": 0.5,
                "volatility": 0.99,  # Extreme volatility
                "as_of": datetime.now(tz=timezone.utc).isoformat(),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["label"] == "indeterminate"  # Low confidence
        assert data["confidence"] < 0.25

    def test_extreme_decay(self):
        from cortex_service.app.modulation.regime import RegimeModulator, RegimeState

        settings = RegimeSettings(decay=0.99)  # Very high decay
        modulator = RegimeModulator(settings)

        previous = RegimeState(
            label="bearish", valence=-0.8, confidence=0.9, as_of=datetime.now(timezone.utc)
        )
        # Apply strong positive feedback
        updated = modulator.update(previous, 0.9, 0.1, datetime.now(timezone.utc))
        # With high decay, new feedback should dominate
        assert updated.valence > 0.5


class TestServiceMethods:
    """Test service layer methods."""

    def test_signal_service_empty_features_raises(self):
        from cortex_service.app.errors import ValidationError as CortexValidationError
        from cortex_service.app.services.signal_service import SignalService

        service = SignalService(SignalSettings())
        with pytest.raises(
            (CortexValidationError, ValidationError, ValueError),
            match="feature|required",
        ):
            service.compute_signals([])

    def test_risk_service_negative_volatility(self):
        settings = _test_settings()
        engine = _sqlite_engine()
        app = create_app(settings=settings, engine=engine)
        client = TestClient(app)

        response = client.post(
            "/regime",
            json={
                "feedback": 0.5,
                "volatility": -0.1,  # Negative volatility
                "as_of": datetime.now(tz=timezone.utc).isoformat(),
            },
        )
        # Should be rejected by Pydantic validation
        assert response.status_code in (400, 422)


class TestRepositoryBehaviors:
    """Test repository edge cases."""

    def test_repository_bulk_upsert(self):
        settings = _test_settings()
        engine = _sqlite_engine()
        app = create_app(settings=settings, engine=engine)
        client = TestClient(app)

        # Store initial exposures
        as_of = datetime.now(tz=timezone.utc).isoformat()
        response1 = client.post(
            "/memory",
            json={
                "exposures": [
                    {
                        "portfolio_id": "test",
                        "instrument": "AAPL",
                        "exposure": 100.0,
                        "leverage": 1.0,
                        "as_of": as_of,
                    }
                ]
            },
        )
        assert response1.status_code == 202

        # Update with same as_of (should upsert)
        response2 = client.post(
            "/memory",
            json={
                "exposures": [
                    {
                        "portfolio_id": "test",
                        "instrument": "AAPL",
                        "exposure": 200.0,  # Updated
                        "leverage": 1.5,
                        "as_of": as_of,
                    }
                ]
            },
        )
        assert response2.status_code == 202

        # Fetch and verify update
        response3 = client.get("/memory/test")
        assert response3.status_code == 200
        data = response3.json()
        assert data["exposures"][0]["exposure"] == 200.0
        assert data["exposures"][0]["leverage"] == 1.5


class TestMetricsEmission:
    """Test that metrics are emitted correctly."""

    def test_metrics_endpoint_accessible(self):
        settings = _test_settings()
        engine = _sqlite_engine()
        app = create_app(settings=settings, engine=engine)
        client = TestClient(app)

        response = client.get("/metrics")
        assert response.status_code == 200
        assert "cortex_" in response.text  # Should contain our metrics

    def test_error_count_metric(self):
        settings = _test_settings()
        engine = _sqlite_engine()
        app = create_app(settings=settings, engine=engine)
        client = TestClient(app)

        # Trigger an error
        client.get("/memory/nonexistent")

        # Check metrics
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "cortex_error_total" in response.text


class TestInputValidation:
    """Test input length validation."""

    def test_instrument_length_validation(self):
        settings = _test_settings()
        engine = _sqlite_engine()
        app = create_app(settings=settings, engine=engine)
        client = TestClient(app)

        # Instrument name too long
        very_long_instrument = "X" * 100
        response = client.post(
            "/signals",
            json={
                "as_of": datetime.now(tz=timezone.utc).isoformat(),
                "features": [
                    {
                        "instrument": very_long_instrument,
                        "name": "test",
                        "value": 1.0,
                    }
                ],
            },
        )
        assert response.status_code in (400, 422)  # Validation error
