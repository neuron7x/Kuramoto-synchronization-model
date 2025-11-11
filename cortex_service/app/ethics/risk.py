"""Risk estimation routines used by the cortex service.

This module provides portfolio risk assessment including:
- Value-at-Risk (VaR) computation
- Stress scenario analysis
- Exposure limit breach detection
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import NormalDist
from typing import Iterable, Sequence

from ..config import RiskSettings
from ..errors import RiskComputationError


@dataclass(frozen=True, slots=True)
class Exposure:
    """A portfolio exposure to a single instrument.
    
    Immutable representation of position exposure.
    
    Attributes:
        instrument: Instrument identifier
        exposure: Position size (positive or negative)
        limit: Maximum allowed absolute exposure
        volatility: Instrument volatility estimate
    """

    instrument: str
    exposure: float
    limit: float
    volatility: float


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    """Container for computed risk metrics.
    
    Immutable result of risk assessment.
    
    Attributes:
        score: Normalized risk score (0 to 1+)
        value_at_risk: Portfolio VaR at configured confidence
        stressed_var: Tuple of VaR under stress scenarios
        breached: Tuple of instruments exceeding limits
    """

    score: float
    value_at_risk: float
    stressed_var: Sequence[float]
    breached: Sequence[str]


def _confidence_scale(confidence: float) -> float:
    """Return the normal quantile associated with the provided confidence.
    
    Computes the inverse CDF (quantile) of the standard normal distribution
    for the given confidence level. Used for VaR computation.
    
    Args:
        confidence: Confidence level (must be between 0 and 1, exclusive)
        
    Returns:
        Normal distribution quantile
        
    Raises:
        RiskComputationError: If confidence is invalid
    """
    if not 0.0 < confidence < 1.0:
        raise RiskComputationError(
            f"confidence must be between 0 and 1 (exclusive): {confidence}",
            code="InvalidConfidence",
            details={"confidence": confidence},
        )

    quantile = NormalDist().inv_cdf(confidence)
    if not isfinite(quantile):
        raise RiskComputationError(
            f"confidence produced a non-finite quantile: {confidence}",
            code="NonFiniteQuantile",
            details={"confidence": confidence, "quantile": quantile},
        )

    return quantile


def compute_risk(exposures: Iterable[Exposure], settings: RiskSettings) -> RiskAssessment:
    """Compute a bounded risk score and associated metrics.
    
    This function:
    1. Aggregates exposure-weighted volatility (linear VaR approximation)
    2. Identifies instruments exceeding limits
    3. Applies normal distribution quantile for confidence level
    4. Computes stressed VaR for each stress scenario
    5. Normalizes risk score to [0, 1]
    
    Args:
        exposures: Iterable of portfolio exposures
        settings: Risk assessment parameters
        
    Returns:
        Risk assessment with score, VaR, stressed scenarios, and breaches
        
    Raises:
        RiskComputationError: If computation fails
    """
    exposures = list(exposures)
    if not exposures:
        return RiskAssessment(score=0.0, value_at_risk=0.0, stressed_var=(), breached=())

    aggregate_var = 0.0
    stress_results: list[float] = []
    breaches: list[str] = []
    max_abs = settings.max_absolute_exposure
    
    # Single pass through exposures (O(n) complexity)
    for exposure in exposures:
        # Check for limit breaches
        scaled = abs(exposure.exposure) / (exposure.limit or max_abs)
        if scaled > 1.0:
            breaches.append(exposure.instrument)
        
        # Aggregate VaR (linear approximation)
        exposure_var = abs(exposure.exposure) * exposure.volatility
        aggregate_var += exposure_var
        stress_results.append(exposure_var)

    # Apply stress scenarios
    stress_metrics = [factor * aggregate_var for factor in settings.stress_scenarios]
    
    # Compute portfolio VaR with confidence level
    confidence_scale = _confidence_scale(settings.var_confidence)
    portfolio_var = aggregate_var * confidence_scale
    
    # Normalize risk score to [0, 1] range
    risk_score = min(1.0, aggregate_var / (len(exposures) * max_abs))
    
    return RiskAssessment(
        score=risk_score,
        value_at_risk=portfolio_var,
        stressed_var=tuple(stress_metrics),
        breached=tuple(breaches),
    )


__all__ = ["Exposure", "RiskAssessment", "compute_risk"]
