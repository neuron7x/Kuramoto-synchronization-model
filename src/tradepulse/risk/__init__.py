"""TradePulse risk management module.

This module provides risk management capabilities for trading strategies,
including position sizing, risk limits, and automated risk testing.

Example:
    >>> from tradepulse.risk import RiskManager, RiskLimits
    >>> limits = RiskLimits(max_notional=100_000, max_position=10)
    >>> manager = RiskManager(limits)
    >>> manager.validate_order("BTC-USD", "buy", 1, 50000.0)
"""

# Import RiskManager and related classes from execution.risk
from execution.risk import (
    KillSwitch,
    LimitViolation,
    OrderRateExceeded,
    RiskError,
    RiskLimits,
    RiskManager,
    portfolio_heat,
)

from .automated_testing import (
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
from .config import RiskEngineConfig, load_risk_config
from .engine import CentralRiskEngine, RiskDecision, RiskStatus
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
from .kill_switch import SafetyController, SafetyState, get_safety_controller
from .risk_core import (
    RiskConfig,
    check_risk_breach,
    compute_final_size,
    kelly_shrink,
    var_es,
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
    # Risk Engine
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
    # Core risk functions
    "var_es",
    "kelly_shrink",
    "compute_final_size",
    "check_risk_breach",
    "RiskConfig",
    # Risk Manager
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
