# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Typed domain errors for GeoSync core infrastructure.

This module provides a centralized error taxonomy for the core package,
ensuring consistent error handling, fail-fast behavior on invalid inputs,
and auditable error paths with correlation IDs.

Error Hierarchy:
    GeoSyncError (base)
    ├── ValidationError - input/data validation failures
    ├── ConfigError - configuration errors
    ├── IntegrityError - data integrity/security failures
    ├── ResourceBudgetError - resource limit violations
    ├── EngineError - engine execution failures
    └── PipelineError - pipeline/workflow failures
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ErrorContext:
    """Contextual information attached to domain errors for auditability.

    Attributes:
        correlation_id: Optional correlation ID for distributed tracing
        component: Component or module where the error originated
        operation: Operation being performed when error occurred
        timestamp: When the error occurred (UTC)
        details: Additional structured details for debugging
    """

    correlation_id: str | None = None
    component: str | None = None
    operation: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert context to a dictionary for structured logging."""
        result: dict[str, Any] = {"timestamp": self.timestamp.isoformat()}
        if self.correlation_id:
            result["correlation_id"] = self.correlation_id
        if self.component:
            result["component"] = self.component
        if self.operation:
            result["operation"] = self.operation
        if self.details:
            result["details"] = dict(self.details)
        return result


class GeoSyncError(Exception):
    """Base exception for all GeoSync domain errors.

    All domain-specific errors should inherit from this class to ensure
    consistent error handling and auditability across the codebase.

    Attributes:
        message: Human-readable error description
        context: Structured error context for tracing/logging
        error_code: Optional machine-readable error code
    """

    def __init__(
        self,
        message: str,
        *,
        context: ErrorContext | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or ErrorContext()
        self.error_code = error_code

    def __str__(self) -> str:
        parts = [self.message]
        if self.error_code:
            parts.insert(0, f"[{self.error_code}]")
        if self.context.correlation_id:
            parts.append(f"(correlation_id={self.context.correlation_id})")
        return " ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Convert error to a dictionary for structured logging/serialization."""
        return {
            "error_type": type(self).__name__,
            "message": self.message,
            "error_code": self.error_code,
            "context": self.context.to_dict(),
        }


class ValidationError(GeoSyncError):
    """Error raised when input or data validation fails.

    This error indicates that data does not meet expected constraints,
    formats, or business rules. The system should fail-fast when this
    error is raised to prevent invalid data from propagating.

    Example:
        >>> raise ValidationError(
        ...     "Invalid price value",
        ...     field="close_price",
        ...     value=-10.5,
        ...     constraint="must be non-negative",
        ... )
    """

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        value: Any = None,
        constraint: str | None = None,
        context: ErrorContext | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message, context=context, error_code=error_code or "VALIDATION_ERROR")
        self.field = field
        self.value = value
        self.constraint = constraint

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        if self.field:
            result["field"] = self.field
        if self.value is not None:
            result["value"] = repr(self.value)
        if self.constraint:
            result["constraint"] = self.constraint
        return result


class ConfigError(GeoSyncError):
    """Error raised for configuration-related failures.

    This includes invalid configuration values, missing required settings,
    incompatible configuration combinations, and environment variable issues.

    Example:
        >>> raise ConfigError(
        ...     "Invalid database URL",
        ...     config_key="database.url",
        ...     expected_type="valid PostgreSQL URI",
        ... )
    """

    def __init__(
        self,
        message: str,
        *,
        config_key: str | None = None,
        config_value: Any = None,
        expected_type: str | None = None,
        context: ErrorContext | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message, context=context, error_code=error_code or "CONFIG_ERROR")
        self.config_key = config_key
        self.config_value = config_value
        self.expected_type = expected_type

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        if self.config_key:
            result["config_key"] = self.config_key
        if self.expected_type:
            result["expected_type"] = self.expected_type
        # Note: config_value intentionally not serialized to avoid leaking secrets
        return result


class IntegrityError(GeoSyncError):
    """Error raised when data integrity or security checks fail.

    This includes checksum mismatches, tampered artifacts, TLS verification
    failures, and other security-related integrity violations.

    Example:
        >>> raise IntegrityError(
        ...     "Artifact checksum mismatch",
        ...     artifact="model.pt",
        ...     expected_checksum="abc123...",
        ...     actual_checksum="def456...",
        ... )
    """

    def __init__(
        self,
        message: str,
        *,
        artifact: str | None = None,
        expected_checksum: str | None = None,
        actual_checksum: str | None = None,
        security_violation: str | None = None,
        context: ErrorContext | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message, context=context, error_code=error_code or "INTEGRITY_ERROR")
        self.artifact = artifact
        self.expected_checksum = expected_checksum
        self.actual_checksum = actual_checksum
        self.security_violation = security_violation

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        if self.artifact:
            result["artifact"] = self.artifact
        if self.expected_checksum:
            result["expected_checksum"] = self.expected_checksum
        if self.actual_checksum:
            result["actual_checksum"] = self.actual_checksum
        if self.security_violation:
            result["security_violation"] = self.security_violation
        return result


