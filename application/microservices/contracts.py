from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

os.environ.setdefault("TRADEPULSE_AUDIT_SECRET", "contract-tests-placeholder")

_audit_logger = logging.getLogger("tradepulse.audit")
if not _audit_logger.handlers:
    _audit_logger.addHandler(logging.NullHandler())
_audit_logger.propagate = False

from application.api.service import (  # noqa: E402 - must follow env setup
    FeatureRequest,
    FeatureResponse,
    PredictionRequest,
    PredictionResponse,
)
from core.data.models import InstrumentType  # noqa: E402
from core.messaging.event_bus import EventTopic  # noqa: E402
from domain import Signal, SignalAction  # noqa: E402

StrategyCallable = Callable[[np.ndarray], np.ndarray]


@dataclass(slots=True)
class MarketDataSource:
    """Declarative description of a market data CSV source."""

    path: Path
    symbol: str
    venue: str
    instrument_type: InstrumentType = InstrumentType.SPOT
    market: str | None = None


@dataclass(slots=True)
class StrategyRun:
    """Result of executing a strategy over ingested market data."""

    market_frame: pd.DataFrame
    feature_frame: pd.DataFrame
    signals: list[Signal]
    payloads: list[dict[str, object]]


@dataclass(slots=True)
class ExecutionRequest:
    """Parameters required to hand a signal over to execution."""

    signal: Signal
    venue: str
    quantity: float
    price: float | None = None
    order_type: str | None = None
    correlation_id: str | None = None
    idempotency_key: str | None = None
    request_id: str | None = None


# ---------------------------------------------------------------------------
# Contract metadata definitions


@dataclass(slots=True)
class AuthorizationScheme:
    """Describe how a consumer authenticates when invoking a contract."""

    name: str
    description: str
    scopes: tuple[str, ...] = ()
    audience: str | None = None
    token_type: str = "Bearer"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "scopes": list(self.scopes),
            "audience": self.audience,
            "token_type": self.token_type,
        }


@dataclass(slots=True)
class IdempotencyPolicy:
    """Define how duplicate requests are detected and replayed."""

    key: str
    ttl_seconds: int
    enforce_replay_fingerprint: bool = True
    safe_methods: tuple[str, ...] = ("POST",)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "ttl_seconds": self.ttl_seconds,
            "enforce_replay_fingerprint": self.enforce_replay_fingerprint,
            "safe_methods": list(self.safe_methods),
        }


@dataclass(slots=True)
class RetryPolicy:
    """Describe retry semantics for transient failures."""

    max_attempts: int = 3
    initial_interval_seconds: float = 0.25
    backoff_multiplier: float = 2.0
    max_interval_seconds: float | None = 5.0
    jitter_seconds: float = 0.05

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_attempts": self.max_attempts,
            "initial_interval_seconds": self.initial_interval_seconds,
            "backoff_multiplier": self.backoff_multiplier,
            "max_interval_seconds": self.max_interval_seconds,
            "jitter_seconds": self.jitter_seconds,
        }


@dataclass(slots=True)
class VersioningPolicy:
    """Encode how breaking changes are managed."""

    scheme: str
    current: str
    compatible_since: str | None = None
    lifecycle: str = "active"
    deprecated: bool = False
    changelog_url: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "scheme": self.scheme,
            "current": self.current,
            "compatible_since": self.compatible_since,
            "lifecycle": self.lifecycle,
            "deprecated": self.deprecated,
            "changelog_url": self.changelog_url,
        }


@dataclass(slots=True)
class ServiceLevelIndicator:
    """Measurable signal backing an SLO target."""

    name: str
    metric: str
    target: float
    threshold_type: str
    description: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "metric": self.metric,
            "target": self.target,
            "threshold_type": self.threshold_type,
            "description": self.description,
        }


@dataclass(slots=True)
class ServiceLevelAgreement:
    """Group a set of service level indicators."""

    name: str
    indicators: tuple[ServiceLevelIndicator, ...]
    description: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "indicators": [indicator.as_dict() for indicator in self.indicators],
        }


