# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Numerical-stability and fail-closed hardening for the Kuramoto RK4 engine.

These tests close *risk-relevant decision paths* in ``core/kuramoto/engine.py``
that statement coverage alone leaves untested even after the full kuramoto
suite runs:

* the **4th-order convergence** of the RK4 integrator — the lines execute in
  every simulation, but no test verifies the integrator is actually ``O(dt^4)``;
  a silent drop to a first-order Euler step would keep every existing test green
  while destroying the trajectory accuracy the whole stack depends on;
* the **fail-closed finiteness guards** on :class:`KuramotoResult` for a
  non-finite ``order_parameter`` (engine.py:83) and ``time`` (engine.py:85).
  These are *load-bearing*: a ``NaN`` order parameter slips past the ``[0, 1]``
  range check (``NaN`` comparisons are ``False``), so the dedicated finiteness
  guard is the only barrier protecting INV-K1 (0 ≤ R ≤ 1) from leaking ``NaN``;
* the **fail-closed overflow guard** in the RHS evaluator (engine.py:271).

Invariants exercised: INV-K1 (R ∈ [0, 1]) and the numerical-stability contract
of the RK4 map. See ``CLAUDE.md`` → Kuramoto Synchronization.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.kuramoto import KuramotoConfig, KuramotoResult
from core.kuramoto.engine import _dtheta_dt, _rk4_step

# ---------------------------------------------------------------------------
# Numerical stability — RK4 is 4th-order (metamorphic / Richardson)
# ---------------------------------------------------------------------------


def test_rk4_step__dt_halving__converges_at_fourth_order() -> None:
    """Halving ``dt`` must shrink the RK4 truncation error by ≈ 2**4 = 16.

    Oracle-free (metamorphic) verification via Richardson extrapolation on a
    two-oscillator system with a *nonlinear* RHS (so the truncation error is
    non-zero — RK4 is exact for constant-derivative flows). For a method of
    order ``p`` the successive-difference ratio
    ``||y(dt) − y(dt/2)|| / ||y(dt/2) − y(dt/4)||`` tends to ``2**p``.

    A regression to an Euler step (``p = 1``) collapses this ratio toward 2,
    which the asserted band rejects.
    """
    omega = np.array([0.3, -0.2], dtype=np.float64)
    adj = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.float64)
    theta0 = np.array([0.4, 1.7], dtype=np.float64)
    K = 0.8
    horizon = 1.0

    def integrate(dt: float) -> np.ndarray:
        n_steps = int(round(horizon / dt))
        theta = theta0.copy()
        for _ in range(n_steps):
            theta = _rk4_step(theta, omega, adj, dt, K=K)
        return theta

    y_coarse = integrate(0.04)
    y_med = integrate(0.02)
    y_fine = integrate(0.01)

    err_coarse = float(np.linalg.norm(y_coarse - y_med))
    err_fine = float(np.linalg.norm(y_med - y_fine))
    assert err_fine > 0.0, "degenerate convergence probe: refine produced no change"

    ratio = err_coarse / err_fine
    observed_order = float(np.log2(ratio))
    assert 3.5 <= observed_order <= 4.5, (
        f"RK4 ORDER VIOLATED: observed convergence order p={observed_order:.3f} "
        f"(error ratio={ratio:.3f}) outside [3.5, 4.5]. "
        f"Expected p=4 for Runge-Kutta-4 (ratio≈16 under dt-halving). "
        f"A ratio≈2 indicates a first-order Euler regression. "
        f"Probe: 2 oscillators, K={K}, T={horizon}, dt∈(0.04, 0.02, 0.01)."
    )


def test_rk4_step__zero_frequency__is_rotation_equivariant() -> None:
    """With ω=0 the RK4 step commutes with a global phase shift (metamorphic).

    The Kuramoto RHS depends on phases only through differences
    ``sin(θ_j − θ_i)``; adding a constant ``φ`` to every phase leaves the
    derivative unchanged when ω=0, so one integration step must shift rigidly:
    ``step(θ + φ) == step(θ) + φ``. This pins the structural invariance of the
    coupling term independently of any single-trajectory oracle.
    """
    rng = np.random.default_rng(7)
    n = 6
    theta = rng.uniform(0.0, 2.0 * np.pi, n)
    omega = np.zeros(n, dtype=np.float64)
    adj = rng.uniform(0.0, 1.0, (n, n))
    np.fill_diagonal(adj, 0.0)
    phi = 0.9123

    stepped_then_shifted = _rk4_step(theta, omega, adj, dt=0.05, K=1.3) + phi
    shifted_then_stepped = _rk4_step(theta + phi, omega, adj, dt=0.05, K=1.3)

    np.testing.assert_allclose(
        shifted_then_stepped,
        stepped_then_shifted,
        atol=1e-12,
        err_msg=(
            "Kuramoto RHS rotation equivariance broken: with ω=0 a global phase "
            "shift must commute with the integrator step (coupling depends only "
            "on phase differences)."
        ),
    )


