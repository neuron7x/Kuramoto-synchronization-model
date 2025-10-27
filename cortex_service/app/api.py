"""FastAPI application exposing the cortex microservice."""

from __future__ import annotations

import time
from collections.abc import Iterable
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.routing import APIRouter
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .config import CortexSettings, load_settings
from dataclasses import asdict

from .core.signals import FeatureObservation, Signal, build_signal_ensemble
from .db import Base, configure_session_factory, create_db_engine, session_dependency
from .ethics.risk import Exposure, RiskAssessment, compute_risk
from .logger import configure_logging, get_logger
from .memory.repository import MemoryRepository
from .metrics import REGIME_UPDATES, REQUEST_LATENCY, RISK_SCORE, SIGNAL_STRENGTH
from .models import PortfolioExposure
from .modulation.regime import RegimeModulator, RegimeState
from .sync.ensemble import aggregate_strength, kuramoto_order_parameter

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
    settings = settings or load_settings()
    configure_logging(settings.service.log_level)
    app = FastAPI(title=settings.service.name, version=settings.service.version, description=settings.service.description)

    db_engine = engine or create_db_engine(settings)
    configure_session_factory(db_engine)
    Base.metadata.create_all(db_engine)

    router = APIRouter()

    @router.get("/health", status_code=status.HTTP_200_OK)
    def health_check() -> dict[str, str]:
        with db_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok"}

    @router.get(settings.service.metrics_path, include_in_schema=False)
    def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @router.post("/signals", response_model=SignalsResponse)
    def compute_signals(payload: SignalsRequest, session: Session = Depends(session_dependency)) -> SignalsResponse:
        start = time.perf_counter()
        try:
            features = _build_feature_observations(payload.features)
            raw_signals = build_signal_ensemble(features, settings.signals)
            ensemble_strength = aggregate_strength(raw_signals)
            synchrony = kuramoto_order_parameter(raw_signals)
            for signal in raw_signals:
                SIGNAL_STRENGTH.observe(signal.strength)
            payload = [SignalPayload(**asdict(signal)) for signal in raw_signals]
            return SignalsResponse(signals=payload, ensemble_strength=ensemble_strength, synchrony=synchrony)
        finally:
            _instrument_latency("/signals", "POST", status.HTTP_200_OK, start)

    @router.post("/risk", response_model=RiskResponse)
    def evaluate_risk(payload: RiskRequest) -> RiskResponse:
        start = time.perf_counter()
        exposures = [
            Exposure(instrument=item.instrument, exposure=item.exposure, limit=item.limit, volatility=item.volatility)
            for item in payload.exposures
        ]
        assessment: RiskAssessment = compute_risk(exposures, settings.risk)
        RISK_SCORE.observe(assessment.score)
        _instrument_latency("/risk", "POST", status.HTTP_200_OK, start)
        return RiskResponse(
            score=assessment.score,
            value_at_risk=assessment.value_at_risk,
            stressed_var=assessment.stressed_var,
            breached=assessment.breached,
        )

    @router.post("/regime", response_model=RegimeResponse)
    def update_regime(payload: RegimeRequest, session: Session = Depends(session_dependency)) -> RegimeResponse:
        start = time.perf_counter()
        repository = MemoryRepository(session)
        modulator = RegimeModulator(settings.regime)
        previous = repository.latest_regime()
        previous_state = (
            RegimeState(label=previous.label, valence=previous.valence, confidence=previous.confidence, as_of=previous.as_of)
            if previous
            else None
        )
        updated_state = modulator.update(previous_state, payload.feedback, payload.volatility, payload.as_of)
        repository.store_regime(updated_state.label, updated_state.valence, updated_state.confidence, updated_state.as_of)
        REGIME_UPDATES.labels(regime=updated_state.label).inc()
        _instrument_latency("/regime", "POST", status.HTTP_200_OK, start)
        return RegimeResponse(**asdict(updated_state))

    @router.post("/memory", response_model=None, status_code=status.HTTP_202_ACCEPTED)
    def persist_memory(payload: MemoryRequest, session: Session = Depends(session_dependency)) -> None:
        start = time.perf_counter()
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
        _instrument_latency("/memory", "POST", status.HTTP_202_ACCEPTED, start)

    @router.get("/memory/{portfolio_id}", response_model=MemoryResponse)
    def fetch_memory(portfolio_id: str, session: Session = Depends(session_dependency)) -> MemoryResponse:
        start = time.perf_counter()
        repository = MemoryRepository(session)
        exposures = repository.fetch_exposures(portfolio_id)
        if not exposures:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="portfolio not found")
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
        _instrument_latency("/memory/{portfolio_id}", "GET", status.HTTP_200_OK, start)
        return response

    app.include_router(router)
    return app


__all__ = ["create_app"]
