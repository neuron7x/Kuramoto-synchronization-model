"""Risk management utilities with advanced controls."""

from __future__ import annotations

from .advanced import (  # noqa: F401 - re-exported in __all__
    AdvancedRiskController,
    CorrelationLimitGuard,
    DrawdownBreaker,
    KellyCriterionPositionSizer,
    LiquidationCascadePreventer,
    MarginMonitor,
    RiskMetricsCalculator,
    RiskParityAllocator,
    TimeWeightedExposureTracker,
    VolatilityAdjustedSizer,
)
from .core import *  # noqa: F401,F403 - re-export legacy API
from .core import __all__ as _core_all

__all__ = sorted(
    set(_core_all)
    | {
        "AdvancedRiskController",
        "CorrelationLimitGuard",
        "DrawdownBreaker",
        "KellyCriterionPositionSizer",
        "LiquidationCascadePreventer",
        "MarginMonitor",
        "RiskMetricsCalculator",
        "RiskParityAllocator",
        "TimeWeightedExposureTracker",
        "VolatilityAdjustedSizer",
    }
)
