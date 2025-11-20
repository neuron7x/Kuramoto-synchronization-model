# Copyright (c) 2025 TradePulse
# SPDX-License-Identifier: Apache-2.0
"""Neural modules for TradePulse."""

__all__ = [
    "GABAInhibitionGate",
    "GateParams",
    "GateState",
    "GateMetrics",
    "AdaptiveRiskManager",
    "MarketRegimeAnalyzer",
    "DynamicPositionSizer",
    "AgentCoordinator",
]

# Import GABA gate if torch is available
try:
    from modules.gaba_inhibition_gate import (
        GABAInhibitionGate,
        GateMetrics,
        GateParams,
        GateState,
    )
except ImportError:
    # Torch not available, skip GABA module
    pass

# Import new modules (no torch dependency)
from modules.adaptive_risk_manager import AdaptiveRiskManager
from modules.agent_coordinator import AgentCoordinator
from modules.dynamic_position_sizer import DynamicPositionSizer
from modules.market_regime_analyzer import MarketRegimeAnalyzer
