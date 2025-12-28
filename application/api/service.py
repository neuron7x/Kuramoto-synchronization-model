"""FastAPI application exposing online feature computation and forecasting."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from json import JSONDecodeError
from time import perf_counter
from typing import Any, Awaitable, Callable, Literal, Mapping, TypeVar

import numpy as np
import pandas as pd
from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from analytics.signals.pipeline import FeaturePipelineConfig, SignalFeaturePipeline
from application.api.authorization import require_permission
from application.api.debug import install_debug_routes
from application.api.errors import (
    COMMON_ERROR_RESPONSES,
    ApiErrorCode,
    register_exception_handlers,
)
from application.api.graphql_api import create_graphql_router
from application.api.idempotency import (
    IdempotencyCache,
    IdempotencyConflictError,
    IdempotencySnapshot,
)
from application.api.metrics import MetricsSampler
from application.api.middleware import (
    AccessLogMiddleware,
    PrometheusMetricsMiddleware,
)
from application.api.rate_limit import (
    RateLimiterSnapshot,
    SlidingWindowRateLimiter,
    build_rate_limiter,
)
from application.api.realtime import AnalyticsStore, RealTimeStreamManager
from application.api.security import (
    get_api_security_settings,
    require_two_factor,
    verify_optional_request_identity,
    verify_request_identity,
)
from application.settings import (
    AdminApiSettings,
    ApiRateLimitSettings,
    ApiSecuritySettings,
    BackendRuntimeSettings,
)
from application.trading import signal_to_dto
from core.utils.debug import VariableInspector
from core.utils.metrics import MetricsCollector, get_metrics_collector
from domain import Signal, SignalAction
from execution.risk import (
    PostgresKillSwitchStateStore,
    RiskLimits,
    RiskManager,
    SQLiteKillSwitchStateStore,
)
from observability.audit.trail import get_access_audit_trail
from observability.health import HealthServer
from observability.logging import configure_logging
from src.admin.remote_control import (
    AdminIdentity,
    AdminRateLimiter,
    AdminRateLimiterSnapshot,
    create_remote_control_router,
)
from src.audit.audit_logger import AuditLogger, HttpAuditSink
from src.risk.risk_manager import RiskManagerFacade

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)


@dataclass(slots=True)
class _CacheEntry:
    """In-memory TTL cache entry."""

    payload: BaseModel
    expires_at: datetime
    etag: str


@dataclass(slots=True)
class CacheSnapshot:
    """Observability snapshot of :class:`TTLCache` occupancy."""

    entries: int
    max_entries: int
    ttl_seconds: int


class TTLCache:
    """A tiny in-memory cache with TTL semantics for small payloads."""

    def __init__(self, ttl_seconds: int = 30, max_entries: int = 256) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._entries: dict[str, _CacheEntry] = {}
        self._lock = asyncio.Lock()

    @property
    def ttl_seconds(self) -> int:
        return self._ttl

    async def get(self, key: str) -> _CacheEntry | None:
        async with self._lock:
            entry = self._entries.get(key)
            now = datetime.now(timezone.utc)
            if entry is None:
                return None
            if entry.expires_at <= now:
                del self._entries[key]
                return None
            return entry

    async def set(self, key: str, payload: BaseModel, etag: str) -> None:
        async with self._lock:
            if len(self._entries) >= self._max_entries:
                # Drop the stalest entry deterministically (smallest expiry).
                oldest_key = min(
                    self._entries, key=lambda item: self._entries[item].expires_at
                )
                self._entries.pop(oldest_key, None)
            expires = datetime.now(timezone.utc) + timedelta(seconds=self._ttl)
            self._entries[key] = _CacheEntry(
                payload=payload, expires_at=expires, etag=etag
            )

    async def snapshot(self) -> CacheSnapshot:
        """Return cache occupancy metrics for readiness probes."""

        async with self._lock:
            now = datetime.now(timezone.utc)
            expired = [
                key for key, entry in self._entries.items() if entry.expires_at <= now
            ]
            for key in expired:
                self._entries.pop(key, None)
            return CacheSnapshot(
                entries=len(self._entries),
                max_entries=self._max_entries,
                ttl_seconds=self._ttl,
            )


@dataclass(slots=True)
class DependencyProbeResult:
    """Normalised representation of dependency readiness."""

    healthy: bool
    detail: str | None = None
    data: dict[str, Any] | None = None


class ComponentHealth(BaseModel):
    """Health status for an individual subsystem."""

    healthy: bool
    status: Literal["operational", "degraded", "failed"]
    detail: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """Structured response for the readiness probe."""

    status: Literal["ready", "degraded", "failed"]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    components: dict[str, ComponentHealth]


DependencyProbe = Callable[
    [],
    Awaitable[DependencyProbeResult | bool | dict[str, Any]]
    | DependencyProbeResult
    | bool
    | dict[str, Any],
]


def _coerce_dependency_result(
    value: DependencyProbeResult | bool | dict[str, Any],
) -> DependencyProbeResult:
    """Normalise supported dependency probe return values."""

    if isinstance(value, DependencyProbeResult):
        return value
    if isinstance(value, dict):
        healthy = bool(value.get("healthy", False))
        detail = value.get("detail") or value.get("message")
        data = {
            key: payload
            for key, payload in value.items()
            if key not in {"healthy", "detail", "message"}
        }
        return DependencyProbeResult(healthy=healthy, detail=detail, data=data or None)
    return DependencyProbeResult(healthy=bool(value))


FEATURE_ERROR_RESPONSES: dict[int, dict[str, Any]] = {
    **COMMON_ERROR_RESPONSES,
    status.HTTP_404_NOT_FOUND: {
        **COMMON_ERROR_RESPONSES[status.HTTP_404_NOT_FOUND],
        "description": "No feature snapshots matched the requested filters.",
    },
}


PREDICTION_ERROR_RESPONSES: dict[int, dict[str, Any]] = {
    **COMMON_ERROR_RESPONSES,
    status.HTTP_404_NOT_FOUND: {
        **COMMON_ERROR_RESPONSES[status.HTTP_404_NOT_FOUND],
        "description": "No predictions matched the requested filters.",
    },
}


SUCCESS_HEADERS: dict[str, dict[str, Any]] = {
    "Idempotency-Key": {
        "description": "Echoes the idempotency key associated with the response.",
        "schema": {"type": "string", "maxLength": 128},
    },
    "X-Cache-Status": {
        "description": "Indicates whether the response was served from cache.",
        "schema": {"type": "string", "enum": ["hit", "miss"]},
    },
    "ETag": {
        "description": "Entity tag representing the hash of the response body.",
        "schema": {"type": "string"},
    },
    "X-Idempotent-Replay": {
        "description": (
            "Present with value 'true' when the response is replayed from the "
            "idempotency ledger."
        ),
        "schema": {"type": "string", "enum": ["true"]},
    },
}


@dataclass(slots=True, frozen=True)
class FeatureQueryParams:
    """Query parameters driving feature pagination and filtering."""

    limit: int
    cursor: datetime | None
    start_at: datetime | None
    end_at: datetime | None
    feature_prefix: str | None
    feature_keys: tuple[str, ...]

    def cache_fragment(self) -> dict[str, Any]:
        return {
            "limit": self.limit,
            "cursor": self.cursor.isoformat() if self.cursor else None,
            "start_at": self.start_at.isoformat() if self.start_at else None,
            "end_at": self.end_at.isoformat() if self.end_at else None,
            "feature_prefix": self.feature_prefix,
            "feature_keys": list(self.feature_keys),
        }


@dataclass(slots=True, frozen=True)
class PredictionQueryParams:
    """Query parameters for prediction pagination and filtering."""

    limit: int
    cursor: datetime | None
    start_at: datetime | None
    end_at: datetime | None
    actions: tuple[SignalAction, ...]
    min_confidence: float | None

    def cache_fragment(self) -> dict[str, Any]:
        return {
            "limit": self.limit,
            "cursor": self.cursor.isoformat() if self.cursor else None,
            "start_at": self.start_at.isoformat() if self.start_at else None,
            "end_at": self.end_at.isoformat() if self.end_at else None,
            "actions": [action.value for action in self.actions],
            "min_confidence": self.min_confidence,
        }


def _parse_datetime_param(name: str, raw: str | None) -> datetime | None:
    if raw is None:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": ApiErrorCode.INVALID_CURSOR.value,
                "message": f"Invalid {name} value; expected ISO 8601 format.",
                "meta": {"parameter": name, "value": raw},
            },
        ) from exc
    return _ensure_timezone(parsed)


def _parse_confidence_param(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": ApiErrorCode.INVALID_CONFIDENCE.value,
                "message": "min_confidence must be a floating point number between 0 and 1.",
                "meta": {"parameter": "min_confidence", "value": raw},
            },
        ) from exc
    if not 0.0 <= value <= 1.0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": ApiErrorCode.INVALID_CONFIDENCE.value,
                "message": "min_confidence must be within [0.0, 1.0].",
                "meta": {"parameter": "min_confidence", "value": raw},
            },
        )
    return value


def get_feature_query_params(
    limit: int = Query(
        1, ge=1, le=500, description="Number of feature snapshots to return."
    ),
    cursor: str | None = Query(
        None, description="Pagination cursor (exclusive) encoded as ISO 8601 timestamp."
    ),
    start_at: str | None = Query(
        None,
        alias="startAt",
        description="Filter snapshots on or after this timestamp.",
    ),
    end_at: str | None = Query(
        None, alias="endAt", description="Filter snapshots on or before this timestamp."
    ),
    feature_prefix: str | None = Query(
        None,
        alias="featurePrefix",
        description="Return only feature keys with the provided prefix.",
    ),
    feature: list[str] | None = Query(
        None, alias="feature", description="Specific feature keys to include."
    ),
) -> FeatureQueryParams:
    feature_keys: tuple[str, ...] = tuple(dict.fromkeys(feature or []))
    return FeatureQueryParams(
        limit=limit,
        cursor=_parse_datetime_param("cursor", cursor),
        start_at=_parse_datetime_param("start_at", start_at),
        end_at=_parse_datetime_param("end_at", end_at),
        feature_prefix=feature_prefix,
        feature_keys=feature_keys,
    )


def get_prediction_query_params(
    limit: int = Query(1, ge=1, le=500, description="Number of predictions to return."),
    cursor: str | None = Query(
        None, description="Pagination cursor (exclusive) encoded as ISO 8601 timestamp."
    ),
    start_at: str | None = Query(
        None,
        alias="startAt",
        description="Return predictions generated at or after this time.",
    ),
    end_at: str | None = Query(
        None,
        alias="endAt",
        description="Return predictions generated at or before this time.",
    ),
    action: list[str] | None = Query(
        None, alias="action", description="Filter predictions by signal action."
    ),
    min_confidence: str | None = Query(
        None, alias="minConfidence", description="Minimum signal confidence to include."
    ),
) -> PredictionQueryParams:
    actions: list[SignalAction] = []
    for value in action or []:
        try:
            actions.append(SignalAction(value))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": ApiErrorCode.UNPROCESSABLE.value,
                    "message": f"Unsupported action filter '{value}'.",
                    "meta": {"parameter": "action", "value": value},
                },
            ) from exc
    return PredictionQueryParams(
        limit=limit,
        cursor=_parse_datetime_param("cursor", cursor),
        start_at=_parse_datetime_param("start_at", start_at),
        end_at=_parse_datetime_param("end_at", end_at),
        actions=tuple(actions),
        min_confidence=_parse_confidence_param(min_confidence),
    )


def _ensure_timezone(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


class MarketBar(BaseModel):
    """Representation of a single OHLCV bar for online inference."""

    timestamp: datetime = Field(
        ..., description="Timestamp of the bar in ISO 8601 format."
    )
    open: float | None = Field(None, description="Opening price for the interval.")
    high: float = Field(..., description="High price for the interval.")
    low: float = Field(..., description="Low price for the interval.")
    close: float = Field(..., description="Close price for the interval.")
    volume: float | None = Field(
        None, description="Traded volume for the bar. Optional for illiquid venues."
    )
    bid_volume: float | None = Field(
        default=None,
        alias="bidVolume",
        description="Bid-side queue volume for microstructure features.",
    )
    ask_volume: float | None = Field(
        default=None,
        alias="askVolume",
        description="Ask-side queue volume for microstructure features.",
    )
    signed_volume: float | None = Field(
        default=None,
        alias="signedVolume",
        description="Signed volume (buy-sell imbalance).",
    )

    model_config = ConfigDict(populate_by_name=True, frozen=True)

    @model_validator(mode="after")
    def _normalise_timezone(self) -> "MarketBar":
        object.__setattr__(self, "timestamp", _ensure_timezone(self.timestamp))
        return self

    def as_record(self) -> dict[str, Any]:
        record = self.model_dump(by_alias=False, exclude_none=True)
        record["timestamp"] = self.timestamp
        return record


class FeatureRequest(BaseModel):
    """Payload describing the series to transform into features."""

    symbol: str = Field(..., min_length=1, description="Instrument identifier.")
    bars: list[MarketBar] = Field(..., min_length=1, description="Ordered price bars.")

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "symbol": "BTC-USD",
                    "bars": [
                        {
                            "timestamp": "2025-01-01T00:00:00Z",
                            "open": 42000.1,
                            "high": 42010.5,
                            "low": 41980.0,
                            "close": 42005.2,
                            "volume": 18.2,
                            "bidVolume": 9.1,
                            "askVolume": 9.0,
                            "signedVolume": 0.25,
                        }
                    ],
                }
            ]
        },
    )

    def to_frame(self) -> pd.DataFrame:
        records = [bar.as_record() for bar in self.bars]
        frame = pd.DataFrame.from_records(records)
        frame.sort_values("timestamp", inplace=True)
        frame.set_index("timestamp", inplace=True)
        frame.index = pd.to_datetime(frame.index, utc=True)
        return frame


class PaginationMeta(BaseModel):
    """Pagination envelope used by collection responses."""

    cursor: datetime | None = None
    next_cursor: datetime | None = None
    limit: int = 0
    returned: int = 0

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "cursor": None,
                "next_cursor": "2025-01-01T00:00:00Z",
                "limit": 50,
                "returned": 50,
            }
        },
    )


class FeatureFilters(BaseModel):
    """Echoed filter parameters for feature responses."""

    start_at: datetime | None = None
    end_at: datetime | None = None
    feature_prefix: str | None = None
    feature_keys: tuple[str, ...] = Field(default_factory=tuple)

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "start_at": "2025-01-01T00:00:00Z",
                "end_at": None,
                "feature_prefix": "macd",
                "feature_keys": ["macd", "macd_signal"],
            }
        },
    )


class FeatureSnapshot(BaseModel):
    """Single feature vector at a specific timestamp."""

    timestamp: datetime
    features: dict[str, float]

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "timestamp": "2025-01-01T00:00:30Z",
                "features": {
                    "macd": 0.42,
                    "macd_signal": 0.37,
                    "macd_histogram": 0.05,
                },
            }
        },
    )


class FeatureResponse(BaseModel):
    """Response containing the most recent feature snapshot."""

    symbol: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    features: dict[str, float] = Field(default_factory=dict)
    items: list[FeatureSnapshot] = Field(default_factory=list)
    pagination: PaginationMeta = Field(default_factory=PaginationMeta)
    filters: FeatureFilters = Field(default_factory=FeatureFilters)

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "symbol": "BTC-USD",
                    "generated_at": "2025-01-01T00:00:30Z",
                    "features": {
                        "macd": 0.42,
                        "macd_signal": 0.37,
                        "macd_histogram": 0.05,
                        "rsi": 61.2,
                    },
                    "items": [
                        {
                            "timestamp": "2025-01-01T00:00:30Z",
                            "features": {
                                "macd": 0.42,
                                "macd_signal": 0.37,
                                "macd_histogram": 0.05,
                                "rsi": 61.2,
                            },
                        }
                    ],
                    "pagination": {
                        "cursor": None,
                        "next_cursor": "2025-01-01T00:00:00Z",
                        "limit": 1,
                        "returned": 1,
                    },
                    "filters": {
                        "start_at": None,
                        "end_at": None,
                        "feature_prefix": "macd",
                        "feature_keys": ["macd", "macd_signal"],
                    },
                }
            ]
        },
    )


class PredictionRequest(FeatureRequest):
    """Prediction request payload, optionally specifying a forecast horizon."""

    horizon_seconds: int = Field(
        300,
        ge=60,
        le=3600,
        description="Prediction horizon in seconds for contextual metadata.",
    )

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "symbol": "BTC-USD",
                    "horizon_seconds": 900,
                    "bars": [
                        {
                            "timestamp": "2025-01-01T00:00:00Z",
                            "open": 42000.1,
                            "high": 42010.5,
                            "low": 41980.0,
                            "close": 42005.2,
                            "volume": 18.2,
                            "bidVolume": 9.1,
                            "askVolume": 9.0,
                            "signedVolume": 0.25,
                        }
                    ],
                }
            ]
        },
    )


class PredictionFilters(BaseModel):
    """Echoed filter parameters for prediction responses."""

    start_at: datetime | None = None
    end_at: datetime | None = None
    actions: tuple[SignalAction, ...] = Field(default_factory=tuple)
    min_confidence: float | None = None

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "start_at": "2025-01-01T00:00:00Z",
                "end_at": None,
                "actions": [SignalAction.BUY.value],
                "min_confidence": 0.6,
            }
        },
    )


class PredictionSnapshot(BaseModel):
    """Snapshot of a derived signal at a point in time."""

    timestamp: datetime
    score: float
    signal: dict[str, Any]

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "timestamp": "2025-01-01T00:00:30Z",
                "score": 0.42,
                "signal": {
                    "action": "buy",
                    "confidence": 0.78,
                },
            }
        },
    )


class PredictionResponse(BaseModel):
    """Response representing the generated trading signal."""

    symbol: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    horizon_seconds: int
    score: float | None = Field(
        default=None,
        description="Composite alpha score driving the primary action.",
    )
    signal: dict[str, Any] | None = Field(
        default=None, description="Primary trading signal at the head of the page."
    )
    items: list[PredictionSnapshot] = Field(default_factory=list)
    pagination: PaginationMeta = Field(default_factory=PaginationMeta)
    filters: PredictionFilters = Field(default_factory=PredictionFilters)

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "symbol": "BTC-USD",
                    "generated_at": "2025-01-01T00:00:30Z",
                    "horizon_seconds": 900,
                    "score": 0.42,
                    "signal": {
                        "action": "buy",
                        "confidence": 0.78,
                        "rationale": "Composite heuristic weighting MACD trend...",
                    },
                    "items": [
                        {
                            "timestamp": "2025-01-01T00:00:30Z",
                            "score": 0.42,
                            "signal": {
                                "action": "buy",
                                "confidence": 0.78,
                            },
                        }
                    ],
                    "pagination": {
                        "cursor": None,
                        "next_cursor": "2025-01-01T00:00:00Z",
                        "limit": 1,
                        "returned": 1,
                    },
                    "filters": {
                        "start_at": None,
                        "end_at": None,
                        "actions": ["buy"],
                        "min_confidence": 0.6,
                    },
                }
            ]
        },
    )


FEATURE_SUCCESS_RESPONSE: dict[int, dict[str, Any]] = {
    status.HTTP_200_OK: {
        "model": FeatureResponse,
        "description": "Latest feature vector computed from the submitted bar window.",
        "headers": SUCCESS_HEADERS,
    }
}


PREDICTION_SUCCESS_RESPONSE: dict[int, dict[str, Any]] = {
    status.HTTP_200_OK: {
        "model": PredictionResponse,
        "description": "Latest prediction derived from engineered features.",
        "headers": SUCCESS_HEADERS,
    }
}


class OnlineSignalForecaster:
    """Wraps the feature pipeline and lightweight heuristics for live inference."""

    def __init__(self, pipeline: SignalFeaturePipeline | None = None) -> None:
        self._pipeline = pipeline or SignalFeaturePipeline(FeaturePipelineConfig())

    def compute_features(self, payload: FeatureRequest) -> pd.DataFrame:
        frame = payload.to_frame()
        features = self._pipeline.transform(frame)
        return features

    def _normalise_feature_row(
        self, row: pd.Series, *, strict: bool
    ) -> pd.Series | None:
        required_macd_columns = ("macd", "macd_signal", "macd_histogram")
        missing_columns = [col for col in required_macd_columns if col not in row.index]
        if missing_columns:
            if strict:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "code": ApiErrorCode.FEATURES_MISSING.value,
                        "message": f"Missing MACD features: {', '.join(sorted(missing_columns))}",
                    },
                )
            return None

        invalid_columns = [
            col
            for col in required_macd_columns
            if pd.isna(row[col]) or not np.isfinite(float(row[col]))
        ]
        if invalid_columns:
            if strict:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "code": ApiErrorCode.FEATURES_INVALID.value,
                        "message": (
                            "Unavailable MACD features: "
                            f"{', '.join(sorted(invalid_columns))}"
                        ),
                    },
                )
            return None

        cleaned = row.dropna()
        if cleaned.empty:
            if strict:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "code": ApiErrorCode.FEATURES_INVALID.value,
                        "message": "Insufficient data to derive features",
                    },
                )
            return None
        return cleaned

    def normalised_feature_rows(
        self, features: pd.DataFrame, *, strict: bool = False
    ) -> list[tuple[datetime, pd.Series]]:
        rows: list[tuple[datetime, pd.Series]] = []
        for timestamp, raw in features.iterrows():
            normalised = self._normalise_feature_row(raw, strict=strict)
            if normalised is None:
                continue
            python_ts = (
                timestamp.to_pydatetime()
                if hasattr(timestamp, "to_pydatetime")
                else timestamp
            )
            rows.append((_ensure_timezone(python_ts), normalised))
        return rows

    def latest_feature_vector(self, features: pd.DataFrame) -> pd.Series:
        if features.empty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": ApiErrorCode.FEATURES_EMPTY.value,
                    "message": "No features computed",
                },
            )

        latest_row = features.iloc[-1]
        normalised = self._normalise_feature_row(latest_row, strict=True)
        if normalised is None:  # pragma: no cover - strict=True ensures non-None
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": ApiErrorCode.FEATURES_INVALID.value,
                    "message": "Insufficient data to derive features",
                },
            )
        return normalised

    def derive_signal(
        self, symbol: str, latest: pd.Series, horizon_seconds: int
    ) -> tuple[Signal, float]:
        # Compute a simple composite alpha score using a handful of stable metrics.
        macd = float(latest["macd"])
        macd_signal_line = float(latest["macd_signal"])
        macd_histogram = float(latest["macd_histogram"])
        rsi = float(latest.get("rsi", 50.0))
        ret_1 = float(latest.get("return_1", 0.0))
        volatility_20 = float(latest.get("volatility_20", 0.0))
        queue_imbalance = float(latest.get("queue_imbalance", 0.0))

        # The heuristic emphasises MACD structure: the raw MACD trend captures the
        # dominant fast/slow EMA divergence, the crossover term highlights whether
        # MACD is leading or lagging the signal line, and the histogram term scales
        # the magnitude of the divergence to reward strong momentum while
        # suppressing noise. The balance term gently penalises scenarios where
        # divergence momentum and convergence cadence disagree, preventing the
        # composite score from running too hot on one side of the MACD structure.
        # RSI, short-term returns, and order-book imbalance are complementary
        # momentum and flow signals, while realised volatility acts as a risk
        # haircut.
        macd_components = self._compute_macd_components(
            macd=macd,
            macd_signal_line=macd_signal_line,
            macd_histogram=macd_histogram,
        )

        contributions: dict[str, float] = {
            **macd_components,
            "rsi_bias": ((rsi - 50.0) / 50.0) * 0.12,
            "return_momentum": np.tanh(ret_1 * 120.0) * 0.1,
            "order_flow": np.tanh(queue_imbalance) * 0.06,
            "volatility_risk": -abs(volatility_20) * 0.04,
        }

        score = sum(contributions.values())

        threshold = 0.12
        if score > threshold:
            action = SignalAction.BUY
        elif score < -threshold:
            action = SignalAction.SELL
        else:
            action = SignalAction.HOLD

        confidence = float(min(1.0, max(0.0, abs(score) / 0.85)))
        signal = Signal(
            symbol=symbol,
            action=action,
            confidence=confidence,
            rationale=(
                "Composite heuristic weighting MACD trend, crossover momentum, "
                "histogram strength, RSI, returns, and book imbalance"
            ),
            metadata={
                "score": score,
                "horizon_seconds": horizon_seconds,
                "component_contributions": contributions,
                "macd_component_explanations": {
                    "macd_trend": (
                        "Measures overall EMA divergence; positive values indicate "
                        "bullish acceleration."
                    ),
                    "macd_crossover": (
                        "Rewards MACD leading the signal line; negative values "
                        "highlight bearish crossovers."
                    ),
                    "macd_histogram": (
                        "Scales the magnitude of MACD vs signal separation to favour "
                        "decisive momentum."
                    ),
                    "macd_balance": (
                        "Penalises divergence and convergence disagreement so MACD "
                        "structure remains balanced."
                    ),
                },
            },
        )
        return signal, score

    def _compute_macd_components(
        self,
        *,
        macd: float,
        macd_signal_line: float,
        macd_histogram: float,
    ) -> dict[str, float]:
        """Return the MACD contribution breakdown with a balance correction.

        The balance term discourages the composite signal from overweighting
        either the divergence (trend + histogram) or convergence (crossover)
        components when they materially disagree.
        """

        macd_trend_component = np.tanh(macd)
        macd_crossover_component = np.tanh(macd - macd_signal_line)
        macd_histogram_component = np.tanh(macd_histogram * 2.0)

        # Capture divergence dynamics via both direction (signed strength) and
        # energy (magnitude), mirroring how discretionary traders reason about
        # MACD legs fanning out. Using a compact vector representation keeps the
        # transformations easy to audit while letting us express richer
        # interactions than a single scalar average.
        divergence_vector = np.array(
            [macd_trend_component, macd_histogram_component], dtype=float
        )
        divergence_strength = float(np.mean(divergence_vector))
        divergence_energy = float(
            np.linalg.norm(divergence_vector) / np.sqrt(divergence_vector.size)
        )

        convergence_strength = macd_crossover_component
        convergence_energy = abs(convergence_strength)

        # Alignment measures whether convergence is confirming divergence. Using
        # a smooth activation instead of hard signs avoids choppy behaviour
        # around zero-crossings and mirrors how operators phase-align oscillators
        # in signal processing.
        alignment = np.tanh(divergence_strength * convergence_strength * 2.5)

        # Track how forcefully divergence outpaces convergence. The tanh keeps
        # the ratio bounded while still emphasising large spreads.
        magnitude_gap = divergence_energy - convergence_energy
        magnitude_pressure = np.tanh((magnitude_gap - 0.05) * 1.8)

        # Preserve directionality: when divergence and convergence point in the
        # same direction but at different speeds we want only a gentle nudge,
        # whereas opposing directions should trigger a sharper correction.
        directional_tension = np.tanh(
            (divergence_strength - convergence_strength) * 1.1
        )

        # Blend the above ingredients into a single correction term. Positive
        # raw values imply divergence dominance and yield a negative correction;
        # negative values indicate healthy agreement and therefore earn a
        # positive contribution.
        raw_balance = magnitude_pressure + 0.75 * directional_tension - 1.0 * alignment

        # When both legs are quiet we do not want the balance leg to oscillate
        # unnecessarily, hence the neutraliser softly damps the correction.
        neutraliser = 1.0 - np.exp(-((divergence_energy + convergence_energy) ** 2))
        balance_drive = -np.tanh(raw_balance * 1.6)
        alignment_bonus = float(np.clip(alignment, 0.0, 1.0))
        magnitude_relief = float(np.clip(0.2 - magnitude_gap, 0.0, 0.2) / 0.2)
        supportive_bonus = alignment_bonus * magnitude_relief * 0.25
        balance_correction = (balance_drive + supportive_bonus) * neutraliser

        return {
            "macd_trend": macd_trend_component * 0.26,
            "macd_crossover": macd_crossover_component * 0.22,
            "macd_histogram": macd_histogram_component * 0.18,
            "macd_balance": balance_correction * 0.14,
        }


def _filter_feature_frame(
    features: pd.DataFrame,
    *,
    start_at: datetime | None,
    end_at: datetime | None,
) -> pd.DataFrame:
    frame = features
    if start_at is not None:
        frame = frame[frame.index >= start_at]
    if end_at is not None:
        frame = frame[frame.index <= end_at]
    return frame


def _paginate_frame(
    frame: pd.DataFrame, *, limit: int, cursor: datetime | None
) -> tuple[pd.DataFrame, datetime | None]:
    ordered = frame.sort_index(ascending=False)
    if cursor is not None:
        ordered = ordered[ordered.index < cursor]
    page = ordered.iloc[:limit]
    if page.empty:
        return page, None
    next_cursor_ts = page.index[-1]
    if hasattr(next_cursor_ts, "to_pydatetime"):
        next_cursor = _ensure_timezone(next_cursor_ts.to_pydatetime())
    else:
        next_cursor = _ensure_timezone(next_cursor_ts)
    return page, next_cursor


def _filter_feature_values(
    feature_vector: pd.Series,
    *,
    feature_prefix: str | None,
    feature_keys: tuple[str, ...],
) -> dict[str, float]:
    values: dict[str, float] = {}
    for key in sorted(feature_vector.index):
        if feature_prefix is not None and not key.startswith(feature_prefix):
            continue
        if feature_keys and key not in feature_keys:
            continue
        values[key] = float(feature_vector[key])
    return values


def _hash_payload(
    prefix: str, payload: BaseModel, extra: Mapping[str, Any] | None = None
) -> str:
    body = payload.model_dump(mode="json")
    if extra:
        body["__query__"] = extra
    data = json.dumps(body, sort_keys=True, default=str)
    digest = hashlib.sha256(data.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


_IDEMPOTENCY_ALLOWED_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:"
)


def _validate_idempotency_key(raw: str) -> str:
    key = raw.strip()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": ApiErrorCode.IDEMPOTENCY_INVALID.value,
                "message": "Idempotency-Key header must not be empty.",
            },
        )
    if len(key) > 128:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": ApiErrorCode.IDEMPOTENCY_INVALID.value,
                "message": "Idempotency-Key header exceeds 128 characters.",
            },
        )
    if any(character not in _IDEMPOTENCY_ALLOWED_CHARS for character in key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": ApiErrorCode.IDEMPOTENCY_INVALID.value,
                "message": "Idempotency-Key contains unsupported characters.",
            },
        )
    return key


class PayloadGuardMiddleware(BaseHTTPMiddleware):
    """Inspect incoming JSON payloads for size and suspicious content."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_body_bytes: int,
        suspicious_keys: set[str],
        suspicious_substrings: tuple[str, ...],
    ) -> None:
        super().__init__(app)
        self._max_body_bytes = max_body_bytes
        self._suspicious_keys = {key.lower() for key in suspicious_keys}
        self._suspicious_substrings = tuple(
            sub.lower() for sub in suspicious_substrings
        )

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method in {"POST", "PUT", "PATCH"}:
            content_length = request.headers.get("content-length")
            if content_length is not None:
                try:
                    length_value = int(content_length)
                except ValueError:
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content={"detail": "Invalid Content-Length header."},
                    )
                if length_value > self._max_body_bytes:
                    return JSONResponse(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        content={"detail": "Request body exceeds configured limit."},
                    )

            body = await request.body()
            if len(body) > self._max_body_bytes:
                return JSONResponse(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    content={"detail": "Request body exceeds configured limit."},
                )

            content_type = (
                request.headers.get("content-type", "").split(";")[0].strip().lower()
            )
            if content_type in {"application/json", "application/problem+json", ""}:
                if body:
                    try:
                        parsed = json.loads(body)
                    except JSONDecodeError:
                        return JSONResponse(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            content={"detail": "Malformed JSON payload."},
                        )
                    if not isinstance(parsed, (dict, list)):
                        return JSONResponse(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            content={"detail": "Unsupported JSON payload structure."},
                        )
                    if self._is_suspicious(parsed):
                        return JSONResponse(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            content={"detail": "Suspicious payload rejected."},
                        )
                request._body = body

        return await call_next(request)

    def _is_suspicious(self, payload: object) -> bool:
        if isinstance(payload, dict):
            for key, value in payload.items():
                if isinstance(key, str) and key.lower() in self._suspicious_keys:
                    return True
                if self._is_suspicious(value):
                    return True
            return False
        if isinstance(payload, list):
            return any(self._is_suspicious(item) for item in payload)
        if isinstance(payload, str):
            lowered = payload.lower()
            return any(token in lowered for token in self._suspicious_substrings)
        return False


