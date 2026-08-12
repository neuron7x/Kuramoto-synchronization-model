# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T28 — Wave-2 witness tests for under-anchored P0 invariants.

Wave 1 (PR #222) covered INV-K1, INV-SB2, INV-HPC1, INV-HPC2, INV-TH2
and INV-FE2 on the kuramoto/metrics, falsification, landauer and
tsallis_gate modules.  This wave targets five additional P0 invariants
whose production surfaces have existing behavioural tests but either
no INV-* anchor or only a single low-leverage witness:

* **INV-DA1 — TD-error sign directionality** on
  ``core.neuro.dopamine_execution_adapter.DopamineExecutionAdapter``.
  The existing behavioural tests in
  ``tests/unit/core/neuro/test_dopamine_execution_adapter.py`` carry
  zero INV-* references despite exercising the Schultz-1997 RPE sign
  semantics.  This witness adds a Hypothesis property-test that
  sweeps (realized_pnl, predicted_return, slippage) and falsification
  probes that flip sign exactly at the prediction boundary.

* **INV-DA3 — discount γ ∈ (0, 1]** on
  ``geosync.core.neuro.dopamine.dopamine_controller.DopamineController``.
  The current umbrella witness in
  ``tests/core/neuro/dopamine/test_dopamine_invariants_properties.py``
  only drives Hypothesis over the ``_validate_core_params`` config
  path.  INV-DA3's scope_note explicitly calls out ``compute_rpe``
  (line 737 of dopamine_controller.py) as the canonical enforcement
  point.  This witness fuzzes the public ``compute_rpe`` call with
  invalid γ values and asserts ``ValueError`` on every one of them.

* **INV-DA7 — ∂δ/∂r scope contrast** on
  ``DopamineExecutionAdapter``.  INV-DA7's scope_note states that the
  raw-TD linearity holds for the controller but **does NOT** hold for
  the adapter because of the ``tanh`` normalisation.  The existing
  controller-side witness (T11) proves the positive side of that
  contract; this witness proves the negative side, guarding against a
  regression that accidentally drops the tanh and silently upgrades
  the adapter's RPE into an unbounded path.

* **INV-OA1 — |z(t)| ≤ 1** on
  ``core.kuramoto.ott_antonsen.OttAntonsenEngine``.  T23 iterates a
  hand-picked 4-scenario grid.  This witness adds a full Hypothesis
  sweep over the documented parameter ranges (K > 0, Δ > 0, R0 ∈ [0,
  1]) and asserts the unit-disk bound on the full trajectory.

* **INV-OMS1 — portfolio kinetic energy ≥ 0** on
  ``core.physics.portfolio_conservation.PortfolioEnergyConservation``.
  T14 covers a 50-scenario sweep; this witness adds two structural
  properties that the 50-scenario loop cannot exercise by random
  sampling alone: sign-flip symmetry (replacing pos -> -pos leaves
  E_kinetic invariant, since |·| is the sign-killing primitive) and
  zero-output symmetry (any-zero factor forces E_kinetic to zero).
  These two identities pin the absolute-value path that underlies
  the non-negativity contract.

Each test derives its tolerance from a documented formula — float64
unit roundoff, tanh-monotonicity, RK4 ULP drift, sum-of-non-negatives
exactness — and includes an explicit falsification input per the
falsification ladder.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from core.kuramoto.ott_antonsen import OttAntonsenEngine
from core.neuro.dopamine_execution_adapter import DopamineExecutionAdapter
from core.neuro.signal_bus import NeuroSignalBus
from core.physics.portfolio_conservation import PortfolioEnergyConservation
from geosync.core.neuro.dopamine import DopamineController

# ---------------------------------------------------------------------------
# INV-DA1 — TD-error sign directionality on the execution adapter
# ---------------------------------------------------------------------------


@pytest.fixture()
def adapter() -> DopamineExecutionAdapter:
    """Fresh adapter with the documented defaults (tanh_scale=1, slip=1)."""
    return DopamineExecutionAdapter(NeuroSignalBus(), slippage_penalty_scale=1.0, tanh_scale=1.0)


# Hypothesis domain: stay inside the |raw_rpe| <= 8 regime where tanh
# remains strictly inside (-1, 1) in IEEE-754 float64.  tanh(8) ≈ 1 -
# 2.25e-7, still well under unity; tanh(20) saturates to exactly 1.0.
# Keeping |raw| <= 8 lets the universal `|rpe| < 1` bound remain
# strict without degrading into a boundary check.
_RPE_FLOAT = st.floats(min_value=-3.0, max_value=3.0, allow_nan=False, allow_infinity=False)
_SLIP_FLOAT = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)


