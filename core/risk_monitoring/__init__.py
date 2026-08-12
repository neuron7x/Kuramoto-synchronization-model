# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Risk Monitoring and Mitigation Framework for Autonomous Trading.

This module provides a comprehensive risk monitoring framework that includes:

* **Adaptive Risk Thresholds**: Dynamic thresholds that adjust based on market
  volatility, trade volume, and asset-specific behavior.
* **Stress Detection**: Real-time detection using drawdowns, volatility spikes,
  and order book imbalances.
* **Regulatory Compliance**: Support for MiFID II and Dodd-Frank with audit trails.
* **Performance Tracking**: Key metrics including Sharpe ratio, maximum drawdown,
  and volatility-adjusted returns.
* **Fail-Safe Mechanisms**: Kill-switch and trade halt capabilities.

Example:
    >>> from core.risk_monitoring import RiskMonitoringFramework
    >>> framework = RiskMonitoringFramework()
    >>> assessment = framework.assess_market_conditions(market_state)
    >>> if assessment.stress_level > StressLevel.ELEVATED:
    ...     framework.activate_safe_mode("High volatility detected")
"""

from .adaptive_thresholds import (
    AdaptiveThresholdCalibrator,
    CalibratedThresholds,
    ThresholdConfig,
)
from .advanced_risk_manager import (
    AdvancedRiskAssessment,
    AdvancedRiskConfig,
    AdvancedRiskManager,
    FreeEnergyState,
    LiquidityMetrics,
    MarketDepthData,
    RiskAuditEntry,
    RiskState,
    StressResponseProtocol,
)
from .compliance import (
    AuditTrailEntry,
    ComplianceManager,
    DoddFrankReporter,
    RegulatoryReport,
)
from .fail_safe import (
    FailSafeAction,
    FailSafeController,
    FailSafeState,
)
from .framework import (
    RiskAssessment,
    RiskMonitoringConfig,
    RiskMonitoringFramework,
)
from .performance_tracker import (
    PerformanceMetrics,
    PerformanceReport,
    PerformanceTracker,
)
from .stress_detection import (
    MarketSignals,
    StressAssessment,
    StressDetector,
    StressLevel,
)

__all__ = [
    # Adaptive thresholds
    "AdaptiveThresholdCalibrator",
    "ThresholdConfig",
    "CalibratedThresholds",
    # Stress detection
    "StressDetector",
    "StressLevel",
    "StressAssessment",
    "MarketSignals",
    # Compliance
    "ComplianceManager",
    "DoddFrankReporter",
    "AuditTrailEntry",
    "RegulatoryReport",
    # Performance tracking
    "PerformanceTracker",
    "PerformanceMetrics",
    "PerformanceReport",
    # Fail-safe
    "FailSafeController",
    "FailSafeState",
    "FailSafeAction",
    # Framework
    "RiskMonitoringFramework",
    "RiskAssessment",
    "RiskMonitoringConfig",
    # Advanced risk management
    "AdvancedRiskManager",
    "AdvancedRiskConfig",
    "AdvancedRiskAssessment",
    "RiskState",
    "StressResponseProtocol",
    "MarketDepthData",
    "LiquidityMetrics",
    "FreeEnergyState",
    "RiskAuditEntry",
]
