"""Core error computation for AAR (Acceptor of Action Result).

This module provides functions to compute error signals from predictions
and outcomes. Error signals drive neuro-controller adaptation by quantifying
the difference between expected and actual results.

Error Scale Convention:
    - normalized_error in [-1, 1]
    - sign: +1 = better than expected, -1 = worse, 0 = within tolerance
    - absolute_error >= 0 always

See nak_controller/docs/AAR_SPEC.md for full specification.
"""

from __future__ import annotations

import math
from typing import Any

from .types import ErrorSignal, Outcome, Prediction


def absolute_error(predicted: float, actual: float) -> float:
    """Compute the absolute difference between predicted and actual values.

    Args:
        predicted: The predicted value.
        actual: The actual observed value.

    Returns:
        The absolute difference |predicted - actual|.

    Examples:
        >>> absolute_error(10.0, 8.0)
        2.0
        >>> absolute_error(5.0, 5.0)
        0.0
    """
    return abs(predicted - actual)


def relative_error(predicted: float, actual: float, scale: float = 1.0) -> float:
    """Compute the relative error scaled by a reference value.

    The relative error indicates how far off the prediction was relative
    to a meaningful scale (e.g., typical PnL, expected latency).

    Args:
        predicted: The predicted value.
        actual: The actual observed value.
        scale: Reference scale for normalization. Must be positive.

    Returns:
        The relative error (predicted - actual) / scale.

    Raises:
        ValueError: If scale is not positive.

    Examples:
        >>> relative_error(100.0, 90.0, 50.0)
        0.2
        >>> relative_error(50.0, 100.0, 50.0)
        -1.0
    """
    if scale <= 0.0:
        raise ValueError("scale must be positive")
    return (predicted - actual) / scale


def normalize_error(error: float, scale: float = 1.0) -> float:
    """Normalize error to [-1, 1] range using tanh scaling.

    The tanh function provides smooth saturation at the boundaries,
    preventing extreme errors from dominating adaptation.

    Args:
        error: The raw error value.
        scale: Scaling factor before tanh. Larger values compress the curve.

    Returns:
        Error normalized to [-1, 1].

    Examples:
        >>> abs(normalize_error(0.0)) < 1e-9
        True
        >>> 0.7 < normalize_error(1.0) < 0.8
        True
        >>> -0.8 < normalize_error(-1.0) < -0.7
        True
    """
    safe_scale = max(abs(scale), 1e-9)
    return math.tanh(error / safe_scale)


def error_sign(
    predicted: float,
    actual: float,
    tolerance: float = 0.0,
    *,
    higher_is_better: bool = True,
) -> int:
    """Determine if outcome was better, worse, or equal to prediction.

    Args:
        predicted: The predicted value.
        actual: The actual observed value.
        tolerance: Absolute tolerance for "equal" classification.
        higher_is_better: If True, actual > predicted is "better" (+1).
            If False, actual < predicted is "better" (+1).

    Returns:
        +1 if outcome is better than predicted,
        -1 if outcome is worse than predicted,
        0 if outcome is within tolerance of predicted.

    Examples:
        >>> error_sign(100.0, 110.0, tolerance=5.0, higher_is_better=True)
        1
        >>> error_sign(100.0, 90.0, tolerance=5.0, higher_is_better=True)
        -1
        >>> error_sign(100.0, 102.0, tolerance=5.0)
        0
    """
    diff = actual - predicted
    if abs(diff) <= tolerance:
        return 0
    if higher_is_better:
        return 1 if diff > 0 else -1
    return -1 if diff > 0 else 1


