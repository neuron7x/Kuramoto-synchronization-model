# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Input validation utilities for MLSDM with numerical contract enforcement.

This module provides validated input functions for the MLSDM subsystem,
ensuring numerical stability and correctness across vector/memory/metrics paths.

Numerical Contract:
    - EPS = 1e-9: Universal epsilon for safe divisions and normalization
    - All vectors must be finite (no NaN/Inf) unless explicitly sanitized
    - strict_mode=True: raise ValueError on invalid data
    - strict_mode=False: sanitize with explicit policy + logging
    - Zero vectors: handled via on_zero policy (return_zeros | raise)

References:
    - docs/NUMERICAL_CONTRACTS.md for full specification
    - IEEE 754-2019 floating-point standard
"""

from __future__ import annotations

import logging
from typing import Literal

import numpy as np

__all__ = [
    "NumericalContractError",
    "EPS",
    "validate_finite_array",
    "safe_unit_normalize",
    "ensure_dtype",
    "sanitize_array",
]

logger = logging.getLogger(__name__)

# =============================================================================
# Numerical Contract Constants
# =============================================================================

# Universal epsilon for MLSDM numerical operations.
# Chosen to be well above float64 machine epsilon (2.22e-16) but small enough
# to not affect meaningful computations. Used for:
# - Division safety: denom + EPS
# - Normalization: ||v|| + EPS
# - Zero comparisons: |x| < EPS
EPS: float = 1e-9


class NumericalContractError(ValueError):
    """Raised when numerical contract validation fails in strict mode.

    Attributes:
        name: Name of the array/parameter that failed validation.
        reason: Specific validation failure reason.
    """

    def __init__(self, name: str, reason: str) -> None:
        self.name = name
        self.reason = reason
        super().__init__(f"Numerical contract violation for '{name}': {reason}")


def validate_finite_array(
    x: np.ndarray,
    name: str,
    *,
    allow_nan: bool = False,
    allow_inf: bool = False,
    strict_mode: bool = True,
) -> np.ndarray:
    """Validate that an array contains only finite values.

    Uses vectorized np.isfinite checks for performance. In strict_mode,
    raises NumericalContractError on invalid data. Otherwise, sanitizes
    and logs a warning.

    Args:
        x: Input array to validate. Must be numpy array or convertible.
        name: Descriptive name for error messages.
        allow_nan: If True, NaN values are permitted.
        allow_inf: If True, Inf values are permitted.
        strict_mode: If True, raise on invalid data. If False, sanitize.

    Returns:
        The validated array (same object if valid, sanitized copy if not).

    Raises:
        NumericalContractError: In strict_mode when array contains invalid values.
        TypeError: If x cannot be converted to numpy array.

    Examples:
        >>> import numpy as np
        >>> validate_finite_array(np.array([1.0, 2.0, 3.0]), "embedding")
        array([1., 2., 3.])

        >>> validate_finite_array(np.array([1.0, np.nan]), "x", strict_mode=False)
        array([1., 0.])
    """
    if not isinstance(x, np.ndarray):
        x = np.asarray(x)

    # Use np.errstate to suppress floating-point warnings during checks
    with np.errstate(invalid="ignore"):
        has_nan = np.any(np.isnan(x))
        has_inf = np.any(np.isinf(x))

    # Check for violations
    violations = []
    if has_nan and not allow_nan:
        violations.append("contains NaN values")
    if has_inf and not allow_inf:
        violations.append("contains Inf values")

    if violations:
        reason = "; ".join(violations)
        if strict_mode:
            raise NumericalContractError(name, reason)

        # Sanitize mode: replace invalid values with zeros and log
        logger.warning(
            "Numerical contract: sanitizing '%s' - %s (replaced with zeros)",
            name,
            reason,
        )
        x = sanitize_array(x)

    return x


def sanitize_array(x: np.ndarray) -> np.ndarray:
    """Replace NaN and Inf values with zeros.

    Args:
        x: Input array potentially containing NaN/Inf values.

    Returns:
        Array with NaN -> 0.0, +Inf -> 0.0, -Inf -> 0.0
    """
    return np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0, copy=True)


def safe_unit_normalize(
    vec: np.ndarray,
    *,
    eps: float = EPS,
    on_zero: Literal["return_zeros", "raise"] = "return_zeros",
) -> np.ndarray:
    """Safely normalize a vector to unit length.

    Computes vec / (||vec|| + eps) to avoid division by zero.
    Handles zero vectors according to on_zero policy.

    Args:
        vec: Input vector(s). Can be 1D (single vector) or 2D (batch of vectors).
        eps: Epsilon added to norm for numerical stability. Default: EPS (1e-9).
        on_zero: Policy for zero/near-zero vectors:
            - "return_zeros": Return zero vector (default, safe).
            - "raise": Raise NumericalContractError.

    Returns:
        Unit-normalized vector(s) with the same shape as input.

    Raises:
        NumericalContractError: If on_zero="raise" and vector norm < eps.

    Examples:
        >>> import numpy as np
        >>> vec = np.array([3.0, 4.0])
        >>> safe_unit_normalize(vec)
        array([0.6, 0.8])

        >>> safe_unit_normalize(np.array([0.0, 0.0]))
        array([0., 0.])
    """
    if not isinstance(vec, np.ndarray):
        vec = np.asarray(vec)

    # Handle 1D and 2D cases
    if vec.ndim == 1:
        norm = np.linalg.norm(vec)
        if norm < eps:
            if on_zero == "raise":
                raise NumericalContractError(
                    "vector", f"cannot normalize: norm ({norm:.2e}) < eps ({eps:.2e})"
                )
            return np.zeros_like(vec)
        return vec / (norm + eps)

    elif vec.ndim == 2:
        # Batch normalization: normalize each row
        norms = np.linalg.norm(vec, axis=1, keepdims=True)
        near_zero_mask = norms.squeeze() < eps

        if np.any(near_zero_mask):
            if on_zero == "raise":
                raise NumericalContractError(
                    "vectors",
                    f"cannot normalize: {np.sum(near_zero_mask)} vectors have norm < eps",
                )
            # Return zeros for near-zero vectors, normalized for others
            result = np.zeros_like(vec)
            valid_mask = ~near_zero_mask
            if np.any(valid_mask):
                result[valid_mask] = vec[valid_mask] / (norms[valid_mask] + eps)
            return result

        return vec / (norms + eps)

    else:
        raise NumericalContractError(
            "vector", f"expected 1D or 2D array, got {vec.ndim}D"
        )


def ensure_dtype(
    vec: np.ndarray,
    dtype: type = np.float64,
    *,
    name: str = "array",
    copy: bool = False,
) -> np.ndarray:
    """Ensure array has the specified dtype.

    Args:
        vec: Input array.
        dtype: Target dtype. Default: np.float64 for maximum precision.
        name: Descriptive name for error messages.
        copy: If True, always return a copy even if dtype matches.

    Returns:
        Array with the specified dtype.

    Raises:
        NumericalContractError: If conversion results in overflow/underflow.

    Examples:
        >>> import numpy as np
        >>> ensure_dtype(np.array([1, 2, 3]), np.float32)
        array([1., 2., 3.], dtype=float32)
    """
    if not isinstance(vec, np.ndarray):
        vec = np.asarray(vec)

    if vec.dtype == dtype and not copy:
        return vec

    # Check for potential overflow/underflow for integer to float conversions
    with np.errstate(over="raise", under="ignore"):
        try:
            result = vec.astype(dtype, copy=copy)
        except FloatingPointError as e:
            raise NumericalContractError(
                name, f"dtype conversion overflow: {e}"
            ) from e

    # Verify no inf values were introduced by conversion
    if np.issubdtype(dtype, np.floating):
        if np.any(np.isinf(result)) and not np.any(np.isinf(vec)):
            raise NumericalContractError(
                name, "dtype conversion introduced Inf values"
            )

    return result
