"""FastAPI application exposing the cortex microservice."""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import asdict

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRouter
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import CortexSettings, load_settings
from .core.signals import FeatureObservation
from .db import Base, configure_session_factory, create_db_engine, session_dependency
from .errors import CortexError, NotFoundError, ValidationError
from .ethics.risk import Exposure
from .logger import configure_logging, get_logger
from .memory.repository import MemoryRepository
from .metrics import ERROR_COUNT, REQUEST_INFLIGHT, REQUEST_LATENCY
from .middleware import RequestIDMiddleware, get_request_id
from .models import PortfolioExposure
from .schemas import (
    ErrorDetail,
    ErrorResponse,
    ExposurePayload,
    FeaturePayload,
    HealthResponse,
    MemoryRequest,
    MemoryResponse,
    ReadinessResponse,
    RegimeRequest,
    RegimeResponse,
    RiskRequest,
    RiskResponse,
    SignalPayload,
    SignalsRequest,
    SignalsResponse,
)
from .services.regime_service import RegimeService
from .services.risk_service import RiskService
from .services.signal_service import SignalService

logger = get_logger(__name__)


def _create_error_response(request_id: str, error: CortexError) -> ErrorResponse:
    """Create a standardized error response.

    Args:
        request_id: Request ID for tracing
        error: The error that occurred

    Returns:
        Standardized error response
    """
    details = None
    if error.details:
        details = [
            ErrorDetail(field=k, message=str(v)) for k, v in error.details.items()
        ]

    return ErrorResponse(
        error=error.code,
        message=error.message,
        request_id=request_id,
        details=details,
    )


def _instrument_latency(
    endpoint: str, method: str, status_code: int, start: float
) -> None:
    """Record request latency metrics.

    Args:
        endpoint: API endpoint path
        method: HTTP method
        status_code: HTTP status code
        start: Start time (from time.perf_counter())
    """
    REQUEST_LATENCY.labels(
        endpoint=endpoint, method=method, status=status_code
    ).observe(time.perf_counter() - start)


def _build_feature_observations(
    payload: Iterable[FeaturePayload],
) -> list[FeatureObservation]:
    """Convert API payload to domain models.

    Args:
        payload: Feature payloads from API request

    Returns:
        List of feature observations
    """

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


