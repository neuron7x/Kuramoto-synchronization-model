"""Risk assessment service layer.

This module provides business logic for portfolio risk computation,
separated from the API layer for better testability and reusability.
"""

from __future__ import annotations

from typing import Sequence

from ..config import RiskSettings
from ..errors import RiskComputationError
from ..ethics.risk import Exposure, RiskAssessment, compute_risk


def assess_portfolio_risk(
    exposures: Sequence[Exposure],
    settings: RiskSettings,
) -> RiskAssessment:
    """Assess risk for a portfolio of exposures.
    
    This is the main entry point for risk assessment. It:
    1. Validates exposure data
    2. Computes Value-at-Risk (VaR)
    3. Applies stress scenarios
    4. Identifies limit breaches
    
    Args:
        exposures: List of portfolio exposures
        settings: Risk assessment parameters
        
    Returns:
        Risk assessment with score, VaR, and stressed scenarios
        
    Raises:
        RiskComputationError: If assessment fails
    """
    if not exposures:
        # Empty portfolio has zero risk
        return RiskAssessment(
            score=0.0,
            value_at_risk=0.0,
            stressed_var=(),
            breached=(),
        )
    
    # Validate exposure data
    for exposure in exposures:
        if exposure.limit <= 0:
            raise RiskComputationError(
                f"Invalid exposure limit for {exposure.instrument}: {exposure.limit}",
                code="InvalidExposureLimit",
                details={"instrument": exposure.instrument, "limit": exposure.limit},
            )
        if exposure.volatility < 0:
            raise RiskComputationError(
                f"Invalid volatility for {exposure.instrument}: {exposure.volatility}",
                code="InvalidVolatility",
                details={"instrument": exposure.instrument, "volatility": exposure.volatility},
            )
    
    try:
        return compute_risk(exposures, settings)
    except ValueError as exc:
        raise RiskComputationError(
            f"Risk computation failed: {exc}",
            code="ComputationFailed",
        ) from exc


__all__ = [
    "assess_portfolio_risk",
]
