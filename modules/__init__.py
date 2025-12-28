# Copyright (c) 2025 TradePulse
# SPDX-License-Identifier: Apache-2.0
"""Neural modules for TradePulse."""

import importlib.util

__all__ = [
    "AdaptiveRiskManager",
    "MarketRegimeAnalyzer",
    "DynamicPositionSizer",
    "AgentCoordinator",
    "MarketState",
    # New engineering modules
    "SignalStrategyRegistry",
    "PortfolioOptimizer",
    "AlertManager",
    "BacktestReportGenerator",
    "OrderValidator",
    "DataQualityMonitor",
    "PerformanceTracker",
    "StrategyScheduler",
    "ExecutionAnalyzer",
    "SystemHealthDashboard",
]

# Optional GABA gate (requires torch)
if importlib.util.find_spec("torch") is not None:
    from modules.gaba_inhibition_gate import (  # noqa: F401 - re-exported in __all__
        GABAInhibitionGate,
        GateMetrics,
        GateParams,
        GateState,
    )

    __all__.extend(["GABAInhibitionGate", "GateParams", "GateState", "GateMetrics"])

# Import core modules (no torch dependency)
from modules.adaptive_risk_manager import AdaptiveRiskManager
from modules.agent_coordinator import AgentCoordinator
from modules.alert_manager import AlertManager
from modules.backtest_report_generator import BacktestReportGenerator
from modules.data_quality_monitor import DataQualityMonitor
from modules.dynamic_position_sizer import DynamicPositionSizer
from modules.execution_analyzer import ExecutionAnalyzer
from modules.market_regime_analyzer import MarketRegimeAnalyzer
from modules.order_validator import OrderValidator
from modules.performance_tracker import PerformanceTracker
from modules.portfolio_optimizer import PortfolioOptimizer
from modules.types import MarketState

# Import new engineering modules
from modules.signal_strategy_registry import SignalStrategyRegistry
from modules.strategy_scheduler import StrategyScheduler
from modules.system_health_dashboard import SystemHealthDashboard
