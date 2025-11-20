# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""High-precision numerical utilities for financial computations.

This module provides numerically stable algorithms for critical financial
calculations where precision is paramount. All functions follow 2025 best
practices for numerical computing in quantitative finance.

Key Features:
- Kahan-Babuška compensated summation for large aggregations
- Numerically stable mean calculations
- Safe division with configurable fallbacks
- Input validation and sanitization helpers

The utilities here are designed for production trading systems where even
small numerical errors can compound into significant P&L impacts.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np


def kahan_sum(values: np.ndarray | Sequence[float]) -> float:
    """Compute sum using Kahan-Babuška compensated summation algorithm.
    
    This algorithm maintains a running compensation term to capture bits lost
    during floating-point addition, significantly improving accuracy for large
    summations compared to naive summation.
    
    Args:
        values: Array or sequence of values to sum
        
    Returns:
        float: Accurately summed total
        
    Notes:
        **Algorithm Complexity:** O(n) time, O(1) space
        **Accuracy Improvement:** Reduces accumulated error from O(n*ε) to O(ε)
        where ε is machine epsilon and n is the number of values.
        
        For IEEE 754 double precision (float64), this means:
        - Naive sum error: ~2.22e-16 * n
        - Kahan sum error: ~2.22e-16 (independent of n)
        
        Critical for trading systems summing 1000+ positions or bond energies.
        
    Examples:
        >>> # For small values, results match np.sum
        >>> values = [1.0, 2.0, 3.0]
        >>> kahan_sum(values) == sum(values)
        True
        
        >>> # For many small values, Kahan is more accurate
        >>> values = [1e-10] * 10000000
        >>> abs(kahan_sum(values) - 1e-3) < 1e-15
        True
        
    References:
        - Kahan, W. (1965). Further remarks on reducing truncation errors.
        - Neumaier, A. (1974). Rundungsfehleranalyse einiger Verfahren.
    """
    arr = np.asarray(values, dtype=np.float64)
    
    if arr.size == 0:
        return 0.0
    
    # Remove non-finite values
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return 0.0
    
    total = 0.0
    compensation = 0.0  # Running compensation for lost low-order bits
    
    for value in arr:
        corrected = value - compensation
        new_sum = total + corrected
        # Calculate what was lost in the addition
        # (new_sum - total) is the rounded value added
        # (new_sum - total) - corrected is what was lost
        compensation = (new_sum - total) - corrected
        total = new_sum
    
    return total


def kahan_mean(values: np.ndarray | Sequence[float]) -> float:
    """Compute mean using compensated summation for the numerator.
    
    Args:
        values: Array or sequence of values to average
        
    Returns:
        float: Numerically stable mean value
        
    Raises:
        ValueError: If input is empty or contains only non-finite values
        
    Notes:
        Uses Kahan summation for the numerator to ensure accuracy even when
        averaging many small values or values with large differences in magnitude.
        
    Examples:
        >>> values = [1.0, 2.0, 3.0, 4.0, 5.0]
        >>> kahan_mean(values)
        3.0
    """
    arr = np.asarray(values, dtype=np.float64)
    finite_arr = arr[np.isfinite(arr)]
    
    if finite_arr.size == 0:
        raise ValueError("Cannot compute mean of empty or all-NaN array")
    
    total = kahan_sum(finite_arr)
    return total / finite_arr.size


def safe_divide(
    numerator: float | np.ndarray,
    denominator: float | np.ndarray,
    *,
    default: float = 0.0,
    min_denominator: float = 1e-15,
) -> float | np.ndarray:
    """Perform division with protection against division by zero or near-zero.
    
    Args:
        numerator: Dividend value(s)
        denominator: Divisor value(s)
        default: Value to return when denominator is too small or non-finite
        min_denominator: Minimum absolute value for denominator (default: 1e-15)
        
    Returns:
        float | np.ndarray: Result of division or default value
        
    Notes:
        This function is critical for production systems where division by zero
        can occur due to market conditions (e.g., zero volume, zero volatility).
        
        The default minimum denominator (1e-15) is slightly above float64 epsilon
        to prevent numerical instability while still allowing very small values.
        
    Examples:
        >>> safe_divide(10.0, 2.0)
        5.0
        
        >>> safe_divide(10.0, 0.0, default=0.0)
        0.0
        
        >>> safe_divide(10.0, 1e-20, default=0.0)
        0.0
    """
    num_arr = np.asarray(numerator, dtype=np.float64)
    denom_arr = np.asarray(denominator, dtype=np.float64)
    
    # Check if denominator is too small or non-finite
    safe_mask = np.isfinite(denom_arr) & (np.abs(denom_arr) >= min_denominator)
    
    # Also check numerator for finiteness
    safe_mask = safe_mask & np.isfinite(num_arr)
    
    # Perform division only where safe
    result = np.where(
        safe_mask,
        num_arr / denom_arr,
        default,
    )
    
    # If inputs were scalars, return scalar
    if np.ndim(numerator) == 0 and np.ndim(denominator) == 0:
        return float(result)
    
    return result


def validate_probability(value: float | np.ndarray, *, strict: bool = True) -> float | np.ndarray:
    """Validate and clamp values to the [0.0, 1.0] probability range.
    
    Args:
        value: Value(s) to validate as probability
        strict: If True, raise ValueError for values significantly outside [0,1]
                If False, silently clamp to [0,1]
                
    Returns:
        float | np.ndarray: Validated probability value(s)
        
    Raises:
        ValueError: If strict=True and values are outside [0,1] by more than 1e-10
        
    Notes:
        Allows small numerical errors (±1e-10) due to floating-point arithmetic
        but catches genuine logic errors. Critical for probability-based indicators.
        
    Examples:
        >>> validate_probability(0.5)
        0.5
        
        >>> validate_probability(1.0 + 1e-15)  # Small numerical error
        1.0
        
        >>> validate_probability(1.5, strict=False)
        1.0
    """
    arr = np.asarray(value, dtype=np.float64)
    
    # Check for non-finite values
    if not np.all(np.isfinite(arr)):
        if strict:
            raise ValueError("Probability value must be finite")
        arr = np.nan_to_num(arr, nan=0.0, posinf=1.0, neginf=0.0)
    
    # Check for values significantly outside [0, 1]
    tolerance = 1e-10
    if strict:
        if np.any(arr < -tolerance) or np.any(arr > 1.0 + tolerance):
            raise ValueError(f"Probability value must be in [0, 1], got {arr}")
    
    # Clamp to [0, 1]
    return np.clip(arr, 0.0, 1.0)


def is_numerically_stable(value: float | np.ndarray, *, max_abs: float = 1e10) -> bool:
    """Check if value(s) are numerically stable (finite and not too large).
    
    Args:
        value: Value(s) to check
        max_abs: Maximum absolute value considered stable (default: 1e10)
        
    Returns:
        bool: True if all values are finite and within [-max_abs, max_abs]
        
    Notes:
        Use this to validate intermediate calculations before they propagate
        to critical system decisions (e.g., order sizing, risk limits).
        
    Examples:
        >>> is_numerically_stable(42.0)
        True
        
        >>> is_numerically_stable(np.inf)
        False
        
        >>> is_numerically_stable(1e15)
        False
    """
    arr = np.asarray(value)
    return bool(np.all(np.isfinite(arr)) and np.all(np.abs(arr) <= max_abs))


__all__ = [
    "kahan_sum",
    "kahan_mean",
    "safe_divide",
    "validate_probability",
    "is_numerically_stable",
]
