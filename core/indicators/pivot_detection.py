"""Pivot-based divergence detection utilities.

The module implements a lightweight pivot detection algorithm inspired by
techniques used in charting packages such as TradingView's ``Divergence IQ``.
It exposes two public entry points:

``detect_pivots``
    Locate local extrema (pivot highs and lows) for a scalar time series using
    configurable look-back / look-ahead windows.

``detect_pivot_divergences``
    Pair price and indicator pivots to surface early bullish / bearish
    divergences. The function favours low latency by constraining the allowed
    lag between price and indicator pivots and by relying on the most recent
    confirmed pivots only.

Both routines are implemented without third party signal-processing
dependencies which keeps them portable while still offering a well-tested
baseline for technical-pattern analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np


@dataclass(frozen=True, slots=True)
class PivotPoint:
    """Represents a confirmed local extremum in a time series."""

    index: int
    value: float
    kind: str
    timestamp: Optional[object] = None

    def __post_init__(self) -> None:  # pragma: no cover - dataclass validation
        if self.kind not in {"high", "low"}:
            msg = "kind must be either 'high' or 'low'"
            raise ValueError(msg)


class DivergenceKind(str, Enum):
    """Enumeration of supported divergence archetypes."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    BULLISH_HIDDEN = "bullish_hidden"
    BEARISH_HIDDEN = "bearish_hidden"


@dataclass(frozen=True, slots=True)
class PivotDivergenceSignal:
    """Encapsulates a divergence detected between price and indicator pivots."""

    kind: DivergenceKind
    price_pivots: Tuple[PivotPoint, PivotPoint]
    indicator_pivots: Tuple[PivotPoint, PivotPoint]
    price_change: float
    indicator_change: float
    strength: float


def detect_pivots(
    series: Sequence[float],
    *,
    left: int = 3,
    right: int = 3,
    tolerance: float = 1e-9,
    timestamps: Optional[Sequence[object]] = None,
) -> Tuple[List[PivotPoint], List[PivotPoint]]:
    """Detect pivot highs and lows in ``series``.

    Parameters
    ----------
    series:
        Ordered sequence of price or indicator values.
    left / right:
        Number of neighbouring observations that must be lower (for highs) or
        higher (for lows) on either side of a pivot candidate. Higher values
        reduce noise at the expense of latency.
    tolerance:
        Minimum delta required between the candidate pivot value and the
        extremum of its surrounding window. This suppresses plateaus and
        repeated values from being flagged as pivots.
    timestamps:
        Optional sequence of timestamps aligned with ``series``. When provided,
        the timestamp from ``timestamps[i]`` is attached to the pivot detected
        at index ``i``.

    Returns
    -------
    tuple[list[PivotPoint], list[PivotPoint]]
        A pair ``(highs, lows)`` with strictly increasing indices.
    """

    if left < 1 or right < 1:
        raise ValueError("left and right must be positive integers")

    values = np.asarray(series, dtype=float)
    if values.ndim != 1:
        raise ValueError("series must be one-dimensional")

    n = values.size
    if n == 0:
        return [], []

    if timestamps is not None and len(timestamps) != n:
        raise ValueError("timestamps must match series length")

    highs: list[PivotPoint] = []
    lows: list[PivotPoint] = []

    window = left + right + 1
    if n < window:
        return highs, lows

    for idx in range(left, n - right):
        center = values[idx]
        segment = values[(idx - left) : (idx + right + 1)]

        left_segment = segment[:left]
        right_segment = segment[left + 1 :]

        is_high = np.all(center >= left_segment) and np.all(center >= right_segment)
        is_low = np.all(center <= left_segment) and np.all(center <= right_segment)

        if is_high:
            best_other = max(np.max(left_segment, initial=-np.inf), np.max(right_segment, initial=-np.inf))
            if center - best_other > tolerance:
                highs.append(
                    PivotPoint(
                        index=idx,
                        value=float(center),
                        kind="high",
                        timestamp=timestamps[idx] if timestamps is not None else None,
                    )
                )

        if is_low:
            best_other = min(
                np.min(left_segment, initial=np.inf),
                np.min(right_segment, initial=np.inf),
            )
            if best_other - center > tolerance:
                lows.append(
                    PivotPoint(
                        index=idx,
                        value=float(center),
                        kind="low",
                        timestamp=timestamps[idx] if timestamps is not None else None,
                    )
                )

    return highs, lows