def _resolve_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        for part in forwarded_for.split(","):
            candidate = part.strip().split()[0]
            if candidate:
                return candidate

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def configure_openapi(app: FastAPI) -> None:
    """Install a deterministic OpenAPI generator with TradePulse extensions."""

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )

        schema["servers"] = [
            {
                "url": "https://api.tradepulse.example.com",
                "description": "Production",
            },
            {
                "url": "https://staging-api.tradepulse.example.com",
                "description": "Staging",
            },
        ]

        info = schema.setdefault("info", {})
        info.setdefault(
            "x-api-lifecycle",
            {
                "current": "v1",
                "deprecated": ["v0"],
                "retirement": "v0 endpoints are removed 90 days after deprecation notice.",
            },
        )
        info.setdefault(
            "x-deprecation-policy",
            {
                "policy": "Breaking changes require a new major version with 90-day overlap.",
                "notificationChannels": ["release-notes", "status-page"],
            },
        )
        info.setdefault(
            "x-backwards-compatibility",
            {
                "guarantees": [
                    (
                        "Schemas for existing response fields remain backward "
                        "compatible within a major version."
                    ),
                    "Deprecated fields retain original semantics until removal.",
                ]
            },
        )

        components = schema.setdefault("components", {})
        headers = components.setdefault("headers", {})
        headers.setdefault(
            "Idempotency-Key",
            {
                "description": (
                    "Idempotency key echoed on responses. Keys are valid for 15 "
                    "minutes."
                ),
                "schema": {"type": "string", "maxLength": 128},
            },
        )

        headers.setdefault(
            "X-Idempotent-Replay",
            {
                "description": (
                    "Sent with value 'true' when a response is replayed from the "
                    "idempotency ledger."
                ),
                "schema": {"type": "string", "enum": ["true"]},
            },
        )

        security_schemes = components.setdefault("securitySchemes", {})
        security_schemes.setdefault(
            "MutualTLS",
            {
                "type": "mutualTLS",
                "description": (
                    "Client certificate required for administrative endpoints. "
                    "Certificates must be issued by the TradePulse platform CA."
                ),
            },
        )

        admin_security: list[dict[str, list[str]]] = [
            {"OAuth2Bearer": [], "MutualTLS": []}
        ]
        admin_error_responses = {
            "401": {
                "description": "Authentication token missing or invalid.",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                    }
                },
            },
            "403": {
                "description": "Authenticated caller lacks sufficient privileges.",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                    }
                },
            },
            "429": {
                "description": "Administrator exceeded configured rate limits.",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                    }
                },
            },
            "500": {
                "description": "Unexpected server-side failure.",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                    }
                },
            },
        }

        paths = schema.setdefault("paths", {})
        admin_path = paths.get("/admin/kill-switch")
        if isinstance(admin_path, dict):
            for method in ("get", "post", "delete"):
                operation = admin_path.get(method)
                if not isinstance(operation, dict):
                    continue
                operation["security"] = admin_security
                responses = operation.setdefault("responses", {})
                for status_code, payload in admin_error_responses.items():
                    existing = responses.get(status_code)
                    if isinstance(existing, dict):
                        existing.setdefault("description", payload["description"])
                        existing.setdefault("content", payload["content"])
                    else:
                        responses[status_code] = payload

        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi


