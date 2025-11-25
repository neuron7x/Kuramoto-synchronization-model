# Copyright (c) 2025 TradePulse
# SPDX-License-Identifier: Apache-2.0
"""Neural modules for TradePulse."""

import importlib.util

__all__ = [
    "AdaptiveRiskManager",
    "MarketRegimeAnalyzer",
    "DynamicPositionSizer",
    "AgentCoordinator",
]

# Optional GABA gate (requires torch)
if importlib.util.find_spec("torch") is not None:
    from modules.gaba_inhibition_gate import (
        GABAInhibitionGate,
        GateParams,
        GateState,
        GateMetrics,
    )

    __all__.extend(["GABAInhibitionGate", "GateParams", "GateState", "GateMetrics"])

# Import new modules (no torch dependency)
from modules.adaptive_risk_manager import AdaptiveRiskManager
from modules.market_regime_analyzer import MarketRegimeAnalyzer
from modules.dynamic_position_sizer import DynamicPositionSizer
from modules.agent_coordinator import AgentCoordinator
