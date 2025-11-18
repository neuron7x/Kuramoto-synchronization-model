from __future__ import annotations

import numpy as np

from core.neuro.fractal import (
    fractal_dimension_from_hurst,
    hurst_exponent,
    summarise_fractal_properties,
)


def test_hurst_exponent_with_persistent_series() -> None:
    rng = np.random.default_rng(42)
    series = np.cumsum(rng.normal(scale=0.1, size=512))

    hurst = hurst_exponent(series)

    assert 0.0 <= hurst <= 1.0
    assert hurst > 0.5


def test_fractal_summary_matches_dimension_relationship() -> None:
    rng = np.random.default_rng(7)
    series = rng.normal(size=1024)

    summary = summarise_fractal_properties(series)
    mapping = summary.as_mapping()

    assert set(mapping) == {
        "hurst",
        "fractal_dim",
        "volatility",
        "scaling_exponent",
        "stability",
        "energy",
    }
    assert mapping["fractal_dim"] == fractal_dimension_from_hurst(mapping["hurst"])
