"""Market regime service layer.

This module provides business logic for market regime state management,
separated from the API layer for better testability and reusability.
"""

from __future__ import annotations

from datetime import datetime

from ..config import RegimeSettings
from ..errors import RegimeUpdateError
from ..modulation.regime import RegimeModulator, RegimeState


def update_market_regime(
    previous_state: RegimeState | None,
    feedback: float,
    volatility: float,
    as_of: datetime,
    settings: RegimeSettings,
) -> RegimeState:
    """Update the market regime based on feedback and volatility.
    
    This is the main entry point for regime updates. It:
    1. Validates input parameters
    2. Applies exponential smoothing to valence
    3. Computes confidence from volatility
    4. Classifies the regime label
    
    Args:
        previous_state: Previous regime state (None for initial state)
        feedback: Market feedback signal (-inf to +inf, typically -1 to 1)
        volatility: Market volatility (0 to +inf)
        as_of: Timestamp for the regime state
        settings: Regime modulation parameters
        
    Returns:
        Updated regime state
        
    Raises:
        RegimeUpdateError: If update fails
    """
    # Validate inputs
    if volatility < 0:
        raise RegimeUpdateError(
            f"Volatility must be non-negative: {volatility}",
            code="InvalidVolatility",
            details={"volatility": volatility},
        )
    
    try:
        modulator = RegimeModulator(settings)
        return modulator.update(previous_state, feedback, volatility, as_of)
    except Exception as exc:
        raise RegimeUpdateError(
            f"Regime update failed: {exc}",
            code="UpdateFailed",
        ) from exc


__all__ = [
    "update_market_regime",
]
