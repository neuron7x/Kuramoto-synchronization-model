"""TradePulse risk management module."""

from .risk_core import (
    RiskConfig,
    check_risk_breach,
    compute_final_size,
    kelly_shrink,
    var_es,
)

__all__ = [
    "var_es",
    "kelly_shrink",
    "compute_final_size",
    "check_risk_breach",
    "RiskConfig",
]
