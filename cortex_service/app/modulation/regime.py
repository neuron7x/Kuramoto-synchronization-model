"""Market regime modulation algorithms.

This module implements market regime classification and state evolution
using exponential smoothing and volatility-based confidence scoring.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..config import RegimeSettings

# Classification thresholds (configurable in future iterations)
CONFIDENCE_THRESHOLD_INDETERMINATE = 0.25
VALENCE_THRESHOLD_BULLISH = 0.5
VALENCE_THRESHOLD_BEARISH = -0.5


@dataclass(frozen=True, slots=True)
class RegimeState:
    """The inferred state of the market regime.
    
    Immutable representation of market regime at a point in time.
    
    Attributes:
        label: Classification label (bullish, bearish, neutral, indeterminate)
        valence: Numeric sentiment score (typically -1 to 1)
        confidence: Confidence in the classification (0 to 1)
        as_of: Timestamp for this regime state
    """

    label: str
    valence: float
    confidence: float
    as_of: datetime


class RegimeModulator:
    """Applies feedback to update the prevailing market regime.
    
    Uses exponential smoothing to evolve regime valence and
    volatility-based confidence scoring.
    
    Attributes:
        _settings: Regime modulation parameters
    """

    def __init__(self, settings: RegimeSettings):
        """Initialize the modulator with settings.
        
        Args:
            settings: Regime modulation parameters
        """
        self._settings = settings

    def update(self, previous: RegimeState | None, feedback: float, volatility: float, as_of: datetime) -> RegimeState:
        """Update the regime state with new feedback and volatility.
        
        Applies exponential smoothing to valence:
        - If no previous state: valence = feedback
        - Otherwise: valence = (1-decay)*prev_valence + decay*feedback
        
        Confidence is computed as max(confidence_floor, 1 - volatility).
        
        Args:
            previous: Previous regime state (None for initial state)
            feedback: Market feedback signal
            volatility: Current market volatility
            as_of: Timestamp for the new state
            
        Returns:
            Updated regime state with classification
        """
        decay = self._settings.decay
        if previous is None:
            seed_valence = feedback
        else:
            seed_valence = (1 - decay) * previous.valence + decay * feedback
        
        # Clamp valence to configured bounds
        bounded_valence = max(self._settings.min_valence, min(self._settings.max_valence, seed_valence))
        
        # Compute confidence from inverse volatility
        confidence = max(self._settings.confidence_floor, 1.0 - volatility)
        
        # Classify regime based on valence and confidence
        label = self._classify(bounded_valence, confidence)
        
        return RegimeState(label=label, valence=bounded_valence, confidence=confidence, as_of=as_of)

    def _classify(self, valence: float, confidence: float) -> str:
        """Classify regime based on valence and confidence.
        
        Classification rules:
        - confidence < 0.25: indeterminate
        - valence >= 0.5: bullish
        - valence <= -0.5: bearish
        - otherwise: neutral
        
        Args:
            valence: Regime valence value
            confidence: Confidence level
            
        Returns:
            Regime label string
        """
        if confidence < CONFIDENCE_THRESHOLD_INDETERMINATE:
            return "indeterminate"
        if valence >= VALENCE_THRESHOLD_BULLISH:
            return "bullish"
        if valence <= VALENCE_THRESHOLD_BEARISH:
            return "bearish"
        return "neutral"


__all__ = ["RegimeModulator", "RegimeState"]
