# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Integration-style tests around the Polygon validator."""

from __future__ import annotations

import os

import pytest

from scripts.polygon_validator import PolygonValidator

RUN_REAL = os.getenv("RUN_POLYGON_TESTS") == "1"


@pytest.mark.integration
@pytest.mark.skipif(not RUN_REAL, reason="requires RUN_POLYGON_TESTS=1")
def test_polygon_spy_validation() -> None:
    validator = PolygonValidator(api_key=os.getenv("POLYGON_API_KEY"))
    validator.load_data("SPY", "2024-10-01", "2024-10-07")
    samples = validator.run_ga_benchmark(num_trials=10)
    assert len(samples) == 10
    cvar = validator.compute_cvar(samples, alpha=0.05)
    assert cvar >= min(samples)


@pytest.mark.integration
def test_flash_crash_simulation() -> None:
    validator = PolygonValidator(api_key=None)
    F_baseline = 0.09994
    F_stress, F_post, monotonic_held = validator.simulate_flash_crash(F_baseline)
    assert F_stress > F_baseline
    assert F_post >= F_baseline
    assert isinstance(monotonic_held, bool)
