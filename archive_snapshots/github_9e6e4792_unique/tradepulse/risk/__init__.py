# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""TradePulse central risk engine and safety controls.

This module provides the authoritative risk-management layer for TradePulse,
implementing:
- Unified environment modes (BACKTEST, PAPER, LIVE)
- Central risk engine with configurable limits
- Kill-switch and safe-mode mechanisms
- Structured logging and metrics for risk decisions

For backward compatibility, this module also re-exports legacy risk management
classes from execution.risk and automated testing utilities from
src.tradepulse.risk.
"""

# Legacy API re-exports for backward compatibility
from execution.risk import (
    KillSwitch,
    LimitViolation,
    OrderRateExceeded,
    RiskError,
    RiskLimits,
    RiskManager,
    portfolio_heat,
)

# Automated testing utilities
from src.tradepulse.risk.automated_testing import (
    AutomatedRiskTester,
    MonteCarloConfig,
    RiskScenario,
    ScenarioType,
    StressTestResult,
    generate_flash_crash_scenarios,
    generate_liquidity_crisis_scenarios,
    generate_market_stress_scenarios,
    validate_risk_metrics,
)

from .config import (
    RiskEngineConfig,
    load_risk_config,
)
from .engine import (
    CentralRiskEngine,
    RiskDecision,
    RiskStatus,
)
from .environment import (
    EnvironmentConfig,
    EnvironmentError,
    EnvironmentMode,
    get_current_mode,
    is_live_trading_allowed,
    require_mode,
    set_current_mode,
    validate_environment,
)
from .kill_switch import (
    SafetyController,
    SafetyState,
    get_safety_controller,
)

__all__ = [
    # Environment
    "EnvironmentMode",
    "EnvironmentConfig",
    "EnvironmentError",
    "validate_environment",
    "get_current_mode",
    "set_current_mode",
    "require_mode",
    "is_live_trading_allowed",
    # Risk Engine (new API)
    "CentralRiskEngine",
    "RiskDecision",
    "RiskStatus",
    # Safety
    "SafetyState",
    "SafetyController",
    "get_safety_controller",
    # Configuration
    "RiskEngineConfig",
    "load_risk_config",
    # Legacy API (backward compatibility)
    "RiskManager",
    "RiskLimits",
    "RiskError",
    "LimitViolation",
    "OrderRateExceeded",
    "KillSwitch",
    "portfolio_heat",
    # Automated testing
    "AutomatedRiskTester",
    "RiskScenario",
    "ScenarioType",
    "StressTestResult",
    "MonteCarloConfig",
    "generate_market_stress_scenarios",
    "generate_liquidity_crisis_scenarios",
    "generate_flash_crash_scenarios",
    "validate_risk_metrics",
]
