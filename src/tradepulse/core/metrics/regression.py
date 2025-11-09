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
    """Return the mean absolute error between two equally shaped sequences."""

    true = _as_float_array(y_true)
    pred = _as_float_array(y_pred)
    if true.shape != pred.shape:
        raise ValueError("y_true and y_pred must share the same shape")
    return float(np.mean(np.abs(true - pred)))


def mean_squared_error(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    """Return the mean squared error between targets and predictions."""

    true = _as_float_array(y_true)
    pred = _as_float_array(y_pred)
    if true.shape != pred.shape:
        raise ValueError("y_true and y_pred must share the same shape")
    diff = true - pred
    return float(np.mean(np.square(diff)))


def root_mean_squared_error(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    """Return the root mean squared error between two sequences."""

    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


def mean_absolute_percentage_error(
    y_true: Iterable[float],
    y_pred: Iterable[float],
    *,
    epsilon: float = 1e-8,
) -> float:
    """Return the MAPE while guarding against division-by-zero."""

    true = _as_float_array(y_true)
    pred = _as_float_array(y_pred)
    if true.shape != pred.shape:
        raise ValueError("y_true and y_pred must share the same shape")
    safe_true = np.clip(np.abs(true), epsilon, None)
    return float(np.mean(np.abs((true - pred) / safe_true)))


def symmetric_mean_absolute_percentage_error(
    y_true: Iterable[float],
    y_pred: Iterable[float],
    *,
    epsilon: float = 1e-8,
) -> float:
    """Return sMAPE with optional epsilon to stabilise near-zero targets."""

    true = _as_float_array(y_true)
    pred = _as_float_array(y_pred)
    if true.shape != pred.shape:
        raise ValueError("y_true and y_pred must share the same shape")
    denom = np.maximum(np.abs(true) + np.abs(pred), epsilon)
    return float(np.mean(np.abs(true - pred) / denom) * 2.0)


def r2_score(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    """Return the coefficient of determination (R²)."""

    true = _as_float_array(y_true)
    pred = _as_float_array(y_pred)
    if true.shape != pred.shape:
        raise ValueError("y_true and y_pred must share the same shape")
    mean_true = np.mean(true)
    ss_tot = np.sum(np.square(true - mean_true))
    if ss_tot == 0.0:
        # Degenerate case: constant target sequence. Match scikit-learn's behaviour
        # by returning zero when predictions deviate from the constant value.
        return 0.0 if np.any(np.abs(true - pred) > 0) else 1.0
    ss_res = np.sum(np.square(true - pred))
    return float(1.0 - (ss_res / ss_tot))


__all__ = [
    "mean_absolute_error",
    "mean_squared_error",
    "root_mean_squared_error",
    "mean_absolute_percentage_error",
    "symmetric_mean_absolute_percentage_error",
    "r2_score",
]
