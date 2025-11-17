"""Comprehensive tests for cortex service refactor."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import StaticPool

os.environ.setdefault("CORTEX__DATABASE__URL", "'sqlite+pysqlite:///:memory:'")
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
from cortex_service.app.services.regime_service import RegimeCache


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
        regime=RegimeSettings(
            decay=0.2, min_valence=-1.0, max_valence=1.0, confidence_floor=0.1
        ),
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
        cache = RegimeCache(ttl_seconds=1.0)
        assert cache.get() is None

    def test_cache_hit_returns_state(self):
        from cortex_service.app.modulation.regime import RegimeState

        cache = RegimeCache(ttl_seconds=1.0)
        state = RegimeState(
            label="bullish", valence=0.7, confidence=0.8, as_of=datetime.now(UTC)
        )
        cache.set(state)
        retrieved = cache.get()
        assert retrieved is not None
        assert retrieved.label == "bullish"

    def test_cache_expires_after_ttl(self):
        from cortex_service.app.modulation.regime import RegimeState

        cache = RegimeCache(ttl_seconds=0.05)  # Very short TTL
        state = RegimeState(
            label="bullish", valence=0.7, confidence=0.8, as_of=datetime.now(UTC)
        )
        cache.set(state)
        time.sleep(0.1)  # Wait for expiration
        assert cache.get() is None

    def test_cache_invalidate(self):
        from cortex_service.app.modulation.regime import RegimeState

        cache = RegimeCache(ttl_seconds=10.0)
        state = RegimeState(
            label="bullish", valence=0.7, confidence=0.8, as_of=datetime.now(UTC)
        )
        cache.set(state)
        cache.invalidate()
        assert cache.get() is None


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
                "as_of": datetime.now(tz=UTC).isoformat(),
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
            label="bearish", valence=-0.8, confidence=0.9, as_of=datetime.now(UTC)
        )
        # Apply strong positive feedback
        updated = modulator.update(previous, 0.9, 0.1, datetime.now(UTC))
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
                "as_of": datetime.now(tz=UTC).isoformat(),
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
        as_of = datetime.now(tz=UTC).isoformat()
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
                "as_of": datetime.now(tz=UTC).isoformat(),
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