@given(realized=_RPE_FLOAT, predicted=_RPE_FLOAT, slippage=_SLIP_FLOAT)
@settings(max_examples=250, deadline=None)
def test_adapter_rpe_sign_matches_surprise(
    realized: float, predicted: float, slippage: float
) -> None:
    """INV-DA1: sign(adapter.compute_rpe) = sign(raw) where raw =
    realized - predicted - |slippage|.

    The adapter's compute_rpe returns ``tanh(scale * raw_rpe)``.  tanh
    is strictly monotone and an odd function, so for every raw != 0
    the output shares the sign of raw exactly, and raw == 0 produces
    RPE == 0 bit-exactly.  The assertion derives its threshold from
    this monotonicity — no magic epsilon.
    """
    # Reject boundary rows where raw is smaller than the machine-epsilon
    # error of the tanh reduction.  Inside the rejected sliver, the sign
    # test is an algebraic ambiguity (not a falsification of the
    # invariant) so Hypothesis should re-draw.
    raw = (realized - predicted) - abs(slippage)
    assume(abs(raw) > 1e-12)

    bus_adapter = DopamineExecutionAdapter(
        NeuroSignalBus(), slippage_penalty_scale=1.0, tanh_scale=1.0
    )
    rpe = bus_adapter.compute_rpe(
        realized_pnl=realized, predicted_return=predicted, slippage=slippage
    )

    # INV-DA1: tanh is an odd monotone function, so sign(tanh(x)) == sign(x).
    # epsilon: 0.0 — sign identity is a theoretical tolerance, not numerical.
    if raw > 0.0:
        # epsilon: 0.0 — theory-derived, sign(tanh(x))=sign(x) for x!=0.
        assert rpe > 0.0, (
            f"INV-DA1 VIOLATED: observed rpe={rpe:.6e} <= 0 at raw={raw:.6e} "
            f"with realized={realized}, predicted={predicted}, slippage={slippage}. "
            f"Expected tanh(scale*raw) > 0 for raw > 0. "
            f"Physical reasoning: better-than-expected outcomes must emit "
            f"positive RPE (Schultz 1997)."
        )
    else:
        # epsilon: 0.0 — theory-derived, sign(tanh(x))=sign(x) for x!=0.
        assert rpe < 0.0, (
            f"INV-DA1 VIOLATED: observed rpe={rpe:.6e} >= 0 at raw={raw:.6e} "
            f"with realized={realized}, predicted={predicted}, slippage={slippage}. "
            f"Expected tanh(scale*raw) < 0 for raw < 0. "
            f"Physical reasoning: worse-than-expected outcomes must emit "
            f"negative RPE (Schultz 1997)."
        )

    # Universal bound witness: tanh is bounded in (-1, 1) so the adapter
    # can never return |rpe| >= 1.  This is the tightness side of the
    # sign witness and rules out the regression that drops the tanh.
    assert abs(rpe) < 1.0, (
        f"INV-DA1 VIOLATED: |rpe|={abs(rpe):.6f} >= 1 at raw={raw:.6e} "
        f"(realized={realized}, predicted={predicted}, slippage={slippage}). "
        f"Expected |tanh(scale*raw)| < 1 for every finite raw. "
        f"Physical reasoning: tanh saturates to +-1 asymptotically; dropping "
        f"the tanh would leak unbounded P&L into the RPE channel."
    )


