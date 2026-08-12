# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Signal computation primitives."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean
from typing import Iterable, Sequence

from ..config import SignalSettings
from ..constants import ZERO_STD_THRESHOLD


@dataclass(slots=True, frozen=True)
class FeatureObservation:
    """A feature value associated with an instrument.

    Attributes:
        instrument: Instrument identifier
        name: Feature name
        value: Raw feature value
        mean: Optional mean for normalization
        std: Optional standard deviation for normalization
        weight: Feature weight for aggregation (default: 1.0)
    """

    instrument: str
    name: str
    value: float
    mean: float | None = None
    std: float | None = None
    weight: float = 1.0

    def zscore(self) -> float:
        """Compute the standardized z-score of the feature value.

        Returns:
            Standardized value (z-score)
        """
        if self.std is None or abs(self.std) <= ZERO_STD_THRESHOLD:
            return self.value - (self.mean or 0.0)
        return (self.value - (self.mean or 0.0)) / self.std


@dataclass(slots=True, frozen=True)
class Signal:
    """Represents the signal strength for an instrument.

    Attributes:
        instrument: Instrument identifier
        strength: Computed signal strength in range [rescale_min, rescale_max]
        contributors: Names of features that contributed to this signal
    """

    instrument: str
    strength: float
    contributors: Sequence[str]


def _rescale(value: float, settings: SignalSettings) -> float:
    """Rescale a value to the configured signal range.

    Args:
        value: Value to rescale
        settings: Signal settings containing rescale bounds

    Returns:
        Rescaled value bounded to [rescale_min, rescale_max]
    """
    span = settings.rescale_max - settings.rescale_min
    midpoint = settings.rescale_min + span / 2
    scaled = max(settings.rescale_min, min(settings.rescale_max, midpoint + value * (span / 2)))
    return scaled


def compute_signal(
    feature_bundle: Sequence[FeatureObservation], settings: SignalSettings
) -> Signal:
    """Compute a bounded signal for a collection of related features.

    Args:
        feature_bundle: Sequence of features for the same instrument
        settings: Signal computation settings

    Returns:
        Computed signal for the instrument

    Raises:
        ValueError: If feature_bundle is empty
    """
    if not feature_bundle:
        msg = "feature_bundle cannot be empty"
        raise ValueError(msg)

    weighted_values: list[float] = []
    weights: list[float] = []
    contributors: list[str] = []

    for feature in feature_bundle:
        zscore = feature.zscore()
        weighted_values.append(zscore * feature.weight)
        weights.append(feature.weight)
        contributors.append(feature.name)

    mean_weight = sum(weights) if weights else 1.0
    normalized = sum(weighted_values) / mean_weight
    smoothed = (1 - settings.smoothing_factor) * fmean(
        [f.zscore() for f in feature_bundle]
    ) + settings.smoothing_factor * normalized
    strength = _rescale(smoothed, settings)
    return Signal(
        instrument=feature_bundle[0].instrument,
        strength=strength,
        contributors=tuple(contributors),
    )


def build_signal_ensemble(
    features: Iterable[FeatureObservation], settings: SignalSettings
) -> list[Signal]:
    """Group features by instrument and compute their signal.

    Args:
        features: Iterable of feature observations
        settings: Signal computation settings

    Returns:
        List of computed signals, one per unique instrument
    """
    grouped: dict[str, list[FeatureObservation]] = {}
    for feature in features:
        grouped.setdefault(feature.instrument, []).append(feature)

    return [compute_signal(bundle, settings) for bundle in grouped.values()]


__all__ = ["FeatureObservation", "Signal", "build_signal_ensemble", "compute_signal"]
