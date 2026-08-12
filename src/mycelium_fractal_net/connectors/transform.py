# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Transformation pipeline for normalizing raw events to MFN requests.

This module provides the transformation layer that converts RawEvent instances
from external sources into validated NormalizedEvent and MFNRequest objects
suitable for the MFN core engine.

Pipeline:
    RawEvent → NormalizedEvent → MFNRequest

Example:
    >>> transformer = Transformer()
    >>> raw = RawEvent(source="api", timestamp=datetime.now(timezone.utc), payload={"seeds": [1,2,3]})
    >>> normalized = transformer.normalize(raw)
    >>> request = transformer.to_feature_request(normalized)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .base import RawEvent

__all__ = [
    "NormalizedEvent",
    "MFNRequest",
    "Transformer",
    "NormalizationError",
    "MappingError",
]

logger = logging.getLogger(__name__)


def _coerce_timestamp(value: datetime | float | int | str) -> datetime:
    """Convert various timestamp formats to UTC datetime.

    Args:
        value: Timestamp in various formats

    Returns:
        UTC-aware datetime

    Raises:
        TypeError: If value cannot be converted
    """
    if isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
    elif isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
    elif isinstance(value, datetime):
        dt = value
    else:
        raise TypeError(f"Cannot convert {type(value).__name__} to datetime")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


class NormalizationError(Exception):
    """Raised when raw event normalization fails.

    This exception indicates that the input data does not conform to
    expected schema or contains invalid values.

    Attributes:
        source: The source identifier from the failed event
        field: The field that failed validation (if applicable)
        reason: Human-readable description of the failure
    """

    def __init__(
        self,
        reason: str,
        source: str | None = None,
        field: str | None = None,
    ) -> None:
        self.source = source
        self.field = field
        self.reason = reason
        message = "Normalization failed"
        if source:
            message += f" for source '{source}'"
        if field:
            message += f" on field '{field}'"
        message += f": {reason}"
        super().__init__(message)


class MappingError(Exception):
    """Raised when normalized event cannot be mapped to MFN request.

    This exception indicates that while the data is valid, it cannot
    be properly mapped to the target MFN request type.

    Attributes:
        request_type: The target request type (feature, simulation)
        reason: Human-readable description of the failure
    """

    def __init__(
        self,
        reason: str,
        request_type: str | None = None,
    ) -> None:
        self.request_type = request_type
        self.reason = reason
        message = "Mapping failed"
        if request_type:
            message += f" for request type '{request_type}'"
        message += f": {reason}"
        super().__init__(message)


class NormalizedEvent(BaseModel):
    """Validated and normalized event ready for MFN processing.

    NormalizedEvent represents a RawEvent that has been validated,
    coerced to correct types, and prepared for mapping to MFN requests.

    Attributes:
        source: Original data source identifier
        timestamp: Event timestamp (UTC)
        event_type: Classification of the event (data, signal, config)
        seeds: Seed values for fractal operations
        grid_size: Grid dimension for simulation
        params: Additional parameters as key-value pairs
        raw_payload: Original payload for reference
    """

    model_config = ConfigDict(
        frozen=True,
        strict=False,
        str_strip_whitespace=True,
        extra="forbid",
    )

    source: str = Field(..., min_length=1, description="Data source identifier")
    timestamp: datetime = Field(..., description="Event timestamp (UTC)")
    event_type: Literal["data", "signal", "config"] = Field(
        default="data", description="Event classification"
    )
    seeds: list[float] = Field(default_factory=list, description="Seed values")
    grid_size: int = Field(default=64, ge=8, le=1024, description="Grid dimension")
    params: dict[str, Any] = Field(default_factory=dict, description="Additional parameters")
    raw_payload: dict[str, Any] = Field(default_factory=dict, description="Original payload")

    @field_validator("timestamp", mode="before")
    @classmethod
    def _validate_timestamp(cls, value: datetime | float | int | str) -> datetime:
        """Ensure timestamp is UTC-aware."""
        return _coerce_timestamp(value)

    @field_validator("seeds", mode="before")
    @classmethod
    def _coerce_seeds(cls, value: Any) -> list[float]:
        """Coerce seeds to list of floats."""
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            result = []
            for v in value:
                if isinstance(v, (int, float, Decimal)):
                    result.append(float(v))
                elif isinstance(v, str):
                    result.append(float(v))
                else:
                    raise ValueError(f"Invalid seed value: {v}")
            return result
        raise ValueError(f"seeds must be a list, got {type(value).__name__}")


class MFNRequest(BaseModel):
    """Request object for MFN core operations.

    MFNRequest is the final adapter that maps normalized events to
    the structures expected by MFN simulation and feature extraction APIs.

    Attributes:
        request_type: Type of MFN operation (feature, simulation)
        request_id: Unique identifier for tracking
        timestamp: Request creation time (UTC)
        seeds: Seed values for fractal computation
        grid_size: Grid dimension for simulation
        params: Operation-specific parameters
        source_event: Reference to originating normalized event
    """

    model_config = ConfigDict(
        frozen=True,
        strict=False,
        str_strip_whitespace=True,
        extra="forbid",
    )

    request_type: Literal["feature", "simulation"] = Field(..., description="Type of MFN operation")
    request_id: str = Field(..., min_length=1, description="Unique request identifier")
    timestamp: datetime = Field(..., description="Request timestamp (UTC)")
    seeds: list[float] = Field(default_factory=list, description="Seed values")
    grid_size: int = Field(default=64, ge=8, le=1024, description="Grid dimension")
    params: dict[str, Any] = Field(default_factory=dict, description="Operation parameters")
    source_event: NormalizedEvent | None = Field(default=None, description="Originating event")

    @field_validator("timestamp", mode="before")
    @classmethod
    def _validate_timestamp(cls, value: datetime | float | int | str) -> datetime:
        """Ensure timestamp is UTC-aware."""
        return _coerce_timestamp(value)

    @model_validator(mode="after")
    def _validate_seeds_for_type(self) -> "MFNRequest":
        """Validate that feature requests have seeds."""
        if self.request_type == "feature" and not self.seeds:
            # Allow empty seeds for feature extraction - they may use params
            pass
        return self


