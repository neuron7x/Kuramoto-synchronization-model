# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""
Autonomous Automation Framework

This module provides autonomous automation capabilities for the 7 critical
system components of TradePulse. All automation runs without human intervention,
self-healing, and adapts to changing conditions.
"""

from __future__ import annotations

from .config_automation import ConfigAutomation
from .data_pipeline_automation import DataPipelineAutomation
from .infrastructure_automation import InfrastructureAutomation
from .monitoring_automation import MonitoringAutomation
from .orchestrator import AutomationOrchestrator
from .security_automation import SecurityAutomation
from .strategy_automation import StrategyAutomation
from .testing_automation import TestingAutomation

__all__ = [
    "ConfigAutomation",
    "DataPipelineAutomation",
    "StrategyAutomation",
    "MonitoringAutomation",
    "SecurityAutomation",
    "InfrastructureAutomation",
    "TestingAutomation",
    "AutomationOrchestrator",
]

__version__ = "2.0.0"
