"""Shared configuration structures for TradePulse modules."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
import json
from pathlib import Path
from typing import Any, Dict, Optional, Type, TypeVar

T = TypeVar("T")


def _build_config(config_type: Type[T], raw: Optional[Dict[str, Any]]) -> T:
    if not raw:
        return config_type()
    allowed = {item.name for item in fields(config_type)}
    filtered = {key: value for key, value in raw.items() if key in allowed}
    return config_type(**filtered)


@dataclass
class AdaptiveRiskManagerConfig:
    """Configuration for AdaptiveRiskManager initialization."""

    risk_tolerance: float = 0.02
    var_window: int = 252
    volatility_window: int = 20
    enable_tacl_integration: bool = True


@dataclass
class MarketRegimeAnalyzerConfig:
    """Configuration for MarketRegimeAnalyzer initialization."""

    regime_window: int = 100
    transition_threshold: float = 0.7
    min_regime_duration: int = 10


@dataclass
class ExecutionAnalyzerConfig:
    """Configuration for ExecutionAnalyzer initialization."""

    slippage_threshold_bps: float = 10.0
    latency_threshold_ms: float = 100.0


@dataclass
class AlertManagerConfig:
    """Configuration for AlertManager initialization."""

    deduplication_window_seconds: int = 300
    max_history_size: int = 10000
    enable_aggregation: bool = True


@dataclass
class SystemHealthDashboardConfig:
    """Configuration for SystemHealthDashboard initialization."""

    check_interval_seconds: float = 30.0
    unhealthy_threshold_errors: int = 3
    degraded_threshold_latency_ms: float = 500.0


@dataclass
class ModulesConfig:
    """Bundled configuration for key TradePulse modules."""

    adaptive_risk_manager: AdaptiveRiskManagerConfig = field(
        default_factory=AdaptiveRiskManagerConfig
    )
    market_regime_analyzer: MarketRegimeAnalyzerConfig = field(
        default_factory=MarketRegimeAnalyzerConfig
    )
    execution_analyzer: ExecutionAnalyzerConfig = field(
        default_factory=ExecutionAnalyzerConfig
    )
    alert_manager: AlertManagerConfig = field(default_factory=AlertManagerConfig)
    system_health_dashboard: SystemHealthDashboardConfig = field(
        default_factory=SystemHealthDashboardConfig
    )


def modules_config_from_dict(raw: Dict[str, Any]) -> ModulesConfig:
    """Build ModulesConfig from a dict structure."""
    return ModulesConfig(
        adaptive_risk_manager=_build_config(
            AdaptiveRiskManagerConfig, raw.get("adaptive_risk_manager")
        ),
        market_regime_analyzer=_build_config(
            MarketRegimeAnalyzerConfig, raw.get("market_regime_analyzer")
        ),
        execution_analyzer=_build_config(
            ExecutionAnalyzerConfig, raw.get("execution_analyzer")
        ),
        alert_manager=_build_config(AlertManagerConfig, raw.get("alert_manager")),
        system_health_dashboard=_build_config(
            SystemHealthDashboardConfig, raw.get("system_health_dashboard")
        ),
    )


def load_modules_config(path: str | Path) -> ModulesConfig:
    """Load module configuration from a JSON file."""
    config_path = Path(path)
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Config JSON must be an object at the top level")
    return modules_config_from_dict(raw)
