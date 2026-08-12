# SPDX-License-Identifier: MIT
"""Tests for :mod:`core.kuramoto.phase_correction`.

Pins three physics contracts:

* **INV-K-CORR1** (universal): output phases lie in ``[-π, π]``.
* **INV-K-CORR2** (monotonic): Kuramoto potential ``V`` is
  non-increasing across an Euler step under the stability bound
  ``K·dt < 2``.
* **INV-K-CORR3** (asymptotic): under stability bound, ``max
  phase error`` decays to zero.

Plus negative controls: instability bound ``K·dt > 2`` produces
non-monotone V (positive falsification — the bound itself is
verifiable).
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.kuramoto.phase_correction import (
    KuramotoCorrectionReport,
    KuramotoResetTrajectory,
    circular_phase_distance,
    kuramoto_correction_step,
    reset_to_baseline,
    wrap_to_pi,
)

# ---------------------------------------------------------------------------
# wrap_to_pi
# ---------------------------------------------------------------------------


def test_wrap_to_pi_identity_in_band() -> None:
    """Within ``(-π, π)`` wrap is identity to machine precision."""
    inputs = np.array([0.0, 0.5, -0.5, 1.5, -1.5, 3.0, -3.0])
    out = wrap_to_pi(inputs)
    assert np.allclose(
        out, inputs, atol=1e-15
    ), f"wrap_to_pi non-identity inside (-π, π): {inputs!r} → {out!r}"


def test_wrap_to_pi_handles_full_cycles() -> None:
    """Adding 2π·k must not change the wrapped result."""
    base = np.array([0.5, -0.7, 1.2, -1.9])
    for k in [-3, -1, 1, 5]:
        shifted = base + 2.0 * math.pi * k
        assert np.allclose(wrap_to_pi(shifted), base, atol=1e-12), (
            f"wrap_to_pi failed full-cycle invariance at k={k}: "
            f"{shifted!r} did not return to {base!r}"
        )


@given(
    st.lists(
        st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=20,
    )
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_wrap_to_pi_property_output_in_pi_range(values: list[float]) -> None:
    """INV-K-CORR1: output always in [-π, π]."""
    out = wrap_to_pi(np.asarray(values, dtype=np.float64))
    assert np.all(out >= -math.pi - 1e-12) and np.all(out <= math.pi + 1e-12), (
        f"wrap_to_pi output escaped [-π, π]: min={out.min()}, max={out.max()}; "
        f"input had {len(values)} values."
    )


# ---------------------------------------------------------------------------
# circular_phase_distance
# ---------------------------------------------------------------------------


def test_circular_distance_handles_wrap_correctly() -> None:
    """Near-2π values: 0.01 vs 6.27 → distance ≈ 0.023, NOT 6.26.

    This is the bug class that the audit exposed in the original
    diff. The correct distance modulo 2π must account for the
    short way around the unit circle.
    """
    a = np.array([0.01])
    b = np.array([6.27])
    d = circular_phase_distance(a, b)[0]
    naive = abs(0.01 - 6.27)
    assert d < 0.05, (
        f"circular_phase_distance gave {d:.4f}; naive abs gives {naive:.4f}. "
        "Expected modular distance well below 0.05 — close to 2·0.013 = 0.026 "
        "(the short arc around the unit circle)."
    )


def test_circular_distance_in_zero_pi_range() -> None:
    """Output range is [0, π]."""
    rng = np.random.default_rng(seed=42)
    a = rng.uniform(-50.0, 50.0, size=200)
    b = rng.uniform(-50.0, 50.0, size=200)
    d = circular_phase_distance(a, b)
    assert d.min() >= 0.0
    assert d.max() <= math.pi + 1e-12


# ---------------------------------------------------------------------------
# Single step — INV-K-CORR1 (output in [-π, π])
# ---------------------------------------------------------------------------


def test_step_output_phases_in_pi_range() -> None:
    """INV-K-CORR1: a single Euler step keeps phases in [-π, π]."""
    rng = np.random.default_rng(seed=1)
    phases = rng.uniform(-100.0, 100.0, size=50)
    baseline = rng.uniform(-100.0, 100.0, size=50)
    new_phases, _ = kuramoto_correction_step(phases, baseline, coupling=1.5, dt=0.1)
    assert np.all(new_phases >= -math.pi - 1e-12)
    assert np.all(new_phases <= math.pi + 1e-12)


def test_step_rejects_non_positive_coupling() -> None:
    phases = np.zeros(3, dtype=np.float64)
    baseline = np.zeros(3, dtype=np.float64)
    for bad in (0.0, -1.0, math.nan, math.inf):
        with pytest.raises(ValueError, match="coupling"):
            kuramoto_correction_step(phases, baseline, coupling=bad, dt=0.1)


def test_step_rejects_non_positive_dt() -> None:
    phases = np.zeros(3, dtype=np.float64)
    baseline = np.zeros(3, dtype=np.float64)
    for bad in (0.0, -0.01, math.nan, math.inf):
        with pytest.raises(ValueError, match="dt"):
            kuramoto_correction_step(phases, baseline, coupling=1.0, dt=bad)


def test_step_rejects_shape_mismatch() -> None:
    with pytest.raises(ValueError, match="share shape"):
        kuramoto_correction_step(
            np.zeros(3, dtype=np.float64),
            np.zeros(4, dtype=np.float64),
            coupling=1.0,
            dt=0.1,
        )


def test_step_rejects_non_finite() -> None:
    bad_phases = np.array([0.0, math.nan, 0.5], dtype=np.float64)
    baseline = np.zeros(3, dtype=np.float64)
    with pytest.raises(ValueError, match="INV-HPC2"):
        kuramoto_correction_step(bad_phases, baseline, coupling=1.0, dt=0.1)


def test_step_at_baseline_yields_zero_velocity() -> None:
    """At the fixed point ``θ = θ_ref``, the velocity is zero."""
    baseline = np.array([0.3, -0.7, 1.2])
    new_phases, report = kuramoto_correction_step(baseline.copy(), baseline, coupling=2.0, dt=0.1)
    assert report.velocity_norm < 1e-12
    assert report.potential_energy < 1e-12
    assert report.max_phase_error < 1e-12
    assert np.allclose(new_phases, baseline, atol=1e-12)


# ---------------------------------------------------------------------------
# Reset trajectory — INV-K-CORR2 (monotonic V) + INV-K-CORR3 (convergence)
# ---------------------------------------------------------------------------


def test_reset_trajectory_potential_monotonically_non_increasing() -> None:
    """INV-K-CORR2: ``V`` non-increasing under stability bound K·dt < 2."""
    phases = np.array([2.5, -2.0, 1.7, -1.3, 0.8])
    baseline = np.zeros(5)
    coupling, dt = 1.0, 0.1  # K·dt = 0.1 — well inside stability
    traj = reset_to_baseline(
        phases,
        baseline,
        coupling=coupling,
        dt=dt,
        max_iters=200,
        convergence_tol=1e-3,
    )
    diffs = np.diff(traj.potential_history)
    # Allow ULP slack of 1e-12; the contract is monotone non-increasing.
    assert np.all(diffs <= 1e-12), (
        f"INV-K-CORR2 VIOLATED: max(diff(V)) = {diffs.max():.3e} > 1e-12. "
        f"Stability bound K·dt = {coupling * dt} < 2 was respected; "
        f"V_history (first 5) = {traj.potential_history[:5]!r}; "
        f"V_history (last 5) = {traj.potential_history[-5:]!r}. "
        "Under the stability bound the Kuramoto potential is a Lyapunov "
        "function for forced-Kuramoto descent."
    )


def test_reset_trajectory_converges_under_stability_bound() -> None:
    """INV-K-CORR3: max phase error → 0 exponentially under K·dt < 2."""
    rng = np.random.default_rng(seed=42)
    n = 16
    phases = rng.uniform(-math.pi, math.pi, size=n)
    baseline = rng.uniform(-math.pi, math.pi, size=n)
    traj = reset_to_baseline(
        phases,
        baseline,
        coupling=1.0,
        dt=0.1,
        max_iters=300,
        convergence_tol=1e-3,
    )
    assert traj.converged, (
        f"INV-K-CORR3 VIOLATED: did not converge within 300 iters at K=1, dt=0.1. "
        f"final max error = {traj.final_report.max_phase_error}, "
        f"iters_run = {traj.iterations_run}, n_nodes = {n}."
    )
    assert traj.final_report.max_phase_error < 1e-3


def test_reset_negative_control_unstable_bound_can_break_monotonicity() -> None:
    """Outside stability bound (K·dt ≥ 2), V may oscillate — falsifiable.

    This is a *positive control* for INV-K-CORR2: pushing past the
    documented stability boundary should produce observable
    non-monotonicity, otherwise the bound itself is unfalsifiable.
    """
    phases = np.array([math.pi - 0.01, -(math.pi - 0.01), 0.5, -0.5])
    baseline = np.zeros(4)
    # K·dt = 2.5 — past the stability bound. Initial misalignment
    # near ±π puts the dynamics in the regime where the discrete
    # update over-shoots and the potential oscillates.
    traj = reset_to_baseline(
        phases,
        baseline,
        coupling=2.5,
        dt=1.0,
        max_iters=20,
        convergence_tol=1e-3,
    )
    diffs = np.diff(traj.potential_history)
    # We expect at least one upward step (V increased) somewhere
    # in the trajectory — the discrete instability surfaces.
    assert np.any(diffs > 1e-9), (
        "Negative control failed: V never increased even past the stability "
        f"bound (K·dt = 2.5 > 2). diffs = {diffs!r}. "
        "Either the bound is loose for this fixture, or the discrete update "
        "is more stable than expected. Update fixture or relax the claim."
    )


def test_reset_returns_well_typed_trajectory() -> None:
    """Output dataclass shape and types are pinned."""
    phases = np.array([0.5, -0.7])
    baseline = np.zeros(2)
    traj = reset_to_baseline(
        phases, baseline, coupling=1.0, dt=0.1, max_iters=10, convergence_tol=1e-2
    )
    assert isinstance(traj, KuramotoResetTrajectory)
    assert isinstance(traj.final_report, KuramotoCorrectionReport)
    assert traj.final_phases.dtype == np.float64
    assert traj.potential_history.dtype == np.float64
    assert traj.potential_history.shape == (traj.iterations_run + 1,)
    assert traj.final_report.n_nodes == 2


def test_reset_rejects_zero_max_iters() -> None:
    with pytest.raises(ValueError, match="max_iters"):
        reset_to_baseline(
            np.zeros(2), np.zeros(2), coupling=1.0, dt=0.1, max_iters=0, convergence_tol=1e-3
        )


def test_reset_rejects_non_positive_tol() -> None:
    with pytest.raises(ValueError, match="convergence_tol"):
        reset_to_baseline(
            np.zeros(2),
            np.zeros(2),
            coupling=1.0,
            dt=0.1,
            max_iters=10,
            convergence_tol=0.0,
        )


# ---------------------------------------------------------------------------
# Hypothesis: convergence rate property
# ---------------------------------------------------------------------------


@given(
    seed=st.integers(min_value=0, max_value=10_000),
    n=st.integers(min_value=2, max_value=32),
    coupling=st.floats(min_value=0.5, max_value=5.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_converges_under_stability_envelope(seed: int, n: int, coupling: float) -> None:
    """INV-K-CORR3 fuzz: under K·dt < 2, the trajectory converges.

    Pick dt = 1 / (2·K) — keeps K·dt = 0.5, comfortably inside the
    stability envelope. Convergence in ≤ 500 iterations for any
    seed / n / K combination.
    """
    rng = np.random.default_rng(seed=seed)
    phases = rng.uniform(-math.pi, math.pi, size=n)
    baseline = rng.uniform(-math.pi, math.pi, size=n)
    dt = 1.0 / (2.0 * coupling)
    traj = reset_to_baseline(
        phases,
        baseline,
        coupling=coupling,
        dt=dt,
        max_iters=500,
        convergence_tol=1e-3,
    )
    assert traj.converged, (
        f"INV-K-CORR3 fuzz: failed to converge in 500 iters at "
        f"K={coupling}, dt={dt}, K·dt={coupling * dt}, n={n}, seed={seed}. "
        f"final max_error = {traj.final_report.max_phase_error}."
    )
