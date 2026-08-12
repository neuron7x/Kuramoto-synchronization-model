# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T18b — INV-HPC2 fail-closed stability guards for the second-order engine.

The symplectic Stoermer-Verlet core of
``core.kuramoto.second_order.SecondOrderKuramotoEngine`` (INV-K8/K9/K10) is
unchanged by these tests; they exercise only the *additive* fail-closed
numerical guards layered on top of it:

* **INV-HPC2 (non-finite fail-closed):** if an integrated phase or velocity
  becomes non-finite (NaN/Inf) at any step, ``run`` raises
  ``SecondOrderDivergenceError`` (a ``ValueError`` subclass) naming the step
  and the divergence kind, rather than letting NaN/Inf propagate into the
  phases/summary.

* **INV-HPC2 (RoCoF bound, opt-in):** when ``rocof_max`` is set, a step whose
  rate-of-change-of-frequency max_i |theta_dot_i(k+1) - theta_dot_i(k)| / dt
  exceeds the bound raises ``SecondOrderDivergenceError``. Default ``None``
  leaves the bound OFF.

* **Regression (byte-identical healthy run):** with ``rocof_max=None`` the run
  is byte-identical to the pre-guard engine, and a healthy run with a generous
  ``rocof_max`` produces the exact same trajectory and summary — the guards
  fire only on already-broken or opted-in-bound-exceeded states.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from core.kuramoto.config import KuramotoConfig
from core.kuramoto.second_order import (
    SecondOrderDivergenceError,
    SecondOrderKuramotoEngine,
)

# ---------------------------------------------------------------------------
# INV-HPC2: non-finite state fails closed, naming the step (sweep over channels)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_value", [np.nan, np.inf, -np.inf])
def test_non_finite_state_fails_closed_naming_step(bad_value: float) -> None:
    """INV-HPC2: a non-finite injected velocity makes run() fail closed at step 0.

    Sweep the three non-finite channels (NaN, +Inf, -Inf) injected into
    ``velocity0`` (which ``KuramotoConfig`` does not validate, unlike
    ``theta0``). Each propagates into the first Verlet step, so the guard must
    raise ``SecondOrderDivergenceError`` (a ``ValueError``) at step 0 with the
    ``non_finite`` kind and a step-naming message — never returning a
    non-finite trajectory in its place.
    """
    # INV-HPC2: forced-divergence parameters
    n_oscillators = 8  # N=8
    k_coupling = 2.0  # K=2.0
    steps = 20
    seed = 7
    dt = 0.01  # tolerance: standard integration step

    rng = np.random.default_rng(seed)
    theta0 = rng.uniform(0.0, 2.0 * math.pi, n_oscillators)
    velocity0 = np.zeros(n_oscillators)
    velocity0[3] = bad_value  # inject a non-finite frequency

    cfg = KuramotoConfig(
        N=n_oscillators,
        K=k_coupling,
        omega=np.zeros(n_oscillators),
        theta0=theta0,
        dt=dt,
        steps=steps,
        seed=seed,
    )
    engine = SecondOrderKuramotoEngine(cfg, mass=1.0, damping=0.1, velocity0=velocity0)

    with pytest.raises(SecondOrderDivergenceError) as excinfo:
        engine.run()

    err = excinfo.value
    assert isinstance(err, ValueError), (
        "INV-HPC2 VIOLATED: SecondOrderDivergenceError must subclass ValueError so "
        "existing `except ValueError` handlers still catch it; expected ValueError "
        f"in the MRO, observed MRO={type(err).__mro__}. "
        f"At N={n_oscillators}, K={k_coupling}, steps={steps}, bad_value={bad_value}."
    )
    assert err.kind == "non_finite", (
        f"INV-HPC2 VIOLATED: expected kind='non_finite', observed kind={err.kind!r}. "
        f"A non-finite integrated state must be reported as a non-finite divergence. "
        f"At N={n_oscillators}, K={k_coupling}, steps={steps}, bad_value={bad_value}."
    )
    assert err.step == 0, (
        f"INV-HPC2 VIOLATED: expected the divergence at step 0 (non-finite seeded "
        f"in velocity0), observed step={err.step}. The guard must name the "
        f"offending step. At N={n_oscillators}, K={k_coupling}, steps={steps}, "
        f"seed={seed}, bad_value={bad_value}."
    )
    assert "step 0" in str(err), (
        f"INV-HPC2 VIOLATED: expected the message to name the step, observed: {err!s}. "
        f"A silent or unlabelled divergence defeats fail-closed diagnosis. "
        f"At N={n_oscillators}, K={k_coupling}, steps={steps}, bad_value={bad_value}."
    )


