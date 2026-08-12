# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T12 — Serotonin stability witnesses for INV-5HT1, INV-5HT4 and INV-5HT6.

Three independent invariants on the serotonin subsystem, all P0:

* **INV-5HT1** — Lyapunov non-increasing. The 2-state 5-HT ODE in
  ``core.neuro.serotonin_ode`` is equipped with a documented Lyapunov
  function V(level, desens) = ½(level − target)² + λ·desens². With
  stress = 0 (zero exogenous forcing), V is non-increasing along the
  RK4 trajectory. The witness runs a 200-step trajectory from a
  perturbed initial state and asserts V never rises.

* **INV-5HT4** — desensitisation sensitivity stays in [0.1, 1.0] across
  any sequence of (stress, drawdown, novelty) inputs to the production
  ``SerotoninController``. Covered by a 50-step stochastic sweep.

* **INV-5HT6** — tonic_level finite and non-negative under the same
  sweep. Combined with INV-5HT4 into the single-loop witness to keep
  the sweep efficient while exercising both bounds on every step.
"""

from __future__ import annotations

from typing import List, Tuple

import numpy as np

from core.neuro.serotonin_ode import SerotoninODE, SerotoninODEParams
from geosync.core.neuro.serotonin.serotonin_controller import SerotoninController


def _lyapunov_value(level: float, desens: float, target: float, lambda_weight: float) -> float:
    """Compute V(level, desens) using the published Lyapunov form.

    V = 0.5 · (level − target)² + λ · desens²

    Defined locally (rather than calling the private ``_lyapunov`` on
    the ODE class) so the witness does not depend on a private API and
    so the formula is explicit in the test for reviewers.
    """
    return 0.5 * (level - target) ** 2 + lambda_weight * desens**2


def test_serotonin_lyapunov_is_non_increasing_under_zero_stress() -> None:
    """INV-5HT1: V(level, desens) is non-increasing when stress = 0.

    Initialises the 2-state serotonin ODE away from its target
    (level=0.8, desens=0.5, target=0.3) and integrates 200 RK4 steps
    with zero stress. Records V at every step and demands it never
    rises by more than 1e-10 (integrator-order slack for RK4 at dt=1).
    Any observed rise is a Lyapunov certificate failure — the ODE is
    not asymptotically stable toward its documented equilibrium.
    """
    params = SerotoninODEParams()
    ode = SerotoninODE(params=params, level=0.8, desensitization=0.5)
    lyapunov_trajectory: list[float] = [
        _lyapunov_value(ode.level, ode.desensitization, params.target, params.lambda_)
    ]

    n_steps = 200
    integrator_epsilon = 1e-10  # RK4 slack; tolerance from integrator order
    dt = 1.0

    for step_idx in range(n_steps):
        ode.step(stress=0.0, dt=dt)
        current_v = _lyapunov_value(ode.level, ode.desensitization, params.target, params.lambda_)
        previous_v = lyapunov_trajectory[-1]
        rise = current_v - previous_v
        assert rise <= integrator_epsilon, (
            f"INV-5HT1 VIOLATED at step={step_idx}: V rose by {rise:.3e} "
            f"(prev={previous_v:.6e}, curr={current_v:.6e}). "
            f"Expected dV/dt ≤ 0 under zero stress — the ODE has a "
            f"documented Lyapunov function certifying asymptotic stability. "
            f"Observed at level={ode.level:.4f}, desens={ode.desensitization:.4f}, "
            f"target={params.target}, lambda_={params.lambda_}, dt={dt}, steps={n_steps}. "
            f"Physical reasoning: V = ½(l−target)² + λ·d² is a Lyapunov "
            f"candidate for the 5-HT ODE with zero exogenous forcing; "
            f"any rise indicates the integrator produced a non-dissipative step."
        )
        lyapunov_trajectory.append(current_v)

    # Additional sanity — the trajectory must actually evolve toward
    # the target, otherwise the Lyapunov decrease is trivially vacuous.
    v_start = lyapunov_trajectory[0]
    v_final = lyapunov_trajectory[-1]
    assert v_final < v_start, (
        f"INV-5HT1 witness vacuous: V did not decrease over the full run "
        f"(V_start={v_start:.6e}, V_final={v_final:.6e}). "
        f"Expected monotone descent toward the equilibrium (level=target). "
        f"Observed at N=200 steps, target=0.3, seed=none (deterministic ODE), dt={dt}. "
        f"Physical reasoning: starting from (level=0.8, desens=0.5) the ODE "
        f"should pull the state back to the baseline within 200 steps."
    )


def test_serotonin_controller_sensitivity_and_tonic_bounds() -> None:
    """INV-5HT4 + INV-5HT6: sensitivity ∈ [0.1, 1.0] and tonic_level
    finite and non-negative across a 50-step stochastic sweep.

    Drives the production SerotoninController with seeded-random
    (stress, drawdown, novelty) triples and asserts both bounds at
    every step. A single violation anywhere in the sweep is a bug in
    the controller's receptor-desensitisation or tonic-integration path.
    """
    rng = np.random.default_rng(seed=31)
    controller = SerotoninController()
    n_steps = 50
    sensitivity_lower = 0.1
    sensitivity_upper = 1.0

    observations: List[Tuple[int, float, float]] = []
    for step_idx in range(n_steps):
        stress = float(rng.uniform(0.0, 2.5))
        drawdown = float(rng.uniform(-0.4, 0.0))
        novelty = float(rng.uniform(0.0, 1.5))
        controller.step(stress=stress, drawdown=drawdown, novelty=novelty)
        observations.append((step_idx, controller.sensitivity, controller.tonic_level))

        # INV-5HT4: sensitivity stays in [0.1, 1.0] per the 5-HT receptor
        # desensitisation contract.
        assert sensitivity_lower <= controller.sensitivity <= sensitivity_upper, (
            f"INV-5HT4 VIOLATED at step={step_idx}: "
            f"sensitivity={controller.sensitivity:.6f} outside "
            f"[{sensitivity_lower}, {sensitivity_upper}]. "
            f"Expected receptor sensitivity in the biologically-valid band. "
            f"Observed at stress={stress:.4f}, drawdown={drawdown:.4f}, "
            f"novelty={novelty:.4f}, seed=31. "
            f"Physical reasoning: sensitivity encodes receptor density; it "
            f"floors at 0.1 under heavy desensitisation and caps at 1.0 at "
            f"full recovery — escapes indicate a missing clamp."
        )

        # INV-5HT6: tonic level is finite and non-negative under bounded inputs.
        assert np.isfinite(controller.tonic_level), (
            f"INV-5HT6 VIOLATED at step={step_idx}: "
            f"tonic_level={controller.tonic_level} non-finite. "
            f"Expected finite tonic_level for bounded stress/drawdown/novelty inputs. "
            f"Observed at stress={stress:.4f}, drawdown={drawdown:.4f}, "
            f"novelty={novelty:.4f}, seed=31. "
            f"Physical reasoning: tonic integration is an exponential moving "
            f"average over finite inputs and cannot produce NaN/Inf."
        )
        # Lower bound epsilon = 0 is theoretical, derived from the
        # non-negative-concentration tolerance in the 5-HT ODE contract.
        tonic_floor_epsilon = 0.0
        assert controller.tonic_level >= tonic_floor_epsilon, (
            f"INV-5HT6 VIOLATED at step={step_idx}: "
            f"tonic_level={controller.tonic_level:.6f} < epsilon={tonic_floor_epsilon}. "
            f"Expected tonic_level ≥ 0 as an integrated concentration proxy. "
            f"Observed at stress={stress:.4f}, drawdown={drawdown:.4f}, "
            f"novelty={novelty:.4f}, seed=31. "
            f"Physical reasoning: tonic level is a non-negative accumulator "
            f"of 5-HT pressure — negative values are physically meaningless."
        )

    assert len(observations) == n_steps, (
        f"INV-5HT4/5HT6 sweep incomplete: recorded {len(observations)} steps, "
        f"expected {n_steps}. "
        f"Observed at seed=31. "
        f"Physical reasoning: the witness must exercise every step to be a "
        f"universal-property check."
    )


# ---------------------------------------------------------------------------
# TEETH — measured gap: mutation_probe --only-logic showed core/neuro/serotonin_ode.py
# killing 0 of 6 logic mutants (:64 Or->And, :176 NotEq->Eq, :179 LtE->Gt,
# :181 Gt->LtE, :209 Lt->GtE, :216 Gt->LtE). Every comparison in the Lyapunov
# certificate and the trajectory check could be inverted undetected. These tests pin
# each branch's semantics, so a flipped operator can no longer agree with them.
# ---------------------------------------------------------------------------
def test_lyapunov_certificate_holds_for_default_parameters() -> None:
    """Defaults satisfy a*(2*lambda*mu) > (delta/2)^2 — the certificate must say True.

    Kills the guard inversions: under NotEq->Eq the equal target/baseline defaults would
    bail False; under LtE->Gt the positive a would bail False; under Gt->LtE the satisfied
    criterion would read False.
    """
    ode = SerotoninODE()
    p = ode.p
    a = p.alpha + p.gamma
    assert a > 0.0 and p.target == p.baseline, "default parameter precondition changed"
    assert a * (2.0 * p.lambda_ * p.mu) > (p.delta / 2.0) ** 2, "default criterion changed"
    assert ode.lyapunov_parameter_certificate() is True


def test_lyapunov_certificate_refuses_when_target_differs_from_baseline() -> None:
    """V is not centred on the equilibrium when target != baseline -> no certificate."""
    ode = SerotoninODE(params=SerotoninODEParams(target=0.4, baseline=0.3))
    assert ode.lyapunov_parameter_certificate() is False


def test_lyapunov_certificate_refuses_non_positive_decay_sum() -> None:
    """alpha + gamma <= 0 leaves no contraction -> no certificate."""
    ode = SerotoninODE(params=SerotoninODEParams(alpha=-0.05, gamma=0.05))
    assert ode.lyapunov_parameter_certificate() is False


def test_lyapunov_certificate_refuses_when_criterion_is_violated() -> None:
    """Raising delta past the criterion boundary must flip the certificate to False."""
    ode = SerotoninODE(params=SerotoninODEParams(delta=1.0))
    p = ode.p
    a = p.alpha + p.gamma
    assert a * (2.0 * p.lambda_ * p.mu) <= (p.delta / 2.0) ** 2, "fixture no longer violates"
    assert ode.lyapunov_parameter_certificate() is False


def test_verify_lyapunov_rejects_an_increasing_trajectory() -> None:
    """V must be non-increasing; a trajectory that climbs away from target is rejected.

    Kills Lt->GtE (which would short-circuit every multi-point trajectory to True) and
    Gt->LtE (which would invert the non-increase test).
    """
    ode = SerotoninODE()
    at_target = (ode.p.target, 0.0)
    far_away = (ode.p.target + 0.6, 0.5)
    assert ode._lyapunov(*far_away) > ode._lyapunov(*at_target), "fixture is not increasing"
    assert ode.verify_lyapunov([at_target, far_away]) is False


def test_serotonin_ode_uses_the_parameters_it_is_given() -> None:
    """Explicit params must be honoured, not silently replaced by defaults.

    Kills :64 Or->And, under which a truthy params argument yields a fresh default set.
    """
    custom = SerotoninODEParams(baseline=0.42, threshold=0.77)
    ode = SerotoninODE(params=custom)
    assert ode.p is custom
    assert ode.p.baseline == 0.42 and ode.p.threshold == 0.77