@dataclass(slots=True)
class ObservabilityPolicy:
    """Specify tracing and metrics conventions for a contract."""

    span_name: str
    metrics_namespace: str | None = None
    default_attributes: Mapping[str, Any] | None = None

    def attributes(self, extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = dict(self.default_attributes or {})
        if extra:
            payload.update(extra)
        return payload

    def as_dict(self) -> dict[str, Any]:
        return {
            "span_name": self.span_name,
            "metrics_namespace": self.metrics_namespace,
            "default_attributes": dict(self.default_attributes or {}),
        }


@dataclass(slots=True, kw_only=True)
class InteractionContract:
    """Base metadata shared by API, event, queue, and service contracts."""

    name: str
    versioning: VersioningPolicy
    authorization: AuthorizationScheme
    idempotency: IdempotencyPolicy | None = None
    retry_policy: RetryPolicy | None = None
    sla: ServiceLevelAgreement | None = None
    observability: ObservabilityPolicy | None = None
    description: str | None = None

    def metadata(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "versioning": self.versioning.as_dict(),
            "authorization": self.authorization.as_dict(),
        }
        if self.idempotency:
            payload["idempotency"] = self.idempotency.as_dict()
        if self.retry_policy:
            payload["retry_policy"] = self.retry_policy.as_dict()
        if self.sla:
            payload["sla"] = self.sla.as_dict()
        if self.observability:
            payload["observability"] = self.observability.as_dict()
        if self.description:
            payload["description"] = self.description
        return payload


@dataclass(slots=True, kw_only=True)
class ApiContract(InteractionContract):
    """Contract metadata for HTTP endpoints."""

    method: str
    path: str
    request_model: type[BaseModel] | None = None
    response_model: type[BaseModel] | None = None
    error_responses: Mapping[int, str] | None = None
    rate_limit_per_minute: int | None = None

    def request_schema(self) -> dict[str, Any] | None:
        if self.request_model is None:
            return None
        return self.request_model.model_json_schema()

    def response_schema(self) -> dict[str, Any] | None:
        if self.response_model is None:
            return None
        return self.response_model.model_json_schema()


@dataclass(slots=True, kw_only=True)
class EventContract(InteractionContract):
    """Contract metadata for published domain events."""

    topic: EventTopic
    payload_model: type[BaseModel]
    content_type: str = "application/json"
    schema_version: str = "1.0"
    delivery_guarantee: str = "at-least-once"
    retention_hours: int = 24

    def payload_schema(self) -> dict[str, Any]:
        return self.payload_model.model_json_schema()


@dataclass(slots=True, kw_only=True)
class QueueContract(InteractionContract):
    """Contract metadata for point-to-point queue interactions."""

    queue: str
    visibility_timeout_seconds: int = 30
    max_in_flight: int = 10


@dataclass(slots=True, kw_only=True)
class ServiceInteractionContract(InteractionContract):
    """Contract metadata for in-process or RPC microservice interactions."""

    operation: str
    channel: str = "sync"
    inputs: Mapping[str, str] | None = None
    outputs: Mapping[str, str] | None = None


# ---------------------------------------------------------------------------
# Event payload models exposed via the contract registry


class MarketTickEvent(BaseModel):
    symbol: str
    venue: str
    price: float
    volume: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    market: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "BTC-USD",
                "venue": "binance",
                "price": 42001.52,
                "volume": 1.25,
                "timestamp": "2025-01-01T00:00:00Z",
                "market": "spot",
            }
        }
    )


class FeatureVectorComputedEvent(BaseModel):
    symbol: str
    feature_keys: list[str]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    feature_window: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "BTC-USD",
                "feature_keys": ["macd", "rsi"],
                "generated_at": "2025-01-01T00:00:30Z",
                "feature_window": "5m",
            }
        }
    )


class SignalGeneratedEvent(BaseModel):
    symbol: str
    action: SignalAction
    confidence: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    rationale: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "BTC-USD",
                "action": SignalAction.BUY,
                "confidence": 0.76,
                "timestamp": "2025-01-01T00:00:30Z",
                "rationale": "Composite signal from Kuramoto pipeline",
            }
        }
    )


class OrderSubmittedEvent(BaseModel):
    symbol: str
    venue: str
    quantity: float
    side: str
    order_type: str
    price: float | None = None
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "BTCUSDT",
                "venue": "binance",
                "quantity": 0.5,
                "side": "buy",
                "order_type": "limit",
                "price": 42010.5,
                "submitted_at": "2025-01-01T00:00:32Z",
                "correlation_id": "btc-1700000000",
            }
        }
    )


