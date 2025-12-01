"""Shared validation utilities for neuro controller modules.

This module provides common validation functions used across dopamine,
serotonin, GABA, and NA/ACh neuromodulator controllers. By centralizing
these utilities, we eliminate code duplication and ensure consistent
validation behavior.

Public API
----------
ensure_float : Validate and convert to float with optional bounds
ensure_int : Validate and convert to int with optional minimum
ensure_bool : Validate and convert to bool
ensure_finite : Validate that a value is finite (not NaN/Inf)
clamp : Clamp a value to a specified range
validate_probability : Validate value is in [0, 1]
validate_positive : Validate value is positive (optionally allowing zero)
"""

from __future__ import annotations

import math
from typing import Optional


def ensure_float(
    name: str,
    value: object,
    *,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
) -> float:
    """Validate and convert a value to float with optional bounds checking.

    Args:
        name: Parameter name for error messages
        value: Value to validate and convert
        min_value: Optional minimum allowed value (inclusive)
        max_value: Optional maximum allowed value (inclusive)

    Returns:
        The validated float value

    Raises:
        ValueError: If value is not numeric or outside specified bounds
    """
    if not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number, got {result}")
    if min_value is not None and result < min_value:
        raise ValueError(f"{name} must be >= {min_value}")
    if max_value is not None and result > max_value:
        raise ValueError(f"{name} must be <= {max_value}")
    return result


def ensure_int(
    name: str,
    value: object,
    *,
    min_value: Optional[int] = None,
    max_value: Optional[int] = None,
) -> int:
    """Validate and convert a value to int with optional bounds checking.

    Args:
        name: Parameter name for error messages
        value: Value to validate and convert
        min_value: Optional minimum allowed value (inclusive)
        max_value: Optional maximum allowed value (inclusive)

    Returns:
        The validated int value

    Raises:
        ValueError: If value is not an integer or outside specified bounds
    """
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    if min_value is not None and value < min_value:
        raise ValueError(f"{name} must be >= {min_value}")
    if max_value is not None and value > max_value:
        raise ValueError(f"{name} must be <= {max_value}")
    return value


def ensure_bool(name: str, value: object) -> bool:
    """Validate and convert a value to bool.

    Args:
        name: Parameter name for error messages
        value: Value to validate

    Returns:
        The validated bool value

    Raises:
        ValueError: If value is not a boolean
    """
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


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
