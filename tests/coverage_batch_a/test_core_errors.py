# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Behavioral coverage tests for core.errors."""

from __future__ import annotations

from datetime import datetime, timezone

from core.errors import (
    ConfigError,
    DataQualityError,
    EngineError,
    ErrorContext,
    GeoSyncError,
    IntegrityError,
    PipelineError,
    ResourceBudgetError,
    ValidationError,
)


class TestErrorContext:
    def test_default_timestamp_is_utc(self) -> None:
        ctx = ErrorContext()
        assert ctx.timestamp.tzinfo == timezone.utc
        assert ctx.correlation_id is None

    def test_to_dict_minimal_only_timestamp(self) -> None:
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        ctx = ErrorContext(timestamp=ts)
        assert ctx.to_dict() == {"timestamp": ts.isoformat()}

    def test_to_dict_full(self) -> None:
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        ctx = ErrorContext(
            correlation_id="cid",
            component="engine",
            operation="tick",
            timestamp=ts,
            details={"k": "v"},
        )
        result = ctx.to_dict()
        assert result == {
            "timestamp": ts.isoformat(),
            "correlation_id": "cid",
            "component": "engine",
            "operation": "tick",
            "details": {"k": "v"},
        }


class TestGeoSyncError:
    def test_basic(self) -> None:
        err = GeoSyncError("boom")
        assert err.message == "boom"
        assert isinstance(err.context, ErrorContext)
        assert err.error_code is None
        assert str(err) == "boom"

    def test_str_with_code(self) -> None:
        err = GeoSyncError("boom", error_code="E1")
        assert str(err) == "[E1] boom"

    def test_str_with_correlation_id(self) -> None:
        ctx = ErrorContext(correlation_id="abc")
        err = GeoSyncError("boom", context=ctx)
        assert str(err) == "boom (correlation_id=abc)"

    def test_str_with_code_and_correlation(self) -> None:
        ctx = ErrorContext(correlation_id="abc")
        err = GeoSyncError("boom", context=ctx, error_code="E1")
        assert str(err) == "[E1] boom (correlation_id=abc)"

    def test_to_dict(self) -> None:
        ctx = ErrorContext(correlation_id="abc")
        err = GeoSyncError("boom", context=ctx, error_code="E1")
        result = err.to_dict()
        assert result["error_type"] == "GeoSyncError"
        assert result["message"] == "boom"
        assert result["error_code"] == "E1"
        assert result["context"]["correlation_id"] == "abc"


class TestValidationError:
    def test_default_code(self) -> None:
        err = ValidationError("bad")
        assert err.error_code == "VALIDATION_ERROR"
        assert err.field is None

    def test_custom_code_override(self) -> None:
        err = ValidationError("bad", error_code="CUSTOM")
        assert err.error_code == "CUSTOM"

    def test_to_dict_all_fields(self) -> None:
        err = ValidationError(
            "bad", field="price", value=-1, constraint="non-negative"
        )
        result = err.to_dict()
        assert result["field"] == "price"
        assert result["value"] == repr(-1)
        assert result["constraint"] == "non-negative"

    def test_to_dict_omits_none_value(self) -> None:
        err = ValidationError("bad", field="price")
        result = err.to_dict()
        assert result["field"] == "price"
        assert "value" not in result
        assert "constraint" not in result

    def test_value_zero_is_serialized(self) -> None:
        # value=0 is not None, so it should appear.
        err = ValidationError("bad", value=0)
        assert err.to_dict()["value"] == repr(0)


class TestConfigError:
    def test_defaults(self) -> None:
        err = ConfigError("cfg")
        assert err.error_code == "CONFIG_ERROR"

    def test_to_dict_fields_and_secret_omission(self) -> None:
        err = ConfigError(
            "cfg",
            config_key="db.url",
            config_value="secret://x",
            expected_type="URI",
        )
        result = err.to_dict()
        assert result["config_key"] == "db.url"
        assert result["expected_type"] == "URI"
        # config_value intentionally not serialized.
        assert "config_value" not in result

    def test_to_dict_omits_none(self) -> None:
        err = ConfigError("cfg")
        result = err.to_dict()
        assert "config_key" not in result
        assert "expected_type" not in result


class TestIntegrityError:
    def test_defaults(self) -> None:
        err = IntegrityError("bad")
        assert err.error_code == "INTEGRITY_ERROR"

    def test_to_dict_all(self) -> None:
        err = IntegrityError(
            "bad",
            artifact="m.pt",
            expected_checksum="abc",
            actual_checksum="def",
            security_violation="tamper",
        )
        result = err.to_dict()
        assert result["artifact"] == "m.pt"
        assert result["expected_checksum"] == "abc"
        assert result["actual_checksum"] == "def"
        assert result["security_violation"] == "tamper"

    def test_to_dict_omits_none(self) -> None:
        err = IntegrityError("bad")
        result = err.to_dict()
        for key in ("artifact", "expected_checksum", "actual_checksum", "security_violation"):
            assert key not in result


