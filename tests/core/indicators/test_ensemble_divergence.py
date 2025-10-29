"""Tests for the ensemble divergence aggregator."""

from __future__ import annotations

import math

import pytest

from core.indicators import (
    DivergenceKind,
    EnsembleDivergenceResult,
    IndicatorDivergenceSignal,
    compute_ensemble_divergence,
)


def _make_signal(
    indicator: str,
    kind: DivergenceKind,
    *,
    strength: float,
    confidence: float = 1.0,
) -> IndicatorDivergenceSignal:
    return IndicatorDivergenceSignal(
        indicator=indicator,
        kind=kind,
        strength=strength,
        confidence=confidence,
    )


def test_compute_ensemble_divergence_requires_minimum_support() -> None:
    signals = [
        _make_signal("macd", DivergenceKind.BULLISH, strength=1.5),
        _make_signal("rsi", DivergenceKind.BEARISH, strength=1.1),
    ]

    result = compute_ensemble_divergence(signals, min_support=2)

    assert isinstance(result, EnsembleDivergenceResult)
    assert result.kind is None
    assert result.score == 0.0
    assert result.support == 0
    assert not result.contributing_signals


def test_compute_ensemble_divergence_prefers_direction_with_higher_consensus() -> None:
    signals = [
        _make_signal("macd", DivergenceKind.BULLISH, strength=2.0),
        _make_signal("rsi", DivergenceKind.BULLISH, strength=1.4, confidence=0.8),
        _make_signal("kuramoto", DivergenceKind.BEARISH, strength=1.6, confidence=0.2),
    ]

    result = compute_ensemble_divergence(signals, min_support=2, min_consensus=0.55)

    assert result.kind == DivergenceKind.BULLISH
    assert result.support == 2
    assert math.isclose(result.consensus, (1.0 + 0.8) / (1.0 + 0.8 + 0.2))
    assert result.score > 0.0
    assert len(result.contributing_signals) == 2
    assert len(result.conflicting_signals) == 1


def test_compute_ensemble_divergence_respects_min_consensus_threshold() -> None:
    signals = [
        _make_signal("macd", DivergenceKind.BULLISH, strength=3.0),
        _make_signal("rsi", DivergenceKind.BULLISH, strength=1.0, confidence=0.2),
        _make_signal("stoch", DivergenceKind.BEARISH, strength=0.8, confidence=0.8),
    ]

    # Bullish support count is sufficient (2), but the consensus ratio is only 0.6.
    result = compute_ensemble_divergence(signals, min_support=2, min_consensus=0.7)

    assert result.kind is None
    assert result.score == 0.0
    assert result.support == 0


def test_compute_ensemble_divergence_emits_negative_score_for_bearish_setup() -> None:
    signals = [
        _make_signal("macd", DivergenceKind.BEARISH, strength=2.5),
        _make_signal("rsi", DivergenceKind.BEARISH, strength=1.7),
        _make_signal("kuramoto", DivergenceKind.BEARISH, strength=1.2, confidence=0.5),
    ]

    result = compute_ensemble_divergence(signals, min_support=2, min_consensus=0.5)

    assert result.kind == DivergenceKind.BEARISH
    assert result.score < 0.0
    assert result.support == 3
    assert result.consensus == pytest.approx((1.0 + 1.0 + 0.5) / (1.0 + 1.0 + 0.5))


def test_compute_ensemble_divergence_validates_consensus_bounds() -> None:
    signals = [_make_signal("macd", DivergenceKind.BULLISH, strength=1.0)]

    with pytest.raises(ValueError):
        compute_ensemble_divergence(signals, min_consensus=0.0)
