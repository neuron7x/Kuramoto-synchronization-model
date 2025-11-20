"""Utilities for measuring convergence between multiple trading signals.

This module provides a light-weight "convergence detector" that evaluates whether
different indicators (for example, MACD, RSI, price momentum) move in the same
direction and with comparable strength.  The detector focuses on two
complementary concepts:

* **Directional alignment** – do the signals point to the same side?
* **Support strength** – is the majority direction backed by stronger
  magnitudes than the opposing side?

The metrics are designed for downstream analytics where consistent confirmation
between indicators increases confidence in a trading decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, MutableMapping

import numpy as np
import pandas as pd

DEFAULT_EPSILON = 1e-12


def _as_dataframe(
    signals: Mapping[str, pd.Series] | pd.DataFrame,
    *,
    join: str,
) -> pd.DataFrame:
    """Coerce a mapping of series or dataframe into a clean DataFrame.

    Parameters
    ----------
    signals:
        Mapping of signal names to series or a pre-built DataFrame where each
        column represents an indicator timeline.
    join:
        Join strategy when aligning indexes across signals (``"inner"`` or
        ``"outer"``).  ``"inner"`` is safer for statistical ratios as it removes
        missing values.

    Returns
    -------
    pd.DataFrame
        The aligned data frame with float dtype columns.
    """

    if isinstance(signals, pd.DataFrame):
        frame = signals.copy()
    else:
        if not signals:
            raise ValueError("`signals` mapping cannot be empty")
        items = list(signals.items())
        frame = pd.concat([value for _, value in items], axis=1, join=join)
        frame.columns = [key for key, _ in items]

    if frame.empty:
        return frame.astype(float)

    frame = frame.sort_index()
    frame = frame.apply(pd.to_numeric, errors="coerce").astype(float)
    frame = frame.replace([np.inf, -np.inf], np.nan)
    return frame


def _directional_change(
    series: pd.Series,
    *,
    window: int,
    method: str,
) -> pd.Series:
    """Return the directional change for a signal.

    ``method`` can be ``"diff"`` (absolute difference) or ``"pct"`` (percentage
    change).  A ``window`` greater than one looks further back when assessing
    the direction.
    """

    if series.empty:
        return series.copy()

    if method == "diff":
        change = series.diff(periods=window)
    elif method == "pct":
        change = series.pct_change(periods=window)
    else:
        raise ValueError(f"Unsupported method '{method}'. Expected 'diff' or 'pct'.")

    return change.astype(float)


def _smooth(series: pd.Series, *, window: int | None) -> pd.Series:
    if window is None or window <= 1:
        return series
    return series.rolling(window=window, min_periods=1).mean()


def _normalise_magnitude(change: pd.Series) -> pd.Series:
    """Normalise magnitudes via a robust median-based scaling."""

    if change.empty:
        return change.copy()

    abs_change = change.abs()
    median = float(np.nanmedian(abs_change.to_numpy()))
    if not np.isfinite(median) or median < DEFAULT_EPSILON:
        median = float(np.nanmean(abs_change.to_numpy()))
    if not np.isfinite(median) or median < DEFAULT_EPSILON:
        return pd.Series(0.0, index=change.index)
    return abs_change / median


def _sign_matrix(values: pd.DataFrame, *, tolerance: float) -> pd.DataFrame:
    """Convert a matrix of directional changes into {-1, 0, +1} signs."""

    sign = np.sign(values)
    if tolerance > 0.0:
        mask = values.abs() < tolerance
        sign = sign.mask(mask, other=0.0)
    return sign


def _majority_sign(signs: pd.DataFrame) -> pd.Series:
    summed = signs.sum(axis=1)
    return np.sign(summed).astype(float)


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator = denominator.replace(0.0, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        result = numerator / denominator
    return result.fillna(0.0)


@dataclass(slots=True)
class ConvergenceConfig:
    """Configuration for :class:`ConvergenceDetector`."""

    window: int = 1
    method: str = "pct"
    smoothing: int | None = None
    tolerance: float = 1e-6
    join: str = "inner"

    def validate(self) -> None:
        if self.window < 1:
            raise ValueError("`window` must be >= 1")
        if self.join not in {"inner", "outer"}:
            raise ValueError("`join` must be 'inner' or 'outer'")
        if self.method not in {"diff", "pct"}:
            raise ValueError("`method` must be 'diff' or 'pct'")
        if self.tolerance < 0.0:
            raise ValueError("`tolerance` must be non-negative")


@dataclass(slots=True)
class ConvergenceScores:
    """Aggregated convergence metrics."""

    alignment: pd.Series
    support_ratio: pd.Series
    strength_diff: pd.Series

    def latest(self) -> pd.Series:
        """Return the latest available measurements as a Series."""

        if self.alignment.empty:
            return pd.Series(dtype=float)
        idx = self.alignment.index[-1]
        return pd.Series(
            {
                "alignment": float(self.alignment.iloc[-1]),
                "support_ratio": float(self.support_ratio.loc[idx]),
                "strength_diff": float(self.strength_diff.loc[idx]),
            }
        )


class ConvergenceDetector:
    """Compute convergence metrics for a collection of directional signals."""

    def __init__(self, config: ConvergenceConfig | None = None) -> None:
        self.config = config or ConvergenceConfig()
        self.config.validate()

    def compute(
        self, signals: Mapping[str, pd.Series] | pd.DataFrame
    ) -> ConvergenceScores:
        """Evaluate convergence metrics for the provided signals."""

        cfg = self.config
        frame = _as_dataframe(signals, join=cfg.join)
        if frame.empty or frame.shape[1] == 0:
            empty = pd.Series(dtype=float)
            return ConvergenceScores(empty, empty, empty)

        direction_changes: MutableMapping[str, pd.Series] = {}
        for column in frame.columns:
            change = _directional_change(
                frame[column], window=cfg.window, method=cfg.method
            )
            change = _smooth(change, window=cfg.smoothing)
            direction_changes[column] = change

        direction_df = pd.DataFrame(direction_changes)
        sign_df = _sign_matrix(direction_df, tolerance=cfg.tolerance)

        active_mask = sign_df.notna() & (sign_df != 0)
        counts = active_mask.sum(axis=1)
        alignment = _safe_divide(sign_df.sum(axis=1), counts)

        majority = _majority_sign(sign_df)
        majority_mask = sign_df.eq(majority, axis=0) & active_mask
        support_ratio = _safe_divide(majority_mask.sum(axis=1), counts)

        magnitude_cols: MutableMapping[str, pd.Series] = {}
        for column in direction_df.columns:
            magnitude_cols[column] = _normalise_magnitude(direction_df[column])
        magnitude_df = pd.DataFrame(magnitude_cols)

        majority_strength = magnitude_df.where(majority_mask).sum(axis=1)
        majority_count = majority_mask.sum(axis=1)
        majority_strength = _safe_divide(majority_strength, majority_count)

        opposing_mask = active_mask & ~majority_mask
        opposing_strength = magnitude_df.where(opposing_mask).sum(axis=1)
        opposing_count = opposing_mask.sum(axis=1)
        opposing_strength = _safe_divide(opposing_strength, opposing_count)

        strength_diff = (majority_strength - opposing_strength).fillna(0.0)

        return ConvergenceScores(
            alignment=alignment,
            support_ratio=support_ratio,
            strength_diff=strength_diff,
        )


def compute_convergence(
    signals: Mapping[str, pd.Series] | pd.DataFrame,
    config: ConvergenceConfig | None = None,
) -> ConvergenceScores:
    """Convenience wrapper around :class:`ConvergenceDetector.compute`."""

    detector = ConvergenceDetector(config=config)
    return detector.compute(signals)


def is_convergent(
    scores: ConvergenceScores,
    *,
    alignment_threshold: float = 0.8,
    support_ratio_threshold: float = 0.6,
    strength_diff_threshold: float = 0.0,
) -> pd.Series:
    """Determine convergence flags based on score thresholds.

    Parameters
    ----------
    scores:
        Output from :class:`ConvergenceDetector`.
    alignment_threshold:
        Minimum average direction agreement in ``[-1, 1]`` required.
    support_ratio_threshold:
        Minimum fraction of actively moving signals backing the majority
        direction.
    strength_diff_threshold:
        Minimum excess strength of majority-aligned signals over the opposing
        side.
    """

    if scores.alignment.empty:
        return pd.Series(dtype=bool)

    alignment_mask = scores.alignment >= alignment_threshold
    support_mask = scores.support_ratio >= support_ratio_threshold
    strength_mask = scores.strength_diff >= strength_diff_threshold
    return alignment_mask & support_mask & strength_mask


__all__ = [
    "ConvergenceConfig",
    "ConvergenceDetector",
    "ConvergenceScores",
    "compute_convergence",
    "is_convergent",
]
