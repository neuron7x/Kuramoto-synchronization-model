"""Signal computation primitives.

This module provides core data structures and algorithms for computing
trading signals from feature observations.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean
from typing import Iterable, Sequence

from ..config import SignalSettings
from ..errors import SignalComputationError

# Volatility floor constant to prevent division by zero
VOLATILITY_FLOOR = 1e-12


@dataclass(frozen=True, slots=True)
class FeatureObservation:
    """A feature value associated with an instrument.
    
    Features are individual market indicators (e.g., momentum, volatility)
    that contribute to the final signal computation.
    
    Attributes:
        instrument: Instrument identifier (e.g., ticker symbol)
        name: Feature name (e.g., "momentum", "volatility")
        value: Raw feature value
        mean: Optional historical mean for normalization
        std: Optional historical standard deviation for normalization
        weight: Relative importance weight (default 1.0)
    """

    instrument: str
    name: str
    value: float
    mean: float | None = None
    std: float | None = None
    weight: float = 1.0

    def zscore(self) -> float:
        """Compute the standardized (z-score) value.
        
        If standard deviation is provided and non-zero, returns
        (value - mean) / std. Otherwise returns value - mean.
        
        Returns:
            Standardized feature value
        """
        if self.std is None or abs(self.std) <= VOLATILITY_FLOOR:
            return self.value - (self.mean or 0.0)
        return (self.value - (self.mean or 0.0)) / self.std


@dataclass(frozen=True, slots=True)
class Signal:
    """Represents the signal strength for an instrument.
    
    Signals aggregate multiple features into a single strength value
    that indicates trading conviction for an instrument.
    
    Attributes:
        instrument: Instrument identifier
        strength: Normalized signal strength (typically -1 to 1)
        contributors: Tuple of feature names that contributed to this signal
    """

    instrument: str
    strength: float
    contributors: Sequence[str]


def _rescale(value: float, settings: SignalSettings) -> float:
    """Rescale a value to the configured min/max range.
    
    Maps the input value to the range [rescale_min, rescale_max] using
    a linear transformation centered at the midpoint.
    
    Args:
        value: Input value to rescale
        settings: Signal settings with rescale bounds
        
    Returns:
        Rescaled value clamped to [rescale_min, rescale_max]
    """
    span = settings.rescale_max - settings.rescale_min
    midpoint = settings.rescale_min + span / 2
    scaled = max(settings.rescale_min, min(settings.rescale_max, midpoint + value * (span / 2)))
    return scaled


def compute_signal(feature_bundle: Sequence[FeatureObservation], settings: SignalSettings) -> Signal:
    """Compute a bounded signal for a collection of related features.
    
    This function:
    1. Computes z-scores for all features
    2. Applies weights to create a weighted average
    3. Applies exponential smoothing
    4. Rescales to configured bounds
    
    The algorithm ensures numerical stability and O(n) complexity.
    
    Args:
        feature_bundle: Collection of features for a single instrument
        settings: Signal computation parameters
        
    Returns:
        Computed signal with strength and contributors
        
    Raises:
        SignalComputationError: If feature_bundle is empty
    """
    if not feature_bundle:
        raise SignalComputationError(
            "feature_bundle cannot be empty",
            code="EmptyFeatureBundle",
        )

    # Compute weighted z-scores (O(n) complexity)
    weighted_values = []
    weights = []
    contributors: list[str] = []
    for feature in feature_bundle:
        zscore = feature.zscore()
        weighted_values.append(zscore * feature.weight)
        weights.append(feature.weight)
        contributors.append(feature.name)

    # Normalize by total weight to prevent overflow
    mean_weight = sum(weights) if weights else 1.0
    normalized = sum(weighted_values) / mean_weight
    
    # Apply exponential smoothing for numerical stability
    smoothed = (1 - settings.smoothing_factor) * fmean([f.zscore() for f in feature_bundle]) + settings.smoothing_factor * normalized
    
    # Rescale to configured bounds
    strength = _rescale(smoothed, settings)
    
    # Return immutable signal with deterministic contributor ordering
    return Signal(instrument=feature_bundle[0].instrument, strength=strength, contributors=tuple(contributors))


def build_signal_ensemble(features: Iterable[FeatureObservation], settings: SignalSettings) -> list[Signal]:
    """Group features by instrument and compute their signals.
    
    This function ensures O(n) complexity by:
    1. Single pass to group features by instrument
    2. Single signal computation per instrument group
    
    Args:
        features: Iterable of feature observations (potentially from multiple instruments)
        settings: Signal computation parameters
        
    Returns:
        List of signals, one per instrument
    """
    # Group features by instrument (O(n))
    grouped: dict[str, list[FeatureObservation]] = {}
    for feature in features:
        grouped.setdefault(feature.instrument, []).append(feature)

    # Compute signal for each instrument group (O(n) total)
    return [compute_signal(bundle, settings) for bundle in grouped.values()]


__all__ = ["FeatureObservation", "Signal", "build_signal_ensemble", "compute_signal"]
