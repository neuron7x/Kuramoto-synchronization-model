"""TradePulse risk management module."""

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