def create_app(
    *,
    rate_limiter: SlidingWindowRateLimiter | None = None,
    cache: TTLCache | None = None,
    forecaster_factory: Callable[[], OnlineSignalForecaster] | None = None,
    settings: AdminApiSettings | None = None,
    rate_limit_settings: ApiRateLimitSettings | None = None,
    security_settings: ApiSecuritySettings | None = None,
    dependency_probes: Mapping[str, DependencyProbe] | None = None,
    health_server: HealthServer | None = None,
    runtime_settings: BackendRuntimeSettings | None = None,
) -> FastAPI:
    """Build the FastAPI application with configured dependencies.

    Args:
        rate_limiter: Optional AsyncLimiter controlling request throughput for
            inference endpoints.
        cache: Shared cache instance for feature and prediction responses.
        forecaster_factory: Callable returning the forecaster implementation.
        settings: Administrative configuration backing the kill-switch API. When
            omitted the values are loaded from :class:`AdminApiSettings` using
            environment variables.
    """

    runtime_settings = runtime_settings or BackendRuntimeSettings()
    resolved_log_level = runtime_settings.resolve_log_level()
    root_logger = logging.getLogger()
    if runtime_settings.should_configure_logging(
        handlers_installed=bool(root_logger.handlers)
    ):
        configure_logging(level=resolved_log_level)
    else:
        root_logger.setLevel(resolved_log_level)

    resolved_rate_settings = rate_limit_settings or ApiRateLimitSettings()
    limiter = rate_limiter or build_rate_limiter(resolved_rate_settings)
    ttl_cache = cache or TTLCache(ttl_seconds=30, max_entries=512)
    idempotency_cache = IdempotencyCache(ttl_seconds=900, max_entries=2048)
    forecaster_provider = forecaster_factory or (lambda: OnlineSignalForecaster())
    forecaster = forecaster_provider()
    dependency_probe_map: dict[str, DependencyProbe] = dict(dependency_probes or {})

    try:
        resolved_settings = settings or AdminApiSettings()
    except ValidationError as exc:  # pragma: no cover - defensive branch
        alias_map = {
            "audit_secret": "TRADEPULSE_AUDIT_SECRET",  # pragma: allowlist secret
            "AUDIT_SECRET": "TRADEPULSE_AUDIT_SECRET",  # pragma: allowlist secret
            "admin_subject": "TRADEPULSE_ADMIN_SUBJECT",
            "ADMIN_SUBJECT": "TRADEPULSE_ADMIN_SUBJECT",
            "admin_rate_limit_max_attempts": "TRADEPULSE_ADMIN_RATE_LIMIT_MAX_ATTEMPTS",
            "ADMIN_RATE_LIMIT_MAX_ATTEMPTS": "TRADEPULSE_ADMIN_RATE_LIMIT_MAX_ATTEMPTS",
            "admin_rate_limit_interval_seconds": "TRADEPULSE_ADMIN_RATE_LIMIT_INTERVAL_SECONDS",
            "ADMIN_RATE_LIMIT_INTERVAL_SECONDS": "TRADEPULSE_ADMIN_RATE_LIMIT_INTERVAL_SECONDS",
            "audit_webhook_url": "TRADEPULSE_AUDIT_WEBHOOK_URL",
            "AUDIT_WEBHOOK_URL": "TRADEPULSE_AUDIT_WEBHOOK_URL",
        }
        missing = [
            alias_map.get(error["loc"][0], error["loc"][0])
            for error in exc.errors()
            if error.get("type") == "missing"
        ]
        joined = ", ".join(sorted(set(missing))) or "configuration values"
        raise RuntimeError(
            (
                "Missing required secret(s): {}. Provide them via AdminApiSettings "
                "or environment variables."
            ).format(joined)
        ) from exc

    try:
        resolved_security_settings = security_settings or get_api_security_settings()
    except ValidationError as exc:
        alias_map = {
            "oauth2_issuer": "TRADEPULSE_OAUTH2_ISSUER",
            "oauth2_audience": "TRADEPULSE_OAUTH2_AUDIENCE",
            "oauth2_jwks_uri": "TRADEPULSE_OAUTH2_JWKS_URI",
        }
        missing = [
            alias_map.get(error["loc"][0], error["loc"][0])
            for error in exc.errors()
            if error.get("type") == "missing"
        ]
        joined = ", ".join(sorted(set(missing))) or "OAuth configuration values"
        raise RuntimeError(
            ("Missing required OAuth configuration: {}.").format(joined)
        ) from exc
    if security_settings is not None:
        setattr(get_api_security_settings, "_instance", resolved_security_settings)
        setattr(get_api_security_settings, "_manual_override", True)
        if hasattr(get_api_security_settings, "_loader"):
            delattr(get_api_security_settings, "_loader")
    elif hasattr(get_api_security_settings, "_manual_override"):
        delattr(get_api_security_settings, "_manual_override")
    audit_sink = None
    if resolved_settings.audit_webhook_url is not None:
        audit_sink = HttpAuditSink(str(resolved_settings.audit_webhook_url))

    access_controller = resolved_settings.build_access_controller()

    secret_manager = resolved_settings.build_secret_manager(
        audit_logger_factory=lambda manager: AuditLogger(
            secret_resolver=manager.provider("audit_secret"),
            sink=audit_sink,
        ),
        access_controller=access_controller,
    )
    require_bearer = verify_request_identity()
    optional_bearer = verify_optional_request_identity()
    require_bearer_with_mtls = verify_request_identity(require_client_certificate=True)
    audit_secret_provider = secret_manager.provider("audit_secret")
    two_factor_secret_provider = secret_manager.provider("two_factor_secret")
    rate_limit_max_attempts = resolved_settings.admin_rate_limit_max_attempts
    rate_limit_interval = resolved_settings.admin_rate_limit_interval_seconds

    audit_logger = secret_manager.audit_logger
    if audit_logger is None:
        audit_logger = AuditLogger(
            secret_resolver=audit_secret_provider, sink=audit_sink
        )

    kill_switch_store_settings = resolved_settings.kill_switch_postgres
    if kill_switch_store_settings is not None:
        kill_switch_store = PostgresKillSwitchStateStore(
            str(kill_switch_store_settings.dsn),
            tls=kill_switch_store_settings.tls,
            pool_min_size=int(kill_switch_store_settings.min_pool_size),
            pool_max_size=int(kill_switch_store_settings.max_pool_size),
            acquire_timeout=(
                float(kill_switch_store_settings.acquire_timeout_seconds)
                if kill_switch_store_settings.acquire_timeout_seconds is not None
                else None
            ),
            connect_timeout=float(kill_switch_store_settings.connect_timeout_seconds),
            statement_timeout_ms=int(kill_switch_store_settings.statement_timeout_ms),
            max_retries=int(kill_switch_store_settings.max_retries),
            retry_interval=float(kill_switch_store_settings.retry_interval_seconds),
            backoff_multiplier=float(kill_switch_store_settings.backoff_multiplier),
        )
    else:
        kill_switch_store = SQLiteKillSwitchStateStore(
            resolved_settings.kill_switch_store_path
        )
    risk_manager_facade = RiskManagerFacade(
        RiskManager(RiskLimits(), kill_switch_store=kill_switch_store),
        access_controller=access_controller,
    )
    admin_rate_limiter = AdminRateLimiter(
        max_attempts=int(rate_limit_max_attempts),
        interval_seconds=float(rate_limit_interval),
    )

    def _kill_switch_attributes(_: Request, __: AdminIdentity) -> Mapping[str, str]:
        return {"environment": resolved_settings.admin_environment}

    two_factor_dependency = require_two_factor(
        secret_provider=two_factor_secret_provider,
        header_name=resolved_settings.two_factor_header_name,
        digits=int(resolved_settings.two_factor_digits),
        period_seconds=int(resolved_settings.two_factor_period_seconds),
        drift_windows=int(resolved_settings.two_factor_allowed_drift_windows),
        algorithm=resolved_settings.two_factor_algorithm,
        identity_dependency=require_bearer_with_mtls,
    )

    kill_switch_read_permission = require_permission(
        "risk.kill_switch",
        "read",
        identity_dependency=two_factor_dependency,
        attributes_provider=_kill_switch_attributes,
    )
    kill_switch_execute_permission = require_permission(
        "risk.kill_switch",
        "execute",
        identity_dependency=two_factor_dependency,
        attributes_provider=_kill_switch_attributes,
    )

    app = FastAPI(
        title="TradePulse Online Inference API",
        description=(
            "Production-ready endpoints for computing feature vectors and generating "
            "lightweight trading signals from streaming market data."
        ),
        version="0.2.0",
        debug=runtime_settings.debug,
        contact={
            "name": "TradePulse Platform Team",
            "url": "https://github.com/neuron7x/TradePulse",
        },
        license_info={
            "name": "TradePulse Proprietary License Agreement (TPLA)",
            "url": "https://github.com/neuron7x/TradePulse/blob/main/LICENSE",
        },
        openapi_tags=[
            {"name": "health", "description": "Operational endpoints"},
            {"name": "features", "description": "Feature engineering APIs"},
            {"name": "predictions", "description": "Signal forecasting APIs"},
        ],
    )

    metrics_disabled = os.getenv("TRADEPULSE_DISABLE_METRICS") == "1"
    metrics_registry = None
    try:  # Lazy import to avoid hard dependency during tests without prometheus_client
        from prometheus_client import (
            REGISTRY as prometheus_registry,
        )
        from prometheus_client import (
            CollectorRegistry,
            ProcessCollector,
        )
    except Exception:  # pragma: no cover - optional dependency
        metrics_registry = None
    else:
        if metrics_disabled:
            metrics_registry = CollectorRegistry()
        else:
            metrics_registry = prometheus_registry
            try:
                sample = metrics_registry.get_sample_value("process_cpu_seconds_total")
            except Exception:  # pragma: no cover - registry API may differ across versions
                sample = None
            if sample is None:
                try:
                    ProcessCollector(registry=metrics_registry)
                except ValueError:
                    pass

    metrics_module = __import__("core.utils.metrics", fromlist=["MetricsCollector"])
    metrics_collector = get_metrics_collector(metrics_registry)
    if (
        metrics_registry is not None
        and getattr(metrics_collector, "registry", None) is None
    ):
        refreshed_metrics = metrics_module.MetricsCollector(metrics_registry)
        metrics_collector.__dict__.update(refreshed_metrics.__dict__)
        setattr(metrics_module, "_collector", metrics_collector)
    app.state.metrics = metrics_collector

    analytics_store = AnalyticsStore()
    stream_manager = RealTimeStreamManager()
    app.state.analytics_store = analytics_store
    app.state.stream_manager = stream_manager
    app.state.shutting_down = False
    analytics_logger = logging.getLogger("tradepulse.api.analytics")
    lifecycle_logger = logging.getLogger("tradepulse.api.lifecycle")

    async def _record_feature_analytics(result: FeatureResponse) -> None:
        try:
            event = await analytics_store.record_feature(result)
        except Exception:  # pragma: no cover - defensive
            analytics_logger.exception("Failed to record feature analytics snapshot")
            return
        await stream_manager.broadcast(event)

    async def _record_prediction_analytics(result: PredictionResponse) -> None:
        try:
            event = await analytics_store.record_prediction(result)
        except Exception:  # pragma: no cover - defensive
            analytics_logger.exception("Failed to record prediction analytics snapshot")
            return
        await stream_manager.broadcast(event)

    configure_openapi(app)

    app.add_middleware(
        PrometheusMetricsMiddleware,
        collector=metrics_collector,
    )

    app.add_middleware(
        AccessLogMiddleware,
        audit_trail=get_access_audit_trail(),
        service="online_inference_api",
        capture_headers=("x-request-id", "x-correlation-id", "traceparent"),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(resolved_security_settings.trusted_hosts),
    )
    app.add_middleware(
        PayloadGuardMiddleware,
        max_body_bytes=int(resolved_security_settings.max_request_bytes),
        suspicious_keys=set(resolved_security_settings.suspicious_json_keys),
        suspicious_substrings=tuple(
            resolved_security_settings.suspicious_json_substrings
        ),
    )

    app.include_router(
        create_remote_control_router(
            risk_manager_facade,
            audit_logger,
            identity_dependency=two_factor_dependency,
            rate_limiter=admin_rate_limiter,
            read_permission=kill_switch_read_permission,
            execute_permission=kill_switch_execute_permission,
            reset_permission=kill_switch_execute_permission,
        )
    )
    app.state.risk_manager = risk_manager_facade.risk_manager
    app.state.access_controller = access_controller
    app.state.audit_logger = audit_logger
    app.state.secret_manager = secret_manager
    app.state.admin_rate_limiter = admin_rate_limiter
    app.state.client_rate_limiter = limiter
    app.state.rate_limit_settings = resolved_rate_settings
    app.state.ttl_cache = ttl_cache
    app.state.idempotency_cache = idempotency_cache
    app.state.dependency_probes = dependency_probe_map
    app.state.health_server = health_server
    inspector = VariableInspector(
        redact_patterns=runtime_settings.redact_pattern_values()
    )
    if runtime_settings.inspect_variables:
        inspector.register(
            "environment",
            lambda: inspector.collect_environment(runtime_settings.inspect_variables),
        )
    inspector.register("rate_limiter", limiter.snapshot)
    inspector.register("admin_rate_limiter", admin_rate_limiter.snapshot)
    inspector.register("ttl_cache", ttl_cache.snapshot)
    inspector.register("idempotency_cache", idempotency_cache.snapshot)
    inspector.register(
        "runtime",
        lambda: {
            "debug": runtime_settings.debug,
            "log_level": logging.getLevelName(resolved_log_level),
            "forecaster": type(forecaster).__name__,
        },
    )
    app.state.variable_inspector = inspector
    app.state.runtime_settings = runtime_settings
    inspector.register(
        "metrics",
        lambda: {
            "collector": type(metrics_collector).__name__,
            "registry_attached": metrics_registry is not None,
        },
    )
    metrics_sampler = MetricsSampler(metrics_collector)
    app.state.metrics_sampler = metrics_sampler
    inspector.register(
        "metrics_sampler",
        lambda: {
            "interval_seconds": metrics_sampler.interval,
            "running": metrics_sampler.is_running,
        },
    )
    install_debug_routes(
        app,
        inspector=inspector,
        enabled=runtime_settings.debug,
        identity_dependency=require_bearer,
    )

    async def _start_metrics_sampler() -> None:
        metrics_sampler.start()

    async def _stop_metrics_sampler() -> None:
        await metrics_sampler.stop()

    app.add_event_handler("startup", _start_metrics_sampler)
    app.add_event_handler("shutdown", _stop_metrics_sampler)
    if runtime_settings.debug and runtime_settings.log_variables_on_startup:
        debug_logger = logging.getLogger("tradepulse.debug")

        @app.on_event("startup")
        async def _log_debug_snapshot() -> None:
            snapshot = await inspector.snapshot()
            debug_logger.debug(
                "debug.variables.snapshot",
                extra={"variables": snapshot, "component": "inference_api"},
            )

    async def _apply_rate_limit(
        request: Request, identity: AdminIdentity | None
    ) -> AdminIdentity | None:
        ip_address = _resolve_ip(request)
        subject = identity.subject if identity is not None else None
        await limiter.check(subject=subject, ip_address=ip_address)
        return identity

    async def enforce_rate_limit(
        request: Request,
        identity: AdminIdentity = Depends(require_bearer),
    ) -> AdminIdentity:
        resolved_identity = await _apply_rate_limit(request, identity)
        assert resolved_identity is not None
        return resolved_identity

    async def enforce_public_rate_limit(
        request: Request,
        identity: AdminIdentity | None = Depends(optional_bearer),
    ) -> AdminIdentity | None:
        return await _apply_rate_limit(request, identity)

    def get_forecaster() -> OnlineSignalForecaster:
        return forecaster

    def _append_vary_header(response: Response, value: str) -> None:
        existing = response.headers.get("Vary")
        if not existing:
            response.headers["Vary"] = value
            return
        values = {entry.strip() for entry in existing.split(",") if entry.strip()}
        if value not in values:
            response.headers["Vary"] = f"{existing}, {value}"

    v1_router = APIRouter()

    async def replay_if_available(
        *,
        key: str,
        fingerprint: str,
        response: Response,
        factory: Callable[[dict[str, Any]], ResponseModelT],
    ) -> ResponseModelT | None:
        record = await idempotency_cache.get(key)
        if record is None:
            return None
        if record.payload_hash != fingerprint:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": ApiErrorCode.IDEMPOTENCY_CONFLICT.value,
                    "message": "Idempotency-Key already used with a different payload.",
                },
            )
        for header_name, header_value in record.headers.items():
            response.headers[header_name] = header_value
        response.headers["Idempotency-Key"] = key
        response.headers["X-Idempotent-Replay"] = "true"
        response.status_code = record.status_code
        return factory(record.body)

    async def persist_idempotency_result(
        *,
        key: str,
        fingerprint: str,
        model: BaseModel,
        response: Response,
        status_code: int = status.HTTP_200_OK,
    ) -> None:
        header_subset = {
            header: response.headers[header]
            for header in ("ETag", "X-Cache-Status")
            if header in response.headers
        }
        try:
            await idempotency_cache.set(
                key=key,
                payload_hash=fingerprint,
                body=model.model_dump(mode="json"),
                status_code=status_code,
                headers=header_subset,
            )
        except IdempotencyConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": ApiErrorCode.IDEMPOTENCY_CONFLICT.value,
                    "message": "Idempotency-Key already used with a different payload.",
                },
            ) from exc

    @app.middleware("http")
    async def add_cache_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/admin") or response.status_code >= 400:
            response.headers["Cache-Control"] = "no-store"
            response.headers.setdefault("Pragma", "no-cache")
            _append_vary_header(response, "Authorization")
        else:
            response.headers["Cache-Control"] = (
                f"private, max-age={ttl_cache.ttl_seconds}"
            )
        _append_vary_header(response, "Accept")
        return response

    @app.get(
        "/health",
        tags=["health"],
        summary="Health probe",
        response_model=HealthResponse,
    )
    async def health_check(response: Response) -> HealthResponse:
        overall_start = perf_counter()
        metrics_collector: MetricsCollector | None = getattr(app.state, "metrics", None)
        components: dict[str, ComponentHealth] = {}
        shutdown_in_progress = bool(getattr(app.state, "shutting_down", False))

        risk_manager: RiskManager = app.state.risk_manager
        kill_switch = risk_manager.kill_switch
        kill_engaged = kill_switch.is_triggered()
        kill_metrics = {"kill_switch_engaged": kill_engaged}
        if kill_switch.reason:
            kill_metrics["reason"] = kill_switch.reason
        kill_detail = (
            kill_switch.reason if kill_engaged and kill_switch.reason else None
        )
        components["risk_manager"] = ComponentHealth(
            healthy=not kill_engaged,
            status="operational" if not kill_engaged else "failed",
            detail=kill_detail,
            metrics=kill_metrics,
        )

        cache_snapshot = await ttl_cache.snapshot()
        cache_utilisation = (
            cache_snapshot.entries / cache_snapshot.max_entries
            if cache_snapshot.max_entries
            else 0.0
        )
        cache_metrics = {
            "entries": cache_snapshot.entries,
            "max_entries": cache_snapshot.max_entries,
            "ttl_seconds": cache_snapshot.ttl_seconds,
            "utilization": round(cache_utilisation, 4),
        }
        cache_healthy = cache_snapshot.entries < cache_snapshot.max_entries
        components["inference_cache"] = ComponentHealth(
            healthy=cache_healthy,
            status="operational" if cache_healthy else "degraded",
            metrics=cache_metrics,
        )

        client_snapshot: RateLimiterSnapshot = limiter.snapshot()
        client_metrics = {
            "backend": client_snapshot.backend,
            "tracked_keys": client_snapshot.tracked_keys,
            "max_utilization": (
                round(client_snapshot.max_utilization, 4)
                if client_snapshot.max_utilization is not None
                else None
            ),
            "saturated_keys": list(client_snapshot.saturated_keys),
            "default_policy": {
                "max_requests": resolved_rate_settings.default_policy.max_requests,
                "window_seconds": resolved_rate_settings.default_policy.window_seconds,
            },
        }
        client_healthy = True
        client_status = "operational"
        if (
            client_snapshot.max_utilization is not None
            and client_snapshot.max_utilization >= 0.9
        ):
            client_healthy = False
            client_status = "degraded"
        if client_snapshot.saturated_keys:
            client_healthy = False
            client_status = "degraded"
        components["client_rate_limiter"] = ComponentHealth(
            healthy=client_healthy,
            status=client_status,
            metrics=client_metrics,
        )

        idempotency_snapshot: IdempotencySnapshot = await idempotency_cache.snapshot()
        idempotency_metrics = {
            "entries": idempotency_snapshot.entries,
            "ttl_seconds": idempotency_snapshot.ttl_seconds,
        }
        components["idempotency_ledger"] = ComponentHealth(
            healthy=True,
            status="operational",
            metrics=idempotency_metrics,
        )

        admin_snapshot: AdminRateLimiterSnapshot = await admin_rate_limiter.snapshot()
        admin_metrics = {
            "tracked_identifiers": admin_snapshot.tracked_identifiers,
            "max_attempts": admin_snapshot.max_attempts,
            "interval_seconds": admin_snapshot.interval_seconds,
            "max_utilization": round(admin_snapshot.max_utilization, 4),
            "saturated_identifiers": list(admin_snapshot.saturated_identifiers),
        }
        admin_healthy = (
            admin_snapshot.max_utilization < 1.0
            and not admin_snapshot.saturated_identifiers
        )
        components["admin_rate_limiter"] = ComponentHealth(
            healthy=admin_healthy,
            status="operational" if admin_healthy else "degraded",
            metrics=admin_metrics,
        )

        dependency_failures = False
        for name, probe in dependency_probe_map.items():
            start = perf_counter()
            try:
                result = probe()
                if inspect.isawaitable(result):
                    result = await result
                elapsed_ms = (perf_counter() - start) * 1000
            except Exception as exc:  # pragma: no cover - defensive
                elapsed_ms = (perf_counter() - start) * 1000
                dependency_failures = True
                components[f"dependency:{name}"] = ComponentHealth(
                    healthy=False,
                    status="failed",
                    detail=str(exc),
                    metrics={"latency_ms": round(elapsed_ms, 2)},
                )
                continue

            normalised = _coerce_dependency_result(result)
            component_metrics = dict(normalised.data or {})
            component_metrics["latency_ms"] = round(elapsed_ms, 2)
            status_value = "operational" if normalised.healthy else "failed"
            if not normalised.healthy:
                dependency_failures = True
            components[f"dependency:{name}"] = ComponentHealth(
                healthy=normalised.healthy,
                status=status_value,
                detail=normalised.detail,
                metrics=component_metrics,
            )

        if shutdown_in_progress:
            components["lifecycle"] = ComponentHealth(
                healthy=False,
                status="failed",
                detail="application shutting down",
            )

        severity = "ready"
        if (
            shutdown_in_progress
            or any(component.status == "failed" for component in components.values())
            or dependency_failures
            or kill_engaged
        ):
            severity = "failed"
        elif any(component.status == "degraded" for component in components.values()):
            severity = "degraded"

        health_payload = HealthResponse(status=severity, components=components)

        probe_status = (
            status.HTTP_200_OK
            if severity == "ready"
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        response.status_code = probe_status

        health_state: HealthServer | None = app.state.health_server
        if health_state is not None:
            if shutdown_in_progress:
                health_state.set_live(False)
                health_state.set_ready(False)
            else:
                health_state.set_live(True)
                health_state.set_ready(severity == "ready")
            for name, component in components.items():
                health_state.update_component(name, component.healthy, component.detail)

        if metrics_collector and metrics_collector.enabled:
            duration = perf_counter() - overall_start
            metrics_collector.observe_health_check_latency("api.overall", duration)
            metrics_collector.set_health_check_status(
                "api.overall", severity == "ready"
            )
            for name, component in components.items():
                metrics_collector.set_health_check_status(
                    f"component.{name}", component.healthy
                )

        return health_payload

    @app.get(
        "/metrics",
        tags=["health"],
        summary="Prometheus metrics",
        response_class=PlainTextResponse,
    )
    async def prometheus_metrics() -> PlainTextResponse:
        metrics: MetricsCollector | None = getattr(app.state, "metrics", None)
        if metrics is None:
            metrics = get_metrics_collector()

        if not metrics.enabled:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Prometheus metrics are disabled"
            )

        payload = metrics.render_prometheus()
        return PlainTextResponse(
            payload,
            media_type="text/plain; version=0.0.4; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )

    @v1_router.post(
        "/features",
        response_model=FeatureResponse,
        tags=["features"],
        summary="Generate the latest engineered feature vector",
        responses={**FEATURE_SUCCESS_RESPONSE, **FEATURE_ERROR_RESPONSES},
    )
    async def v1_compute_features(
        payload: FeatureRequest,
        response: Response,
        query: FeatureQueryParams = Depends(get_feature_query_params),
        _identity: AdminIdentity = Depends(enforce_rate_limit),
        predictor: OnlineSignalForecaster = Depends(get_forecaster),
        idempotency_key_header: str | None = Header(
            default=None, alias="Idempotency-Key", convert_underscores=False
        ),
    ) -> FeatureResponse:
        cache_key = _hash_payload("features", payload, query.cache_fragment())
        idempotency_key: str | None = None
        if idempotency_key_header is not None:
            idempotency_key = _validate_idempotency_key(idempotency_key_header)
            replay = await replay_if_available(
                key=idempotency_key,
                fingerprint=cache_key,
                response=response,
                factory=FeatureResponse.model_validate,
            )
            if replay is not None:
                return replay

        cached = await ttl_cache.get(cache_key)
        if cached is not None:
            response.headers["X-Cache-Status"] = "hit"
            response.headers["ETag"] = cached.etag
            result_model: FeatureResponse = cached.payload  # type: ignore[assignment]
            if idempotency_key is not None:
                await persist_idempotency_result(
                    key=idempotency_key,
                    fingerprint=cache_key,
                    model=result_model,
                    response=response,
                )
                response.headers["Idempotency-Key"] = idempotency_key
            return result_model

        features = predictor.compute_features(payload)
        filtered = _filter_feature_frame(
            features,
            start_at=query.start_at,
            end_at=query.end_at,
        )
        ordered = filtered.sort_index(ascending=False)
        if query.cursor is not None:
            ordered = ordered[ordered.index < query.cursor]

        snapshots: list[FeatureSnapshot] = []
        next_cursor: datetime | None = None
        last_position: int | None = None
        last_timestamp: pd.Timestamp | datetime | None = None

        for position, (row_timestamp, raw_vector) in enumerate(ordered.iterrows()):
            last_position = position
            last_timestamp = row_timestamp
            normalised = predictor._normalise_feature_row(raw_vector, strict=False)
            if normalised is None:
                continue
            values = _filter_feature_values(
                normalised,
                feature_prefix=query.feature_prefix,
                feature_keys=query.feature_keys,
            )
            if not values:
                continue
            python_ts = (
                row_timestamp.to_pydatetime()
                if hasattr(row_timestamp, "to_pydatetime")
                else row_timestamp
            )
            snapshots.append(
                FeatureSnapshot(timestamp=_ensure_timezone(python_ts), features=values)
            )
            if len(snapshots) >= query.limit:
                break

        if last_timestamp is not None and last_position is not None:
            remaining = ordered.iloc[last_position + 1 :]
            if not remaining.empty:
                python_ts = (
                    last_timestamp.to_pydatetime()
                    if hasattr(last_timestamp, "to_pydatetime")
                    else last_timestamp
                )
                next_cursor = _ensure_timezone(python_ts)

        if not snapshots:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": ApiErrorCode.FEATURES_FILTER_MISMATCH.value,
                    "message": "No feature snapshots matched the requested filters.",
                },
            )

        pagination = PaginationMeta(
            cursor=query.cursor,
            next_cursor=next_cursor,
            limit=query.limit,
            returned=len(snapshots),
        )
        filters = FeatureFilters(
            start_at=query.start_at,
            end_at=query.end_at,
            feature_prefix=query.feature_prefix,
            feature_keys=query.feature_keys,
        )
        feature_dict = snapshots[0].features if snapshots else {}
        body = FeatureResponse(
            symbol=payload.symbol,
            features=feature_dict,
            items=snapshots,
            pagination=pagination,
            filters=filters,
        )
        etag = hashlib.sha256(
            json.dumps(body.model_dump(), sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        await ttl_cache.set(cache_key, body, etag)
        response.headers["X-Cache-Status"] = "miss"
        response.headers["ETag"] = etag
        if idempotency_key is not None:
            await persist_idempotency_result(
                key=idempotency_key,
                fingerprint=cache_key,
                model=body,
                response=response,
            )
            response.headers["Idempotency-Key"] = idempotency_key
        await _record_feature_analytics(body)
        return body

    @v1_router.post(
        "/predictions",
        response_model=PredictionResponse,
        tags=["predictions"],
        summary="Produce a trading signal for the latest bar",
        responses={
            **PREDICTION_SUCCESS_RESPONSE,
            **PREDICTION_ERROR_RESPONSES,
        },
    )
    async def v1_generate_prediction(
        payload: PredictionRequest,
        response: Response,
        query: PredictionQueryParams = Depends(get_prediction_query_params),
        _identity: AdminIdentity = Depends(enforce_rate_limit),
        predictor: OnlineSignalForecaster = Depends(get_forecaster),
        idempotency_key_header: str | None = Header(
            default=None, alias="Idempotency-Key", convert_underscores=False
        ),
    ) -> PredictionResponse:
        cache_key = _hash_payload("predictions", payload, query.cache_fragment())
        idempotency_key: str | None = None
        if idempotency_key_header is not None:
            idempotency_key = _validate_idempotency_key(idempotency_key_header)
            replay = await replay_if_available(
                key=idempotency_key,
                fingerprint=cache_key,
                response=response,
                factory=PredictionResponse.model_validate,
            )
            if replay is not None:
                return replay

        cached = await ttl_cache.get(cache_key)
        if cached is not None:
            response.headers["X-Cache-Status"] = "hit"
            response.headers["ETag"] = cached.etag
            result_model: PredictionResponse = cached.payload  # type: ignore[assignment]
            if idempotency_key is not None:
                await persist_idempotency_result(
                    key=idempotency_key,
                    fingerprint=cache_key,
                    model=result_model,
                    response=response,
                )
                response.headers["Idempotency-Key"] = idempotency_key
            return result_model

        features = predictor.compute_features(payload)
        filtered = _filter_feature_frame(
            features,
            start_at=query.start_at,
            end_at=query.end_at,
        )
        ordered = filtered.sort_index(ascending=False)
        if query.cursor is not None:
            ordered = ordered[ordered.index < query.cursor]

        predictions: list[PredictionSnapshot] = []
        next_cursor: datetime | None = None
        last_position: int | None = None
        last_timestamp: pd.Timestamp | datetime | None = None

        for position, (row_timestamp, raw_vector) in enumerate(ordered.iterrows()):
            last_position = position
            last_timestamp = row_timestamp
            normalised = predictor._normalise_feature_row(raw_vector, strict=False)
            if normalised is None:
                continue
            signal, score = predictor.derive_signal(
                payload.symbol, normalised, payload.horizon_seconds
            )
            if query.actions and signal.action not in query.actions:
                continue
            if (
                query.min_confidence is not None
                and float(signal.confidence) < query.min_confidence
            ):
                continue
            python_ts = (
                row_timestamp.to_pydatetime()
                if hasattr(row_timestamp, "to_pydatetime")
                else row_timestamp
            )
            predictions.append(
                PredictionSnapshot(
                    timestamp=_ensure_timezone(python_ts),
                    score=score,
                    signal=signal_to_dto(signal),
                )
            )
            if len(predictions) >= query.limit:
                break

        if last_timestamp is not None and last_position is not None:
            remaining = ordered.iloc[last_position + 1 :]
            if not remaining.empty:
                python_ts = (
                    last_timestamp.to_pydatetime()
                    if hasattr(last_timestamp, "to_pydatetime")
                    else last_timestamp
                )
                next_cursor = _ensure_timezone(python_ts)

        if not predictions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": ApiErrorCode.PREDICTIONS_FILTER_MISMATCH.value,
                    "message": "No predictions matched the requested filters.",
                },
            )

        pagination = PaginationMeta(
            cursor=query.cursor,
            next_cursor=next_cursor,
            limit=query.limit,
            returned=len(predictions),
        )
        filters = PredictionFilters(
            start_at=query.start_at,
            end_at=query.end_at,
            actions=query.actions,
            min_confidence=query.min_confidence,
        )
        head = predictions[0] if predictions else None
        body = PredictionResponse(
            symbol=payload.symbol,
            horizon_seconds=payload.horizon_seconds,
            score=head.score if head else None,
            signal=head.signal if head else None,
            items=predictions,
            pagination=pagination,
            filters=filters,
        )
        etag = hashlib.sha256(
            json.dumps(body.model_dump(), sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        await ttl_cache.set(cache_key, body, etag)
        response.headers["X-Cache-Status"] = "miss"
        response.headers["ETag"] = etag
        if idempotency_key is not None:
            await persist_idempotency_result(
                key=idempotency_key,
                fingerprint=cache_key,
                model=body,
                response=response,
            )
            response.headers["Idempotency-Key"] = idempotency_key
        await _record_prediction_analytics(body)
        return body

    versioned_router = APIRouter(prefix="/api")
    versioned_router.include_router(v1_router, prefix="/v1")
    app.include_router(versioned_router)

    graphql_router = create_graphql_router(analytics_store)
    app.include_router(
        graphql_router,
        prefix="/graphql",
        dependencies=[Depends(enforce_public_rate_limit)],
    )

    def _websocket_http_request(websocket: WebSocket) -> Request:
        scope = dict(websocket.scope)
        scope["type"] = "http"
        scope["state"] = websocket.scope.setdefault("state", {})
        return Request(scope)

    async def _authenticate_websocket(websocket: WebSocket) -> AdminIdentity:
        request = _websocket_http_request(websocket)
        authorization = request.headers.get("authorization")
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token required for this endpoint.",
            )
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token required for this endpoint.",
            )

        credentials = HTTPAuthorizationCredentials(scheme=scheme, credentials=token)
        settings = get_api_security_settings()
        identity = await require_bearer(request, credentials, settings)
        ip_address = _resolve_ip(request)
        await limiter.check(subject=identity.subject, ip_address=ip_address)
        websocket.scope.setdefault("state", {})["identity"] = identity
        return identity

    def _websocket_close_reason(detail: Any) -> str:
        if isinstance(detail, str):
            return detail
        if isinstance(detail, Mapping):
            message = detail.get("message")
            if isinstance(message, str):
                return message
            description = detail.get("detail")
            if isinstance(description, str):
                return description
        return "Unauthorized"

    @app.websocket("/ws/stream")
    async def realtime_stream(websocket: WebSocket) -> None:
        try:
            await _authenticate_websocket(websocket)
        except HTTPException as exc:
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason=_websocket_close_reason(exc.detail),
            )
            return

        await stream_manager.connect(websocket)
        try:
            snapshot = await analytics_store.snapshot()
            await websocket.send_json(snapshot)
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception:  # pragma: no cover - defensive
            logging.getLogger("tradepulse.api.websocket").exception(
                "Unexpected error while streaming realtime updates",
                exc_info=True,
            )
        finally:
            await stream_manager.disconnect(websocket)

    legacy_v1_router = APIRouter(prefix="/v1")
    legacy_v1_router.include_router(v1_router)
    app.include_router(legacy_v1_router)

    app.add_api_route(
        "/features",
        v1_compute_features,
        methods=["POST"],
        response_model=FeatureResponse,
        tags=["features"],
        summary="Generate the latest engineered feature vector",
        responses={**FEATURE_SUCCESS_RESPONSE, **FEATURE_ERROR_RESPONSES},
        deprecated=True,
    )
    app.add_api_route(
        "/predictions",
        v1_generate_prediction,
        methods=["POST"],
        response_model=PredictionResponse,
        tags=["predictions"],
        summary="Produce a trading signal for the latest bar",
        responses={
            **PREDICTION_SUCCESS_RESPONSE,
            **PREDICTION_ERROR_RESPONSES,
        },
        deprecated=True,
    )

    async def _shutdown_app() -> None:
        app.state.shutting_down = True
        health_state: HealthServer | None = getattr(app.state, "health_server", None)
        if health_state is not None:
            try:
                health_state.set_ready(False)
                health_state.set_live(False)
            except Exception:  # pragma: no cover - defensive
                lifecycle_logger.exception(
                    "Failed to update health server state during shutdown",
                    exc_info=True,
                )

        try:
            await stream_manager.close_all()
        except Exception:  # pragma: no cover - defensive
            lifecycle_logger.exception(
                "Failed to close realtime websocket connections during shutdown",
                exc_info=True,
            )

        if health_state is not None:
            try:
                health_state.shutdown()
            except Exception:  # pragma: no cover - defensive
                lifecycle_logger.exception(
                    "Failed to stop health server during shutdown",
                    exc_info=True,
                )

        risk_manager_instance = getattr(app.state, "risk_manager", None)
        if risk_manager_instance is not None:
            close_method = getattr(risk_manager_instance, "close", None)
            if callable(close_method):
                try:
                    result = close_method()
                    if inspect.isawaitable(result):
                        await result
                except Exception:  # pragma: no cover - defensive
                    lifecycle_logger.exception(
                        "Failed to close risk manager during shutdown",
                        exc_info=True,
                    )

    app.add_event_handler("shutdown", _shutdown_app)

    register_exception_handlers(app)

    return app


