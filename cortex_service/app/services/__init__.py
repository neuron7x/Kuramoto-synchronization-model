"""Service layer modules for business logic.

This package contains service layer functions that implement
business logic separate from the API and persistence layers.
"""

from __future__ import annotations

from .memory_service import (
    fetch_latest_regime,
    fetch_portfolio_exposures,
    store_portfolio_exposures,
    store_regime_state,
)
from .regime_service import update_market_regime
from .risk_service import assess_portfolio_risk
from .signal_service import SignalEnsembleResult, compute_signal_ensemble

__all__ = [
    "SignalEnsembleResult",
    "assess_portfolio_risk",
    "compute_signal_ensemble",
    "fetch_latest_regime",
    "fetch_portfolio_exposures",
    "store_portfolio_exposures",
    "store_regime_state",
    "update_market_regime",
]
