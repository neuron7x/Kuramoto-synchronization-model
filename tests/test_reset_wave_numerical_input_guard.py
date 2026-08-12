"""Numerical-input fail-closed contract tests for reset-wave.

Anchored to a real 2026-05-05 cross-stress validation finding:
``run_reset_wave([0.1, NaN, 0.2], [0,0,0], cfg)`` previously returned
``final_potential = NaN`` instead of raising. That violated INV-DET3
(every contract violation → ValueError) and INV-HPC2 (finite inputs
→ finite outputs). This file pins the guard so the regression cannot
silently return.
"""

from __future__ import annotations

import math

import pytest

from geosync.neuroeconomics.reset_wave_engine import (
    AsyncResilienceConfig,
    ResetWaveConfig,
    run_reset_wave,
    run_reset_wave_async_resilient,
)

_NON_FINITE = (float("nan"), float("inf"), float("-inf"))


@pytest.mark.parametrize("bad", _NON_FINITE)
def test_run_reset_wave_rejects_non_finite_node(bad: float) -> None:
    with pytest.raises(ValueError, match="must be finite"):
        run_reset_wave([0.1, bad, 0.2], [0.0, 0.0, 0.0], ResetWaveConfig())


@pytest.mark.parametrize("bad", _NON_FINITE)
def test_run_reset_wave_rejects_non_finite_baseline(bad: float) -> None:
    with pytest.raises(ValueError, match="must be finite"):
        run_reset_wave([0.1, 0.2, 0.3], [0.0, bad, 0.0], ResetWaveConfig())


@pytest.mark.parametrize("bad", _NON_FINITE)
def test_async_resilient_rejects_non_finite_node(bad: float) -> None:
    with pytest.raises(ValueError, match="must be finite"):
        run_reset_wave_async_resilient(
            [0.1, bad], [0.0, 0.0], ResetWaveConfig(), AsyncResilienceConfig()
        )


@pytest.mark.parametrize("bad", _NON_FINITE)
def test_async_resilient_rejects_non_finite_baseline(bad: float) -> None:
    with pytest.raises(ValueError, match="must be finite"):
        run_reset_wave_async_resilient(
            [0.1, 0.2], [bad, 0.0], ResetWaveConfig(), AsyncResilienceConfig()
        )


def test_finite_inputs_still_work_after_guard() -> None:
    """INV-HPC2 sanity: legitimate finite inputs must keep producing finite outputs."""
    out = run_reset_wave(
        [0.4, -0.3, 0.2], [0.0, 0.0, 0.0], ResetWaveConfig(coupling_gain=1.0, dt=0.1)
    )
    assert math.isfinite(out.initial_potential)
    assert math.isfinite(out.final_potential)
    assert out.final_potential <= out.initial_potential
