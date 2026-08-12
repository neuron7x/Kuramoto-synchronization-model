# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Normalization utilities for technical indicator time series.

The divergence detection routines operate on both price and indicator series.
Indicators, however, frequently expose wildly different scales (e.g. RSI on
``0–100`` vs. MACD spanning several orders of magnitude). To keep the
comparison robust we provide a lightweight normalisation layer that can be
used to align indicator magnitudes before they are paired with price data.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol, Tuple, Union, runtime_checkable

import numpy as np
from numpy.typing import ArrayLike, NDArray

Array1D = NDArray[np.float64]


class NormalizationMode(str, Enum):
    """Supported indicator normalisation strategies."""

    IDENTITY = "identity"
    Z_SCORE = "zscore"
    MIN_MAX = "minmax"


@runtime_checkable
class IndicatorNormalizer(Protocol):
    """Runtime protocol for normalising indicator series."""

    def __call__(self, series: ArrayLike) -> Array1D:  # pragma: no cover - protocol
        """Transform ``series`` into a normalised ``numpy.ndarray``."""


@dataclass(frozen=True, slots=True)
class IndicatorNormalizationConfig:
    """Configuration for built-in indicator normalisation strategies."""

    mode: NormalizationMode = NormalizationMode.Z_SCORE
    epsilon: float = 1e-12
    feature_range: Tuple[float, float] = (0.0, 1.0)

    def __post_init__(self) -> None:
        if self.epsilon <= 0:
            raise ValueError("epsilon must be strictly positive")
        low, high = self.feature_range
        if high <= low:
            raise ValueError("feature_range must satisfy high > low")

    def __call__(self, series: ArrayLike) -> Array1D:
        return normalize_indicator_series(series, config=self)


def _ensure_array(series: ArrayLike) -> Array1D:
    values = np.asarray(series, dtype=float)
    if values.ndim != 1:
        raise ValueError("series must be one-dimensional")
    return values.copy()


def _zscore_normalize(values: Array1D, *, epsilon: float) -> Array1D:
    mean = float(np.mean(values))
    std = float(np.std(values))
    if std <= epsilon:
        return np.zeros_like(values)
    return (values - mean) / std


def _minmax_normalize(
    values: Array1D, *, epsilon: float, feature_range: Tuple[float, float]
) -> Array1D:
    low, high = feature_range
    min_val = float(np.min(values))
    max_val = float(np.max(values))
    span = max_val - min_val
    if span <= epsilon:
        midpoint = (high + low) / 2.0
        return np.full_like(values, midpoint)
    scale = (high - low) / span
    return (values - min_val) * scale + low


def normalize_indicator_series(
    series: ArrayLike,
    *,
    mode: Optional[Union[NormalizationMode, str]] = None,
    config: Optional[IndicatorNormalizationConfig] = None,
) -> Array1D:
    """Normalise ``series`` and return a ``numpy.ndarray``.

    Parameters
    ----------
    series:
        Indicator observations ordered in time.
    mode:
        Optional name of the normalisation mode to apply. When ``None`` the
        ``config`` parameter is consulted. If both are omitted the default
        ``NormalizationMode.Z_SCORE`` is used.
    config:
        Optional :class:`IndicatorNormalizationConfig`. When supplied it takes
        precedence over ``mode``.
    """

    values = _ensure_array(series)
    if values.size == 0:
        return values

    if config is not None and mode is not None:
        raise ValueError("Provide either config or mode, not both")

    if config is None:
        resolved_mode = NormalizationMode(mode) if mode is not None else NormalizationMode.Z_SCORE
        config = IndicatorNormalizationConfig(mode=resolved_mode)

    if config.mode is NormalizationMode.IDENTITY:
        return values
    if config.mode is NormalizationMode.Z_SCORE:
        return _zscore_normalize(values, epsilon=config.epsilon)
    if config.mode is NormalizationMode.MIN_MAX:
        return _minmax_normalize(values, epsilon=config.epsilon, feature_range=config.feature_range)

    raise ValueError(f"Unsupported normalisation mode: {config.mode}")


def resolve_indicator_normalizer(
    normalizer: Optional[
        Union[str, NormalizationMode, IndicatorNormalizer, IndicatorNormalizationConfig]
    ],
) -> IndicatorNormalizer:
    """Resolve ``normalizer`` into a callable that normalises indicator series."""

    if normalizer is None:
        return IndicatorNormalizationConfig()

    if isinstance(normalizer, IndicatorNormalizationConfig):
        return normalizer

    if isinstance(normalizer, (str, NormalizationMode)):
        config = IndicatorNormalizationConfig(mode=NormalizationMode(normalizer))
        return config

    if callable(normalizer):

        def _wrapper(series: ArrayLike) -> Array1D:
            values = normalizer(series)
            array = np.asarray(values, dtype=float)
            if array.ndim != 1:
                raise ValueError("Indicator normalizer must return a one-dimensional array")
            return array.copy()

        return _wrapper

    raise TypeError("Unsupported normalizer type")


__all__ = [
    "Array1D",
    "IndicatorNormalizationConfig",
    "IndicatorNormalizer",
    "NormalizationMode",
    "normalize_indicator_series",
    "resolve_indicator_normalizer",
]