BOOTSTRAP_STRATEGY_ENV = "TRADEPULSE_BOOTSTRAP_STRATEGY"
_DEFAULT_BOOTSTRAP_STRATEGY = "eager"
_LAZY_STRATEGIES = {"lazy"}
_FALLBACK_STRATEGIES = {"degraded"}


def _normalise_bootstrap_strategy(value: str | None) -> str:
    """Return a normalised bootstrap strategy value."""

    if not value:
        return _DEFAULT_BOOTSTRAP_STRATEGY
    normalised = value.strip().lower()
    return normalised or _DEFAULT_BOOTSTRAP_STRATEGY


def _safe_exception_message(exc: Exception, *, limit: int = 240) -> str:
    """Generate a bounded textual representation of an exception."""

    message = str(exc).strip() or exc.__class__.__name__
    if len(message) <= limit:
        return message
    return f"{message[: limit - 1]}…"


def _build_degraded_application(*, reason: str, detail: str | None = None) -> FastAPI:
    """Construct a lightweight FastAPI instance exposing degraded status."""

    degraded_app = FastAPI(
        title="TradePulse API (bootstrap disabled)",
        description=(
            "This instance is running in a degraded mode where the full application "
            "stack was not initialised."
        ),
        version="0.0.0",
        docs_url=None,
        redoc_url=None,
    )
    degraded_app.state.degraded_reason = reason
    degraded_app.state.degraded_detail = detail

    @degraded_app.get("/healthz", tags=["health"], include_in_schema=False)
    async def degraded_healthcheck() -> dict[str, str]:
        payload = {"status": "degraded", "reason": reason}
        if detail:
            payload["detail"] = detail
        return payload

    @degraded_app.get("/", include_in_schema=False)
    async def degraded_root() -> None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=reason,
        )

    return degraded_app


