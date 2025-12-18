# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for core.errors module - typed domain errors."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.errors import (
    ConfigError,
    DataQualityError,
    EngineError,
    ErrorContext,
    IntegrityError,
    PipelineError,
    ResourceBudgetError,
    TradePulseError,
    ValidationError,
)


class TestErrorContext:
    """Tests for ErrorContext dataclass."""

    def test_default_values(self) -> None:
        """ErrorContext should have sensible defaults."""
        ctx = ErrorContext()
        assert ctx.correlation_id is None
        assert ctx.component is None
        assert ctx.operation is None
        assert ctx.timestamp is not None
        assert ctx.details == {}

    def test_with_all_values(self) -> None:
        """ErrorContext should accept all values."""
        now = datetime.now(timezone.utc)
        ctx = ErrorContext(
            correlation_id="abc123",
            component="engine",
            operation="signal_generation",
            timestamp=now,
            details={"key": "value"},
        )
        assert ctx.correlation_id == "abc123"
        assert ctx.component == "engine"
        assert ctx.operation == "signal_generation"
        assert ctx.timestamp == now
        assert ctx.details == {"key": "value"}

    def test_to_dict(self) -> None:
        """ErrorContext.to_dict should serialize correctly."""
        ctx = ErrorContext(
            correlation_id="test-123",
            component="data",
            operation="ingest",
            details={"source": "exchange"},
        )
        result = ctx.to_dict()
        assert result["correlation_id"] == "test-123"
        assert result["component"] == "data"
        assert result["operation"] == "ingest"
        assert result["details"] == {"source": "exchange"}
        assert "timestamp" in result

    def test_to_dict_minimal(self) -> None:
        """to_dict should only include set fields."""
        ctx = ErrorContext()
        result = ctx.to_dict()
        assert "timestamp" in result
        assert "correlation_id" not in result
        assert "component" not in result


class TestTradePulseError:
    """Tests for base TradePulseError."""

    def test_basic_creation(self) -> None:
        """TradePulseError should accept basic message."""
        err = TradePulseError("Something went wrong")
        assert str(err) == "Something went wrong"
        assert err.message == "Something went wrong"
        assert err.context is not None
        assert err.error_code is None

    def test_with_error_code(self) -> None:
        """TradePulseError should include error code in string."""
        err = TradePulseError("Failed", error_code="E001")
        assert "[E001]" in str(err)
        assert err.error_code == "E001"

    def test_with_correlation_id(self) -> None:
        """TradePulseError should include correlation_id in string."""
        ctx = ErrorContext(correlation_id="corr-123")
        err = TradePulseError("Failed", context=ctx)
        assert "corr-123" in str(err)

    def test_to_dict(self) -> None:
        """TradePulseError.to_dict should serialize correctly."""
        err = TradePulseError("Test error", error_code="TEST_001")
        result = err.to_dict()
        assert result["error_type"] == "TradePulseError"
        assert result["message"] == "Test error"
        assert result["error_code"] == "TEST_001"
        assert "context" in result

    def test_is_exception(self) -> None:
        """TradePulseError should be raisable."""
        with pytest.raises(TradePulseError) as exc_info:
            raise TradePulseError("Test exception")
        assert exc_info.value.message == "Test exception"


class TestValidationError:
    """Tests for ValidationError."""

    def test_basic_creation(self) -> None:
        """ValidationError should work with just a message."""
        err = ValidationError("Invalid input")
        assert err.error_code == "VALIDATION_ERROR"
        assert err.field is None
        assert err.value is None
        assert err.constraint is None

    def test_with_details(self) -> None:
        """ValidationError should capture field details."""
        err = ValidationError(
            "Invalid price",
            field="close_price",
            value=-10.5,
            constraint="must be non-negative",
        )
        assert err.field == "close_price"
        assert err.value == -10.5
        assert err.constraint == "must be non-negative"

    def test_to_dict(self) -> None:
        """ValidationError.to_dict should include extra fields."""
        err = ValidationError(
            "Invalid",
            field="amount",
            value=999,
            constraint="max 100",
        )
        result = err.to_dict()
        assert result["field"] == "amount"
        assert "999" in result["value"]
        assert result["constraint"] == "max 100"

    def test_is_tradepulse_error(self) -> None:
        """ValidationError should be a TradePulseError."""
        err = ValidationError("Test")
        assert isinstance(err, TradePulseError)


class TestConfigError:
    """Tests for ConfigError."""

    def test_basic_creation(self) -> None:
        """ConfigError should work with just a message."""
        err = ConfigError("Invalid config")
        assert err.error_code == "CONFIG_ERROR"
        assert err.config_key is None

    def test_with_details(self) -> None:
        """ConfigError should capture config details."""
        err = ConfigError(
            "Invalid database URL",
            config_key="database.url",
            config_value="not-a-url",
            expected_type="valid PostgreSQL URI",
        )
        assert err.config_key == "database.url"
        assert err.config_value == "not-a-url"
        assert err.expected_type == "valid PostgreSQL URI"

    def test_to_dict_excludes_value(self) -> None:
        """to_dict should NOT include config_value (security)."""
        err = ConfigError(
            "Bad secret",
            config_key="api_key",
            config_value="super-secret-key",
        )
        result = err.to_dict()
        assert result["config_key"] == "api_key"
        assert "config_value" not in result
        assert "super-secret" not in str(result)


