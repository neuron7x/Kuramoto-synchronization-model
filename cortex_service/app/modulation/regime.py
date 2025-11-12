"""Market regime modulation algorithms."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..config import RegimeSettings
from ..constants import (
    REGIME_CONFIDENCE_THRESHOLD_INDETERMINATE,
    REGIME_VALENCE_THRESHOLD_BEARISH,
    REGIME_VALENCE_THRESHOLD_BULLISH,
)


@dataclass(slots=True, frozen=True)
class RegimeState:
    """The inferred state of the market regime.

    Attributes:
        label: Regime classification (bullish, bearish, neutral, indeterminate)
        valence: Numerical valence score
        confidence: Confidence in the regime classification
        as_of: Timestamp of this regime state
    """

    label: str
    valence: float
    confidence: float
    as_of: datetime


class RegimeModulator:
    """Applies feedback to update the prevailing market regime.

    Uses exponential decay to blend historical regime state with new feedback.
    """

    def __init__(self, settings: RegimeSettings) -> None:
        """Initialize the regime modulator.

        Args:
            settings: Regime modulation parameters
        """
        self._settings = settings

    def update(
        self,
        previous: RegimeState | None,
        feedback: float,
        volatility: float,
        as_of: datetime,
    ) -> RegimeState:
        """Update the regime based on feedback and volatility.

        Args:
            previous: Previous regime state (None if first update)
            feedback: Feedback signal value
            volatility: Current market volatility
            as_of: Timestamp for this update

        Returns:
            Updated regime state
        """
        decay = self._settings.decay
        if previous is None:
            seed_valence = feedback
        else:
            seed_valence = (1 - decay) * previous.valence + decay * feedback

        bounded_valence = max(
            self._settings.min_valence,
            min(self._settings.max_valence, seed_valence),
        )
        confidence = max(self._settings.confidence_floor, 1.0 - volatility)
        label = self._classify(bounded_valence, confidence)

        return RegimeState(
            label=label,
            valence=bounded_valence,
            confidence=confidence,
            as_of=as_of,
        )

    def _classify(self, valence: float, confidence: float) -> str:
        """Classify regime based on valence and confidence.

        Args:
            valence: Valence score
            confidence: Confidence level

        Returns:
            Regime label: bullish, bearish, neutral, or indeterminate
        """
        if confidence < REGIME_CONFIDENCE_THRESHOLD_INDETERMINATE:
            return "indeterminate"
        if valence >= REGIME_VALENCE_THRESHOLD_BULLISH:
            return "bullish"
        if valence <= REGIME_VALENCE_THRESHOLD_BEARISH:
            return "bearish"
        return "neutral"


__all__ = ["RegimeModulator", "RegimeState"]
