"""Risk estimation routines used by the cortex service."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import NormalDist
from typing import Iterable, Sequence

from ..config import RiskSettings
from ..constants import MAX_CONFIDENCE, MIN_CONFIDENCE


@dataclass(slots=True, frozen=True)
class Exposure:
    """A portfolio exposure to a single instrument.

    Attributes:
        instrument: Instrument identifier
        exposure: Position exposure value
        limit: Maximum allowed exposure for this instrument
        volatility: Expected volatility of the instrument
    """

    instrument: str
    exposure: float
    limit: float
    volatility: float


@dataclass(slots=True, frozen=True)
class RiskAssessment:
    """Container for computed risk metrics.

    Attributes:
        score: Aggregate risk score (0 to 1+)
        value_at_risk: Portfolio Value at Risk
        stressed_var: VaR under stress scenarios
        breached: Instruments that breached exposure limits
    """

    score: float
    value_at_risk: float
    stressed_var: Sequence[float]
    breached: Sequence[str]


def _confidence_scale(confidence: float) -> float:
    """Compute the normal quantile for a given confidence level.

    Args:
        confidence: Confidence level (must be between 0 and 1, exclusive)

    Returns:
        Normal distribution quantile

    Raises:
        ValueError: If confidence is outside valid range or produces non-finite quantile
    """
    if not MIN_CONFIDENCE < confidence < MAX_CONFIDENCE:
        msg = f"confidence must be between {MIN_CONFIDENCE} and {MAX_CONFIDENCE} (exclusive), got {confidence}"
        raise ValueError(msg)

    quantile = NormalDist().inv_cdf(confidence)
    if not isfinite(quantile):
        msg = f"confidence {confidence} produced a non-finite quantile"
        raise ValueError(msg)

    return quantile


def compute_risk(
    exposures: Iterable[Exposure], settings: RiskSettings
) -> RiskAssessment:
    """Compute portfolio risk score and associated metrics.

    Args:
        exposures: Portfolio exposures to assess
        settings: Risk computation settings

    Returns:
        Risk assessment with score, VaR, stressed VaR, and breached instruments
    """
    exposures = list(exposures)
    if not exposures:
        return RiskAssessment(
            score=0.0, value_at_risk=0.0, stressed_var=(), breached=()
        )

    aggregate_var = 0.0
    stress_results: list[float] = []
    breaches: list[str] = []
    max_abs = settings.max_absolute_exposure

    for exposure in exposures:
        scaled = abs(exposure.exposure) / (exposure.limit or max_abs)
        if scaled > 1.0:
            breaches.append(exposure.instrument)
        aggregate_var += abs(exposure.exposure) * exposure.volatility
        stress_results.append(abs(exposure.exposure) * exposure.volatility)

    stress_metrics = [factor * aggregate_var for factor in settings.stress_scenarios]
    confidence_scale = _confidence_scale(settings.var_confidence)
    portfolio_var = aggregate_var * confidence_scale
    risk_score = min(1.0, aggregate_var / (len(exposures) * max_abs))

    return RiskAssessment(
        score=risk_score,
        value_at_risk=portfolio_var,
        stressed_var=tuple(stress_metrics),
        breached=tuple(breaches),
    )


__all__ = ["Exposure", "RiskAssessment", "compute_risk"]
