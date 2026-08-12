# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Standardized numerical constants for mathematical precision.

This module provides well-documented numerical constants used throughout
GeoSync for consistent numerical stability. Using standardized constants
ensures predictable behavior across different computation modules and
simplifies maintenance when precision requirements change.

Constants are organized by purpose:
- Machine epsilon values for different precision levels
- Safe minimum values for logarithm and division operations
- Probability clipping bounds
- Comparison tolerances

References:
    - IEEE 754-2019 floating-point standard
    - Higham, N. J. (2002). Accuracy and Stability of Numerical Algorithms
    - Goldberg, D. (1991). What Every Computer Scientist Should Know About
      Floating-Point Arithmetic
"""

from __future__ import annotations

import numpy as np

# =============================================================================
# Machine Epsilon Constants
# =============================================================================

# Machine epsilon for float64 (approximately 2.22e-16)
FLOAT64_EPS: float = float(np.finfo(np.float64).eps)

# Machine epsilon for float32 (approximately 1.19e-7)
FLOAT32_EPS: float = float(np.finfo(np.float32).eps)

# =============================================================================
# Safe Minimum Values for Mathematical Operations
# =============================================================================

# Safe minimum for division operations to avoid division by zero.
# Chosen to be well above machine epsilon but small enough to not affect
# meaningful computations significantly.
DIV_SAFE_MIN: float = 1e-12

# Safe minimum for logarithm arguments to avoid log(0) = -inf.
# Using a smaller value than DIV_SAFE_MIN because log is more tolerant
# of very small positive values.
LOG_SAFE_MIN: float = 1e-15

# Safe minimum for variance/standard deviation before computing statistics.
# Variance below this threshold indicates essentially constant data.
VARIANCE_SAFE_MIN: float = 1e-12

# Safe minimum for volatility estimates in trading calculations.
# Lower values would indicate unrealistic market conditions.
VOLATILITY_SAFE_MIN: float = 1e-10

# =============================================================================
# Probability and Statistical Bounds
# =============================================================================

# Minimum probability for clipping to avoid log(0) in entropy calculations.
PROB_CLIP_MIN: float = 1e-10

# Maximum probability for clipping to avoid log(1-p) = -inf in entropy calculations.
PROB_CLIP_MAX: float = 1.0 - 1e-10

# Minimum probability for binary distribution calculations.
BINARY_PROB_MIN: float = 1e-5

# =============================================================================
# Position Sizing and Financial Calculations
# =============================================================================

# Minimum position size threshold below which positions are considered zero.
POSITION_SIZE_MIN: float = 1e-9

# Cash balance tolerance for determining overdraft conditions.
CASH_TOLERANCE: float = 1e-9

# =============================================================================
# Comparison Tolerances
# =============================================================================

# Relative tolerance for floating-point comparisons.
FLOAT_REL_TOL: float = 1e-9

# Absolute tolerance for floating-point comparisons.
FLOAT_ABS_TOL: float = 1e-12

# Tolerance for considering a quantity as zero.
ZERO_TOL: float = 1e-12


# =============================================================================
# Helper Functions
# =============================================================================


def safe_divide(
    numerator: float,
    denominator: float,
    *,
    default: float = 0.0,
    min_denom: float = DIV_SAFE_MIN,
) -> float:
    """Perform safe division avoiding division by zero.

    Args:
        numerator: The numerator value.
        denominator: The denominator value.
        default: Value to return if division is unsafe.
        min_denom: Minimum denominator threshold.

    Returns:
        Result of numerator/denominator or default if denominator is too small.
    """
    if abs(denominator) < min_denom:
        return default
    return numerator / denominator


def safe_log(
    value: float,
    *,
    min_value: float = LOG_SAFE_MIN,
) -> float:
    """Compute safe natural logarithm avoiding log(0).

    Args:
        value: Value to compute log of.
        min_value: Minimum value threshold before clamping.

    Returns:
        Natural logarithm of max(value, min_value).
    """
    return float(np.log(max(value, min_value)))


def safe_sqrt(
    value: float,
    *,
    min_value: float = 0.0,
) -> float:
    """Compute safe square root avoiding sqrt of negative values.

    Args:
        value: Value to compute sqrt of.
        min_value: Minimum value threshold before clamping.

    Returns:
        Square root of max(value, min_value).
    """
    return float(np.sqrt(max(value, min_value)))


def clip_probability(prob: float) -> float:
    """Clip probability to valid range avoiding numerical edge cases.

    Args:
        prob: Probability value to clip.

    Returns:
        Probability clipped to [PROB_CLIP_MIN, PROB_CLIP_MAX].
    """
    return float(np.clip(prob, PROB_CLIP_MIN, PROB_CLIP_MAX))


def is_effectively_zero(value: float, tol: float = ZERO_TOL) -> bool:
    """Check if a value is effectively zero within tolerance.

    Args:
        value: Value to check.
        tol: Tolerance for zero comparison.

    Returns:
        True if abs(value) < tol.
    """
    return abs(value) < tol


__all__ = [
    # Machine epsilon
    "FLOAT64_EPS",
    "FLOAT32_EPS",
    # Safe minimums
    "DIV_SAFE_MIN",
    "LOG_SAFE_MIN",
    "VARIANCE_SAFE_MIN",
    "VOLATILITY_SAFE_MIN",
    # Probability bounds
    "PROB_CLIP_MIN",
    "PROB_CLIP_MAX",
    "BINARY_PROB_MIN",
    # Financial
    "POSITION_SIZE_MIN",
    "CASH_TOLERANCE",
    # Tolerances
    "FLOAT_REL_TOL",
    "FLOAT_ABS_TOL",
    "ZERO_TOL",
    # Helper functions
    "safe_divide",
    "safe_log",
    "safe_sqrt",
    "clip_probability",
    "is_effectively_zero",
]
