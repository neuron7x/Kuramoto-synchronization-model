from __future__ import annotations

import numpy as np
import pytest

from core.indicators import (
    IndicatorNormalizationConfig,
    NormalizationMode,
    normalize_indicator_series,
    resolve_indicator_normalizer,
)


def test_zscore_normalization_centres_and_scales_unit_variance() -> None:
    series = [10.0, 12.0, 14.0, 16.0, 18.0]

    normalized = normalize_indicator_series(series, mode="zscore")

    assert pytest.approx(float(np.mean(normalized)), abs=1e-12) == 0.0
    assert pytest.approx(float(np.std(normalized)), rel=1e-6) == 1.0


def test_minmax_normalization_respects_feature_range() -> None:
    config = IndicatorNormalizationConfig(mode=NormalizationMode.MIN_MAX, feature_range=(-1.0, 1.0))

    normalized = normalize_indicator_series([5.0, 10.0, 15.0], config=config)

    assert pytest.approx(float(normalized[0]), abs=1e-12) == -1.0
    assert pytest.approx(float(normalized[-1]), abs=1e-12) == 1.0
    assert -1.0 <= float(np.min(normalized)) <= float(np.max(normalized)) <= 1.0


def test_resolve_indicator_normalizer_accepts_custom_callable() -> None:
    def halve(series: list[float]) -> np.ndarray:
        return np.asarray(series, dtype=float) / 2.0

    normalizer = resolve_indicator_normalizer(halve)
    result = normalizer([2.0, 4.0, 6.0])

    assert result.tolist() == [1.0, 2.0, 3.0]
