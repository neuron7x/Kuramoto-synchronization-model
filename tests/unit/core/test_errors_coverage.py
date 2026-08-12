# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Full coverage tests for core.errors — every error class, hierarchy,
formatting, to_dict, and edge cases for uncovered lines."""

from __future__ import annotations

from datetime import datetime

import pytest

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

# ---------------------------------------------------------------------------
# ErrorContext
# ---------------------------------------------------------------------------


class TestErrorContext:
    def test_defaults(self):
        ctx = ErrorContext()
        assert ctx.correlation_id is None
        assert ctx.component is None
        assert ctx.operation is None
        assert isinstance(ctx.timestamp, datetime)
        assert ctx.details == {}

    def test_to_dict_minimal(self):
        ctx = ErrorContext()
        d = ctx.to_dict()
        assert "timestamp" in d
        assert "correlation_id" not in d
        assert "component" not in d

    def test_to_dict_full(self):
        ctx = ErrorContext(
            correlation_id="abc-123",
            component="engine",
            operation="compute",
            details={"key": "value"},
        )
        d = ctx.to_dict()
        assert d["correlation_id"] == "abc-123"
        assert d["component"] == "engine"
        assert d["operation"] == "compute"
        assert d["details"] == {"key": "value"}


# ---------------------------------------------------------------------------
# GeoSyncError (base)
# ---------------------------------------------------------------------------


class TestGeoSyncError:
    def test_basic(self):
        err = GeoSyncError("something broke")
        assert str(err) == "something broke"
        assert err.message == "something broke"
        assert err.error_code is None

    def test_with_error_code(self):
        err = GeoSyncError("fail", error_code="ERR_001")
        assert "[ERR_001]" in str(err)

    def test_with_correlation_id(self):
        ctx = ErrorContext(correlation_id="corr-1")
        err = GeoSyncError("fail", context=ctx)
        assert "corr-1" in str(err)

    def test_with_code_and_correlation(self):
        ctx = ErrorContext(correlation_id="corr-1")
        err = GeoSyncError("fail", context=ctx, error_code="ERR_X")
        s = str(err)
        assert "[ERR_X]" in s
        assert "corr-1" in s

    def test_to_dict(self):
        ctx = ErrorContext(correlation_id="c1")
        err = GeoSyncError("fail", context=ctx, error_code="E1")
        d = err.to_dict()
        assert d["error_type"] == "GeoSyncError"
        assert d["message"] == "fail"
        assert d["error_code"] == "E1"
        assert "context" in d

    def test_is_exception(self):
        err = GeoSyncError("x")
        assert isinstance(err, Exception)


# ---------------------------------------------------------------------------
# ValidationError
# ---------------------------------------------------------------------------


class TestValidationError:
    def test_defaults(self):
        err = ValidationError("bad input")
        assert err.error_code == "VALIDATION_ERROR"
        assert err.field is None
        assert err.value is None
        assert err.constraint is None

    def test_with_all_fields(self):
        err = ValidationError(
            "bad input",
            field="price",
            value=-10.5,
            constraint="must be non-negative",
        )
        assert err.field == "price"
        assert err.value == -10.5
        assert err.constraint == "must be non-negative"

    def test_to_dict(self):
        err = ValidationError("bad", field="qty", value=0, constraint="positive")
        d = err.to_dict()
        assert d["field"] == "qty"
        assert "value" in d
        assert d["constraint"] == "positive"

    def test_to_dict_minimal(self):
        err = ValidationError("bad")
        d = err.to_dict()
        assert "field" not in d
        assert "constraint" not in d

    def test_hierarchy(self):
        err = ValidationError("x")
        assert isinstance(err, GeoSyncError)
        assert isinstance(err, Exception)


# ---------------------------------------------------------------------------
# ConfigError
# ---------------------------------------------------------------------------


class TestConfigError:
    def test_defaults(self):
        err = ConfigError("bad config")
        assert err.error_code == "CONFIG_ERROR"
        assert err.config_key is None
        assert err.config_value is None
        assert err.expected_type is None

    def test_with_details(self):
        err = ConfigError(
            "bad url",
            config_key="db.url",
            config_value="not-a-url",
            expected_type="valid PostgreSQL URI",
        )
        assert err.config_key == "db.url"
        assert err.expected_type == "valid PostgreSQL URI"

    def test_to_dict_includes_key_and_type(self):
        err = ConfigError("bad", config_key="k", expected_type="int")
        d = err.to_dict()
        assert d["config_key"] == "k"
        assert d["expected_type"] == "int"

    def test_to_dict_excludes_value(self):
        err = ConfigError("bad", config_key="k", config_value="secret")
        d = err.to_dict()
        # config_value intentionally NOT in dict to avoid leaking secrets
        assert "config_value" not in d

    def test_to_dict_minimal(self):
        err = ConfigError("bad")
        d = err.to_dict()
        assert "config_key" not in d
        assert "expected_type" not in d


# ---------------------------------------------------------------------------
# IntegrityError (covers lines 219-228)
# ---------------------------------------------------------------------------


class TestIntegrityError:
    def test_defaults(self):
        err = IntegrityError("checksum mismatch")
        assert err.error_code == "INTEGRITY_ERROR"
        assert err.artifact is None
        assert err.expected_checksum is None
        assert err.actual_checksum is None
        assert err.security_violation is None

    def test_with_all_fields(self):
        err = IntegrityError(
            "mismatch",
            artifact="model.pt",
            expected_checksum="abc",
            actual_checksum="def",
            security_violation="tampered",
        )
        assert err.artifact == "model.pt"
        assert err.security_violation == "tampered"

    def test_to_dict_full(self):
        err = IntegrityError(
            "mismatch",
            artifact="a.bin",
            expected_checksum="e1",
            actual_checksum="a1",
            security_violation="tls_fail",
        )
        d = err.to_dict()
        assert d["artifact"] == "a.bin"
        assert d["expected_checksum"] == "e1"
        assert d["actual_checksum"] == "a1"
        assert d["security_violation"] == "tls_fail"

    def test_to_dict_minimal(self):
        err = IntegrityError("oops")
        d = err.to_dict()
        assert "artifact" not in d
        assert "expected_checksum" not in d
        assert "actual_checksum" not in d
        assert "security_violation" not in d


# ---------------------------------------------------------------------------
# ResourceBudgetError (covers lines 286, 288 and overage_percent)
# ---------------------------------------------------------------------------


class TestResourceBudgetError:
    def test_defaults(self):
        err = ResourceBudgetError("budget exceeded")
        assert err.error_code == "RESOURCE_BUDGET_ERROR"
        assert err.resource is None
        assert err.budget_ms is None
        assert err.actual_ms is None
        assert err.budget_bytes is None
        assert err.actual_bytes is None

    def test_overage_percent_ms(self):
        err = ResourceBudgetError("x", budget_ms=100.0, actual_ms=150.0)
        assert err.overage_percent == pytest.approx(50.0)

    def test_overage_percent_bytes(self):
        err = ResourceBudgetError("x", budget_bytes=1000, actual_bytes=1500)
        assert err.overage_percent == pytest.approx(50.0)

    def test_overage_percent_none(self):
        err = ResourceBudgetError("x")
        assert err.overage_percent is None

    def test_overage_percent_ms_takes_precedence(self):
        err = ResourceBudgetError(
            "x", budget_ms=100.0, actual_ms=200.0, budget_bytes=100, actual_bytes=200
        )
        assert err.overage_percent == pytest.approx(100.0)

    def test_to_dict_full(self):
        err = ResourceBudgetError(
            "x",
            resource="cpu",
            budget_ms=100.0,
            actual_ms=150.0,
            budget_bytes=1000,
            actual_bytes=2000,
        )
        d = err.to_dict()
        assert d["resource"] == "cpu"
        assert d["budget_ms"] == 100.0
        assert d["actual_ms"] == 150.0
        assert d["budget_bytes"] == 1000
        assert d["actual_bytes"] == 2000
        assert "overage_percent" in d

    def test_to_dict_minimal(self):
        err = ResourceBudgetError("x")
        d = err.to_dict()
        assert "resource" not in d
        assert "budget_ms" not in d
        assert "overage_percent" not in d

    def test_to_dict_with_zero_budget_ms(self):
        # budget_ms=0.0 is falsy -> overage_percent should be None
        err = ResourceBudgetError("x", budget_ms=0.0, actual_ms=10.0)
        d = err.to_dict()
        assert d["budget_ms"] == 0.0
        assert d["actual_ms"] == 10.0

    def test_overage_percent_zero_budget_ms(self):
        err = ResourceBudgetError("x", budget_ms=0.0, actual_ms=10.0)
        assert err.overage_percent is None

    def test_overage_percent_zero_budget_bytes(self):
        err = ResourceBudgetError("x", budget_bytes=0, actual_bytes=10)
        assert err.overage_percent is None


# ---------------------------------------------------------------------------
# EngineError (covers lines 327-334)
# ---------------------------------------------------------------------------


class TestEngineError:
    def test_defaults(self):
        err = EngineError("engine fail")
        assert err.error_code == "ENGINE_ERROR"
        assert err.stage is None
        assert err.run_id is None
        assert err.cycle_number is None

    def test_with_all_fields(self):
        err = EngineError("fail", stage="signal", run_id="r1", cycle_number=42)
        assert err.stage == "signal"
        assert err.run_id == "r1"
        assert err.cycle_number == 42

    def test_to_dict_full(self):
        err = EngineError("fail", stage="s", run_id="r", cycle_number=1)
        d = err.to_dict()
        assert d["stage"] == "s"
        assert d["run_id"] == "r"
        assert d["cycle_number"] == 1

    def test_to_dict_minimal(self):
        err = EngineError("fail")
        d = err.to_dict()
        assert "stage" not in d
        assert "run_id" not in d
        assert "cycle_number" not in d

    def test_to_dict_cycle_number_zero(self):
        err = EngineError("fail", cycle_number=0)
        d = err.to_dict()
        assert d["cycle_number"] == 0


# ---------------------------------------------------------------------------
# PipelineError
# ---------------------------------------------------------------------------


class TestPipelineError:
    def test_defaults(self):
        err = PipelineError("pipe fail")
        assert err.error_code == "PIPELINE_ERROR"
        assert err.pipeline is None
        assert err.stage is None
        assert err.idempotency_key is None
        assert err.recoverable is True

    def test_with_all_fields(self):
        err = PipelineError(
            "fail",
            pipeline="etl",
            stage="transform",
            idempotency_key="k1",
            recoverable=False,
        )
        assert err.pipeline == "etl"
        assert err.recoverable is False

    def test_to_dict_full(self):
        err = PipelineError("fail", pipeline="p", stage="s", idempotency_key="k")
        d = err.to_dict()
        assert d["pipeline"] == "p"
        assert d["stage"] == "s"
        assert d["idempotency_key"] == "k"
        assert d["recoverable"] is True

    def test_to_dict_minimal(self):
        err = PipelineError("fail")
        d = err.to_dict()
        assert "pipeline" not in d
        assert "stage" not in d
        assert "idempotency_key" not in d
        assert d["recoverable"] is True

    def test_not_recoverable_in_dict(self):
        err = PipelineError("fail", recoverable=False)
        d = err.to_dict()
        assert d["recoverable"] is False


# ---------------------------------------------------------------------------
# DataQualityError
# ---------------------------------------------------------------------------


class TestDataQualityError:
    def test_defaults(self):
        err = DataQualityError("quality fail")
        assert err.error_code == "DATA_QUALITY_ERROR"
        assert err.quality_check is None
        assert err.threshold is None
        assert err.actual_value is None

    def test_with_all_fields(self):
        err = DataQualityError(
            "fail",
            quality_check="null_ratio",
            threshold=0.05,
            actual_value=0.15,
            field="col_a",
        )
        assert err.quality_check == "null_ratio"
        assert err.threshold == 0.05
        assert err.actual_value == 0.15
        assert err.field == "col_a"

    def test_to_dict_full(self):
        err = DataQualityError("fail", quality_check="qc", threshold=0.1, actual_value=0.2)
        d = err.to_dict()
        assert d["quality_check"] == "qc"
        assert d["threshold"] == 0.1
        assert d["actual_value"] == 0.2

    def test_to_dict_minimal(self):
        err = DataQualityError("fail")
        d = err.to_dict()
        assert "quality_check" not in d
        assert "threshold" not in d
        assert "actual_value" not in d

    def test_hierarchy(self):
        err = DataQualityError("x")
        assert isinstance(err, ValidationError)
        assert isinstance(err, GeoSyncError)

    def test_to_dict_inherits_validation_fields(self):
        err = DataQualityError("fail", field="col", quality_check="qc")
        d = err.to_dict()
        assert d["field"] == "col"
        assert d["quality_check"] == "qc"

    def test_threshold_zero(self):
        err = DataQualityError("fail", threshold=0.0, actual_value=0.0)
        d = err.to_dict()
        assert d["threshold"] == 0.0
        assert d["actual_value"] == 0.0


# ---------------------------------------------------------------------------
# Hierarchy and isinstance checks
# ---------------------------------------------------------------------------


class TestErrorHierarchy:
    @pytest.mark.parametrize(
        "cls",
        [
            ValidationError,
            ConfigError,
            IntegrityError,
            ResourceBudgetError,
            EngineError,
            PipelineError,
            DataQualityError,
        ],
    )
    def test_all_inherit_from_geosync_error(self, cls):
        # Just construct with minimal args
        if cls is DataQualityError:
            err = cls("test")
        else:
            err = cls("test")
        assert isinstance(err, GeoSyncError)
        assert isinstance(err, Exception)

    def test_data_quality_is_validation_error(self):
        err = DataQualityError("x")
        assert isinstance(err, ValidationError)

    def test_custom_error_code_override(self):
        err = ValidationError("x", error_code="CUSTOM")
        assert err.error_code == "CUSTOM"

    def test_context_default_created(self):
        err = GeoSyncError("x")
        assert err.context is not None
        assert isinstance(err.context, ErrorContext)