class TestIntegrityError:
    """Tests for IntegrityError."""

    def test_basic_creation(self) -> None:
        """IntegrityError should work with just a message."""
        err = IntegrityError("Checksum mismatch")
        assert err.error_code == "INTEGRITY_ERROR"
        assert err.artifact is None

    def test_with_checksum_details(self) -> None:
        """IntegrityError should capture checksum details."""
        err = IntegrityError(
            "Artifact checksum mismatch",
            artifact="model.pt",
            expected_checksum="abc123",
            actual_checksum="def456",
        )
        assert err.artifact == "model.pt"
        assert err.expected_checksum == "abc123"
        assert err.actual_checksum == "def456"

    def test_security_violation(self) -> None:
        """IntegrityError should capture security violations."""
        err = IntegrityError(
            "TLS verification failed",
            security_violation="certificate_expired",
        )
        assert err.security_violation == "certificate_expired"


class TestResourceBudgetError:
    """Tests for ResourceBudgetError."""

    def test_basic_creation(self) -> None:
        """ResourceBudgetError should work with just a message."""
        err = ResourceBudgetError("Budget exceeded")
        assert err.error_code == "RESOURCE_BUDGET_ERROR"

    def test_latency_budget(self) -> None:
        """ResourceBudgetError should handle latency budgets."""
        err = ResourceBudgetError(
            "Latency budget exceeded",
            resource="cpu_time",
            budget_ms=100.0,
            actual_ms=150.0,
        )
        assert err.resource == "cpu_time"
        assert err.budget_ms == 100.0
        assert err.actual_ms == 150.0

    def test_memory_budget(self) -> None:
        """ResourceBudgetError should handle memory budgets."""
        err = ResourceBudgetError(
            "Memory budget exceeded",
            resource="heap",
            budget_bytes=1_000_000,
            actual_bytes=1_500_000,
        )
        assert err.budget_bytes == 1_000_000
        assert err.actual_bytes == 1_500_000

    def test_overage_percent(self) -> None:
        """overage_percent should calculate correctly."""
        err = ResourceBudgetError(
            "Over budget",
            budget_ms=100.0,
            actual_ms=150.0,
        )
        assert err.overage_percent == 50.0

        err2 = ResourceBudgetError(
            "Over budget",
            budget_bytes=100,
            actual_bytes=200,
        )
        assert err2.overage_percent == 100.0

        err3 = ResourceBudgetError("No details")
        assert err3.overage_percent is None

    def test_to_dict(self) -> None:
        """to_dict should include overage_percent."""
        err = ResourceBudgetError(
            "Over budget",
            resource="latency",
            budget_ms=100.0,
            actual_ms=150.0,
        )
        result = err.to_dict()
        assert result["resource"] == "latency"
        assert result["budget_ms"] == 100.0
        assert result["actual_ms"] == 150.0
        assert result["overage_percent"] == 50.0


class TestEngineError:
    """Tests for EngineError."""

    def test_basic_creation(self) -> None:
        """EngineError should work with just a message."""
        err = EngineError("Engine failed")
        assert err.error_code == "ENGINE_ERROR"

    def test_with_context(self) -> None:
        """EngineError should capture engine context."""
        err = EngineError(
            "Signal generation failed",
            stage="signal",
            run_id="run-123",
            cycle_number=42,
        )
        assert err.stage == "signal"
        assert err.run_id == "run-123"
        assert err.cycle_number == 42


class TestPipelineError:
    """Tests for PipelineError."""

    def test_basic_creation(self) -> None:
        """PipelineError should work with just a message."""
        err = PipelineError("Pipeline failed")
        assert err.error_code == "PIPELINE_ERROR"
        assert err.recoverable is True  # Default

    def test_with_context(self) -> None:
        """PipelineError should capture pipeline context."""
        err = PipelineError(
            "Stage failed",
            pipeline="feature_engineering",
            stage="normalization",
            idempotency_key="pipe-abc123",
            recoverable=False,
        )
        assert err.pipeline == "feature_engineering"
        assert err.stage == "normalization"
        assert err.idempotency_key == "pipe-abc123"
        assert err.recoverable is False


class TestDataQualityError:
    """Tests for DataQualityError."""

    def test_basic_creation(self) -> None:
        """DataQualityError should work with just a message."""
        err = DataQualityError("Quality check failed")
        assert err.error_code == "DATA_QUALITY_ERROR"

    def test_with_quality_details(self) -> None:
        """DataQualityError should capture quality metrics."""
        err = DataQualityError(
            "Too many nulls",
            quality_check="null_ratio",
            threshold=0.05,
            actual_value=0.15,
            field="close_price",
        )
        assert err.quality_check == "null_ratio"
        assert err.threshold == 0.05
        assert err.actual_value == 0.15
        assert err.field == "close_price"

    def test_is_validation_error(self) -> None:
        """DataQualityError should be a ValidationError."""
        err = DataQualityError("Test")
        assert isinstance(err, ValidationError)
        assert isinstance(err, TradePulseError)
