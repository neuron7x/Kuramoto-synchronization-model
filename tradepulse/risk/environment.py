# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unified environment mode definitions and validation.

This module introduces a single source of truth for environment modes
(BACKTEST, PAPER, LIVE) and provides utilities for mode validation,
configuration requirements, and mode-specific guardrails.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import Callable, ParamSpec, TypeVar

__all__ = [
    "EnvironmentMode",
    "EnvironmentConfig",
    "validate_environment",
    "get_current_mode",
    "set_current_mode",
    "require_mode",
    "is_live_trading_allowed",
    "EnvironmentError",
]


class EnvironmentError(RuntimeError):
    """Raised when environment validation fails or mode constraints are violated."""


class EnvironmentMode(str, Enum):
    """Enumerate the supported execution environment modes.

    Attributes:
        BACKTEST: Historical simulation mode. No external connections, no real orders.
        PAPER: Simulated trading with real market data but fake executions.
        LIVE: Real trading mode with actual order execution.
    """

    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"

    @classmethod
    def from_string(cls, value: str) -> "EnvironmentMode":
        """Parse a string into an EnvironmentMode.

        Args:
            value: Case-insensitive mode string.

        Returns:
            The corresponding EnvironmentMode.

        Raises:
            ValueError: If the value is not a valid mode.
        """
        normalized = value.lower().strip()
        for mode in cls:
            if mode.value == normalized:
                return mode
        valid_modes = ", ".join(m.value for m in cls)
        raise ValueError(
            f"Invalid environment mode '{value}'. Valid modes: {valid_modes}"
        )


@dataclass(slots=True, frozen=True)
class EnvironmentConfig:
    """Configuration requirements and constraints for an environment mode.

    Attributes:
        mode: The environment mode.
        require_api_keys: Whether API keys are required (LIVE mode).
        require_risk_engine: Whether risk engine must be enabled.
        allow_real_orders: Whether real orders can be submitted.
        enforce_kill_switch: Whether kill-switch checks are mandatory.
        max_position_multiplier: Multiplier applied to position limits.
    """

    mode: EnvironmentMode
    require_api_keys: bool = False
    require_risk_engine: bool = False
    allow_real_orders: bool = False
    enforce_kill_switch: bool = False
    max_position_multiplier: float = 1.0

    @classmethod
    def for_mode(cls, mode: EnvironmentMode) -> "EnvironmentConfig":
        """Create the default configuration for a given mode.

        Args:
            mode: The environment mode.

        Returns:
            EnvironmentConfig with appropriate defaults for the mode.
        """
        if mode == EnvironmentMode.BACKTEST:
            return cls(
                mode=mode,
                require_api_keys=False,
                require_risk_engine=False,
                allow_real_orders=False,
                enforce_kill_switch=False,
                max_position_multiplier=1.0,
            )
        elif mode == EnvironmentMode.PAPER:
            return cls(
                mode=mode,
                require_api_keys=False,
                require_risk_engine=True,
                allow_real_orders=False,
                enforce_kill_switch=True,
                max_position_multiplier=1.0,
            )
        else:  # LIVE
            return cls(
                mode=mode,
                require_api_keys=True,
                require_risk_engine=True,
                allow_real_orders=True,
                enforce_kill_switch=True,
                max_position_multiplier=1.0,
            )


# Thread-safe global mode state
_mode_lock = threading.Lock()
_current_mode: EnvironmentMode | None = None


def get_current_mode() -> EnvironmentMode:
    """Get the current environment mode.

    Returns:
        The current EnvironmentMode. Defaults to BACKTEST if not set.
    """
    global _current_mode
    with _mode_lock:
        if _current_mode is None:
            # Check environment variable first
            env_mode = os.environ.get("TRADEPULSE_ENV_MODE")
            if env_mode:
                _current_mode = EnvironmentMode.from_string(env_mode)
            else:
                _current_mode = EnvironmentMode.BACKTEST
        return _current_mode


def set_current_mode(mode: EnvironmentMode | str) -> EnvironmentMode:
    """Set the current environment mode.

    Args:
        mode: The mode to set (EnvironmentMode or string).

    Returns:
        The new EnvironmentMode.

    Raises:
        ValueError: If the mode string is invalid.
    """
    global _current_mode
    if isinstance(mode, str):
        mode = EnvironmentMode.from_string(mode)
    with _mode_lock:
        _current_mode = mode
        return _current_mode


def validate_environment(
    mode: EnvironmentMode,
    *,
    api_keys_present: bool = False,
    risk_engine_enabled: bool = False,
) -> tuple[bool, list[str]]:
    """Validate that environment requirements are met for a given mode.

    Args:
        mode: The target environment mode.
        api_keys_present: Whether API keys are configured.
        risk_engine_enabled: Whether the risk engine is active.

    Returns:
        Tuple of (is_valid, list of error messages).
    """
    config = EnvironmentConfig.for_mode(mode)
    errors: list[str] = []

    if config.require_api_keys and not api_keys_present:
        errors.append(f"{mode.value.upper()} mode requires API keys to be configured")

    if config.require_risk_engine and not risk_engine_enabled:
        errors.append(
            f"{mode.value.upper()} mode requires the risk engine to be enabled"
        )

    return len(errors) == 0, errors


def is_live_trading_allowed() -> bool:
    """Check if live trading is currently allowed.

    Returns:
        True if current mode permits real order execution.
    """
    mode = get_current_mode()
    config = EnvironmentConfig.for_mode(mode)
    return config.allow_real_orders


P = ParamSpec("P")
T = TypeVar("T")


def require_mode(
    *allowed_modes: EnvironmentMode,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator that restricts function execution to specific environment modes.

    Args:
        *allowed_modes: The modes in which the function is allowed to execute.

    Returns:
        A decorator that enforces the mode restriction.

    Raises:
        EnvironmentError: If called in a disallowed mode.

    Example:
        @require_mode(EnvironmentMode.LIVE, EnvironmentMode.PAPER)
        def submit_order(order):
            ...
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            current = get_current_mode()
            if current not in allowed_modes:
                allowed_str = ", ".join(m.value for m in allowed_modes)
                raise EnvironmentError(
                    f"Function '{func.__name__}' is only allowed in modes: "
                    f"{allowed_str}. Current mode: {current.value}"
                )
            return func(*args, **kwargs)

        return wrapper

    return decorator