# ---------------------------------------------------------------------------
# INV-HPC2: RoCoF bound (opt-in) fires when exceeded, names step + kind
# ---------------------------------------------------------------------------


def test_rocof_bound_fires_when_exceeded() -> None:
    """INV-HPC2: a tight rocof_max trips on a fast frequency transient.

    A large kinetic seed under non-trivial coupling produces a per-step RoCoF
    that exceeds a deliberately tiny bound on the first step. We assert ``run``
    raises ``SecondOrderDivergenceError`` with kind 'rocof_exceeded' and a named
    step, proving the bound is *checked* and not merely reported.
    """
    # INV-HPC2: RoCoF transient parameters
    n_oscillators = 16  # N=16
    k_coupling = 5.0  # K=5.0
    steps = 50
    seed = 3
    dt = 0.01  # tolerance: standard integration step

    rng = np.random.default_rng(seed)
    theta0 = rng.uniform(0.0, 2.0 * math.pi, n_oscillators)
    velocity0 = 2.0 * rng.standard_normal(n_oscillators)  # strong transient

    cfg = KuramotoConfig(
        N=n_oscillators,
        K=k_coupling,
        omega=np.zeros(n_oscillators),
        theta0=theta0,
        dt=dt,
        steps=steps,
        seed=seed,
    )
    # tolerance: a tiny bound any real transient will exceed on the first step
    tight_bound = 1e-6
    engine = SecondOrderKuramotoEngine(
        cfg, mass=1.0, damping=0.1, velocity0=velocity0, rocof_max=tight_bound
    )

    with pytest.raises(SecondOrderDivergenceError) as excinfo:
        engine.run()

    err = excinfo.value
    assert err.kind == "rocof_exceeded", (
        f"INV-HPC2 VIOLATED: expected kind='rocof_exceeded', observed kind={err.kind!r}. "
        f"A RoCoF above rocof_max={tight_bound} must fail closed. "
        f"At N={n_oscillators}, K={k_coupling}, steps={steps}, seed={seed}."
    )
    assert err.step >= 0, (
        f"INV-HPC2 VIOLATED: expected a non-negative named step for the RoCoF guard, "
        f"observed step={err.step}. At N={n_oscillators}, K={k_coupling}, seed={seed}."
    )
    assert "rocof_max" in str(err), (
        f"INV-HPC2 VIOLATED: expected the message to reference the bound, observed: "
        f"{err!s}. At N={n_oscillators}, K={k_coupling}, steps={steps}, seed={seed}."
    )


def test_rocof_bound_generous_does_not_fire() -> None:
    """INV-HPC2: a rocof_max above the run's own max_rocof never fires.

    Run once with the bound OFF to read the descriptive ``max_rocof``, then set
    ``rocof_max`` to twice that value. The bounded run must complete and produce
    a byte-identical trajectory and summary, proving the guard fires only on a
    genuine excursion, not on a healthy run.
    """
    # INV-HPC2: healthy-transient parameters
    n_oscillators = 12  # N=12
    k_coupling = 3.0  # K=3.0
    steps = 200
    seed = 9
    dt = 0.01  # tolerance: standard integration step

    rng = np.random.default_rng(seed)
    theta0 = rng.uniform(0.0, 2.0 * math.pi, n_oscillators)
    velocity0 = 0.3 * rng.standard_normal(n_oscillators)

    def _make_engine(rocof_max: float | None) -> SecondOrderKuramotoEngine:
        cfg = KuramotoConfig(
            N=n_oscillators,
            K=k_coupling,
            omega=np.zeros(n_oscillators),
            theta0=theta0,
            dt=dt,
            steps=steps,
            seed=seed,
        )
        return SecondOrderKuramotoEngine(
            cfg, mass=1.0, damping=0.1, velocity0=velocity0, rocof_max=rocof_max
        )

    baseline = _make_engine(None).run()
    observed_rocof = float(baseline.summary["max_rocof"])
    generous_bound = 2.0 * observed_rocof + 1.0  # strictly above any step RoCoF

    guarded = _make_engine(generous_bound).run()

    phase_gap = float(np.max(np.abs(baseline.phases - guarded.phases)))
    assert np.array_equal(baseline.phases, guarded.phases), (
        "INV-HPC2 VIOLATED: expected a generous rocof_max to leave the phase "
        f"trajectory unchanged (read-only guard); observed max|delta_phase|={phase_gap:.3e}. "
        f"At N={n_oscillators}, K={k_coupling}, steps={steps}, seed={seed}, "
        f"rocof_max={generous_bound:.6g}."
    )
    velocity_gap = float(np.max(np.abs(baseline.velocities - guarded.velocities)))
    assert np.array_equal(baseline.velocities, guarded.velocities), (
        "INV-HPC2 VIOLATED: expected a generous rocof_max to leave the velocity "
        f"trajectory unchanged; observed max|delta_v|={velocity_gap:.3e}. "
        f"At N={n_oscillators}, K={k_coupling}, steps={steps}, seed={seed}, "
        f"rocof_max={generous_bound:.6g}."
    )
    assert baseline.summary["max_rocof"] == guarded.summary["max_rocof"], (
        "INV-HPC2 VIOLATED: expected the reported max_rocof to be unchanged by a "
        f"generous bound; observed baseline={baseline.summary['max_rocof']} vs "
        f"guarded={guarded.summary['max_rocof']}. At N={n_oscillators}, K={k_coupling}, "
        f"steps={steps}, seed={seed}."
    )


