"""Normalization helpers for indicator series.

The utilities in this module standardise indicator values before they are
paired with spot prices. Aligning the scale of heterogeneous inputs improves
the stability of comparative analytics such as divergence detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Sequence

import numpy as np

IndicatorNormalizer = Callable[[Sequence[float]], np.ndarray]


class NormalizationMode(str, Enum):
    """Enumeration of supported built-in normalization strategies."""

    ZSCORE = "zscore"
    MINMAX = "minmax"
    IDENTITY = "identity"


@dataclass(frozen=True, slots=True)
class IndicatorNormalizationConfig:
    """Configuration wrapper for delayed normalizer instantiation."""

    mode: NormalizationMode

    def build(self) -> IndicatorNormalizer:
        return resolve_indicator_normalizer(self.mode)


def _normalise_zscore(series: Sequence[float]) -> np.ndarray:
    values = np.asarray(series, dtype=float)
    if values.ndim != 1:
        msg = "indicator normaliser expects a one-dimensional sequence"
        raise ValueError(msg)
    mean = float(np.mean(values)) if values.size else 0.0
    std = float(np.std(values)) if values.size else 0.0
    if std <= 0.0:
        return values - mean
    return (values - mean) / std


def _normalise_minmax(series: Sequence[float]) -> np.ndarray:
    values = np.asarray(series, dtype=float)
    if values.ndim != 1:
        msg = "indicator normaliser expects a one-dimensional sequence"
        raise ValueError(msg)
    if not values.size:
        return values
    v_min = float(np.min(values))
    v_max = float(np.max(values))
    span = v_max - v_min
    if span <= 0.0:
        return values - v_min
    return (values - v_min) / span


def _normalise_identity(series: Sequence[float]) -> np.ndarray:
    values = np.asarray(series, dtype=float)
    if values.ndim != 1:
        msg = "indicator normaliser expects a one-dimensional sequence"
        raise ValueError(msg)
    return values


def resolve_indicator_normalizer(
    normalizer: IndicatorNormalizer | NormalizationMode | IndicatorNormalizationConfig | str | None,
) -> IndicatorNormalizer:
    """Resolve user-supplied normalizer descriptors into callables."""

    if normalizer is None:
        return _normalise_zscore

    if isinstance(normalizer, IndicatorNormalizationConfig):
        return resolve_indicator_normalizer(normalizer.mode)

    if isinstance(normalizer, NormalizationMode):
        mode = normalizer
    elif isinstance(normalizer, str):
        try:
            mode = NormalizationMode(normalizer.lower())
        except ValueError as exc:  # pragma: no cover - defensive branch
            raise ValueError(f"Unknown normalization mode: {normalizer}") from exc
    else:
        return normalizer

    if mode is NormalizationMode.ZSCORE:
        return _normalise_zscore
    if mode is NormalizationMode.MINMAX:
        return _normalise_minmax
    if mode is NormalizationMode.IDENTITY:
        return _normalise_identity

    raise ValueError(f"Unsupported normalization mode: {mode}")


__all__ = [
    "IndicatorNormalizer",
    "IndicatorNormalizationConfig",
    "NormalizationMode",
    "resolve_indicator_normalizer",
]

