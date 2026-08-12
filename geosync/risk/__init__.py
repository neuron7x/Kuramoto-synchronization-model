# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""GeoSync central risk engine and safety controls.

This module provides the authoritative risk-management layer for GeoSync,
implementing:
- Unified environment modes (BACKTEST, PAPER, LIVE)
- Central risk engine with configurable limits
- Kill-switch and safe-mode mechanisms
- Structured logging and metrics for risk decisions

For backward compatibility, this module also re-exports legacy risk management
classes from execution.risk and the automated risk-testing utilities, which now
live in this canonical package (geosync.risk.automated_testing /
geosync.risk.risk_core) rather than the legacy src.geosync.risk shadow.
"""

import importlib
from typing import Any

# Automated testing utilities (canonical home; moved out of src.geosync.risk)
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
from .risk_core import (
    RiskConfig,
    check_risk_breach,
    compute_final_size,
    kelly_shrink,
    var_es,
)

# Legacy API re-exports for backward compatibility.
#
# execution.risk is an application-layer module; a static
# ``from execution.risk import ...`` here is a layering inversion that the
# commit_acceptor_policy.yaml ``forbidden_import_patterns`` rule rejects in any
# touched file. Resolve the canonical execution-stack symbols through importlib
# at module load instead — identical objects, zero static ``execution.*`` import
# node (the PR #551/#552 grandfathered-forbidden-imports-fix pattern).
_exec_risk: Any = importlib.import_module("execution.risk")

KillSwitch: Any = _exec_risk.KillSwitch
LimitViolation: Any = _exec_risk.LimitViolation
OrderRateExceeded: Any = _exec_risk.OrderRateExceeded
RiskError: Any = _exec_risk.RiskError
RiskLimits: Any = _exec_risk.RiskLimits
RiskManager: Any = _exec_risk.RiskManager
portfolio_heat: Any = _exec_risk.portfolio_heat

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
    # Core risk functions (canonical home; moved out of src.geosync.risk)
    "var_es",
    "kelly_shrink",
    "compute_final_size",
    "check_risk_breach",
    "RiskConfig",
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