def test_adapter_rpe_sign_falsification_zero_surprise(
    adapter: DopamineExecutionAdapter,
) -> None:
    """INV-DA1 falsification input: raw == 0 must produce rpe == 0 bit-exactly.

    tanh(0) == 0 is an algebraic identity of IEEE-754 float64, not a
    numerical tolerance.  A non-zero output here proves the adapter
    smuggled a bias term into the RPE path.
    """
    # Falsification inputs: multiple spellings of raw == 0.
    falsifiers = [
        (0.0, 0.0, 0.0),
        (1.5, 1.5, 0.0),
        (-3.25, -3.25, 0.0),
        (7.0, 5.0, 2.0),  # realized - predicted == |slippage|
    ]
    for realized, predicted, slippage in falsifiers:
        rpe = adapter.compute_rpe(
            realized_pnl=realized, predicted_return=predicted, slippage=slippage
        )
        # epsilon: 0.0 — exact IEEE-754 identity for tanh(0.0).
        assert rpe == 0.0, (
            f"INV-DA1 VIOLATED on zero-surprise falsifier: observed "
            f"rpe={rpe!r} != 0.0 with realized={realized}, predicted="
            f"{predicted}, slippage={slippage}. "
            f"Expected bit-exact zero from tanh(0.0). "
            f"Physical reasoning: no surprise -> no RPE."
        )


# ---------------------------------------------------------------------------
# INV-DA3 — discount γ ∈ (0, 1] enforced at DopamineController.compute_rpe
# ---------------------------------------------------------------------------


@pytest.fixture()
def controller(tmp_path: Path) -> DopamineController:
    """Load the shipped dopamine.yaml into a fresh DopamineController.

    Mirrors the T11 fixture pattern exactly so the witness uses the
    production config path without mutating the repo copy.
    """
    src_cfg = Path("config/dopamine.yaml")
    target = tmp_path / "dopamine.yaml"
    target.write_text(src_cfg.read_text(encoding="utf-8"), encoding="utf-8")
    return DopamineController(str(target))


# Invalid γ strategy: explicitly excludes the valid half-open interval
# (0, 1] and rejects NaN/Inf — those are caught by a separate _ensure_finite
# guard upstream of the (0, 1] check.
_INVALID_GAMMA = st.one_of(
    st.floats(min_value=-10.0, max_value=0.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=1.0000001, max_value=10.0, allow_nan=False, allow_infinity=False),
)


