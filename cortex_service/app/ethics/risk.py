"""Risk estimation routines used by the cortex service."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from ..config import RiskSettings


@dataclass(slots=True)
class RiskAssessment:
    """Container for computed risk metrics."""

    risk_score: float


def _validate_inputs(pnl_deltas: Sequence[float], weights: Sequence[float]) -> None:
    if len(pnl_deltas) != len(weights):
        msg = "pnl_deltas and weights must have the same length"
        raise ValueError(msg)
    if not pnl_deltas:
        msg = "pnl_deltas cannot be empty"
        raise ValueError(msg)


def compute_risk(pnl_deltas: Sequence[float], weights: Sequence[float], settings: RiskSettings) -> RiskAssessment:
    """Compute a bounded risk score from PnL deltas and weights."""

    _validate_inputs(pnl_deltas, weights)
    total_weight = sum(weights)
    if not math.isfinite(total_weight) or total_weight == 0:
        msg = "weights must sum to a non-zero finite value"
        raise ValueError(msg)

    normalized_weights = [weight / total_weight for weight in weights]
    mean_delta = sum(delta * weight for delta, weight in zip(pnl_deltas, normalized_weights))
    amplified = -settings.penalty_gain * mean_delta
    risk_score = math.tanh(amplified)
    return RiskAssessment(risk_score=risk_score)


__all__ = ["RiskAssessment", "compute_risk"]
