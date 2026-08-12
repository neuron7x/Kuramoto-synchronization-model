# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""FastAPI application for MLSDM HTTP API.

This module provides a REST API for interacting with MLSDM components
remotely. It exposes endpoints for biomarker computation, decision making,
and simulation management.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, List

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel, Field
except ImportError as e:
    msg = "FastAPI and pydantic are required for the API. Install with: pip install fastapi pydantic uvicorn"
    raise ImportError(msg) from e

from ..facade import MLSDM

logger = logging.getLogger(__name__)

# Global MLSDM instance (initialized on startup)
mlsdm_instance: MLSDM | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifespan (startup and shutdown)."""
    global mlsdm_instance
    # Startup
    logger.info("Starting MLSDM API")
    mlsdm_instance = MLSDM.default()
    logger.info("MLSDM API started successfully")
    yield
    # Shutdown
    logger.info("Shutting down MLSDM API")


# Create FastAPI app with lifespan
app = FastAPI(
    title="MLSDM API",
    description="Multi-Level Stochastic Decision Model HTTP API",
    version="0.1.0",
    lifespan=lifespan,
)


class BiomarkerRequest(BaseModel):
    """Request model for biomarker computation."""

    exp_return: float = Field(..., description="Expected return signal")
    novelty: float = Field(..., description="Novelty/surprise signal")
    load: float = Field(..., description="Cognitive/computational load")
    maxdd: float = Field(..., description="Maximum drawdown")
    volshock: float = Field(..., description="Volatility shock indicator")
    cp_score: float = Field(..., description="Change-point detection score")


class BiomarkerResponse(BaseModel):
    """Response model for biomarker state."""

    orexin: float = Field(..., description="Orexin (arousal) level")
    threat: float = Field(..., description="Threat level")
    state: str = Field(..., description="FHMC state (WAKE/SLEEP)")
    alpha_history: List[float] = Field(default_factory=list, description="DFA alpha history")
    slope_history: List[float] = Field(default_factory=list, description="Slope history")


class DecisionResponse(BaseModel):
    """Response model for decision state."""

    free_energy: float = Field(..., description="Free energy estimate")
    baseline_free_energy: float = Field(..., description="Baseline free energy")
    latency_spike: float = Field(..., description="Latency spike factor")
    steps_in_crisis: int = Field(..., description="Number of steps in crisis mode")
    window_seconds: float = Field(..., description="Adaptive time window in seconds")


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str = Field(..., description="Service status")
    version: str = Field(..., description="API version")


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint.

    Returns:
        Health status and version information.
    """
    return HealthResponse(status="healthy", version="0.1.0")


@app.post("/biomarkers", response_model=BiomarkerResponse)
async def compute_biomarkers(request: BiomarkerRequest) -> BiomarkerResponse:
    """Compute biomarkers from market conditions.

    Args:
        request: Biomarker computation parameters.

    Returns:
        Computed biomarker state.

    Raises:
        HTTPException: If MLSDM is not initialized.
    """
    if mlsdm_instance is None:
        raise HTTPException(status_code=500, detail="MLSDM not initialized")

    biomarkers = mlsdm_instance.compute_drive(
        exp_return=request.exp_return,
        novelty=request.novelty,
        load=request.load,
        maxdd=request.maxdd,
        volshock=request.volshock,
        cp_score=request.cp_score,
    )

    return BiomarkerResponse(
        orexin=biomarkers.orexin,
        threat=biomarkers.threat,
        state=biomarkers.state,
        alpha_history=list(biomarkers.alpha_history),
        slope_history=list(biomarkers.slope_history),
    )


@app.get("/decision", response_model=DecisionResponse)
async def get_decision_state() -> DecisionResponse:
    """Get current decision state.

    Returns:
        Current decision state with adaptive parameters.

    Raises:
        HTTPException: If MLSDM is not initialized.
    """
    if mlsdm_instance is None:
        raise HTTPException(status_code=500, detail="MLSDM not initialized")

    decision = mlsdm_instance.get_decision_state()

    return DecisionResponse(
        free_energy=decision.free_energy,
        baseline_free_energy=decision.baseline_free_energy,
        latency_spike=decision.latency_spike,
        steps_in_crisis=decision.steps_in_crisis,
        window_seconds=decision.window_seconds,
    )


@app.get("/biomarkers", response_model=BiomarkerResponse)
async def get_biomarkers() -> BiomarkerResponse:
    """Get current biomarker state.

    Returns:
        Current biomarker state.

    Raises:
        HTTPException: If MLSDM is not initialized.
    """
    if mlsdm_instance is None:
        raise HTTPException(status_code=500, detail="MLSDM not initialized")

    biomarkers = mlsdm_instance.get_biomarkers()

    return BiomarkerResponse(
        orexin=biomarkers.orexin,
        threat=biomarkers.threat,
        state=biomarkers.state,
        alpha_history=list(biomarkers.alpha_history),
        slope_history=list(biomarkers.slope_history),
    )