@given(gamma=_INVALID_GAMMA)
@settings(
    max_examples=120,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_dopamine_compute_rpe_rejects_invalid_gamma(
    controller: DopamineController, gamma: float
) -> None:
    """INV-DA3: DopamineController.compute_rpe raises ValueError for γ outside (0, 1].

    The invariant registry (INV-DA3 scope_note) pins the enforcement
    point to dopamine_controller.py line 737, which is exactly the
    branch exercised by passing discount_gamma via compute_rpe.  A
    silent coercion or clamp here would be a C1 hidden-invariant
    repair; we therefore require a raised exception on every invalid
    Hypothesis draw.
    """
    # Skip gamma == 1.0 boundary (valid under the half-open contract).
    assume(gamma != 1.0)
    # The documented error message is "discount_gamma must be in (0, 1]".
    with pytest.raises(ValueError, match=r"discount_gamma must be in"):
        controller.compute_rpe(reward=0.1, value=0.5, next_value=0.6, discount_gamma=gamma)


def test_dopamine_compute_rpe_accepts_boundary_gamma(
    controller: DopamineController,
) -> None:
    """INV-DA3 falsification inputs: γ values on the open-interval interior
    AND at γ=1.0 (upper boundary) are all valid.

    The contract is the half-open interval (0, 1]; every valid γ must
    execute compute_rpe without raising.  γ=1.0 is the closed-boundary
    case that a tightened bound would erroneously reject; the interior
    points exercise the happy-path branch.  Sweeping across multiple
    draws satisfies the universal-property-test contract for INV-DA3.
    """
    # Valid γ sweep: interior of (0, 1] plus the closed upper boundary.
    valid_gammas = (1e-6, 0.01, 0.25, 0.5, 0.75, 0.98, 0.999999, 1.0)
    # Fixed (reward, value, next_value) — the TD identity validates each γ.
    reward, value, next_value = 0.1, 0.5, 0.6
    for gamma in valid_gammas:
        rpe = controller.compute_rpe(
            reward=reward, value=value, next_value=next_value, discount_gamma=gamma
        )
        # INV-DA7 algebraic identity: δ = r + γ·V' − V exactly for every γ.
        expected = reward + gamma * next_value - value
        # epsilon: 1e-12 — one float64 ULP at the scale of reward+V'-V.
        assert rpe == pytest.approx(expected, abs=1e-12), (
            f"INV-DA3 VIOLATED: observed rpe={rpe} != expected={expected} "
            f"with gamma={gamma}, reward={reward}, value={value}, "
            f"next_value={next_value}. "
            f"Expected bit-close match to r + γ·V' − V per INV-DA7 identity. "
            f"Physical reasoning: γ ∈ (0, 1] is the valid domain; every "
            f"such γ must pass the compute_rpe gate without coercion."
        )

    # Explicit closed-boundary check at γ=1.0 (the tightest falsification
    # probe for a regression that tightens (0, 1] to (0, 1)).
    rpe_at_one = controller.compute_rpe(
        reward=reward, value=value, next_value=next_value, discount_gamma=1.0
    )
    expected_one = reward + 1.0 * next_value - value
    # epsilon: 1e-12 — one float64 ULP at the scale of the TD residual.
    assert rpe_at_one == pytest.approx(expected_one, abs=1e-12), (
        f"INV-DA3 boundary test failed: observed "
        f"compute_rpe(gamma=1.0)={rpe_at_one} != expected={expected_one} "
        f"with reward={reward}, value={value}, next_value={next_value}. "
        f"Expected bit-exact match to r + V' - V under γ=1.0. "
        f"Physical reasoning: the (0, 1] contract is closed at 1; "
        f"rejecting 1.0 would over-narrow the valid domain."
    )


# ---------------------------------------------------------------------------
# INV-DA7 — scope contrast: adapter's tanh breaks linearity by design
# ---------------------------------------------------------------------------


def test_adapter_is_nonlinear_in_reward_and_bounded(
    adapter: DopamineExecutionAdapter,
) -> None:
    """INV-DA7 scope contrast: DopamineExecutionAdapter.compute_rpe has
    ∂δ/∂r != 1 (by design) and |δ| < 1 (by design).

    INV-DA7's scope_note states the raw-TD linearity holds only on
    DopamineController.compute_rpe (T11 proves that positively).  The
    adapter applies ``tanh(scale * raw)`` whose derivative is
    ``sech^2 ≠ 1`` everywhere except the single trivial point raw=0.
    This witness proves the negative half of the scope by measuring
    that the finite-difference slope of the adapter's RPE with respect
    to the reward is strictly less than 1 on a three-point sweep and
    that the output is strictly bounded, ensuring a regression that
    drops the tanh would surface here instead of silently upgrading
    the adapter path to raw-TD semantics.
    """
    # Three-point sweep chosen so every sampled raw = reward - predicted -
    # slippage is bounded away from zero from the same side (raw ∈ [1, 3]).
    # This avoids the tanh inflection at raw=0 where the secant of a unit
    # interval approaches 1 (twice sech²(0) ≈ 1) and guarantees a measurable
    # nonlinearity gap.
    predicted = 0.0
    slippage = 0.0
    rewards = (1.0, 2.0, 3.0)
    rpes = tuple(
        adapter.compute_rpe(realized_pnl=r, predicted_return=predicted, slippage=slippage)
        for r in rewards
    )

    # Finite-difference slope ∂δ/∂r across the two unit-width intervals.
    slopes = (rpes[1] - rpes[0], rpes[2] - rpes[1])

    # INV-DA7 contrast: on the raw-TD path, each slope would be EXACTLY 1.
    # On the adapter, the secant of tanh over [a, a+1] is strictly less
    # than sech²(a).  With raw ∈ {1, 2} the ceiling is sech²(1) ≈ 0.420,
    # and both observed secants must sit strictly below that value.  A
    # slope at 1 here would mean the tanh was dropped and the adapter
    # silently upgraded to an unbounded RPE path.  epsilon: sech²(1) =
    # 1/cosh²(1) ≈ 0.41997434.
    linearity_ceiling = 1.0 / (math.cosh(1.0) ** 2)
    for slope in slopes:
        assert slope < linearity_ceiling, (
            f"INV-DA7 scope contrast VIOLATED: observed slope={slope:.6f} "
            f">= ceiling sech²(1)={linearity_ceiling:.6f} "
            f"at rewards={rewards}, predicted={predicted}, slippage={slippage}. "
            f"Expected slope < sech²(1) ≈ 0.420 under tanh normalisation. "
            f"Physical reasoning: INV-DA7 holds on DopamineController (raw TD, "
            f"slope=1); on the adapter the tanh kills linearity by design. "
            f"A slope at 1 here would mean the tanh was dropped and the "
            f"adapter silently upgraded to an unbounded RPE path."
        )

    # Companion bound: every rpe lies strictly inside (-1, 1) — the core
    # reason the adapter is non-linear in the first place.
    for r, rpe in zip(rewards, rpes):
        assert -1.0 < rpe < 1.0, (
            f"INV-DA7 scope contrast VIOLATED: observed |rpe|={abs(rpe):.6f} "
            f"not in (-1, 1) at reward={r}, predicted={predicted}, "
            f"slippage={slippage}. "
            f"Expected strict containment in the tanh image (-1, 1). "
            f"Physical reasoning: the adapter's whole purpose is to bound "
            f"the RPE so downstream consumers see a comparable signal; "
            f"losing this bound is a regression."
        )


# ---------------------------------------------------------------------------
# INV-OA1 — Ott-Antonsen |z(t)| ≤ 1 across the full parameter domain
# ---------------------------------------------------------------------------


@given(
    K=st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False),
    delta=st.floats(min_value=0.05, max_value=5.0, allow_nan=False, allow_infinity=False),
    R0=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=40, deadline=None)
