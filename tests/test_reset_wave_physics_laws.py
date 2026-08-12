"""Numerical invariant checks for damped phase synchronization model."""

from __future__ import annotations

import math

from geosync.neuroeconomics.reset_wave_engine import (
    ResetWaveConfig,
    phase_alignment_potential,
    phase_distance,
    run_reset_wave,
    wrap_phase,
)


def test_numerical_invariant_1_potential_nonnegative() -> None:
    out = run_reset_wave([0.2, -0.1], [0.0, 0.0], ResetWaveConfig())
    assert out.initial_potential >= 0.0
    assert out.final_potential >= 0.0


def test_numerical_invariant_2_potential_nonincreasing_under_stable_reset() -> None:
    out = run_reset_wave([0.2, 0.1, -0.2], [0.0, 0.0, 0.0], ResetWaveConfig())
    assert out.final_potential <= out.initial_potential


def test_numerical_invariant_3_zero_error_fixed_point() -> None:
    out = run_reset_wave([1.0, 1.0], [1.0, 1.0], ResetWaveConfig())
    assert math.isclose(out.initial_potential, 0.0, abs_tol=1e-9)
    assert math.isclose(out.final_potential, 0.0, abs_tol=1e-9)
    assert out.converged


def test_numerical_invariant_4_lock_on_critical_error() -> None:
    out = run_reset_wave([10.0, -10.0], [0.0, 0.0], ResetWaveConfig(max_phase_error=0.5))
    assert out.locked


def test_numerical_invariant_5_determinism() -> None:
    cfg = ResetWaveConfig(coupling_gain=1.2)
    assert run_reset_wave([0.11, 0.09], [0.1, 0.1], cfg) == run_reset_wave(
        [0.11, 0.09], [0.1, 0.1], cfg
    )


def test_phase_wrapping_and_distance() -> None:
    w = wrap_phase(4 * math.pi + 0.1)
    assert -math.pi <= w < math.pi
    d = phase_distance(math.pi - 0.01, -math.pi + 0.01)
    assert abs(d) < 0.05


def test_phase_alignment_potential_wrap_consistency() -> None:
    a = phase_alignment_potential([math.pi - 0.01], [-math.pi + 0.01])
    b = phase_alignment_potential([-math.pi + 0.01], [math.pi - 0.01])
    assert math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