class TestResourceBudgetError:
    def test_defaults(self) -> None:
        err = ResourceBudgetError("over")
        assert err.error_code == "RESOURCE_BUDGET_ERROR"

    def test_overage_percent_ms(self) -> None:
        err = ResourceBudgetError("over", budget_ms=100.0, actual_ms=150.0)
        assert err.overage_percent == 50.0

    def test_overage_percent_bytes(self) -> None:
        err = ResourceBudgetError("over", budget_bytes=100, actual_bytes=120)
        assert err.overage_percent == 20.0

    def test_overage_percent_none_when_no_data(self) -> None:
        err = ResourceBudgetError("over")
        assert err.overage_percent is None

    def test_overage_percent_none_when_budget_zero(self) -> None:
        err = ResourceBudgetError("over", budget_ms=0.0, actual_ms=10.0)
        assert err.overage_percent is None

    def test_to_dict_ms_and_overage(self) -> None:
        err = ResourceBudgetError(
            "over", resource="cpu", budget_ms=100.0, actual_ms=150.0
        )
        result = err.to_dict()
        assert result["resource"] == "cpu"
        assert result["budget_ms"] == 100.0
        assert result["actual_ms"] == 150.0
        assert result["overage_percent"] == 50.0

    def test_to_dict_bytes(self) -> None:
        err = ResourceBudgetError("over", budget_bytes=100, actual_bytes=120)
        result = err.to_dict()
        assert result["budget_bytes"] == 100
        assert result["actual_bytes"] == 120
        assert result["overage_percent"] == 20.0

    def test_to_dict_omits_none_and_overage(self) -> None:
        err = ResourceBudgetError("over")
        result = err.to_dict()
        for key in ("resource", "budget_ms", "actual_ms", "budget_bytes", "actual_bytes"):
            assert key not in result
        assert "overage_percent" not in result


class TestEngineError:
    def test_defaults(self) -> None:
        err = EngineError("fail")
        assert err.error_code == "ENGINE_ERROR"

    def test_to_dict_all(self) -> None:
        err = EngineError("fail", stage="signal", run_id="r1", cycle_number=3)
        result = err.to_dict()
        assert result["stage"] == "signal"
        assert result["run_id"] == "r1"
        assert result["cycle_number"] == 3

    def test_to_dict_omits_none_cycle(self) -> None:
        err = EngineError("fail", stage="signal")
        result = err.to_dict()
        assert result["stage"] == "signal"
        assert "run_id" not in result
        assert "cycle_number" not in result

    def test_cycle_number_zero_serialized(self) -> None:
        err = EngineError("fail", cycle_number=0)
        assert err.to_dict()["cycle_number"] == 0


class TestPipelineError:
    def test_defaults_recoverable_true(self) -> None:
        err = PipelineError("fail")
        assert err.error_code == "PIPELINE_ERROR"
        assert err.recoverable is True
        assert err.to_dict()["recoverable"] is True

    def test_to_dict_all(self) -> None:
        err = PipelineError(
            "fail",
            pipeline="feat",
            stage="norm",
            idempotency_key="k1",
            recoverable=False,
        )
        result = err.to_dict()
        assert result["pipeline"] == "feat"
        assert result["stage"] == "norm"
        assert result["idempotency_key"] == "k1"
        assert result["recoverable"] is False

    def test_to_dict_omits_none(self) -> None:
        err = PipelineError("fail")
        result = err.to_dict()
        for key in ("pipeline", "stage", "idempotency_key"):
            assert key not in result
        assert result["recoverable"] is True


class TestDataQualityError:
    def test_is_validation_error(self) -> None:
        assert issubclass(DataQualityError, ValidationError)

    def test_default_code(self) -> None:
        err = DataQualityError("bad")
        assert err.error_code == "DATA_QUALITY_ERROR"

    def test_to_dict_all(self) -> None:
        err = DataQualityError(
            "bad",
            quality_check="null_ratio",
            threshold=0.05,
            actual_value=0.15,
            field="close",
        )
        result = err.to_dict()
        assert result["quality_check"] == "null_ratio"
        assert result["threshold"] == 0.05
        assert result["actual_value"] == 0.15
        assert result["field"] == "close"

    def test_to_dict_omits_none(self) -> None:
        err = DataQualityError("bad")
        result = err.to_dict()
        for key in ("quality_check", "threshold", "actual_value"):
            assert key not in result

    def test_threshold_zero_serialized(self) -> None:
        err = DataQualityError("bad", threshold=0.0, actual_value=0.0)
        result = err.to_dict()
        assert result["threshold"] == 0.0
        assert result["actual_value"] == 0.0