# ---------------------------------------------------------------------------
# Fail-closed finiteness guards on KuramotoResult (INV-K1 leak protection)
# ---------------------------------------------------------------------------


@pytest.fixture()
def _result_fields() -> tuple[KuramotoConfig, np.ndarray, np.ndarray, np.ndarray]:
    cfg = KuramotoConfig(N=4, K=1.0, dt=0.01, steps=8, seed=0)
    phases = np.zeros((cfg.steps + 1, cfg.N), dtype=np.float64)
    order = np.zeros(cfg.steps + 1, dtype=np.float64)
    time = np.arange(cfg.steps + 1, dtype=np.float64) * cfg.dt
    return cfg, phases, order, time


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_kuramoto_result__nonfinite_order_parameter__fails_closed(
    _result_fields: tuple[KuramotoConfig, np.ndarray, np.ndarray, np.ndarray],
    bad: float,
) -> None:
    """A non-finite ``order_parameter`` must be rejected, not stored.

    INV-K1 leak protection: the ``[0, 1]`` range check uses ``np.any(R < -tol)``
    / ``np.any(R > 1 + tol)``, both ``False`` for ``NaN`` — so without the
    dedicated finiteness guard a ``NaN`` R would be accepted as a valid order
    parameter. This test pins that guard (engine.py:83).
    """
    cfg, phases, order, time = _result_fields
    order_bad = order.copy()
    order_bad[0] = bad
    with pytest.raises(ValueError, match="non-finite"):
        KuramotoResult(phases=phases, order_parameter=order_bad, time=time, config=cfg)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_kuramoto_result__nonfinite_time__fails_closed(
    _result_fields: tuple[KuramotoConfig, np.ndarray, np.ndarray, np.ndarray],
    bad: float,
) -> None:
    """A non-finite ``time`` axis must be rejected (engine.py:85)."""
    cfg, phases, order, time = _result_fields
    time_bad = time.copy()
    time_bad[-1] = bad
    with pytest.raises(ValueError, match="non-finite"):
        KuramotoResult(phases=phases, order_parameter=order, time=time_bad, config=cfg)


def test_kuramoto_result__nan_order_parameter_bypasses_range_guard_witness(
    _result_fields: tuple[KuramotoConfig, np.ndarray, np.ndarray, np.ndarray],
) -> None:
    """Mutation-resistance witness: the range check alone cannot catch ``NaN``.

    Proves the finiteness guard (engine.py:82-83) is load-bearing rather than
    redundant. If a mutation removed that guard, the surviving ``[0, 1]`` range
    check would silently accept the ``NaN`` order parameter demonstrated here,
    so the guard's removal is *not* observable through the range check — only
    through the dedicated finiteness assertion this test set exercises.
    """
    _cfg, _phases, order, _time = _result_fields
    nan_order = order.copy()
    nan_order[0] = np.nan
    tol = 1e-12
    # The exact predicate used by the production range check:
    range_check_trips = bool(np.any(nan_order < -tol) or np.any(nan_order > 1.0 + tol))
    assert range_check_trips is False, (
        "INV-K1 witness invalidated: the [0,1] range predicate is expected to "
        "be False for NaN (NaN comparisons are False), which is precisely why "
        "the dedicated finiteness guard must exist."
    )


# ---------------------------------------------------------------------------
# Fail-closed overflow guard in the RHS evaluator
# ---------------------------------------------------------------------------


def test_dtheta_dt__overflow_to_nonfinite_rhs__fails_closed() -> None:
    """A finite-input evaluation that overflows to ``inf`` must raise.

    The guard converts a silent ``inf`` derivative (which would later poison
    INV-K1) into an explicit :class:`FloatingPointError` (engine.py:271).
    Overflow warnings are expected and suppressed — the contract under test is
    the *raise*, not the warning.
    """
    theta = np.array([0.0, np.pi / 2.0], dtype=np.float64)
    omega = np.array([1e308, 1e308], dtype=np.float64)
    adj = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.float64)
    with np.errstate(over="ignore", invalid="ignore"):
        with pytest.raises(FloatingPointError, match="Non-finite derivative"):
            _dtheta_dt(theta, omega, adj, K=1e308)


def test_rk4_step__overflow_propagates_fail_closed() -> None:
    """An RK4 step whose stages overflow must surface the RHS guard, not ``inf``."""
    theta = np.array([0.0, 1.0], dtype=np.float64)
    omega = np.array([1e308, 1e308], dtype=np.float64)
    adj = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.float64)
    with np.errstate(over="ignore", invalid="ignore"):
        with pytest.raises(FloatingPointError, match="Non-finite derivative"):
            _rk4_step(theta, omega, adj, dt=1e3, K=1e305)
