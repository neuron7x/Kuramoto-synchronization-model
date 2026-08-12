# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import numpy as np

from core.neuro.fractal import (
    multiscale_energy,
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


def test_multiscale_energy_accumulates_every_resolved_scale() -> None:
    """`if data.size <= scale: break` stops the loop only when the series is too short.

    Under `LtE -> Gt` the guard becomes `data.size > scale: break`, which fires on the very
    first scale (any non-trivial series is longer than scale 1), so the loop collects nothing
    and the function returns the empty-path 0.0 for every input. A unit ramp has increment ==
    scale at lag `scale`, so over scales 1..8 the mean is 4.5 — a value the truncated mutant
    cannot produce.
    """
    ramp = np.arange(64, dtype=float)
    energy = multiscale_energy(ramp, max_scale=8)
    assert energy == 4.5, f"expected the mean of increments 1..8 = 4.5, got {energy}"
