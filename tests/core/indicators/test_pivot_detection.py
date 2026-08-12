# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from core.indicators import (
    DivergenceClass,
    DivergenceKind,
    PivotDivergenceSignal,
    PivotPoint,
    detect_pivot_divergences,
    detect_pivots,
)


def test_detect_pivots_returns_expected_highs_and_lows() -> None:
    series = [1.0, 2.0, 3.0, 2.1, 1.2, 2.2, 3.4, 3.9, 3.2]
    highs, lows = detect_pivots(series, left=1, right=1, tolerance=1e-6)

    assert [p.index for p in highs] == [2, 7]
    assert [round(p.value, 2) for p in highs] == [3.0, 3.9]

    assert [p.index for p in lows] == [4]
    assert pytest.approx(lows[0].value, rel=1e-6) == 1.2


def test_detect_pivot_divergences_identifies_bearish_setup() -> None:
    price = [1.0, 3.2, 2.5, 4.1, 3.3, 5.2, 4.4]
    indicator = [1.0, 4.0, 2.2, 3.0, 2.7, 2.6, 2.1]

    signals = detect_pivot_divergences(price, indicator, left=1, right=1, tolerance=1e-6)

    assert len(signals) == 1
    signal = signals[0]

    assert signal.kind is DivergenceKind.BEARISH
    assert signal.divergence_class is DivergenceClass.REGULAR
    assert [p.index for p in signal.price_pivots] == [1, 3]
    assert [p.index for p in signal.indicator_pivots] == [1, 3]
    assert signal.price_change > 0
    assert signal.indicator_change < 0
    assert signal.strength > 0


def test_detect_pivot_divergences_identifies_bullish_setup() -> None:
    price = [5.0, 3.1, 3.8, 2.0, 3.0, 1.6, 2.5]
    indicator = [4.8, 2.4, 3.1, 2.2, 2.9, 2.6, 3.0]

    signals = detect_pivot_divergences(price, indicator, left=1, right=1, tolerance=1e-6)

    bullish_signals = [s for s in signals if s.kind is DivergenceKind.BULLISH]
    assert len(bullish_signals) == 1
    signal = bullish_signals[0]

    assert [p.index for p in signal.price_pivots] == [3, 5]
    assert [p.index for p in signal.indicator_pivots] == [3, 5]
    assert signal.price_change < 0
    assert signal.indicator_change > 0
    assert signal.divergence_class is DivergenceClass.REGULAR


def test_detect_pivot_divergences_identifies_hidden_bullish_setup() -> None:
    price = [5.0, 4.0, 4.6, 4.1, 4.9, 4.3, 5.2]
    indicator = [3.5, 3.0, 3.4, 2.5, 3.0, 2.6, 3.2]

    signals = detect_pivot_divergences(price, indicator, left=1, right=1, tolerance=1e-6)

    hidden_bullish = [
        s
        for s in signals
        if s.kind is DivergenceKind.BULLISH and s.divergence_class is DivergenceClass.HIDDEN
    ]
    assert len(hidden_bullish) == 1
    signal = hidden_bullish[0]

    assert [p.index for p in signal.price_pivots] == [1, 3]
    assert [p.index for p in signal.indicator_pivots] == [1, 3]
    assert signal.price_change > 0
    assert signal.indicator_change < 0


def test_detect_pivot_divergences_identifies_hidden_bearish_setup() -> None:
    price = [1.0, 3.5, 2.7, 3.2, 2.8, 3.0, 2.5]
    indicator = [1.0, 2.0, 1.5, 2.4, 1.8, 2.2, 1.6]

    signals = detect_pivot_divergences(price, indicator, left=1, right=1, tolerance=1e-6)

    hidden_bearish = [
        s
        for s in signals
        if s.kind is DivergenceKind.BEARISH and s.divergence_class is DivergenceClass.HIDDEN
    ]
    assert len(hidden_bearish) == 1
    signal = hidden_bearish[0]

    assert [p.index for p in signal.price_pivots] == [1, 3]
    assert [p.index for p in signal.indicator_pivots] == [1, 3]
    assert signal.price_change < 0
    assert signal.indicator_change > 0


def test_detect_pivot_divergences_respects_max_lag_constraint() -> None:
    price = [1.0, 2.6, 1.4, 3.4, 1.2, 2.7, 1.1, 3.3, 1.0]
    indicator = [1.0, 2.1, 2.4, 2.5, 2.6, 2.4, 2.5, 2.2, 1.9]

    lagged_signals = detect_pivot_divergences(price, indicator, left=1, right=1, tolerance=1e-6)
    constrained_signals = detect_pivot_divergences(
        price,
        indicator,
        left=1,
        right=1,
        tolerance=1e-6,
        max_lag=0,
    )

    assert lagged_signals  # baseline should detect at least one divergence
    assert all(isinstance(s, PivotDivergenceSignal) for s in lagged_signals)
    assert constrained_signals == []


def test_detect_pivots_validates_input_shapes() -> None:
    with pytest.raises(ValueError):
        detect_pivots([], left=1, right=0)

    with pytest.raises(ValueError):
        detect_pivot_divergences([1.0, 2.0], [1.0])

    def shrink(series: list[float]) -> list[float]:
        return series[:-1]

    with pytest.raises(ValueError):
        detect_pivot_divergences(
            [1.0, 2.0, 3.0],
            [2.0, 3.0, 4.0],
            indicator_normalizer=shrink,
        )


def test_detect_pivots_supports_timestamps() -> None:
    series = [1.0, 3.0, 1.0]
    timestamps = ["t0", "t1", "t2"]

    highs, lows = detect_pivots(series, left=1, right=1, timestamps=timestamps)

    assert highs == [PivotPoint(index=1, value=3.0, kind="high", timestamp="t1")]
    assert lows == []
