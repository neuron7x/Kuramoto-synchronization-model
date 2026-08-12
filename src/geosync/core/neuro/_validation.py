# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
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
validate_neuro_invariants : Validate neuromodulator metric bounds
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Literal, Optional

__all__ = [
    "BoundsSpec",
    "ensure_float",
    "ensure_int",
    "ensure_bool",
    "ensure_finite",
    "clamp",
    "validate_probability",
    "validate_positive",
    "validate_neuro_metric_bounds",
    "validate_neuro_invariants",
]


@dataclass(frozen=True)
class BoundsSpec:
    """Structured bounds specification for parameter validation.

    Attributes
    ----------
    min_value : float
        Inclusive lower bound.
    max_value : float
        Inclusive upper bound.
    behavior : Literal["clip", "raise"]
        Behavior when a value falls outside bounds.
    """

    min_value: float
    max_value: float
    behavior: Literal["clip", "raise"] = "clip"


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

    Note: Boolean values are explicitly rejected despite bool being a subclass
    of int in Python. This is intentional because configuration values like
    cooldown_ticks or chronic_window should never accept True/False as valid
    inputs - they require explicit integer values.

    Args:
        name: Parameter name for error messages
        value: Value to validate and convert
        min_value: Optional minimum allowed value (inclusive)
        max_value: Optional maximum allowed value (inclusive)

    Returns:
        The validated int value

    Raises:
        ValueError: If value is not an integer (or is a boolean) or outside bounds
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


def validate_neuro_invariants(
    *,
    dopamine_serotonin_ratio: float,
    excitation_inhibition_balance: float,
    arousal_attention_coherence: float,
    stability: float,
    da_5ht_ratio_range: tuple[float, float] = (1.0, 3.0),
    ei_balance_range: tuple[float, float] = (1.0, 2.5),
) -> None:
    """Validate neuromodulator invariants for neuro optimization metrics.

    Parameters
    ----------
    dopamine_serotonin_ratio : float
        Dopamine to serotonin ratio (DA/5-HT).
    excitation_inhibition_balance : float
        Excitation to inhibition balance (E/I).
    arousal_attention_coherence : float
        Coherence between arousal and attention, expected in [0, 1].
    stability : float
        Stability metric expected in [0, 1].
    da_5ht_ratio_range : tuple[float, float]
        Inclusive bounds for DA/5-HT ratio.
    ei_balance_range : tuple[float, float]
        Inclusive bounds for E/I balance.

    Raises
    ------
    ValueError
        If any invariant is violated.
    """
    da_min, da_max = da_5ht_ratio_range
    ei_min, ei_max = ei_balance_range

    validate_neuro_metric_bounds(
        dopamine_serotonin_ratio=dopamine_serotonin_ratio,
        excitation_inhibition_balance=excitation_inhibition_balance,
        arousal_attention_coherence=arousal_attention_coherence,
        stability=stability,
        da_5ht_ratio_bounds=BoundsSpec(da_min, da_max, "raise"),
        ei_balance_bounds=BoundsSpec(ei_min, ei_max, "raise"),
        arousal_attention_bounds=BoundsSpec(0.0, 1.0, "raise"),
        stability_bounds=BoundsSpec(0.0, 1.0, "raise"),
        logger=None,
    )


def validate_neuro_metric_bounds(
    *,
    dopamine_serotonin_ratio: float,
    excitation_inhibition_balance: float,
    arousal_attention_coherence: float,
    stability: float,
    da_5ht_ratio_bounds: BoundsSpec = BoundsSpec(1.0, 3.0, "raise"),
    ei_balance_bounds: BoundsSpec = BoundsSpec(1.0, 2.5, "raise"),
    arousal_attention_bounds: BoundsSpec = BoundsSpec(0.0, 1.0, "raise"),
    stability_bounds: BoundsSpec = BoundsSpec(0.0, 1.0, "raise"),
    logger: Optional[logging.Logger] = None,
) -> dict[str, float]:
    """Validate (and optionally clip) neuro metrics against bounds.

    Parameters
    ----------
    dopamine_serotonin_ratio : float
        Dopamine to serotonin ratio (DA/5-HT).
    excitation_inhibition_balance : float
        Excitation to inhibition balance (E/I).
    arousal_attention_coherence : float
        Coherence between arousal and attention.
    stability : float
        Stability metric.
    da_5ht_ratio_bounds : BoundsSpec
        Bounds/behavior for dopamine-serotonin ratio.
    ei_balance_bounds : BoundsSpec
        Bounds/behavior for excitation-inhibition balance.
    arousal_attention_bounds : BoundsSpec
        Bounds/behavior for arousal-attention coherence.
    stability_bounds : BoundsSpec
        Bounds/behavior for stability.
    logger : logging.Logger, optional
        Logger to emit warnings/errors for out-of-bounds metrics.

    Returns
    -------
    dict[str, float]
        Validated (or clipped) metric values.
    """
    resolved_logger = logger or logging.getLogger(__name__)

    def _apply_bounds(name: str, value: float, bounds: BoundsSpec) -> float:
        checked_value = ensure_finite(name, value)
        if bounds.min_value <= checked_value <= bounds.max_value:
            return checked_value
        message = f"{name} out of bounds [{bounds.min_value}, {bounds.max_value}]: {checked_value}"
        if bounds.behavior == "clip":
            clipped = clamp(checked_value, bounds.min_value, bounds.max_value)
            resolved_logger.warning("%s; clipped to %s", message, clipped)
            return clipped
        resolved_logger.error(message)
        raise ValueError(
            f"{name} must be in [{bounds.min_value}, {bounds.max_value}], got {checked_value}"
        )

    return {
        "dopamine_serotonin_ratio": _apply_bounds(
            "dopamine_serotonin_ratio", dopamine_serotonin_ratio, da_5ht_ratio_bounds
        ),
        "excitation_inhibition_balance": _apply_bounds(
            "excitation_inhibition_balance",
            excitation_inhibition_balance,
            ei_balance_bounds,
        ),
        "arousal_attention_coherence": _apply_bounds(
            "arousal_attention_coherence",
            arousal_attention_coherence,
            arousal_attention_bounds,
        ),
        "stability": _apply_bounds("stability", stability, stability_bounds),
    }