class OrderFillEvent(BaseModel):
    symbol: str
    venue: str
    fill_price: float
    fill_quantity: float
    remaining_quantity: float
    side: str
    fill_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "BTCUSDT",
                "venue": "binance",
                "fill_price": 42011.0,
                "fill_quantity": 0.5,
                "remaining_quantity": 0.0,
                "side": "buy",
                "fill_timestamp": "2025-01-01T00:00:35Z",
                "correlation_id": "btc-1700000000",
            }
        }
    )


# ---------------------------------------------------------------------------
# Contract registry utilities


class IntegrationContractRegistry:
    """Registry exposing the canonical interaction contracts for TradePulse."""

    def __init__(self) -> None:
        self._api: MutableMapping[str, ApiContract] = {}
        self._events: MutableMapping[str, EventContract] = {}
        self._queues: MutableMapping[str, QueueContract] = {}
        self._services: MutableMapping[str, ServiceInteractionContract] = {}

    # Registration helpers -------------------------------------------------
    def register_api(self, contract: ApiContract) -> None:
        if contract.name in self._api:
            raise ValueError(f"API contract '{contract.name}' already registered")
        self._api[contract.name] = contract

    def register_event(self, contract: EventContract) -> None:
        if contract.name in self._events:
            raise ValueError(f"Event contract '{contract.name}' already registered")
        self._events[contract.name] = contract

    def register_queue(self, contract: QueueContract) -> None:
        if contract.name in self._queues:
            raise ValueError(f"Queue contract '{contract.name}' already registered")
        self._queues[contract.name] = contract

    def register_service(self, contract: ServiceInteractionContract) -> None:
        if contract.name in self._services:
            raise ValueError(f"Service contract '{contract.name}' already registered")
        self._services[contract.name] = contract

    # Lookup helpers -------------------------------------------------------
    def get_api(self, name: str) -> ApiContract:
        return self._api[name]

    def get_event(self, name: str) -> EventContract:
        return self._events[name]

    def get_queue(self, name: str) -> QueueContract:
        return self._queues[name]

    def get_service(self, name: str) -> ServiceInteractionContract:
        return self._services[name]

    # Introspection --------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        return {
            "api": {
                name: self._api_metadata(contract)
                for name, contract in self._api.items()
            },
            "events": {
                name: self._event_metadata(contract)
                for name, contract in self._events.items()
            },
            "queues": {
                name: self._queue_metadata(contract)
                for name, contract in self._queues.items()
            },
            "services": {
                name: self._service_metadata(contract)
                for name, contract in self._services.items()
            },
        }

    def _api_metadata(self, contract: ApiContract) -> dict[str, Any]:
        payload = contract.metadata()
        payload.update(
            {
                "method": contract.method,
                "path": contract.path,
                "request_schema_digest": _schema_digest(contract.request_model),
                "response_schema_digest": _schema_digest(contract.response_model),
                "rate_limit_per_minute": contract.rate_limit_per_minute,
            }
        )
        return payload

    def _event_metadata(self, contract: EventContract) -> dict[str, Any]:
        payload = contract.metadata()
        payload.update(
            {
                "topic": contract.topic.value.name,
                "content_type": contract.content_type,
                "schema_version": contract.schema_version,
                "payload_schema_digest": _schema_digest(contract.payload_model),
                "delivery_guarantee": contract.delivery_guarantee,
                "retention_hours": contract.retention_hours,
            }
        )
        return payload

    def _queue_metadata(self, contract: QueueContract) -> dict[str, Any]:
        payload = contract.metadata()
        payload.update(
            {
                "queue": contract.queue,
                "visibility_timeout_seconds": contract.visibility_timeout_seconds,
                "max_in_flight": contract.max_in_flight,
            }
        )
        return payload

    def _service_metadata(self, contract: ServiceInteractionContract) -> dict[str, Any]:
        payload = contract.metadata()
        payload.update(
            {
                "operation": contract.operation,
                "channel": contract.channel,
                "inputs": dict(contract.inputs or {}),
                "outputs": dict(contract.outputs or {}),
            }
        )
        return payload