def create_app(
    settings: CortexSettings | None = None, engine: Engine | None = None
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        settings: Optional cortex settings (loads from config if None)
        engine: Optional SQLAlchemy engine (creates if None)

    Returns:
        Configured FastAPI application
    """
    settings = settings or load_settings()
    configure_logging(settings.service.log_level)

    app = FastAPI(
        title=settings.service.name,
        version=settings.service.version,
        description=settings.service.description,
        responses={
            400: {"model": ErrorResponse, "description": "Bad Request"},
            404: {"model": ErrorResponse, "description": "Not Found"},
            422: {"model": ErrorResponse, "description": "Validation Error"},
            500: {"model": ErrorResponse, "description": "Internal Server Error"},
        },
    )

    db_engine = engine or create_db_engine(settings)
    configure_session_factory(db_engine)
    Base.metadata.create_all(db_engine)

    # Add middleware
    app.add_middleware(RequestIDMiddleware)

    # Create service instances
    signal_service = SignalService(settings.signals)
    risk_service = RiskService(settings.risk)
    regime_service = RegimeService(settings.regime)

    # Exception handlers
    @app.exception_handler(CortexError)
    async def cortex_error_handler(request: Request, exc: CortexError) -> Response:
        """Handle CortexError exceptions."""
        ERROR_COUNT.labels(code=exc.code).inc()
        error_response = _create_error_response(get_request_id(), exc)
        return Response(
            content=error_response.model_dump_json(),
            status_code=exc.status_code,
            media_type="application/json",
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> Response:
        """Handle Pydantic validation errors."""
        ERROR_COUNT.labels(code="VALIDATION_ERROR").inc()
        error = ValidationError(
            "Request validation failed", details={"errors": str(exc.errors())}
        )
        error_response = _create_error_response(get_request_id(), error)
        return Response(
            content=error_response.model_dump_json(),
            status_code=error.status_code,
            media_type="application/json",
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(
        request: Request, exc: SQLAlchemyError
    ) -> Response:
        """Handle SQLAlchemy errors."""
        ERROR_COUNT.labels(code="DATABASE_ERROR").inc()
        from .errors import DatabaseError

        error = DatabaseError(f"Database operation failed: {exc}")
        error_response = _create_error_response(get_request_id(), error)
        return Response(
            content=error_response.model_dump_json(),
            status_code=error.status_code,
            media_type="application/json",
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> Response:
        """Handle unexpected exceptions."""
        ERROR_COUNT.labels(code="INTERNAL_ERROR").inc()
        logger.error("Unexpected error", exc_info=True)
        error = CortexError(
            message="An unexpected error occurred",
            code="INTERNAL_ERROR",
            status_code=500,
        )
        error_response = _create_error_response(get_request_id(), error)
        return Response(
            content=error_response.model_dump_json(),
            status_code=500,
            media_type="application/json",
        )

    router = APIRouter()

    @router.get(
        "/health",
        status_code=status.HTTP_200_OK,
        response_model=HealthResponse,
        tags=["Health"],
        summary="Health check endpoint",
    )
    def health_check() -> HealthResponse:
        """Check if the service is healthy and can connect to the database."""
        with db_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return HealthResponse(status="ok")

    @router.get(
        "/ready",
        status_code=status.HTTP_200_OK,
        response_model=ReadinessResponse,
        tags=["Health"],
        summary="Readiness check endpoint",
    )
    def readiness_check() -> ReadinessResponse:
        """Check if the service is ready to accept traffic."""
        checks = {}
        try:
            with db_engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            checks["database"] = True
        except Exception:
            checks["database"] = False

        ready = all(checks.values())
        return ReadinessResponse(ready=ready, checks=checks)

    @router.get(settings.service.metrics_path, include_in_schema=False)
    def metrics() -> Response:
        """Expose Prometheus metrics."""
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @router.post(
        "/signals",
        response_model=SignalsResponse,
        status_code=status.HTTP_200_OK,
        tags=["Signals"],
        summary="Compute signals from features",
    )
    def compute_signals(payload: SignalsRequest) -> SignalsResponse:
        """Compute trading signals from feature observations.

        Processes feature observations grouped by instrument and returns
        computed signals with ensemble metrics.
        """
        endpoint = "/signals"
        REQUEST_INFLIGHT.labels(endpoint=endpoint).inc()
        start = time.perf_counter()
        try:
            features = [
                FeatureObservation(
                    instrument=item.instrument,
                    name=item.name,
                    value=item.value,
                    mean=item.mean,
                    std=item.std,
                    weight=item.weight,
                )
                for item in payload.features
            ]

            signals, ensemble_strength, synchrony = signal_service.compute_signals(
                features
            )

            signal_payloads = [SignalPayload(**asdict(signal)) for signal in signals]
            return SignalsResponse(
                signals=signal_payloads,
                ensemble_strength=ensemble_strength,
                synchrony=synchrony,
            )
        finally:
            REQUEST_INFLIGHT.labels(endpoint=endpoint).dec()
            _instrument_latency(endpoint, "POST", status.HTTP_200_OK, start)

    @router.post(
        "/risk",
        response_model=RiskResponse,
        status_code=status.HTTP_200_OK,
        tags=["Risk"],
        summary="Assess portfolio risk",
    )
    def evaluate_risk(payload: RiskRequest) -> RiskResponse:
        """Assess portfolio risk from exposures.

        Computes risk metrics including VaR, stressed VaR, and exposure breaches.
        """
        endpoint = "/risk"
        REQUEST_INFLIGHT.labels(endpoint=endpoint).inc()
        start = time.perf_counter()
        try:
            exposures = [
                Exposure(
                    instrument=item.instrument,
                    exposure=item.exposure,
                    limit=item.limit,
                    volatility=item.volatility,
                )
                for item in payload.exposures
            ]
            assessment = risk_service.assess_risk(exposures)
            return RiskResponse(
                score=assessment.score,
                value_at_risk=assessment.value_at_risk,
                stressed_var=assessment.stressed_var,
                breached=assessment.breached,
            )
        finally:
            REQUEST_INFLIGHT.labels(endpoint=endpoint).dec()
            _instrument_latency(endpoint, "POST", status.HTTP_200_OK, start)

    @router.post(
        "/regime",
        response_model=RegimeResponse,
        status_code=status.HTTP_200_OK,
        tags=["Regime"],
        summary="Update market regime",
    )
    def update_regime(
        payload: RegimeRequest, session: Session = Depends(session_dependency)
    ) -> RegimeResponse:
        """Update the market regime based on feedback and volatility.

        Uses exponential decay to blend historical state with new feedback.
        """
        endpoint = "/regime"
        REQUEST_INFLIGHT.labels(endpoint=endpoint).inc()
        start = time.perf_counter()
        try:
            updated_state = regime_service.update_regime(
                session, payload.feedback, payload.volatility, payload.as_of
            )
            return RegimeResponse(**asdict(updated_state))
        finally:
            REQUEST_INFLIGHT.labels(endpoint=endpoint).dec()
            _instrument_latency(endpoint, "POST", status.HTTP_200_OK, start)

    @router.post(
        "/memory",
        response_model=None,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["Memory"],
        summary="Persist portfolio exposures",
    )
    def persist_memory(
        payload: MemoryRequest, session: Session = Depends(session_dependency)
    ) -> None:
        """Persist portfolio exposures to memory.

        Stores or updates exposures for later retrieval.
        """
        endpoint = "/memory"
        REQUEST_INFLIGHT.labels(endpoint=endpoint).inc()
        start = time.perf_counter()
        try:
            repository = MemoryRepository(session)
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
            repository.store_exposures(exposures)
        finally:
            REQUEST_INFLIGHT.labels(endpoint=endpoint).dec()
            _instrument_latency(endpoint, "POST", status.HTTP_202_ACCEPTED, start)

    @router.get(
        "/memory/{portfolio_id}",
        response_model=MemoryResponse,
        status_code=status.HTTP_200_OK,
        tags=["Memory"],
        summary="Fetch portfolio exposures",
    )
    def fetch_memory(
        portfolio_id: str, session: Session = Depends(session_dependency)
    ) -> MemoryResponse:
        """Retrieve stored portfolio exposures.

        Args:
            portfolio_id: Portfolio identifier to fetch

        Returns:
            Portfolio exposures

        Raises:
            NotFoundError: If portfolio not found
        """
        endpoint = "/memory/{portfolio_id}"
        REQUEST_INFLIGHT.labels(endpoint=endpoint).inc()
        start = time.perf_counter()
        try:
            repository = MemoryRepository(session)
            exposures = repository.fetch_exposures(portfolio_id)
            if not exposures:
                raise NotFoundError(f"Portfolio '{portfolio_id}' not found")

            response = MemoryResponse(
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
            return response
        finally:
            REQUEST_INFLIGHT.labels(endpoint=endpoint).dec()
            _instrument_latency(endpoint, "GET", status.HTTP_200_OK, start)

    app.include_router(router)
    return app


__all__ = ["create_app"]