def bootstrap_application() -> FastAPI:
    """Create the FastAPI application honouring bootstrap strategy overrides."""

    strategy = _normalise_bootstrap_strategy(os.getenv(BOOTSTRAP_STRATEGY_ENV))
    bootstrap_logger = logging.getLogger("tradepulse.bootstrap")

    if strategy in _LAZY_STRATEGIES:
        bootstrap_logger.info(
            "Skipping TradePulse API bootstrap (strategy=%s).", strategy
        )
        return _build_degraded_application(
            reason=(
                "Bootstrap disabled via TRADEPULSE_BOOTSTRAP_STRATEGY={}.".format(
                    strategy
                )
            )
        )

    try:
        return create_app()
    except Exception as exc:
        if strategy in _FALLBACK_STRATEGIES:
            detail = _safe_exception_message(exc)
            bootstrap_logger.warning(
                "Falling back to degraded bootstrap due to initialisation failure.",
                exc_info=True,
            )
            return _build_degraded_application(
                reason="Application bootstrap failed in degraded mode.",
                detail=detail,
            )
        raise


app = bootstrap_application()

__all__ = [
    "app",
    "create_app",
    "bootstrap_application",
    "FeatureRequest",
    "FeatureResponse",
    "PredictionRequest",
    "PredictionResponse",
    "OnlineSignalForecaster",
    "TTLCache",
    "CacheSnapshot",
    "ComponentHealth",
    "HealthResponse",
    "DependencyProbe",
    "DependencyProbeResult",
]