def compute_error(
    prediction: Prediction,
    outcome: Outcome,
    context: dict[str, Any] | None = None,
    *,
    pnl_scale: float = 100.0,
    latency_scale: float = 10.0,
    slippage_scale: float = 0.001,
    tolerance_pnl: float = 0.0,
    tolerance_latency: float = 0.0,
    tolerance_slippage: float = 0.0,
) -> ErrorSignal:
    """Compute comprehensive error signal from prediction and outcome.

    This function computes errors across multiple dimensions (PnL, latency,
    slippage) and produces a combined error signal suitable for controller
    adaptation.

    The overall normalized error is a weighted combination:
    - 60% weight on PnL error (primary trading objective)
    - 20% weight on latency error (execution quality)
    - 20% weight on slippage error (price quality)

    Args:
        prediction: The predicted outcome.
        outcome: The actual observed outcome.
        context: Optional system context (unused currently, for future use).
        pnl_scale: Scale for PnL error normalization.
        latency_scale: Scale for latency error normalization (ms).
        slippage_scale: Scale for slippage error normalization.
        tolerance_pnl: Tolerance for PnL sign determination.
        tolerance_latency: Tolerance for latency sign determination.
        tolerance_slippage: Tolerance for slippage sign determination.

    Returns:
        ErrorSignal with computed error metrics.

    Raises:
        ValueError: If prediction and outcome have different action_ids.

    Examples:
        >>> pred = Prediction(action_id="1", expected_pnl=100.0)
        >>> out = Outcome(action_id="1", actual_pnl=80.0)
        >>> err = compute_error(pred, out)
        >>> err.absolute_error > 0
        True
    """
    if prediction.action_id != outcome.action_id:
        raise ValueError("prediction and outcome must have the same action_id")

    # Compute per-dimension errors
    pnl_abs = absolute_error(prediction.expected_pnl, outcome.actual_pnl)
    pnl_rel = relative_error(prediction.expected_pnl, outcome.actual_pnl, pnl_scale)
    pnl_sign = error_sign(
        prediction.expected_pnl,
        outcome.actual_pnl,
        tolerance=tolerance_pnl,
        higher_is_better=True,  # Higher PnL is better
    )

    latency_abs = absolute_error(
        prediction.expected_latency_ms, outcome.actual_latency_ms
    )
    latency_rel = relative_error(
        prediction.expected_latency_ms, outcome.actual_latency_ms, latency_scale
    )
    latency_sign = error_sign(
        prediction.expected_latency_ms,
        outcome.actual_latency_ms,
        tolerance=tolerance_latency,
        higher_is_better=False,  # Lower latency is better
    )

    slippage_abs = absolute_error(prediction.expected_slippage, outcome.actual_slippage)
    slippage_rel = relative_error(
        prediction.expected_slippage, outcome.actual_slippage, slippage_scale
    )
    slippage_sign = error_sign(
        abs(prediction.expected_slippage),
        abs(outcome.actual_slippage),
        tolerance=tolerance_slippage,
        higher_is_better=False,  # Lower slippage is better
    )

    # Combined absolute error (weighted sum of absolute errors)
    combined_abs = (
        0.6 * (pnl_abs / pnl_scale)
        + 0.2 * (latency_abs / latency_scale)
        + 0.2 * (slippage_abs / slippage_scale)
    )

    # Combined normalized error (weighted average of normalized relative errors)
    # Convention: positive normalized_error = outcome better than expected
    #
    # For PnL (higher is better):
    #   relative_error = (predicted - actual) / scale
    #   If actual > predicted (better), relative_error < 0
    #   We want positive for better, so negate: -pnl_rel
    #
    # For latency (lower is better):
    #   If actual < predicted (better), relative_error > 0
    #   positive relative_error means better, so use as-is: latency_rel
    #
    # For slippage (lower is better):
    #   If actual < predicted (better), relative_error > 0
    #   positive relative_error means better, so use as-is: slippage_rel
    pnl_norm = normalize_error(-pnl_rel, scale=1.0)  # Negate: higher actual is better
    latency_norm = normalize_error(latency_rel, scale=1.0)  # Lower actual is better
    slippage_norm = normalize_error(slippage_rel, scale=1.0)  # Lower actual is better

    combined_norm = 0.6 * pnl_norm + 0.2 * latency_norm + 0.2 * slippage_norm

    # Weighted sign determination
    sign_weight = 0.6 * pnl_sign + 0.2 * latency_sign + 0.2 * slippage_sign
    if sign_weight > 0.1:
        combined_sign = 1
    elif sign_weight < -0.1:
        combined_sign = -1
    else:
        combined_sign = 0

    return ErrorSignal(
        action_id=prediction.action_id,
        absolute_error=combined_abs,
        relative_error=pnl_rel,  # Primary metric
        sign=combined_sign,
        normalized_error=combined_norm,
        components={
            "pnl_absolute": pnl_abs,
            "pnl_relative": pnl_rel,
            "pnl_normalized": pnl_norm,
            "pnl_sign": float(pnl_sign),
            "latency_absolute": latency_abs,
            "latency_relative": latency_rel,
            "latency_normalized": latency_norm,
            "latency_sign": float(latency_sign),
            "slippage_absolute": slippage_abs,
            "slippage_relative": slippage_rel,
            "slippage_normalized": slippage_norm,
            "slippage_sign": float(slippage_sign),
        },
    )


__all__ = [
    "absolute_error",
    "relative_error",
    "normalize_error",
    "error_sign",
    "compute_error",
]
