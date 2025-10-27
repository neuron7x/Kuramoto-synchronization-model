"""Market regime modulation algorithms."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..config import RegimeSettings


@dataclass(slots=True)
class RegimeState:
    """The inferred state of the market regime."""

    label: str
    valence: float
    confidence: float
    as_of: datetime


class RegimeModulator:
    """Applies feedback to update the prevailing market regime."""

    def __init__(self, settings: RegimeSettings):
        self._settings = settings

    def update(self, previous: RegimeState | None, feedback: float, volatility: float, as_of: datetime) -> RegimeState:
        decay = self._settings.decay
        if previous is None:
            seed_valence = feedback
        else:
            seed_valence = (1 - decay) * previous.valence + decay * feedback
        bounded_valence = max(self._settings.min_valence, min(self._settings.max_valence, seed_valence))
        confidence = max(self._settings.confidence_floor, 1.0 - volatility)
        label = self._classify(bounded_valence, confidence)
        return RegimeState(label=label, valence=bounded_valence, confidence=confidence, as_of=as_of)

    def _classify(self, valence: float, confidence: float) -> str:
        if confidence < 0.25:
            return "indeterminate"
        if valence >= 0.5:
            return "bullish"
        if valence <= -0.5:
            return "bearish"
        return "neutral"


__all__ = ["RegimeModulator", "RegimeState"]
