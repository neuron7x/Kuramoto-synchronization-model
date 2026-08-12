# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Risk engine configuration models and loaders.

This module defines the configuration schema for the central risk engine,
supporting YAML/JSON configuration files and environment variable overrides.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

__all__ = [
    "RiskEngineConfig",
    "SymbolLimits",
    "load_risk_config",
    "DEFAULT_RISK_CONFIG",
]


@dataclass(slots=True)
class SymbolLimits:
    """Per-symbol risk limits.

    Attributes:
        max_position_size: Maximum position size in units for this symbol.
        max_notional: Maximum notional exposure for this symbol.
        max_leverage: Maximum leverage allowed for this symbol.
    """

    max_position_size: float = float("inf")
    max_notional: float = float("inf")
    max_leverage: float = 10.0

    def __post_init__(self) -> None:
        if self.max_position_size < 0:
            raise ValueError("max_position_size must be non-negative")
        if self.max_notional < 0:
            raise ValueError("max_notional must be non-negative")
        if self.max_leverage <= 0:
            raise ValueError("max_leverage must be positive")


@dataclass(slots=True)
class RiskEngineConfig:
    """Configuration for the central risk engine.

    Attributes:
        max_position_size_default: Default max position size per symbol.
        max_notional_per_order: Maximum notional value per single order.
        max_daily_loss: Maximum allowed daily loss (absolute value).
        max_daily_loss_percent: Maximum allowed daily loss (percentage of equity).
        max_total_exposure: Maximum total portfolio exposure.
        max_leverage: Maximum leverage allowed.
        max_orders_per_minute: Rate limit on order submissions.
        max_orders_per_hour: Hourly rate limit on order submissions.
        symbol_limits: Per-symbol limit overrides.
        kill_switch_loss_threshold: Loss threshold that triggers kill-switch.
        kill_switch_loss_streak: Number of consecutive losses triggering kill-switch.
        safe_mode_position_multiplier: Position multiplier in safe mode (<1).
        enable_risk_checks: Global toggle for risk checks.
    """

    # Position limits
    max_position_size_default: float = float("inf")
    max_notional_per_order: float = float("inf")

    # Loss limits
    max_daily_loss: float = float("inf")
    max_daily_loss_percent: float = 1.0  # 100% = no limit

    # Exposure limits
    max_total_exposure: float = float("inf")
    max_leverage: float = 10.0

    # Rate limits
    max_orders_per_minute: int = 60
    max_orders_per_hour: int = 1000

    # Per-symbol overrides
    symbol_limits: dict[str, SymbolLimits] = field(default_factory=dict)

    # Kill-switch thresholds
    kill_switch_loss_threshold: float = float("inf")
    kill_switch_loss_streak: int = 10

    # Safe-mode settings
    safe_mode_position_multiplier: float = 0.5

    # Global toggle
    enable_risk_checks: bool = True

    def __post_init__(self) -> None:
        # Validate and clamp max_daily_loss_percent to valid range
        if self.max_daily_loss_percent <= 0:
            raise ValueError("max_daily_loss_percent must be positive")
        self.max_daily_loss_percent = min(1.0, self.max_daily_loss_percent)

        if self.max_orders_per_minute < 0:
            self.max_orders_per_minute = 0
        if self.max_orders_per_hour < 0:
            self.max_orders_per_hour = 0
        if self.safe_mode_position_multiplier < 0:
            self.safe_mode_position_multiplier = 0.0
        if self.safe_mode_position_multiplier > 1.0:
            self.safe_mode_position_multiplier = 1.0

    def get_symbol_limits(self, symbol: str) -> SymbolLimits:
        """Get limits for a specific symbol, falling back to defaults.

        Args:
            symbol: The trading symbol.

        Returns:
            SymbolLimits for the symbol.
        """
        if symbol in self.symbol_limits:
            return self.symbol_limits[symbol]
        return SymbolLimits(
            max_position_size=self.max_position_size_default,
            max_notional=self.max_notional_per_order,
            max_leverage=self.max_leverage,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RiskEngineConfig":
        """Create a RiskEngineConfig from a dictionary.

        Args:
            data: Configuration dictionary.

        Returns:
            RiskEngineConfig instance.
        """
        symbol_limits_raw = data.get("symbol_limits", {})
        symbol_limits: dict[str, SymbolLimits] = {}
        for symbol, limits in symbol_limits_raw.items():
            if isinstance(limits, dict):
                symbol_limits[symbol] = SymbolLimits(**limits)
            elif isinstance(limits, SymbolLimits):
                symbol_limits[symbol] = limits

        return cls(
            max_position_size_default=float(data.get("max_position_size_default", float("inf"))),
            max_notional_per_order=float(data.get("max_notional_per_order", float("inf"))),
            max_daily_loss=float(data.get("max_daily_loss", float("inf"))),
            max_daily_loss_percent=float(data.get("max_daily_loss_percent", 1.0)),
            max_total_exposure=float(data.get("max_total_exposure", float("inf"))),
            max_leverage=float(data.get("max_leverage", 10.0)),
            max_orders_per_minute=int(data.get("max_orders_per_minute", 60)),
            max_orders_per_hour=int(data.get("max_orders_per_hour", 1000)),
            symbol_limits=symbol_limits,
            kill_switch_loss_threshold=float(data.get("kill_switch_loss_threshold", float("inf"))),
            kill_switch_loss_streak=int(data.get("kill_switch_loss_streak", 10)),
            safe_mode_position_multiplier=float(data.get("safe_mode_position_multiplier", 0.5)),
            enable_risk_checks=bool(data.get("enable_risk_checks", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to a dictionary representation.

        Returns:
            Dictionary representation of the config.
        """
        symbol_limits_dict = {}
        for symbol, limits in self.symbol_limits.items():
            symbol_limits_dict[symbol] = {
                "max_position_size": limits.max_position_size,
                "max_notional": limits.max_notional,
                "max_leverage": limits.max_leverage,
            }

        return {
            "max_position_size_default": self.max_position_size_default,
            "max_notional_per_order": self.max_notional_per_order,
            "max_daily_loss": self.max_daily_loss,
            "max_daily_loss_percent": self.max_daily_loss_percent,
            "max_total_exposure": self.max_total_exposure,
            "max_leverage": self.max_leverage,
            "max_orders_per_minute": self.max_orders_per_minute,
            "max_orders_per_hour": self.max_orders_per_hour,
            "symbol_limits": symbol_limits_dict,
            "kill_switch_loss_threshold": self.kill_switch_loss_threshold,
            "kill_switch_loss_streak": self.kill_switch_loss_streak,
            "safe_mode_position_multiplier": self.safe_mode_position_multiplier,
            "enable_risk_checks": self.enable_risk_checks,
        }


# Default configuration
DEFAULT_RISK_CONFIG = RiskEngineConfig(
    max_position_size_default=100.0,
    max_notional_per_order=100000.0,
    max_daily_loss=10000.0,
    max_daily_loss_percent=0.05,  # 5%
    max_total_exposure=500000.0,
    max_leverage=5.0,
    max_orders_per_minute=60,
    max_orders_per_hour=500,
    kill_switch_loss_threshold=25000.0,
    kill_switch_loss_streak=5,
    safe_mode_position_multiplier=0.25,
    enable_risk_checks=True,
)


def load_risk_config(
    path: Path | str | None = None,
    *,
    env_prefix: str = "GEOSYNC_RISK_",
) -> RiskEngineConfig:
    """Load risk configuration from file and/or environment variables.

    Args:
        path: Path to YAML or JSON configuration file.
        env_prefix: Prefix for environment variable overrides.

    Returns:
        RiskEngineConfig instance.

    Raises:
        FileNotFoundError: If the specified path does not exist.
        ValueError: If the configuration is invalid.
    """
    data: dict[str, Any] = {}

    # Load from file if provided
    if path is not None:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Risk configuration file not found: {path}")

        content = path.read_text(encoding="utf-8")
        if path.suffix in {".yaml", ".yml"}:
            data = yaml.safe_load(content) or {}
        elif path.suffix == ".json":
            data = json.loads(content)
        else:
            # Try YAML first, then JSON
            try:
                data = yaml.safe_load(content) or {}
            except yaml.YAMLError:
                data = json.loads(content)

    # Apply environment variable overrides
    env_overrides = _load_env_overrides(env_prefix)
    data.update(env_overrides)

    if not data:
        return DEFAULT_RISK_CONFIG

    return RiskEngineConfig.from_dict(data)


def _load_env_overrides(prefix: str) -> dict[str, Any]:
    """Load configuration overrides from environment variables.

    Args:
        prefix: Environment variable prefix.

    Returns:
        Dictionary of overrides.
    """
    overrides: dict[str, Any] = {}

    mapping = {
        "MAX_POSITION_SIZE_DEFAULT": ("max_position_size_default", float),
        "MAX_NOTIONAL_PER_ORDER": ("max_notional_per_order", float),
        "MAX_DAILY_LOSS": ("max_daily_loss", float),
        "MAX_DAILY_LOSS_PERCENT": ("max_daily_loss_percent", float),
        "MAX_TOTAL_EXPOSURE": ("max_total_exposure", float),
        "MAX_LEVERAGE": ("max_leverage", float),
        "MAX_ORDERS_PER_MINUTE": ("max_orders_per_minute", int),
        "MAX_ORDERS_PER_HOUR": ("max_orders_per_hour", int),
        "KILL_SWITCH_LOSS_THRESHOLD": ("kill_switch_loss_threshold", float),
        "KILL_SWITCH_LOSS_STREAK": ("kill_switch_loss_streak", int),
        "SAFE_MODE_POSITION_MULTIPLIER": ("safe_mode_position_multiplier", float),
        "ENABLE_RISK_CHECKS": ("enable_risk_checks", _parse_bool),
    }

    for env_suffix, (config_key, converter) in mapping.items():
        env_var = f"{prefix}{env_suffix}"
        value = os.environ.get(env_var)
        if value is not None:
            try:
                overrides[config_key] = converter(value)
            except (ValueError, TypeError):
                pass  # Skip invalid values

    return overrides


def _parse_bool(value: str) -> bool:
    """Parse a string as a boolean.

    Args:
        value: String to parse.

    Returns:
        Boolean value.
    """
    return value.lower() in {"true", "1", "yes", "on"}