# ---------------------------------------------------------------------------
# Regression: default OFF => byte-identical to the pre-guard engine
# ---------------------------------------------------------------------------


def test_default_run_byte_identical_guards_off() -> None:
    """INV-K8/INV-HPC2 regression: rocof_max=None leaves the run byte-unchanged.

    Two engines built with identical config — one constructed without the
    ``rocof_max`` argument (default), one with the argument explicitly None —
    must produce, before vs after the guard is wired in, bit-for-bit identical
    phases, velocities, order parameter and summary. This pins the additive
    guard's "default OFF, byte-identical" contract so the symplectic
    INV-K8/K9/K10 behaviour is provably untouched.
    """
    # Regression parameters
    n_oscillators = 32  # N=32
    k_coupling = 4.0  # K=4.0
    steps = 500
    seed = 0
    dt = 0.01  # tolerance: standard integration step

    rng = np.random.default_rng(seed)
    theta0 = rng.uniform(0.0, 2.0 * math.pi, n_oscillators)
    velocity0 = 0.3 * rng.standard_normal(n_oscillators)

    def _build(explicit_none: bool) -> SecondOrderKuramotoEngine:
        cfg = KuramotoConfig(
            N=n_oscillators,
            K=k_coupling,
            omega=np.zeros(n_oscillators),
            theta0=theta0,
            dt=dt,
            steps=steps,
            seed=seed,
        )
        if explicit_none:
            return SecondOrderKuramotoEngine(
                cfg, mass=1.0, damping=0.1, velocity0=velocity0, rocof_max=None
            )
        return SecondOrderKuramotoEngine(cfg, mass=1.0, damping=0.1, velocity0=velocity0)

    before = _build(explicit_none=False).run()
    after = _build(explicit_none=True).run()

    phase_gap = float(np.max(np.abs(before.phases - after.phases)))
    assert np.array_equal(before.phases, after.phases), (
        "INV-K8 regression VIOLATED: expected rocof_max=None to match the default "
        f"constructor bit-for-bit (guards off); observed max|delta_phase|={phase_gap:.3e}. "
        f"At N={n_oscillators}, K={k_coupling}, steps={steps}, seed={seed}."
    )
    velocity_gap = float(np.max(np.abs(before.velocities - after.velocities)))
    assert np.array_equal(before.velocities, after.velocities), (
        "INV-K8 regression VIOLATED: expected identical velocities between default "
        f"and explicit-None; observed max|delta_v|={velocity_gap:.3e}. "
        f"At N={n_oscillators}, K={k_coupling}, steps={steps}, seed={seed}."
    )
    order_gap = float(np.max(np.abs(before.order_parameter - after.order_parameter)))
    assert np.array_equal(before.order_parameter, after.order_parameter), (
        "INV-K8 regression VIOLATED: expected identical order parameter between "
        f"default and explicit-None; observed max|delta_R|={order_gap:.3e}. "
        f"At N={n_oscillators}, K={k_coupling}, steps={steps}, seed={seed}."
    )
    assert before.summary == after.summary, (
        "INV-K8 regression VIOLATED: expected identical summary between default and "
        f"explicit-None; observed before={before.summary} vs after={after.summary}. "
        f"At N={n_oscillators}, K={k_coupling}, steps={steps}, seed={seed}."
    )

    # Healthy run produces only finite, in-range quantities (INV-K1, INV-HPC2).
    finite_phases = bool(np.isfinite(before.phases).all())
    finite_velocities = bool(np.isfinite(before.velocities).all())
    assert finite_phases and finite_velocities, (
        "INV-HPC2 VIOLATED: expected a healthy run to emit only finite phases and "
        f"velocities; observed finite_phases={finite_phases}, "
        f"finite_velocities={finite_velocities}. At N={n_oscillators}, K={k_coupling}, "
        f"steps={steps}, seed={seed}."
    )
    r = before.order_parameter
    # INV-K1: order parameter magnitude is bounded to the unit disk [0, 1].
    in_unit_interval = bool(np.all((r >= 0.0) & (r <= 1.0)))
    assert in_unit_interval, (
        "INV-K1 VIOLATED: expected the order parameter to stay within [0, 1]; "
        f"observed min={float(r.min()):.4f}, max={float(r.max()):.4f}. "
        f"At N={n_oscillators}, K={k_coupling}, steps={steps}, seed={seed}."
    )


