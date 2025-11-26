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
from typing import Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np

from .normalization import (
    IndicatorNormalizationConfig,
    IndicatorNormalizer,
    NormalizationMode,
    resolve_indicator_normalizer,
)


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
    """Enumeration of supported divergence directions."""

    BULLISH = "bullish"
    BEARISH = "bearish"


class DivergenceClass(str, Enum):
    """Enumeration of divergence families detected by the algorithm."""

    REGULAR = "regular"
    HIDDEN = "hidden"


@dataclass(frozen=True, slots=True)
class PivotDivergenceSignal:
    """Encapsulates a divergence detected between price and indicator pivots."""

    kind: DivergenceKind
    divergence_class: DivergenceClass
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
            best_other = max(
                np.max(left_segment, initial=-np.inf),
                np.max(right_segment, initial=-np.inf),
            )
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
    indicator_normalizer: Optional[
        Union[str, NormalizationMode, IndicatorNormalizer, IndicatorNormalizationConfig]
    ] = None,
) -> List[PivotDivergenceSignal]:
    """Detect bullish and bearish divergences between price and indicator series.

    The function first extracts pivot highs and lows for both inputs. For each
    consecutive pair of price pivots it attempts to align indicator pivots
    within ``max_lag`` steps. Divergence is confirmed when price and indicator
    move in opposite directions beyond ``tolerance``. The routine recognises
    both regular structures (higher-high vs. lower-high, lower-low vs.
    higher-low) and hidden structures (lower-high vs. higher-high, higher-low
    vs. lower-low). Indicator series are first normalised using
    ``indicator_normalizer`` which defaults to ``z``-score scaling to mitigate
    scale-driven distortions when pairing heterogeneous indicators with spot
    prices.

    Parameters
    ----------
    indicator_normalizer:
        Optional normalisation strategy. Accepts a string alias (``"zscore"``,
        ``"minmax"``, ``"identity"``), :class:`NormalizationMode`, a custom
        callable, or an :class:`IndicatorNormalizationConfig` instance. Custom
        normalisers must return a one-dimensional array whose length matches
        ``indicator_series``.
    """

    if len(price_series) != len(indicator_series):
        raise ValueError("price_series and indicator_series must have equal length")

    if max_lag is not None and max_lag < 0:
        raise ValueError("max_lag must be non-negative when provided")

    price_values = np.asarray(price_series, dtype=float)
    if price_values.ndim != 1:
        raise ValueError("price_series must be one-dimensional")

    normalizer = resolve_indicator_normalizer(indicator_normalizer)
    indicator_values = normalizer(indicator_series)
    if indicator_values.shape != price_values.shape:
        raise ValueError("Indicator normalizer must preserve the input series length")

    highs_price, lows_price = detect_pivots(
        price_values,
        left=left,
        right=right,
        tolerance=tolerance,
        timestamps=timestamps,
    )
    highs_indicator, lows_indicator = detect_pivots(
        indicator_values,
        left=left,
        right=right,
        tolerance=tolerance,
        timestamps=timestamps,
    )

    signals: list[PivotDivergenceSignal] = []
    lag = max_lag if max_lag is not None else max(left, right)

    price_scale = float(np.max(np.abs(price_values))) if price_values.size else 0.0
    indicator_scale = float(np.std(indicator_values)) if indicator_values.size else 0.0
    price_scale = max(price_scale, tolerance)
    indicator_scale = max(indicator_scale, tolerance)

    def match_pivot(
        target: PivotPoint, candidates: Iterable[PivotPoint]
    ) -> Optional[PivotPoint]:
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
            if candidate_score < best_dist or (
                np.isclose(candidate_score, best_dist)
                and candidate.index <= target.index
            ):
                best = candidate
                best_dist = candidate_score
        return best

    def compute_strength(delta_price: float, delta_indicator: float) -> float:
        price_norm = abs(delta_price) / price_scale
        indicator_norm = abs(delta_indicator) / indicator_scale
        return price_norm + indicator_norm

    def append_signal(
        *,
        direction: DivergenceKind,
        classification: DivergenceClass,
        price_pair: Tuple[PivotPoint, PivotPoint],
        indicator_pair: Tuple[PivotPoint, PivotPoint],
        price_delta: float,
        indicator_delta: float,
    ) -> None:
        strength = compute_strength(price_delta, indicator_delta)
        signals.append(
            PivotDivergenceSignal(
                kind=direction,
                divergence_class=classification,
                price_pivots=price_pair,
                indicator_pivots=indicator_pair,
                price_change=price_delta,
                indicator_change=indicator_delta,
                strength=strength,
            )
        )

    for prev, curr in zip(highs_price, highs_price[1:]):
        prev_ind = match_pivot(prev, highs_indicator)
        curr_ind = match_pivot(curr, highs_indicator)
        if prev_ind is None or curr_ind is None:
            continue

        price_delta = curr.value - prev.value
        indicator_delta = curr_ind.value - prev_ind.value

        is_higher_high = price_delta > tolerance
        is_lower_high = price_delta < -tolerance
        indicator_lower_high = indicator_delta < -tolerance
        indicator_higher_high = indicator_delta > tolerance

        if is_higher_high and indicator_lower_high:
            append_signal(
                direction=DivergenceKind.BEARISH,
                classification=DivergenceClass.REGULAR,
                price_pair=(prev, curr),
                indicator_pair=(prev_ind, curr_ind),
                price_delta=price_delta,
                indicator_delta=indicator_delta,
            )
        elif is_lower_high and indicator_higher_high:
            append_signal(
                direction=DivergenceKind.BEARISH,
                classification=DivergenceClass.HIDDEN,
                price_pair=(prev, curr),
                indicator_pair=(prev_ind, curr_ind),
                price_delta=price_delta,
                indicator_delta=indicator_delta,
            )

    for prev, curr in zip(lows_price, lows_price[1:]):
        prev_ind = match_pivot(prev, lows_indicator)
        curr_ind = match_pivot(curr, lows_indicator)
        if prev_ind is None or curr_ind is None:
            continue

        price_delta = curr.value - prev.value
        indicator_delta = curr_ind.value - prev_ind.value

        is_lower_low = price_delta < -tolerance
        is_higher_low = price_delta > tolerance
        indicator_higher_low = indicator_delta > tolerance
        indicator_lower_low = indicator_delta < -tolerance

        if is_lower_low and indicator_higher_low:
            append_signal(
                direction=DivergenceKind.BULLISH,
                classification=DivergenceClass.REGULAR,
                price_pair=(prev, curr),
                indicator_pair=(prev_ind, curr_ind),
                price_delta=price_delta,
                indicator_delta=indicator_delta,
            )
        elif is_higher_low and indicator_lower_low:
            append_signal(
                direction=DivergenceKind.BULLISH,
                classification=DivergenceClass.HIDDEN,
                price_pair=(prev, curr),
                indicator_pair=(prev_ind, curr_ind),
                price_delta=price_delta,
                indicator_delta=indicator_delta,
            )

    return signals


__all__ = [
    "PivotPoint",
    "PivotDivergenceSignal",
    "DivergenceKind",
    "DivergenceClass",
    "detect_pivots",
    "detect_pivot_divergences",
]
