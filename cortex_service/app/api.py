"""FastAPI application exposing the cognition microservice."""

from __future__ import annotations

import time
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Response, status
from fastapi.routing import APIRouter
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from .config import CortexSettings, load_settings
from .core.dynamics import CognitionResult, compute_cognition
from .ethics.risk import RiskAssessment, compute_risk
from .logger import configure_logging, get_logger
from .metrics import (
    COHERENCE_GAUGE,
    REGIME_UPDATES,
    REQUEST_COUNT,
    REQUEST_LATENCY,
    RISK_SCORE,
    SIGNAL_STRENGTH,
    VALENCE_GAUGE,
)
from .state import RegimeController

logger = get_logger(__name__)


class SignalsRequest(BaseModel):
    features: list[float] = Field(..., min_length=1)
    neighbors: list[list[float]] = Field(default_factory=list)


class SignalsResponse(BaseModel):
    state: float
    signal: float
    coherence: float
    valence: float


class RiskRequest(BaseModel):
    pnl_deltas: list[float] = Field(..., min_length=1)
    weights: list[float] = Field(..., min_length=1)


class RiskResponse(BaseModel):
    risk_score: float


class RegimeRequest(BaseModel):
    feedback: float = Field(..., ge=-1.0, le=1.0)


class RegimeResponse(BaseModel):
    valence: float


class HealthResponse(BaseModel):
    status: str
    valence: float


def _instrument_latency(endpoint: str, method: str, status_code: int, start: float) -> None:
    elapsed = time.perf_counter() - start
    status_label = str(status_code)
    REQUEST_LATENCY.labels(endpoint=endpoint, method=method, status=status_label).observe(elapsed)
    REQUEST_COUNT.labels(endpoint=endpoint, method=method, status=status_label).inc()


def create_app(settings: CortexSettings | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings.service.log_level)
    app = FastAPI(title=settings.service.name, version=settings.service.version, description=settings.service.description)

    controller = RegimeController(settings.regime)
    VALENCE_GAUGE.set(controller.current())

    router = APIRouter()

    @router.get("/health", response_model=HealthResponse)
    def health_check() -> HealthResponse:
        return HealthResponse(status="ok", valence=controller.current())

    @router.get(settings.service.metrics_path, include_in_schema=False)
    def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @router.post("/signals", response_model=SignalsResponse)
    def compute_signals(payload: SignalsRequest) -> SignalsResponse:
        start = time.perf_counter()
        status_code = status.HTTP_200_OK
        try:
            if any(not bundle for bundle in payload.neighbors):
                msg = "neighbor bundles cannot be empty"
                raise ValueError(msg)
            valence = controller.current()
            result: CognitionResult = compute_cognition(payload.features, payload.neighbors, valence, settings.signals)
            SIGNAL_STRENGTH.observe(result.signal)
            COHERENCE_GAUGE.set(result.coherence)
            response = SignalsResponse(**asdict(result), valence=valence)
            return response
        except ValueError as exc:
            status_code = status.HTTP_400_BAD_REQUEST
            logger.warning("Invalid signal payload: %s", exc)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        finally:
            _instrument_latency("/signals", "POST", status_code, start)

    @router.post("/risk", response_model=RiskResponse)
    def evaluate_risk(payload: RiskRequest) -> RiskResponse:
        start = time.perf_counter()
        status_code = status.HTTP_200_OK
        try:
            assessment: RiskAssessment = compute_risk(payload.pnl_deltas, payload.weights, settings.risk)
            RISK_SCORE.observe(assessment.risk_score)
            return RiskResponse(risk_score=assessment.risk_score)
        except ValueError as exc:
            status_code = status.HTTP_400_BAD_REQUEST
            logger.warning("Invalid risk payload: %s", exc)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        finally:
            _instrument_latency("/risk", "POST", status_code, start)

    @router.post("/regime", response_model=RegimeResponse)
    def update_regime(payload: RegimeRequest) -> RegimeResponse:
        start = time.perf_counter()
        valence = controller.apply_feedback(payload.feedback)
        VALENCE_GAUGE.set(valence)
        polarity = "positive" if valence >= 0 else "negative"
        REGIME_UPDATES.labels(polarity=polarity).inc()
        _instrument_latency("/regime", "POST", status.HTTP_200_OK, start)
        return RegimeResponse(valence=valence)

    app.include_router(router)
    return app


__all__ = ["create_app"]