def _schema_digest(model: type[BaseModel] | None) -> str | None:
    if model is None:
        return None
    schema = model.model_json_schema()
    blob = json.dumps(schema, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# ---------------------------------------------------------------------------
# Default registry configuration


@lru_cache(maxsize=1)
def default_contract_registry() -> IntegrationContractRegistry:
    registry = IntegrationContractRegistry()

    service_jwt = AuthorizationScheme(
        name="service-jwt",
        description="Signed JWT issued by the platform identity provider.",
        scopes=("features:read", "predictions:read"),
        audience="tradepulse.api",
    )

    internal_service = AuthorizationScheme(
        name="internal-service",
        description="Mutual TLS service identity propagated via SPIFFE.",
        scopes=("system:internal",),
    )

    api_idempotency = IdempotencyPolicy(key="Idempotency-Key", ttl_seconds=3600)
    api_retry = RetryPolicy(max_attempts=1)
    api_sla = ServiceLevelAgreement(
        name="api.v1.latency",
        indicators=(
            ServiceLevelIndicator(
                name="p95_latency",
                metric="p95_latency_ms",
                target=350.0,
                threshold_type="lte",
                description="95th percentile latency must remain under 350ms.",
            ),
            ServiceLevelIndicator(
                name="success_rate",
                metric="success_rate",
                target=0.995,
                threshold_type="gte",
                description="Successful responses must exceed 99.5% per rolling hour.",
            ),
        ),
        description="Online inference latency and availability objectives.",
    )

    features_contract = ApiContract(
        name="tradepulse.api.v1.features",
        method="POST",
        path="/api/v1/features",
        request_model=FeatureRequest,
        response_model=FeatureResponse,
        versioning=VersioningPolicy(
            scheme="semver", current="1.2.0", compatible_since="1.0.0"
        ),
        authorization=service_jwt,
        idempotency=api_idempotency,
        retry_policy=api_retry,
        sla=api_sla,
        observability=ObservabilityPolicy(
            span_name="api.features",
            metrics_namespace="api.features",
            default_attributes={"api.version": "v1"},
        ),
        description="Generate engineered feature snapshots for a symbol.",
        rate_limit_per_minute=120,
        error_responses={
            404: "No feature snapshots matched the requested filters.",
            409: "Idempotency conflict when replaying a cached response.",
        },
    )
    registry.register_api(features_contract)

    predictions_contract = ApiContract(
        name="tradepulse.api.v1.predictions",
        method="POST",
        path="/api/v1/predictions",
        request_model=PredictionRequest,
        response_model=PredictionResponse,
        versioning=VersioningPolicy(
            scheme="semver", current="1.2.0", compatible_since="1.0.0"
        ),
        authorization=service_jwt,
        idempotency=api_idempotency,
        retry_policy=api_retry,
        sla=api_sla,
        observability=ObservabilityPolicy(
            span_name="api.predictions",
            metrics_namespace="api.predictions",
            default_attributes={"api.version": "v1"},
        ),
        description="Produce a trading signal for the latest market bar.",
        rate_limit_per_minute=120,
        error_responses={
            404: "No predictions matched the requested filters.",
            409: "Idempotency conflict when replaying a cached response.",
        },
    )
    registry.register_api(predictions_contract)

    # Event contracts ------------------------------------------------------
    registry.register_event(
        EventContract(
            name="tradepulse.events.market-ticks",
            topic=EventTopic.MARKET_TICKS,
            payload_model=MarketTickEvent,
            versioning=VersioningPolicy(scheme="semver", current="1.0.0"),
            authorization=internal_service,
            retry_policy=RetryPolicy(max_attempts=5, initial_interval_seconds=0.1),
            observability=ObservabilityPolicy(
                span_name="event.market_ticks",
                metrics_namespace="events.market_ticks",
            ),
            description="Tick-level market data propagated to downstream consumers.",
            retention_hours=6,
        )
    )

    registry.register_event(
        EventContract(
            name="tradepulse.events.feature-vectors",
            topic=EventTopic.MARKET_BARS,
            payload_model=FeatureVectorComputedEvent,
            versioning=VersioningPolicy(scheme="semver", current="1.0.0"),
            authorization=internal_service,
            retry_policy=RetryPolicy(max_attempts=5, initial_interval_seconds=0.1),
            observability=ObservabilityPolicy(
                span_name="event.feature_vectors",
                metrics_namespace="events.feature_vectors",
            ),
            description="Signals the availability of a new engineered feature vector.",
            retention_hours=24,
        )
    )

    registry.register_event(
        EventContract(
            name="tradepulse.events.signals",
            topic=EventTopic.SIGNALS,
            payload_model=SignalGeneratedEvent,
            versioning=VersioningPolicy(scheme="semver", current="1.0.0"),
            authorization=internal_service,
            retry_policy=RetryPolicy(max_attempts=5, initial_interval_seconds=0.1),
            observability=ObservabilityPolicy(
                span_name="event.signals",
                metrics_namespace="events.signals",
            ),
            description="Emitted whenever a trading signal crosses the execution boundary.",
            retention_hours=48,
        )
    )

    registry.register_event(
        EventContract(
            name="tradepulse.events.orders",
            topic=EventTopic.ORDERS,
            payload_model=OrderSubmittedEvent,
            versioning=VersioningPolicy(scheme="semver", current="1.0.0"),
            authorization=internal_service,
            retry_policy=RetryPolicy(max_attempts=5, initial_interval_seconds=0.1),
            observability=ObservabilityPolicy(
                span_name="event.orders",
                metrics_namespace="events.orders",
            ),
            description="Tracks orders submitted to execution venues.",
            retention_hours=48,
        )
    )

    registry.register_event(
        EventContract(
            name="tradepulse.events.fills",
            topic=EventTopic.FILLS,
            payload_model=OrderFillEvent,
            versioning=VersioningPolicy(scheme="semver", current="1.0.0"),
            authorization=internal_service,
            retry_policy=RetryPolicy(max_attempts=5, initial_interval_seconds=0.1),
            observability=ObservabilityPolicy(
                span_name="event.fills",
                metrics_namespace="events.fills",
            ),
            description="Captures fill confirmations returning from exchanges.",
            retention_hours=168,
        )
    )

    # Queue contract -------------------------------------------------------
    registry.register_queue(
        QueueContract(
            name="tradepulse.queues.execution-requests",
            queue="tradepulse.execution.requests",
            versioning=VersioningPolicy(scheme="semver", current="1.0.0"),
            authorization=internal_service,
            idempotency=IdempotencyPolicy(key="correlation-id", ttl_seconds=3600),
            retry_policy=RetryPolicy(max_attempts=8, initial_interval_seconds=0.5),
            observability=ObservabilityPolicy(
                span_name="queue.execution_requests",
                metrics_namespace="queues.execution",
            ),
            description="Queue carrying execution requests between signal generation and OMS.",
            visibility_timeout_seconds=120,
            max_in_flight=32,
        )
    )

    # Service interaction contracts ---------------------------------------
    ingest_sla = ServiceLevelAgreement(
        name="market-data.ingest",
        indicators=(
            ServiceLevelIndicator(
                name="ingest_latency",
                metric="p95_latency_ms",
                target=250.0,
                threshold_type="lte",
                description="Ingestion P95 latency must stay under 250ms.",
            ),
            ServiceLevelIndicator(
                name="ingest_success",
                metric="success_rate",
                target=0.999,
                threshold_type="gte",
                description="Successful ingestions must exceed 99.9%.",
            ),
        ),
    )

    registry.register_service(
        ServiceInteractionContract(
            name="tradepulse.service.market-data.ingest",
            operation="ingest",
            versioning=VersioningPolicy(
                scheme="semver", current="1.1.0", compatible_since="1.0.0"
            ),
            authorization=internal_service,
            retry_policy=RetryPolicy(
                max_attempts=3, initial_interval_seconds=0.5, max_interval_seconds=4.0
            ),
            sla=ingest_sla,
            observability=ObservabilityPolicy(
                span_name="service.market_data.ingest",
                metrics_namespace="service.market_data",
                default_attributes={"service": "market-data"},
            ),
            description="Ingest CSV datasets into a normalized OHLCV frame.",
            inputs={"source": "MarketDataSource"},
            outputs={"frame": "pd.DataFrame"},
        )
    )

    registry.register_service(
        ServiceInteractionContract(
            name="tradepulse.service.market-data.features",
            operation="build_features",
            versioning=VersioningPolicy(scheme="semver", current="1.0.0"),
            authorization=internal_service,
            retry_policy=RetryPolicy(max_attempts=2, initial_interval_seconds=0.25),
            sla=ingest_sla,
            observability=ObservabilityPolicy(
                span_name="service.market_data.features",
                metrics_namespace="service.market_data",
                default_attributes={"service": "market-data"},
            ),
            description="Derive feature vectors from normalized market frames.",
            inputs={"frame": "pd.DataFrame"},
            outputs={"features": "pd.DataFrame"},
        )
    )

    registry.register_service(
        ServiceInteractionContract(
            name="tradepulse.service.backtesting.run",
            operation="run_backtest",
            versioning=VersioningPolicy(scheme="semver", current="1.0.0"),
            authorization=internal_service,
            retry_policy=RetryPolicy(max_attempts=2, initial_interval_seconds=0.5),
            sla=ServiceLevelAgreement(
                name="backtesting.run",
                indicators=(
                    ServiceLevelIndicator(
                        name="backtest_success",
                        metric="success_rate",
                        target=0.99,
                        threshold_type="gte",
                    ),
                ),
            ),
            observability=ObservabilityPolicy(
                span_name="service.backtesting.run",
                metrics_namespace="service.backtesting",
                default_attributes={"service": "backtesting"},
            ),
            description="Execute the canonical ingestion → features → strategy pipeline.",
            inputs={"source": "MarketDataSource", "strategy": "Callable"},
            outputs={"run": "StrategyRun"},
        )
    )

    registry.register_service(
        ServiceInteractionContract(
            name="tradepulse.service.execution.submit",
            operation="submit",
            versioning=VersioningPolicy(
                scheme="semver", current="1.1.0", compatible_since="1.0.0"
            ),
            authorization=internal_service,
            idempotency=IdempotencyPolicy(key="idempotency_key", ttl_seconds=3600),
            retry_policy=RetryPolicy(
                max_attempts=3, initial_interval_seconds=0.5, max_interval_seconds=5.0
            ),
            sla=ServiceLevelAgreement(
                name="execution.submit",
                indicators=(
                    ServiceLevelIndicator(
                        name="execution_latency",
                        metric="p95_latency_ms",
                        target=500.0,
                        threshold_type="lte",
                        description="Order submission P95 latency must stay under 500ms.",
                    ),
                    ServiceLevelIndicator(
                        name="execution_success",
                        metric="success_rate",
                        target=0.999,
                        threshold_type="gte",
                    ),
                ),
            ),
            observability=ObservabilityPolicy(
                span_name="service.execution.submit",
                metrics_namespace="service.execution",
                default_attributes={"service": "execution"},
            ),
            description="Transform trading signals into executable orders.",
            inputs={"request": "ExecutionRequest"},
            outputs={"order": "Order"},
        )
    )

    registry.register_service(
        ServiceInteractionContract(
            name="tradepulse.service.execution.ensure_live_loop",
            operation="ensure_live_loop",
            versioning=VersioningPolicy(scheme="semver", current="1.0.0"),
            authorization=internal_service,
            retry_policy=RetryPolicy(max_attempts=3, initial_interval_seconds=0.25),
            sla=ServiceLevelAgreement(
                name="execution.ensure_live_loop",
                indicators=(
                    ServiceLevelIndicator(
                        name="loop_success",
                        metric="success_rate",
                        target=0.999,
                        threshold_type="gte",
                    ),
                ),
            ),
            observability=ObservabilityPolicy(
                span_name="service.execution.ensure_live_loop",
                metrics_namespace="service.execution",
                default_attributes={"service": "execution"},
            ),
            description="Provision the long-lived execution loop lazily.",
            inputs={},
            outputs={"loop": "LiveExecutionLoop"},
        )
    )

    return registry


__all__ = [
    "ApiContract",
    "AuthorizationScheme",
    "EventContract",
    "ExecutionRequest",
    "FeatureVectorComputedEvent",
    "IdempotencyPolicy",
    "IntegrationContractRegistry",
    "MarketDataSource",
    "MarketTickEvent",
    "ObservabilityPolicy",
    "OrderFillEvent",
    "OrderSubmittedEvent",
    "QueueContract",
    "RetryPolicy",
    "ServiceInteractionContract",
    "ServiceLevelAgreement",
    "ServiceLevelIndicator",
    "SignalGeneratedEvent",
    "StrategyCallable",
    "StrategyRun",
    "VersioningPolicy",
    "default_contract_registry",
]