def test_ott_antonsen_unit_disk_bound_property(K: float, delta: float, R0: float) -> None:
    """INV-OA1: |z(t)| ≤ 1 for every sampled (K, Δ, R0) in the documented domain.

    T23 pins this with a hand-picked 4-scenario loop.  This Hypothesis
    sweep exercises the same invariant on 40 randomised draws across
    the full sub/supercritical range, including the near-boundary
    initial condition R0 -> 1 and the subcritical regime K ≪ 2Δ.

    The engine's RK4 stepper has an explicit projection
    ``z /= |z|`` when |z| > 1 (ott_antonsen.py line 188).  This
    witness proves the projection is effective at every sampled
    trajectory step, not just for the four canned scenarios, and
    surfaces a regression if a refactor drops the projection guard.
    """
    # T = 30, dt = 0.01 matches T23; shorter trajectories would starve
    # the subcritical cases of enough decay time to reveal drift.
    engine = OttAntonsenEngine(K=K, delta=delta)
    result = engine.integrate(T=30.0, dt=0.01, R0=R0)

    # epsilon: one IEEE-754 ULP at R = 1 (≈ 2.22e-16); the 1e-12 cushion
    # absorbs the accumulated RK4 round-off over 3000 steps (≈ 3000 * 2e-16
    # ≈ 6e-13) and leaves a 2x safety margin.
    ulp_cushion = 1e-12
    r_max = float(np.max(result.R))
    assert r_max <= 1.0 + ulp_cushion, (
        f"INV-OA1 VIOLATED: observed max R={r_max:.6e} > 1 "
        f"with K={K}, delta={delta}, R0={R0}, T=30, dt=0.01, steps=3000. "
        f"Expected |z(t)| ≤ 1 by unit-disk projection at ott_antonsen.py:188. "
        f"Physical reasoning: z is a complex mean of unit phasors; |z| > 1 "
        f"indicates either a dropped projection or a numerical blow-up."
    )

    # Universal finiteness: NaN/Inf in R means the RK4 stepper diverged.
    assert np.all(np.isfinite(result.R)), (
        f"INV-OA1 VIOLATED: observed R trajectory contains non-finite values "
        f"with K={K}, delta={delta}, R0={R0}, T=30, dt=0.01, steps=3000. "
        f"Expected finite R over the full trajectory. "
        f"Physical reasoning: the ODE is stable on the unit disk; a NaN "
        f"here points to an unguarded division by |z|=0 in the projection."
    )


