# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Numerical invariants and safety checks for dopamine module."""

from __future__ import annotations

import math
from typing import Any, Dict


def assert_no_nan_inf(*values: float, context: Dict[str, Any] | None = None) -> None:
    """Assert that all provided values are finite (not NaN or ±Inf).

    Args:
        *values: Numeric values to check
        context: Optional context dict for error reporting

    Raises:
        RuntimeError: If any value is NaN or infinite, with context dump
    """
    for i, val in enumerate(values):
        if not math.isfinite(val):
            ctx_str = ""
            if context:
                ctx_str = f"\nContext: {context}"
            raise RuntimeError(
                f"Numerical instability detected: value[{i}] = {val} "
                f"(NaN or ±Inf not allowed){ctx_str}"
            )


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value to a specified range.

    Args:
        value: Value to clamp
        min_val: Minimum allowed value
        max_val: Maximum allowed value

    Returns:
        Clamped value
    """
    return max(min_val, min(max_val, value))


def ensure_finite(name: str, value: float) -> float:
    """Ensure a value is finite, raising descriptive error if not.

    Args:
        name: Name of the value for error messages
        value: Value to check

    Returns:
        The value if finite

    Raises:
        ValueError: If value is not finite
    """
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number, got {value}")
    return value


def validate_probability(name: str, value: float) -> float:
    """Validate that a value is a valid probability in [0, 1].

    Args:
        name: Name of the value for error messages
        value: Value to check

    Returns:
        The value if valid

    Raises:
        ValueError: If value is not in [0, 1]
    """
    value = ensure_finite(name, value)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be in [0, 1], got {value}")
    return value


def validate_positive(name: str, value: float, allow_zero: bool = False) -> float:
    """Validate that a value is positive (optionally allowing zero).

    Args:
        name: Name of the value for error messages
        value: Value to check
        allow_zero: Whether zero is allowed

    Returns:
        The value if valid

    Raises:
        ValueError: If value is not positive (or non-negative if allow_zero)
    """
    value = ensure_finite(name, value)
    if allow_zero:
        if value < 0.0:
            raise ValueError(f"{name} must be >= 0, got {value}")
    else:
        if value <= 0.0:
            raise ValueError(f"{name} must be > 0, got {value}")
    return value


def check_monotonic_thresholds(go: float, hold: float, no_go: float) -> tuple[float, float, float]:
    """Ensure thresholds follow go >= hold >= no_go invariant.

    If the invariant is violated, adjusts thresholds to the nearest valid configuration.
    This implements a fail-shut mode: inconsistent thresholds are made consistent.

    Args:
        go: Go threshold
        hold: Hold threshold
        no_go: No-go threshold

    Returns:
        Tuple of (go, hold, no_go) satisfying the monotonic constraint
    """
    # Clamp all to [0, 1]
    go = clamp(go, 0.0, 1.0)
    hold = clamp(hold, 0.0, 1.0)
    no_go = clamp(no_go, 0.0, 1.0)

    # Sort to enforce monotonic order: go >= hold >= no_go
    # This is the most straightforward way to ensure all constraints
    values = sorted([go, hold, no_go], reverse=True)
    go_out = values[0]
    hold_out = values[1]
    no_go_out = values[2]

    return go_out, hold_out, no_go_out


def rate_limited_change(current: float, target: float, max_rate: float, dt: float = 1.0) -> float:
    """Apply rate limiting to a parameter change.

    Args:
        current: Current value
        target: Target value
        max_rate: Maximum rate of change per time unit
        dt: Time step (default 1.0)

    Returns:
        New value with rate limiting applied
    """
    delta = target - current
    max_delta = max_rate * dt

    if abs(delta) <= max_delta:
        return target

    return current + math.copysign(max_delta, delta)
