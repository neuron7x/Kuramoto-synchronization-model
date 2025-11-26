"""Ensemble divergence utilities for cross-indicator confirmation.

The module aggregates divergence signals produced by heterogeneous technical
indicators—such as MACD, RSI, or Kuramoto phase synchronisation—into a single
consensus score. Requiring multiple indicators to align before emitting a
signal reduces false positives compared to acting on any individual indicator
in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence, Tuple

from .pivot_detection import DivergenceKind


@dataclass(frozen=True, slots=True)
class IndicatorDivergenceSignal:
    """Represents a divergence emitted by a technical indicator.

    Parameters
    ----------
    indicator:
        Name of the indicator producing the divergence (e.g. ``"macd"``).
    kind:
        Direction of the divergence (bullish or bearish).
    strength:
        Non-negative magnitude describing how forceful the divergence is. The
        scale is indicator-specific, but higher values should imply stronger
        conviction.
    confidence:
        Optional weight in the inclusive range ``[0, 1]`` reflecting the
        reliability of the signal. Defaults to 1 (fully trusted).
    timestamp:
        Optional timestamp aligned with the raw indicator observation that
        triggered the divergence.
    """

    indicator: str
    kind: DivergenceKind
    strength: float
    confidence: float = 1.0
    timestamp: object | None = None

    def __post_init__(self) -> None:  # pragma: no cover - dataclass validation
        if not isinstance(self.indicator, str) or not self.indicator:
            msg = "indicator must be a non-empty string"
            raise ValueError(msg)

        if self.strength < 0.0:
            msg = "strength must be non-negative"
            raise ValueError(msg)

        if not 0.0 <= self.confidence <= 1.0:
            msg = "confidence must lie within [0, 1]"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class EnsembleDivergenceResult:
    """Outcome of the ensemble divergence aggregation.

    Attributes
    ----------
    kind:
        Consensus divergence direction if the ensemble confirms a signal,
        otherwise ``None``.
    score:
        Signed consensus score in ``[-1, 1]``. Positive values indicate
        bullish divergence, negative values indicate bearish divergence, and
        zero denotes indeterminate consensus.
    consensus:
        Fraction of total confidence mass that agreed with ``kind``.
    support:
        Number of indicator signals that supported ``kind``.
    contributing_signals:
        Signals that supported ``kind``.
    conflicting_signals:
        Signals that opposed ``kind``.
    """

    kind: DivergenceKind | None
    score: float
    consensus: float
    support: int
    contributing_signals: Tuple[IndicatorDivergenceSignal, ...]
    conflicting_signals: Tuple[IndicatorDivergenceSignal, ...]

    @property
    def is_confirmed(self) -> bool:
        """Whether the ensemble produced a directional divergence."""

        return self.kind is not None and self.score != 0.0


def compute_ensemble_divergence(
    signals: Iterable[IndicatorDivergenceSignal],
    *,
    min_support: int = 2,
    min_consensus: float = 0.6,
) -> EnsembleDivergenceResult:
    """Aggregate divergence signals from multiple indicators into a consensus.

    The aggregator enforces two safeguards before emitting a directional
    signal:

    * ``min_support`` – the minimum number of indicators that must agree on a
      direction.
    * ``min_consensus`` – the minimum fraction of total confidence mass that
      must support the winning direction.

    Signals failing these thresholds yield a neutral (zero-score) result. When
    the thresholds are satisfied, the score is a hyperbolically squashed
    weighted average of the supporting strengths, modulated by the consensus
    fraction. The sign of the score reflects the divergence direction.

    Parameters
    ----------
    signals:
        Iterable of individual indicator divergences to aggregate. The
        iterable is materialised internally, so generators are supported.
    min_support:
        Minimum number of agreeing signals required to confirm a divergence.
    min_consensus:
        Minimum share of total confidence mass that must agree on the winning
        direction.
    """

    if not 0.0 < min_consensus <= 1.0:
        msg = "min_consensus must lie within (0, 1]"
        raise ValueError(msg)

    if min_support < 1:
        msg = "min_support must be a positive integer"
        raise ValueError(msg)

    materialised = tuple(signals)

    if not materialised:
        return EnsembleDivergenceResult(
            kind=None,
            score=0.0,
            consensus=0.0,
            support=0,
            contributing_signals=tuple(),
            conflicting_signals=tuple(),
        )

    bullish, bearish = _partition_signals(materialised)

    total_confidence = sum(signal.confidence for signal in materialised)
    if total_confidence == 0.0:
        return EnsembleDivergenceResult(
            kind=None,
            score=0.0,
            consensus=0.0,
            support=0,
            contributing_signals=tuple(),
            conflicting_signals=tuple(materialised),
        )

    bull_metrics = _summarise_signals(bullish)
    bear_metrics = _summarise_signals(bearish)

    candidate = _select_candidate(
        bull_metrics,
        bear_metrics,
        min_support=min_support,
        min_consensus=min_consensus,
        total_confidence=total_confidence,
    )

    if candidate is None:
        return EnsembleDivergenceResult(
            kind=None,
            score=0.0,
            consensus=0.0,
            support=0,
            contributing_signals=tuple(),
            conflicting_signals=tuple(materialised),
        )

    kind, summary = candidate
    supporting_raw = bullish if kind == DivergenceKind.BULLISH else bearish
    opposing_raw = bearish if kind == DivergenceKind.BULLISH else bullish
    supporting = tuple(signal for signal in supporting_raw if signal.confidence > 0.0)
    opposing = tuple(signal for signal in opposing_raw if signal.confidence > 0.0)
    avg_strength = (
        summary.weighted_strength / summary.confidence if summary.confidence else 0.0
    )
    consensus = summary.confidence / total_confidence
    score = _squash(avg_strength * consensus)
    if kind == DivergenceKind.BEARISH:
        score *= -1.0

    return EnsembleDivergenceResult(
        kind=kind,
        score=score,
        consensus=consensus,
        support=summary.count,
        contributing_signals=supporting,
        conflicting_signals=opposing,
    )


@dataclass(frozen=True, slots=True)
class _Summary:
    count: int
    confidence: float
    weighted_strength: float


def _partition_signals(
    signals: Iterable[IndicatorDivergenceSignal],
) -> Tuple[
    Tuple[IndicatorDivergenceSignal, ...], Tuple[IndicatorDivergenceSignal, ...]
]:
    bullish: list[IndicatorDivergenceSignal] = []
    bearish: list[IndicatorDivergenceSignal] = []

    for signal in signals:
        if signal.kind == DivergenceKind.BULLISH:
            bullish.append(signal)
        else:
            bearish.append(signal)

    return tuple(bullish), tuple(bearish)


def _summarise_signals(signals: Sequence[IndicatorDivergenceSignal]) -> _Summary:
    confidence = sum(signal.confidence for signal in signals)
    weighted_strength = sum(signal.confidence * signal.strength for signal in signals)
    count = sum(1 for signal in signals if signal.confidence > 0.0)
    return _Summary(
        count=count, confidence=confidence, weighted_strength=weighted_strength
    )


def _select_candidate(
    bull: _Summary,
    bear: _Summary,
    *,
    min_support: int,
    min_consensus: float,
    total_confidence: float,
) -> Tuple[DivergenceKind, _Summary] | None:
    """Pick the divergence direction that satisfies consensus thresholds."""

    candidates: list[tuple[DivergenceKind, _Summary]] = []
    if (
        bull.count >= min_support
        and (bull.confidence / total_confidence) >= min_consensus
    ):
        candidates.append((DivergenceKind.BULLISH, bull))

    if (
        bear.count >= min_support
        and (bear.confidence / total_confidence) >= min_consensus
    ):
        candidates.append((DivergenceKind.BEARISH, bear))

    if not candidates:
        return None

    # Prioritise the direction with the higher consensus-adjusted strength.
    chosen_kind, chosen_summary = max(
        candidates,
        key=lambda item: item[1].weighted_strength
        * (item[1].confidence / total_confidence),
    )

    return chosen_kind, chosen_summary


def _squash(value: float) -> float:
    """Bound ``value`` to ``[-1, 1]`` via a numerically stable tanh."""

    if value == 0.0:
        return 0.0

    if value > 15.0:
        return 1.0

    if value < -15.0:
        return -1.0

    from math import tanh

    return tanh(value)