def test_ott_antonsen_unit_disk_falsification_boundary_ic() -> None:
    """INV-OA1 falsification inputs: R0 exactly at the unit boundary.

    The ODE has a stable manifold at |z| = 1 for the supercritical
    regime; an unguarded RK4 step can overshoot by O(dt^5).  These
    hand-picked supercritical draws force the projection branch at
    ott_antonsen.py:188 — a regression that removes the projection
    would fire here first.  We iterate multiple (K, Δ) combinations
    so the assertion witnesses the universal contract across the
    supercritical cone, not just a single point.
    """
    # Supercritical sweep (K > 2Δ) with R0 = 1 — the tightest input.
    # epsilon: 1e-12 — ULP-cushion derived from 1000-step RK4 accumulation
    # (1000 * 2.22e-16 ~ 2.22e-13) with ~5x safety margin.
    ulp_cushion = 1e-12
    scenarios = [
        (5.0, 0.5),
        (3.0, 1.0),
        (10.0, 0.2),
        (2.1, 1.0),
    ]
    for K, delta in scenarios:
        engine = OttAntonsenEngine(K=K, delta=delta)
        result = engine.integrate(T=10.0, dt=0.01, R0=1.0)
        r_max = float(np.max(result.R))
        assert r_max <= 1.0 + ulp_cushion, (
            f"INV-OA1 VIOLATED on boundary falsifier: observed max R="
            f"{r_max:.6e} > 1 with K={K}, delta={delta}, R0=1.0, "
            f"T=10, dt=0.01, steps=1000. "
            f"Expected |z(t)| ≤ 1 with projection active. "
            f"Physical reasoning: R0=1 lands exactly on the stable manifold; "
            f"an unprojected RK4 step overshoots by O(dt^5) ~ 1e-10 which "
            f"would exceed the 1e-12 ULP cushion."
        )


# ---------------------------------------------------------------------------
# INV-OMS1 — Portfolio kinetic energy symmetry & annihilation properties
# ---------------------------------------------------------------------------


@given(
    n_assets=st.integers(min_value=1, max_value=12),
    seed=st.integers(min_value=0, max_value=2**32 - 1),
)
@settings(max_examples=80, deadline=None)
def test_portfolio_kinetic_energy_sign_flip_symmetry(n_assets: int, seed: int) -> None:
    """INV-OMS1 structural property: E_kinetic(pos) == E_kinetic(-pos) exactly.

    The T14 witness proves kinetic energy stays non-negative across 50
    random scenarios.  This witness adds the structural identity that
    pins the absolute-value path: ``E_kinetic = ½·Σ|pos|·ret²`` is even
    in ``pos``, so flipping every position sign must leave the energy
    bit-identical.  A regression that replaces ``|pos|`` with ``pos``
    would fail here on any mixed-sign input while potentially still
    passing a blind sweep of strictly positive positions.
    """
    rng = np.random.default_rng(seed=seed)
    # Ensure at least one mixed-sign row by drawing from a symmetric
    # interval; all-zero vectors are trivially invariant so we skip them.
    positions = rng.uniform(low=-50.0, high=50.0, size=n_assets)
    returns = rng.uniform(low=-0.1, high=0.1, size=n_assets)

    conservator = PortfolioEnergyConservation(epsilon=0.05, return_window=5)
    e_plus = conservator.compute_kinetic(positions, returns)
    e_minus = conservator.compute_kinetic(-positions, returns)

    # epsilon: 0.0 — |a| == |-a| is a bit-exact IEEE-754 identity (tolerance
    # derived from absolute-value definition, not a numerical cushion).
    assert e_plus == e_minus, (
        f"INV-OMS1 VIOLATED: observed E_kinetic(pos)={e_plus!r} != "
        f"E_kinetic(-pos)={e_minus!r} at N={n_assets} assets, seed={seed}. "
        f"Expected bit-exact equality (|a| == |-a| in IEEE-754). "
        f"Physical reasoning: kinetic energy ½·Σ|pos|·ret² is even in "
        f"position; a sign-flip invariance failure means the |·| path "
        f"was replaced by a signed quantity, which would also let the "
        f"non-negativity bound fail on some other input."
    )
    # Non-negativity companion check — the epsilon here is 0 by theory
    # (sum of non-negative products).
    # epsilon: 0.0 — derived from pointwise non-negativity of |pos|·ret².
    assert e_plus >= 0.0, (
        f"INV-OMS1 VIOLATED: observed E_kinetic={e_plus} < 0 at "
        f"N={n_assets} assets, seed={seed}. "
        f"Expected E_kinetic ≥ 0 as a sum of non-negative products. "
        f"Physical reasoning: |pos|·ret² is pointwise non-negative."
    )


