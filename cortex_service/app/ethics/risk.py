"""Risk estimation routines used by the cortex service."""

from __future__ import annotations

from dataclasses import dataclass
from math import erf, sqrt
from typing import Iterable, Sequence

from ..config import RiskSettings


@dataclass(slots=True)
class Exposure:
    """A portfolio exposure to a single instrument."""

    instrument: str
    exposure: float
    limit: float
    volatility: float


@dataclass(slots=True)
class RiskAssessment:
    """Container for computed risk metrics."""

    score: float
    value_at_risk: float
    stressed_var: Sequence[float]
    breached: Sequence[str]


def _confidence_scale(confidence: float) -> float:
    return sqrt(2) * erf(confidence)


def compute_risk(exposures: Iterable[Exposure], settings: RiskSettings) -> RiskAssessment:
    """Compute a bounded risk score and associated metrics."""

    exposures = list(exposures)
    if not exposures:
        return RiskAssessment(score=0.0, value_at_risk=0.0, stressed_var=(), breached=())

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
    return RiskAssessment(score=risk_score, value_at_risk=portfolio_var, stressed_var=tuple(stress_metrics), breached=tuple(breaches))


__all__ = ["Exposure", "RiskAssessment", "compute_risk"]