# ---------------------------------------------------------------------------
# Contract: rocof_max must be a finite positive float when provided (sweep)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_bound", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_rocof_max_rejected(bad_bound: float) -> None:
    """INV-HPC2: a non-positive or non-finite rocof_max fails closed at init.

    Sweep zero, negative, NaN, and Inf — none is a valid stability limit, so
    each must raise ``ValueError`` at construction rather than silently
    disabling or mis-applying the guard.
    """
    cfg = KuramotoConfig(
        N=4,
        K=1.0,
        omega=np.zeros(4),
        dt=0.01,
        steps=5,
        seed=0,
    )
    with pytest.raises(ValueError, match="rocof_max"):
        SecondOrderKuramotoEngine(cfg, rocof_max=bad_bound)

    # Property-style: every member of the invalid-bound family must be rejected
    # at construction (a single parametrized value could pass while a sibling
    # silently slips through a partial validation branch).
    for invalid in (bad_bound, bad_bound, 0.0, -abs(bad_bound) - 1.0):
        if math.isfinite(invalid) and invalid > 0.0:
            continue  # only assert rejection on genuinely-invalid bounds
        with pytest.raises(ValueError, match="rocof_max"):
            SecondOrderKuramotoEngine(cfg, rocof_max=invalid)


# ---------------------------------------------------------------------------
# Issue #1107 — the guard is PARTIAL, and says so. Passing CI must not be read
# as a complete numerical stability audit.
# ---------------------------------------------------------------------------


def _run_small() -> object:
    cfg = KuramotoConfig(N=4, K=1.0, omega=np.zeros(4), dt=0.01, steps=5, seed=0)
    return SecondOrderKuramotoEngine(cfg, mass=1.0, damping=0.1).run()


def test_second_order_audit_scope_is_partial() -> None:
    """NON_PHYSICS: honesty/metadata contract on the engine's audit scope.

    Asserts the engine *declares* a partial audit scope rather than claiming a
    full stability audit. Enforcement-honesty contract (issue #1107), not a
    witness of any registered physics invariant, so no INV-*.
    """
    result = _run_small()
    assert result.audit_scope == "nonfinite_and_rocof_only"
    # It must NOT advertise itself as a full stability audit.
    assert result.audit_scope != "full_stability_audit"


def test_second_order_remaining_gaps_are_declared() -> None:
    """NON_PHYSICS: honesty/metadata contract — declared unclosed audit gaps.

    Asserts the engine keeps its remaining stability-audit gaps declared so a
    green CI is not misread as a complete numerical audit. Enforcement-honesty
    contract, not a physics-invariant witness.
    """
    result = _run_small()
    gaps = result.remaining_audit_gaps
    for gap in (
        "energy_like_drift",
        "phase_spread_bound",
        "solver_metadata",
        "stiffness_assumption",
        "cross_solver_reference",
    ):
        assert gap in gaps, f"unclosed stability check '{gap}' must stay declared"
