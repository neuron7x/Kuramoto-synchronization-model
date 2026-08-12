# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Pydantic schemas for API requests and responses."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .constants import DEFAULT_FEATURE_WEIGHT, MAX_EXPOSURE_LIMIT, MIN_WEIGHT

# Maximum string lengths for security
MAX_STRING_LENGTH = 256
MAX_INSTRUMENT_LENGTH = 64
MAX_PORTFOLIO_ID_LENGTH = 64
MAX_FEATURE_NAME_LENGTH = 64


class FeaturePayload(BaseModel):
    """Feature observation for signal computation."""

    instrument: str = Field(
        ..., max_length=MAX_INSTRUMENT_LENGTH, description="Instrument identifier"
    )
    name: str = Field(..., max_length=MAX_FEATURE_NAME_LENGTH, description="Feature name")
    value: float = Field(..., description="Feature value")
    mean: float | None = Field(default=None, description="Mean for normalization")
    std: float | None = Field(
        default=None, ge=0, description="Standard deviation for normalization"
    )
    weight: float = Field(
        default=DEFAULT_FEATURE_WEIGHT, gt=MIN_WEIGHT, description="Feature weight"
    )


class SignalsRequest(BaseModel):
    """Request payload for signal computation."""

    as_of: datetime = Field(..., description="Timestamp for this signal computation")
    features: list[FeaturePayload] = Field(..., min_length=1, description="Feature observations")


class SignalPayload(BaseModel):
    """Computed signal for an instrument."""

    instrument: str = Field(..., description="Instrument identifier")
    strength: float = Field(..., description="Signal strength")
    contributors: tuple[str, ...] = Field(..., description="Contributing feature names")


class SignalsResponse(BaseModel):
    """Response payload for signal computation."""

    signals: list[SignalPayload] = Field(..., description="Computed signals per instrument")
    ensemble_strength: float = Field(..., description="Aggregate ensemble strength")
    synchrony: float = Field(..., description="Kuramoto order parameter (synchrony)")


class ExposurePayload(BaseModel):
    """Portfolio exposure for a single instrument."""

    portfolio_id: str = Field(
        ..., max_length=MAX_PORTFOLIO_ID_LENGTH, description="Portfolio identifier"
    )
    instrument: str = Field(
        ..., max_length=MAX_INSTRUMENT_LENGTH, description="Instrument identifier"
    )
    exposure: float = Field(..., description="Position exposure")
    leverage: float = Field(..., description="Leverage factor")
    as_of: datetime = Field(..., description="Timestamp for this exposure")
    limit: float = Field(default=1.0, gt=0, le=MAX_EXPOSURE_LIMIT, description="Exposure limit")
    volatility: float = Field(default=0.2, ge=0, description="Expected volatility")


class RiskRequest(BaseModel):
    """Request payload for risk assessment."""

    exposures: list[ExposurePayload] = Field(..., description="Portfolio exposures to assess")


class RiskResponse(BaseModel):
    """Response payload for risk assessment."""

    score: float = Field(..., description="Aggregate risk score")
    value_at_risk: float = Field(..., description="Portfolio Value at Risk")
    stressed_var: tuple[float, ...] = Field(..., description="VaR under stress scenarios")
    breached: tuple[str, ...] = Field(..., description="Instruments that breached limits")


class RegimeRequest(BaseModel):
    """Request payload for regime update."""

    feedback: float = Field(..., description="Feedback signal value")
    volatility: float = Field(..., ge=0, description="Current market volatility")
    as_of: datetime = Field(..., description="Timestamp for this update")


class RegimeResponse(BaseModel):
    """Response payload for regime state."""

    label: str = Field(..., description="Regime classification")
    valence: float = Field(..., description="Valence score")
    confidence: float = Field(..., description="Confidence level")
    as_of: datetime = Field(..., description="Timestamp")


class MemoryRequest(BaseModel):
    """Request payload for persisting exposures."""

    exposures: list[ExposurePayload] = Field(..., min_length=1, description="Exposures to persist")


class MemoryResponse(BaseModel):
    """Response payload for fetched exposures."""

    portfolio_id: str = Field(..., description="Portfolio identifier")
    exposures: list[ExposurePayload] = Field(..., description="Portfolio exposures")


class ErrorDetail(BaseModel):
    """Detail about a specific error."""

    field: str | None = Field(default=None, description="Field that caused the error")
    message: str = Field(..., description="Error description")


class ErrorResponse(BaseModel):
    """Unified error response structure."""

    error: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    request_id: str = Field(..., description="Request ID for tracing")
    details: list[ErrorDetail] | None = Field(default=None, description="Additional error details")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Service health status")


class ReadinessResponse(BaseModel):
    """Readiness check response."""

    ready: bool = Field(..., description="Whether service is ready to accept traffic")
    checks: dict[str, bool] = Field(..., description="Individual readiness checks")


__all__ = [
    "FeaturePayload",
    "SignalsRequest",
    "SignalPayload",
    "SignalsResponse",
    "ExposurePayload",
    "RiskRequest",
    "RiskResponse",
    "RegimeRequest",
    "RegimeResponse",
    "MemoryRequest",
    "MemoryResponse",
    "ErrorDetail",
    "ErrorResponse",
    "HealthResponse",
    "ReadinessResponse",
]
