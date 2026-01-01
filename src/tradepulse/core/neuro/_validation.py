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
validate_neuro_invariants : Validate neuromodulator metric and state invariants
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Mapping, Optional

__all__ = [
    "BoundsSpec",
    "ensure_float",
    "ensure_int",
    "ensure_bool",
    "ensure_finite",
    "clamp",
    "validate_probability",
    "validate_positive",
    "validate_neuro_invariants",
]

NEURO_STATE_RANGES: Mapping[str, tuple[float, float]] = {
    "dopamine_level": (0.0, 5.0),
    "serotonin_level": (0.0, 5.0),
    "gaba_inhibition": (0.0, 5.0),
    "na_arousal": (0.0, 5.0),
    "ach_attention": (0.0, 5.0),
}

NEURO_STATE_DEFAULTS: Mapping[str, float] = {
    "dopamine_level": 0.5,
    "serotonin_level": 0.3,
    "gaba_inhibition": 0.4,
    "na_arousal": 1.0,
    "ach_attention": 0.7,
}

NEURO_METRIC_RANGES: Mapping[str, tuple[float, float]] = {
    "arousal_attention_coherence": (0.0, 1.0),
    "overall_balance_score": (0.0, 1.0),
    "stability": (0.0, 1.0),
    "homeostatic_deviation": (0.0, math.inf),
}


def _ensure_range(
    name: str,
    value: float,
    *,
    min_value: float,
    max_value: float,
) -> float:
    value = ensure_finite(name, value)
    if value < min_value:
        raise ValueError(f"{name} must be >= {min_value}, got {value}")
    if value > max_value:
        raise ValueError(f"{name} must be <= {max_value}, got {value}")
    return value


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
    overall_balance_score: float,
    homeostatic_deviation: float,
    stability: Optional[float] = None,
    state: Optional[Mapping[str, float]] = None,
    da_5ht_ratio_range: tuple[float, float] = (1.0, 3.0),
    ei_balance_range: tuple[float, float] = (1.0, 2.5),
    epsilon: float = 1e-6,
    tolerance: float = 1e-5,
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
    overall_balance_score : float
        Overall balance score expected in [0, 1].
    homeostatic_deviation : float
        Homeostatic deviation expected to be non-negative.
    stability : Optional[float]
        Stability metric expected in [0, 1] when supplied.
    state : Optional[Mapping[str, float]]
        Optional neuromodulator state (levels, arousal, attention) to validate.
    da_5ht_ratio_range : tuple[float, float]
        Inclusive bounds for DA/5-HT ratio.
    ei_balance_range : tuple[float, float]
        Inclusive bounds for E/I balance.
    epsilon : float
        Numerical stability constant for ratio-based checks.
    tolerance : float
        Tolerance for monotonic consistency checks.

    Raises
    ------
    ValueError
        If any invariant is violated.
    """
    ratio = ensure_finite("dopamine_serotonin_ratio", dopamine_serotonin_ratio)
    ei_balance = ensure_finite(
        "excitation_inhibition_balance", excitation_inhibition_balance
    )
    coherence = ensure_finite(
        "arousal_attention_coherence", arousal_attention_coherence
    )
    balance_score = _ensure_range(
        "overall_balance_score",
        overall_balance_score,
        min_value=NEURO_METRIC_RANGES["overall_balance_score"][0],
        max_value=NEURO_METRIC_RANGES["overall_balance_score"][1],
    )
    deviation = _ensure_range(
        "homeostatic_deviation",
        homeostatic_deviation,
        min_value=NEURO_METRIC_RANGES["homeostatic_deviation"][0],
        max_value=NEURO_METRIC_RANGES["homeostatic_deviation"][1],
    )

    if stability is not None:
        _ensure_range(
            "stability",
            stability,
            min_value=NEURO_METRIC_RANGES["stability"][0],
            max_value=NEURO_METRIC_RANGES["stability"][1],
        )

    da_min, da_max = da_5ht_ratio_range
    if not da_min <= ratio <= da_max:
        raise ValueError(
            f"dopamine_serotonin_ratio must be in [{da_min}, {da_max}], got {ratio}"
        )

    ei_min, ei_max = ei_balance_range
    if not ei_min <= ei_balance <= ei_max:
        raise ValueError(
            f"excitation_inhibition_balance must be in [{ei_min}, {ei_max}], got {ei_balance}"
        )

    if not (
        NEURO_METRIC_RANGES["arousal_attention_coherence"][0]
        <= coherence
        <= NEURO_METRIC_RANGES["arousal_attention_coherence"][1]
    ):
        raise ValueError(
            "arousal_attention_coherence must be in [0, 1], "
            f"got {arousal_attention_coherence}"
        )

    expected_balance = 1.0 / (1.0 + deviation)
    if abs(balance_score - expected_balance) > tolerance:
        raise ValueError(
            "overall_balance_score must decrease monotonically with "
            "homeostatic_deviation (expected "
            f"{expected_balance:.6f}, got {balance_score:.6f})"
        )

    if state is None:
        return

    for name, (min_value, max_value) in NEURO_STATE_RANGES.items():
        value = float(state.get(name, NEURO_STATE_DEFAULTS[name]))
        _ensure_range(
            name,
            value,
            min_value=min_value,
            max_value=max_value,
        )

    dopamine_level = float(
        state.get("dopamine_level", NEURO_STATE_DEFAULTS["dopamine_level"])
    )
    serotonin_level = float(
        state.get("serotonin_level", NEURO_STATE_DEFAULTS["serotonin_level"])
    )
    gaba_inhibition = float(
        state.get("gaba_inhibition", NEURO_STATE_DEFAULTS["gaba_inhibition"])
    )
    na_arousal = float(state.get("na_arousal", NEURO_STATE_DEFAULTS["na_arousal"]))
    ach_attention = float(
        state.get("ach_attention", NEURO_STATE_DEFAULTS["ach_attention"])
    )

    expected_ratio = dopamine_level / (serotonin_level + epsilon)
    if abs(ratio - expected_ratio) > tolerance:
        raise ValueError(
            "dopamine_serotonin_ratio must follow the monotonic DA/5-HT "
            f"ratio formula (expected {expected_ratio:.6f}, got {ratio:.6f})"
        )

    expected_ei = (dopamine_level + na_arousal) / (
        gaba_inhibition + serotonin_level + epsilon
    )
    if abs(ei_balance - expected_ei) > tolerance:
        raise ValueError(
            "excitation_inhibition_balance must follow the monotonic E/I "
            f"balance formula (expected {expected_ei:.6f}, got {ei_balance:.6f})"
        )

    expected_coherence = 1.0 - abs(na_arousal - ach_attention) / 2.0
    expected_coherence = clamp(expected_coherence, 0.0, 1.0)
    if abs(coherence - expected_coherence) > tolerance:
        raise ValueError(
            "arousal_attention_coherence must follow the monotonic arousal/attention "
            f"coherence formula (expected {expected_coherence:.6f}, got {coherence:.6f})"
        )