def test_portfolio_kinetic_energy_zero_annihilation_falsification() -> None:
    """INV-OMS1 falsification input: any-zero factor forces E_kinetic == 0.

    Two hand-picked annihilators drive the absolute-value product to
    zero pointwise.  A non-zero output here proves the computation
    added a positive bias or used a signed position path that leaked
    non-zero sums.  Tolerance is 0.0 (algebraic identity).
    """
    conservator = PortfolioEnergyConservation(epsilon=0.05, return_window=5)

    # Falsifier 1: all-zero positions; every return does not matter.
    pos_zero = np.zeros(6, dtype=np.float64)
    rets_nonzero = np.array([0.01, -0.02, 0.03, -0.04, 0.05, -0.06], dtype=np.float64)
    e1 = conservator.compute_kinetic(pos_zero, rets_nonzero)
    # epsilon: 0.0 — algebraic identity |0|·x² = 0 exactly in IEEE-754.
    assert e1 == 0.0, (
        f"INV-OMS1 VIOLATED on zero-position falsifier: observed "
        f"E_kinetic={e1!r} != 0 with N=6 assets, seed=n/a. "
        f"Expected bit-exact zero from |0|·ret² = 0 pointwise. "
        f"Physical reasoning: no positions -> no kinetic energy."
    )

    # Falsifier 2: all-zero returns; positions do not matter.
    pos_big = np.array([1e6, -1e6, 42.0, -42.0], dtype=np.float64)
    rets_zero = np.zeros(4, dtype=np.float64)
    e2 = conservator.compute_kinetic(pos_big, rets_zero)
    # epsilon: 0.0 — algebraic identity |x|·0² = 0 exactly in IEEE-754.
    assert e2 == 0.0, (
        f"INV-OMS1 VIOLATED on zero-return falsifier: observed "
        f"E_kinetic={e2!r} != 0 with N=4 assets, seed=n/a. "
        f"Expected bit-exact zero from |pos|·0² = 0 pointwise. "
        f"Physical reasoning: no price velocity -> no kinetic energy."
    )

    # Falsifier 3: orthogonal support — no index has both |pos|>0 and |ret|>0.
    pos_outlier = np.array([1e6, 0.0, 0.0, 0.0], dtype=np.float64)
    rets_outlier = np.array([0.0, 1e3, 0.0, 0.0], dtype=np.float64)
    e3 = conservator.compute_kinetic(pos_outlier, rets_outlier)
    # epsilon: 0.0 — algebraic, every pointwise product vanishes.
    assert e3 == 0.0, (
        f"INV-OMS1 VIOLATED on orthogonal-outlier falsifier: observed "
        f"E_kinetic={e3!r} != 0 with N=4 assets, seed=n/a. "
        f"Expected bit-exact zero when no index has both |pos|>0 and |ret|>0. "
        f"Physical reasoning: the product |pos_i|·ret_i² is zero pointwise "
        f"whenever one factor vanishes; the sum stays zero under any "
        f"orthogonal support pattern."
    )
    # Final finiteness (catches NaN bugs under extreme inputs).
    assert math.isfinite(e3), (
        f"INV-OMS1 VIOLATED on orthogonal-outlier falsifier: observed "
        f"E_kinetic={e3} non-finite with N=4 assets, seed=n/a. "
        f"Expected finite E_kinetic for finite inputs. "
        f"Physical reasoning: bounded products of finite float64 stay finite."
    )
