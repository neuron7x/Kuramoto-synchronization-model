"""Utility functions for evaluating regression forecasts.

These helpers intentionally avoid scikit-learn dependencies so that
lightweight deployments (CLI tools, notebooks, unit tests) can compute
standard error metrics using only NumPy.  Each function validates inputs,
handles edge-cases such as empty arrays and division-by-zero, and returns a
plain ``float`` suitable for logging or Prometheus gauges.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np


def _as_float_array(values: Iterable[float]) -> np.ndarray:
    array = np.asarray(list(values), dtype=float)
    if array.size == 0:
        raise ValueError("regression metrics require at least one sample")
    return array


def mean_absolute_error(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    """Return the mean absolute error between two equally shaped sequences.

    Notes:
        **Numerical Stability (2025 Standards):**
        - Uses float64 for all operations to prevent precision loss
        - Handles large arrays efficiently through vectorization
        - Guaranteed non-negative result (absolute values)
    """

    true = _as_float_array(y_true)
    pred = _as_float_array(y_pred)
    if true.shape != pred.shape:
        raise ValueError("y_true and y_pred must share the same shape")

    # Use float64 accumulation for mean to prevent drift
    errors = np.abs(true - pred)
    return float(np.mean(errors, dtype=np.float64))


def mean_squared_error(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    """Return the mean squared error between targets and predictions.

    Notes:
        **Numerical Stability (2025 Standards):**
        - Float64 accumulation prevents overflow for large errors
        - Vectorized operations minimize intermediate storage
        - Guaranteed non-negative (squared values)
    """

    true = _as_float_array(y_true)
    pred = _as_float_array(y_pred)
    if true.shape != pred.shape:
        raise ValueError("y_true and y_pred must share the same shape")

    diff = true - pred
    # Use float64 for mean to handle large squared values accurately
    squared_errors = np.square(diff)
    return float(np.mean(squared_errors, dtype=np.float64))


def root_mean_squared_error(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    """Return the root mean squared error between two sequences."""

    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


def mean_absolute_percentage_error(
    y_true: Iterable[float],
    y_pred: Iterable[float],
    *,
    epsilon: float = 1e-8,
) -> float:
    """Return the MAPE while guarding against division-by-zero.

    Notes:
        **Numerical Stability (2025 Standards):**
        - Epsilon clipping prevents division by zero or near-zero
        - Float64 accumulation for mean prevents precision loss
        - Undefined for zero true values (returns large error via epsilon)
        - Asymmetric: sensitive to over-prediction vs under-prediction
    """

    true = _as_float_array(y_true)
    pred = _as_float_array(y_pred)
    if true.shape != pred.shape:
        raise ValueError("y_true and y_pred must share the same shape")

    # Clip absolute true values to epsilon to prevent division by zero
    # This makes MAPE undefined for zero true values, but provides stable fallback
    safe_true = np.clip(np.abs(true), epsilon, None)

    # Compute percentage errors with float64 precision
    percentage_errors = np.abs((true - pred) / safe_true)

    # Mean with float64 accumulation
    return float(np.mean(percentage_errors, dtype=np.float64))


def symmetric_mean_absolute_percentage_error(
    y_true: Iterable[float],
    y_pred: Iterable[float],
    *,
    epsilon: float = 1e-8,
) -> float:
    """Return sMAPE with optional epsilon to stabilise near-zero targets.

    Notes:
        **Numerical Stability (2025 Standards):**
        - Symmetric formulation: treats over/under-prediction equally
        - Epsilon prevents division by zero when both true and pred are zero
        - Bounded: [0, 2] range (0% to 200% error)
        - Float64 accumulation throughout
        - More stable than MAPE for near-zero values
    """

    true = _as_float_array(y_true)
    pred = _as_float_array(y_pred)
    if true.shape != pred.shape:
        raise ValueError("y_true and y_pred must share the same shape")

    # Compute denominator: |y_true| + |y_pred|, clipped to epsilon
    # This makes the metric symmetric and prevents division by zero
    abs_true = np.abs(true)
    abs_pred = np.abs(pred)
    denom = np.maximum(abs_true + abs_pred, epsilon)

    # sMAPE = 2 * mean(|y_true - y_pred| / (|y_true| + |y_pred|))
    # Factor of 2 normalizes to 0-200% range (0-2 in decimal)
    errors = np.abs(true - pred) / denom

    # Mean with float64 accumulation, then multiply by 2
    return float(np.mean(errors, dtype=np.float64) * 2.0)


def r2_score(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    """Return the coefficient of determination (R²).

    Notes:
        **Numerical Stability (2025 Standards):**
        - Uses Welford-style two-pass algorithm for variance
        - Float64 accumulation throughout to prevent cancellation
        - Proper handling of degenerate cases (constant targets)
        - Prevents division by zero with epsilon tolerance
        - Can return negative values for very poor predictions (as per sklearn convention)
    """

    true = _as_float_array(y_true)
    pred = _as_float_array(y_pred)
    if true.shape != pred.shape:
        raise ValueError("y_true and y_pred must share the same shape")

    # Compute mean with float64 precision
    mean_true = np.mean(true, dtype=np.float64)

    # Total sum of squares: variance * n
    # Use centered differences to avoid catastrophic cancellation
    centered_true = true - mean_true
    ss_tot = np.sum(np.square(centered_true), dtype=np.float64)

    # Check for degenerate case: constant target sequence
    # Use small epsilon to account for numerical errors
    eps = np.finfo(np.float64).eps * max(np.abs(mean_true), 1.0) * true.size
    if ss_tot <= eps:
        # Degenerate case: constant target sequence. Match scikit-learn's behaviour
        # by returning zero when predictions deviate from the constant value.
        residual = np.max(np.abs(true - pred))
        return 0.0 if residual > eps else 1.0

    # Residual sum of squares
    residuals = true - pred
    ss_res = np.sum(np.square(residuals), dtype=np.float64)

    # R² = 1 - (SS_res / SS_tot)
    # Can be negative for very poor fits (worse than horizontal line)
    r2 = 1.0 - (ss_res / ss_tot)
    return float(r2)


__all__ = [
    "mean_absolute_error",
    "mean_squared_error",
    "root_mean_squared_error",
    "mean_absolute_percentage_error",
    "symmetric_mean_absolute_percentage_error",
    "r2_score",
]