def detect_pivot_divergences(
    price_series: Sequence[float],
    indicator_series: Sequence[float],
    *,
    left: int = 3,
    right: int = 3,
    tolerance: float = 1e-9,
    timestamps: Optional[Sequence[object]] = None,
    max_lag: Optional[int] = None,
) -> List[PivotDivergenceSignal]:
    """Detect bullish and bearish divergences between price and indicator series.

    The function first extracts pivot highs and lows for both inputs. For each
    consecutive pair of price pivots it attempts to align indicator pivots
    within ``max_lag`` steps. Divergence is confirmed when price and indicator
    move in opposite directions (higher-high vs. lower-high or lower-low vs.
    higher-low) beyond ``tolerance``.
    """

    if len(price_series) != len(indicator_series):
        raise ValueError("price_series and indicator_series must have equal length")

    if max_lag is not None and max_lag < 0:
        raise ValueError("max_lag must be non-negative when provided")

    highs_price, lows_price = detect_pivots(
        price_series,
        left=left,
        right=right,
        tolerance=tolerance,
        timestamps=timestamps,
    )
    highs_indicator, lows_indicator = detect_pivots(
        indicator_series,
        left=left,
        right=right,
        tolerance=tolerance,
        timestamps=timestamps,
    )

    signals: list[PivotDivergenceSignal] = []
    lag = max_lag if max_lag is not None else max(left, right)

    def match_pivot(target: PivotPoint, candidates: Iterable[PivotPoint]) -> Optional[PivotPoint]:
        best: Optional[PivotPoint] = None
        best_dist = np.inf
        for candidate in candidates:
            dist = abs(candidate.index - target.index)
            if dist > lag:
                continue
            # Prefer non-forward looking matches to keep latency minimal
            is_forward = candidate.index > target.index
            if best is None:
                best = candidate
                best_dist = dist - (0.25 if not is_forward else 0.0)
                continue
            candidate_score = dist - (0.25 if not is_forward else 0.0)
            if candidate_score < best_dist or (np.isclose(candidate_score, best_dist) and candidate.index <= target.index):
                best = candidate
                best_dist = candidate_score
        return best

    def compute_strength(delta_price: float, base_price: float, delta_indicator: float, base_indicator: float) -> float:
        price_norm = abs(delta_price) / max(abs(base_price), tolerance)
        indicator_norm = abs(delta_indicator) / max(abs(base_indicator), tolerance)
        return price_norm + indicator_norm

    for prev, curr in zip(highs_price, highs_price[1:]):
        prev_ind = match_pivot(prev, highs_indicator)
        curr_ind = match_pivot(curr, highs_indicator)
        if prev_ind is None or curr_ind is None:
            continue
        price_delta = curr.value - prev.value
        indicator_delta = curr_ind.value - prev_ind.value
        signal_kind: Optional[DivergenceKind] = None
        if price_delta > tolerance and indicator_delta < -tolerance:
            signal_kind = DivergenceKind.BEARISH
        elif price_delta < -tolerance and indicator_delta > tolerance:
            signal_kind = DivergenceKind.BEARISH_HIDDEN
        if signal_kind is None:
            continue
        strength = compute_strength(price_delta, prev.value, indicator_delta, prev_ind.value)
        signals.append(
            PivotDivergenceSignal(
                kind=signal_kind,
                price_pivots=(prev, curr),
                indicator_pivots=(prev_ind, curr_ind),
                price_change=price_delta,
                indicator_change=indicator_delta,
                strength=strength,
            )
        )

    for prev, curr in zip(lows_price, lows_price[1:]):
        prev_ind = match_pivot(prev, lows_indicator)
        curr_ind = match_pivot(curr, lows_indicator)
        if prev_ind is None or curr_ind is None:
            continue
        price_delta = curr.value - prev.value
        indicator_delta = curr_ind.value - prev_ind.value
        signal_kind: Optional[DivergenceKind] = None
        if price_delta < -tolerance and indicator_delta > tolerance:
            signal_kind = DivergenceKind.BULLISH
        elif price_delta > tolerance and indicator_delta < -tolerance:
            signal_kind = DivergenceKind.BULLISH_HIDDEN
        if signal_kind is None:
            continue
        strength = compute_strength(price_delta, prev.value, indicator_delta, prev_ind.value)
        signals.append(
            PivotDivergenceSignal(
                kind=signal_kind,
                price_pivots=(prev, curr),
                indicator_pivots=(prev_ind, curr_ind),
                price_change=price_delta,
                indicator_change=indicator_delta,
                strength=strength,
            )
        )

    return signals


__all__ = [
    "PivotPoint",
    "PivotDivergenceSignal",
    "DivergenceKind",
    "detect_pivots",
    "detect_pivot_divergences",
]

