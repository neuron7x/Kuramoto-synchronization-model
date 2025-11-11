"""FastAPI application exposing the cortex microservice.

This module defines the HTTP API endpoints and wires up middleware,
exception handlers, and the service layer.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import asdict
from datetime import datetime

from fastapi import Depends, FastAPI, Response, status
from fastapi.routing import APIRouter
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field, ValidationError as PydanticValidationError
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import CortexSettings, load_settings
from .core.signals import FeatureObservation
from .db import Base, configure_session_factory, create_db_engine, session_dependency
from .errors import CortexError, NotFoundError
from .ethics.risk import Exposure
from .exception_handlers import (
    cortex_error_handler,
    generic_error_handler,
    sqlalchemy_error_handler,
    validation_error_handler,
)
from .logger import configure_logging, get_logger
from .metrics import (
    ERROR_COUNT,
    REGIME_TRANSITIONS,
    REGIME_UPDATES,
    REQUEST_INFLIGHT,
    REQUEST_LATENCY,
    RISK_SCORE,
    SIGNAL_DISTRIBUTION,
    SIGNAL_STRENGTH,
)
from .middleware import LoggingContextMiddleware, RateLimitMiddleware, RequestIDMiddleware
from .models import PortfolioExposure
from .services import (
    SignalEnsembleResult,
    assess_portfolio_risk,
    compute_signal_ensemble,
    fetch_latest_regime,
    fetch_portfolio_exposures,
    store_portfolio_exposures,
    store_regime_state,
    update_market_regime,
)

logger = get_logger(__name__)


class FeaturePayload(BaseModel):
    instrument: str
    name: str
    value: float
    mean: float | None = None
    std: float | None = Field(default=None, ge=0)
    weight: float = Field(default=1.0, gt=0)


class SignalsRequest(BaseModel):
    as_of: datetime
    features: list[FeaturePayload]


class SignalPayload(BaseModel):
    instrument: str
    strength: float
    contributors: tuple[str, ...]


class SignalsResponse(BaseModel):
    signals: list[SignalPayload]
    ensemble_strength: float
    synchrony: float


class ExposurePayload(BaseModel):
    portfolio_id: str
    instrument: str
    exposure: float
    leverage: float
    as_of: datetime
    limit: float = Field(default=1.0, gt=0)
    volatility: float = Field(default=0.2, ge=0)


class RiskRequest(BaseModel):
    exposures: list[ExposurePayload]


class RiskResponse(BaseModel):
    score: float
    value_at_risk: float
    stressed_var: tuple[float, ...]
    breached: tuple[str, ...]


class RegimeRequest(BaseModel):
    feedback: float
    volatility: float = Field(ge=0)
    as_of: datetime


class RegimeResponse(BaseModel):
    label: str
    valence: float
    confidence: float
    as_of: datetime


class MemoryRequest(BaseModel):
    exposures: list[ExposurePayload]


class MemoryResponse(BaseModel):
    portfolio_id: str
    exposures: list[ExposurePayload]


def _instrument_latency(endpoint: str, method: str, status_code: int, start: float) -> None:
    REQUEST_LATENCY.labels(endpoint=endpoint, method=method, status=status_code).observe(time.perf_counter() - start)


def _build_feature_observations(payload: Iterable[FeaturePayload]) -> list[FeatureObservation]:
    return [
        FeatureObservation(
            instrument=item.instrument,
            name=item.name,
            value=item.value,
            mean=item.mean,
            std=item.std,
            weight=item.weight,
        )
        for item in payload
    ]


def create_app(settings: CortexSettings | None = None, engine: Engine | None = None) -> FastAPI:
    """Create and configure the FastAPI application.
    
    Args:
        settings: Optional cortex settings (loaded from config if not provided)
        engine: Optional SQLAlchemy engine (created from settings if not provided)
        
    Returns:
        Configured FastAPI application
    """
    settings = settings or load_settings()
    configure_logging(settings.service.log_level)
    
    # Create FastAPI app with OpenAPI metadata
    app = FastAPI(
        title=settings.service.name,
        version=settings.service.version,
        description=settings.service.description,
        openapi_tags=[
            {"name": "health", "description": "Health and readiness checks"},
            {"name": "signals", "description": "Signal computation endpoints"},
            {"name": "risk", "description": "Risk assessment endpoints"},
            {"name": "regime", "description": "Market regime endpoints"},
            {"name": "memory", "description": "Persistence endpoints"},
        ],
    )
    
    # Add middleware (order matters: first added = outermost)
    app.add_middleware(RateLimitMiddleware, enabled=False)  # Placeholder for future
    app.add_middleware(LoggingContextMiddleware)
    app.add_middleware(RequestIDMiddleware)
    
    # Add exception handlers
    app.add_exception_handler(CortexError, cortex_error_handler)  # type: ignore
    app.add_exception_handler(PydanticValidationError, validation_error_handler)  # type: ignore
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_error_handler)  # type: ignore
    app.add_exception_handler(Exception, generic_error_handler)

    # Configure database
    db_engine = engine or create_db_engine(settings)
    configure_session_factory(db_engine)
    Base.metadata.create_all(db_engine)

    router = APIRouter()

    @router.get(
        "/health",
        status_code=status.HTTP_200_OK,
        tags=["health"],
        summary="Health check (liveness)",
        description="Basic health check that returns OK if the service is running. Used for liveness probes.",
    )
    def health_check() -> dict[str, str]:
        """Basic health check endpoint."""
        return {"status": "ok"}
    
    @router.get(
        "/ready",
        status_code=status.HTTP_200_OK,
        tags=["health"],
        summary="Readiness check",
        description="Readiness check that verifies database connectivity. Used for readiness probes.",
    )
    def readiness_check() -> dict[str, str]:
        """Readiness check with database connectivity test."""
        with db_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ready"}

    @router.get(settings.service.metrics_path, include_in_schema=False)
    def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @router.post(
        "/signals",
        response_model=SignalsResponse,
        tags=["signals"],
        summary="Compute signal ensemble",
        description="Compute trading signals from feature observations for multiple instruments.",
    )
    def compute_signals_endpoint(payload: SignalsRequest, session: Session = Depends(session_dependency)) -> SignalsResponse:
        """Compute signal ensemble from feature observations."""
        start = time.perf_counter()
        REQUEST_INFLIGHT.labels(endpoint="/signals", method="POST").inc()
        
        try:
            # Convert API payload to domain objects
            features = _build_feature_observations(payload.features)
            
            # Call service layer
            result: SignalEnsembleResult = compute_signal_ensemble(features, settings.signals)
            
            # Record metrics
            SIGNAL_STRENGTH.observe(result.ensemble_strength)
            for signal in result.signals:
                SIGNAL_DISTRIBUTION.labels(instrument=signal.instrument).observe(signal.strength)
            
            # Convert domain objects to API response
            signal_payloads = [SignalPayload(**asdict(signal)) for signal in result.signals]
            return SignalsResponse(
                signals=signal_payloads,
                ensemble_strength=result.ensemble_strength,
                synchrony=result.synchrony,
            )
        finally:
            REQUEST_INFLIGHT.labels(endpoint="/signals", method="POST").dec()
            _instrument_latency("/signals", "POST", status.HTTP_200_OK, start)

    @router.post(
        "/risk",
        response_model=RiskResponse,
        tags=["risk"],
        summary="Assess portfolio risk",
        description="Compute risk metrics including VaR, stressed scenarios, and limit breaches.",
    )
    def evaluate_risk_endpoint(payload: RiskRequest) -> RiskResponse:
        """Assess portfolio risk from exposures."""
        start = time.perf_counter()
        REQUEST_INFLIGHT.labels(endpoint="/risk", method="POST").inc()
        
        try:
            # Convert API payload to domain objects
            exposures = [
                Exposure(
                    instrument=item.instrument,
                    exposure=item.exposure,
                    limit=item.limit,
                    volatility=item.volatility,
                )
                for item in payload.exposures
            ]
            
            # Call service layer
            assessment = assess_portfolio_risk(exposures, settings.risk)
            
            # Record metrics
            RISK_SCORE.observe(assessment.score)
            
            # Convert domain objects to API response
            return RiskResponse(
                score=assessment.score,
                value_at_risk=assessment.value_at_risk,
                stressed_var=assessment.stressed_var,
                breached=assessment.breached,
            )
        finally:
            REQUEST_INFLIGHT.labels(endpoint="/risk", method="POST").dec()
            _instrument_latency("/risk", "POST", status.HTTP_200_OK, start)

    @router.post(
        "/regime",
        response_model=RegimeResponse,
        tags=["regime"],
        summary="Update market regime",
        description="Update the market regime state based on feedback and volatility.",
    )
    def update_regime_endpoint(payload: RegimeRequest, session: Session = Depends(session_dependency)) -> RegimeResponse:
        """Update market regime state."""
        start = time.perf_counter()
        REQUEST_INFLIGHT.labels(endpoint="/regime", method="POST").inc()
        
        try:
            # Fetch previous state
            previous_state = fetch_latest_regime(session)
            
            # Call service layer
            updated_state = update_market_regime(
                previous_state,
                payload.feedback,
                payload.volatility,
                payload.as_of,
                settings.regime,
            )
            
            # Store updated state
            store_regime_state(session, updated_state)
            
            # Record metrics
            REGIME_UPDATES.labels(regime=updated_state.label).inc()
            if previous_state and previous_state.label != updated_state.label:
                REGIME_TRANSITIONS.labels(
                    from_regime=previous_state.label,
                    to_regime=updated_state.label,
                ).inc()
            
            # Convert domain objects to API response
            return RegimeResponse(**asdict(updated_state))
        finally:
            REQUEST_INFLIGHT.labels(endpoint="/regime", method="POST").dec()
            _instrument_latency("/regime", "POST", status.HTTP_200_OK, start)

    @router.post(
        "/memory",
        response_model=None,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["memory"],
        summary="Store portfolio exposures",
        description="Persist portfolio exposures for later retrieval.",
    )
    def persist_memory_endpoint(payload: MemoryRequest, session: Session = Depends(session_dependency)) -> None:
        """Store portfolio exposures."""
        start = time.perf_counter()
        REQUEST_INFLIGHT.labels(endpoint="/memory", method="POST").inc()
        
        try:
            # Convert API payload to domain objects
            exposures = [
                PortfolioExposure(
                    portfolio_id=item.portfolio_id,
                    instrument=item.instrument,
                    exposure=item.exposure,
                    leverage=item.leverage,
                    as_of=item.as_of,
                )
                for item in payload.exposures
            ]
            
            # Call service layer
            store_portfolio_exposures(session, exposures)
        finally:
            REQUEST_INFLIGHT.labels(endpoint="/memory", method="POST").dec()
            _instrument_latency("/memory", "POST", status.HTTP_202_ACCEPTED, start)

    @router.get(
        "/memory/{portfolio_id}",
        response_model=MemoryResponse,
        tags=["memory"],
        summary="Fetch portfolio exposures",
        description="Retrieve stored portfolio exposures by portfolio ID.",
    )
    def fetch_memory_endpoint(portfolio_id: str, session: Session = Depends(session_dependency)) -> MemoryResponse:
        """Fetch portfolio exposures."""
        start = time.perf_counter()
        REQUEST_INFLIGHT.labels(endpoint="/memory/{portfolio_id}", method="GET").inc()
        
        try:
            # Call service layer (raises NotFoundError if not found)
            exposures = fetch_portfolio_exposures(session, portfolio_id)
            
            # Convert domain objects to API response
            return MemoryResponse(
                portfolio_id=portfolio_id,
                exposures=[
                    ExposurePayload(
                        portfolio_id=item.portfolio_id,
                        instrument=item.instrument,
                        exposure=item.exposure,
                        leverage=item.leverage,
                        as_of=item.as_of,
                    )
                    for item in exposures
                ],
            )
        finally:
            REQUEST_INFLIGHT.labels(endpoint="/memory/{portfolio_id}", method="GET").dec()
            _instrument_latency("/memory/{portfolio_id}", "GET", status.HTTP_200_OK, start)

    app.include_router(router)
    return app


__all__ = ["create_app"]