class Transformer:
    """Transformation pipeline from RawEvent to MFNRequest.

    The Transformer handles the complete normalization and mapping
    pipeline, with configurable field mappings and validation rules.

    Attributes:
        seed_fields: Payload fields to extract seeds from
        grid_field: Payload field for grid_size
        param_fields: Payload fields to include in params

    Example:
        >>> transformer = Transformer(seed_fields=["values", "data"])
        >>> normalized = transformer.normalize(raw_event)
        >>> request = transformer.to_feature_request(normalized, request_id="req-123")
    """

    def __init__(
        self,
        *,
        seed_fields: list[str] | None = None,
        grid_field: str = "grid_size",
        param_fields: list[str] | None = None,
    ) -> None:
        self.seed_fields = seed_fields or ["seeds", "values", "data", "features"]
        self.grid_field = grid_field
        self.param_fields = param_fields or []
        self._request_counter = 0

    def normalize(self, raw: RawEvent) -> NormalizedEvent:
        """Convert RawEvent to NormalizedEvent.

        Args:
            raw: The raw event to normalize

        Returns:
            Validated NormalizedEvent instance

        Raises:
            NormalizationError: If validation fails
        """
        try:
            payload = raw.payload
            seeds: list[float] = []

            # Extract seeds from configured fields
            for field in self.seed_fields:
                if field in payload:
                    value = payload[field]
                    if isinstance(value, (list, tuple)):
                        seeds = [
                            float(v) for v in value if isinstance(v, (int, float, Decimal, str))
                        ]
                        break
                    elif isinstance(value, (int, float, Decimal)):
                        seeds = [float(value)]
                        break

            # Extract grid size
            grid_size = payload.get(self.grid_field, 64)
            if isinstance(grid_size, str):
                grid_size = int(grid_size)
            if not isinstance(grid_size, int):
                grid_size = 64
            grid_size = max(8, min(1024, grid_size))

            # Extract event type
            event_type = payload.get("event_type", "data")
            if event_type not in ("data", "signal", "config"):
                event_type = "data"

            # Extract params
            params = {}
            for field in self.param_fields:
                if field in payload:
                    params[field] = payload[field]

            # Include any extra params from payload
            if "params" in payload and isinstance(payload["params"], dict):
                params.update(payload["params"])

            return NormalizedEvent(
                source=raw.source,
                timestamp=raw.timestamp,
                event_type=event_type,
                seeds=seeds,
                grid_size=grid_size,
                params=params,
                raw_payload=payload,
            )

        except Exception as e:
            logger.warning(f"Normalization failed for source '{raw.source}': {e}")
            raise NormalizationError(
                reason=str(e),
                source=raw.source,
            ) from e

    def to_feature_request(
        self,
        event: NormalizedEvent,
        *,
        request_id: str | None = None,
    ) -> MFNRequest:
        """Map NormalizedEvent to feature extraction request.

        Args:
            event: The normalized event to map
            request_id: Optional request identifier (auto-generated if not provided)

        Returns:
            MFNRequest configured for feature extraction

        Raises:
            MappingError: If mapping fails
        """
        try:
            if request_id is None:
                self._request_counter += 1
                request_id = f"feat-{event.source}-{self._request_counter}"

            return MFNRequest(
                request_type="feature",
                request_id=request_id,
                timestamp=datetime.now(timezone.utc),
                seeds=event.seeds,
                grid_size=event.grid_size,
                params=event.params,
                source_event=event,
            )

        except Exception as e:
            logger.warning(f"Feature request mapping failed: {e}")
            raise MappingError(
                reason=str(e),
                request_type="feature",
            ) from e

    def to_simulation_request(
        self,
        event: NormalizedEvent,
        *,
        request_id: str | None = None,
    ) -> MFNRequest:
        """Map NormalizedEvent to simulation request.

        Args:
            event: The normalized event to map
            request_id: Optional request identifier (auto-generated if not provided)

        Returns:
            MFNRequest configured for simulation

        Raises:
            MappingError: If mapping fails
        """
        try:
            if request_id is None:
                self._request_counter += 1
                request_id = f"sim-{event.source}-{self._request_counter}"

            return MFNRequest(
                request_type="simulation",
                request_id=request_id,
                timestamp=datetime.now(timezone.utc),
                seeds=event.seeds,
                grid_size=event.grid_size,
                params=event.params,
                source_event=event,
            )

        except Exception as e:
            logger.warning(f"Simulation request mapping failed: {e}")
            raise MappingError(
                reason=str(e),
                request_type="simulation",
            ) from e