class ResourceBudgetError(GeoSyncError):
    """Error raised when resource budgets are exceeded.

    This includes latency budget violations, memory limits, CPU quotas,
    and other resource governance constraints. When this error is raised,
    the system should trigger fail-safe decision paths.

    Example:
        >>> raise ResourceBudgetError(
        ...     "Latency budget exceeded",
        ...     resource="cpu_time",
        ...     budget_ms=100.0,
        ...     actual_ms=150.0,
        ... )
    """

    def __init__(
        self,
        message: str,
        *,
        resource: str | None = None,
        budget_ms: float | None = None,
        actual_ms: float | None = None,
        budget_bytes: int | None = None,
        actual_bytes: int | None = None,
        context: ErrorContext | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message, context=context, error_code=error_code or "RESOURCE_BUDGET_ERROR")
        self.resource = resource
        self.budget_ms = budget_ms
        self.actual_ms = actual_ms
        self.budget_bytes = budget_bytes
        self.actual_bytes = actual_bytes

    @property
    def overage_percent(self) -> float | None:
        """Calculate the percentage by which the budget was exceeded."""
        if self.budget_ms and self.actual_ms and self.budget_ms > 0:
            return ((self.actual_ms - self.budget_ms) / self.budget_ms) * 100
        if self.budget_bytes and self.actual_bytes and self.budget_bytes > 0:
            return ((self.actual_bytes - self.budget_bytes) / self.budget_bytes) * 100
        return None

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        if self.resource:
            result["resource"] = self.resource
        if self.budget_ms is not None:
            result["budget_ms"] = self.budget_ms
        if self.actual_ms is not None:
            result["actual_ms"] = self.actual_ms
        if self.budget_bytes is not None:
            result["budget_bytes"] = self.budget_bytes
        if self.actual_bytes is not None:
            result["actual_bytes"] = self.actual_bytes
        overage = self.overage_percent
        if overage is not None:
            result["overage_percent"] = overage
        return result


class EngineError(GeoSyncError):
    """Error raised during engine execution failures.

    This includes errors in the core trading engine loop, signal generation
    failures, risk assessment issues, and execution failures.

    Example:
        >>> raise EngineError(
        ...     "Signal generation failed",
        ...     stage="signal",
        ...     run_id="run-123",
        ... )
    """

    def __init__(
        self,
        message: str,
        *,
        stage: str | None = None,
        run_id: str | None = None,
        cycle_number: int | None = None,
        context: ErrorContext | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message, context=context, error_code=error_code or "ENGINE_ERROR")
        self.stage = stage
        self.run_id = run_id
        self.cycle_number = cycle_number

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        if self.stage:
            result["stage"] = self.stage
        if self.run_id:
            result["run_id"] = self.run_id
        if self.cycle_number is not None:
            result["cycle_number"] = self.cycle_number
        return result


class PipelineError(GeoSyncError):
    """Error raised during pipeline or workflow execution failures.

    This includes errors in data pipelines, feature pipelines, and
    orchestration workflows. Supports idempotency tracking for retries.

    Example:
        >>> raise PipelineError(
        ...     "Pipeline stage failed",
        ...     pipeline="feature_engineering",
        ...     stage="normalization",
        ...     idempotency_key="pipe-abc123",
        ... )
    """

    def __init__(
        self,
        message: str,
        *,
        pipeline: str | None = None,
        stage: str | None = None,
        idempotency_key: str | None = None,
        recoverable: bool = True,
        context: ErrorContext | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message, context=context, error_code=error_code or "PIPELINE_ERROR")
        self.pipeline = pipeline
        self.stage = stage
        self.idempotency_key = idempotency_key
        self.recoverable = recoverable

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        if self.pipeline:
            result["pipeline"] = self.pipeline
        if self.stage:
            result["stage"] = self.stage
        if self.idempotency_key:
            result["idempotency_key"] = self.idempotency_key
        result["recoverable"] = self.recoverable
        return result


class DataQualityError(ValidationError):
    """Error raised when data fails quality control checks.

    Specialized validation error for data quality gates including
    missing values, outliers, schema violations, and drift detection.

    Example:
        >>> raise DataQualityError(
        ...     "Data quality check failed",
        ...     quality_check="null_ratio",
        ...     threshold=0.05,
        ...     actual_value=0.15,
        ... )
    """

    def __init__(
        self,
        message: str,
        *,
        quality_check: str | None = None,
        threshold: float | None = None,
        actual_value: float | None = None,
        field: str | None = None,
        context: ErrorContext | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(
            message,
            field=field,
            context=context,
            error_code=error_code or "DATA_QUALITY_ERROR",
        )
        self.quality_check = quality_check
        self.threshold = threshold
        self.actual_value = actual_value

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        if self.quality_check:
            result["quality_check"] = self.quality_check
        if self.threshold is not None:
            result["threshold"] = self.threshold
        if self.actual_value is not None:
            result["actual_value"] = self.actual_value
        return result


__all__ = [
    "ErrorContext",
    "GeoSyncError",
    "ValidationError",
    "ConfigError",
    "IntegrityError",
    "ResourceBudgetError",
    "EngineError",
    "PipelineError",
    "DataQualityError",
]
