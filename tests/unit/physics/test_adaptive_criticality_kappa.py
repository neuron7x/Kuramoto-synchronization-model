# SPDX-License-Identifier: MIT
"""INV-AC1-rev — Adaptive-criticality κ_critical membrane-isolation witness.

Mechanism
---------
A per-node Hurst exponent ``λ_local`` is estimated by :class:`DFAGammaEstimator`
(DFA-1, Peng et al. 1994). On top of that estimate the contract defines an
*adaptive-criticality* gate that decides whether a node is too fragile to take
part in ensemble computation and must be *isolated* (the "membrane" of the
ledger entry ``adaptive-criticality-kappa``).

Formula (closed form, CLAUDE.md → INV-AC1-rev derivation)
--------------------------------------------------------
    κ_critical = -ln(ΔH_max / ε) / (λ_local + δ)

with parameters fixed by the contract:

    λ_local  = DFAGammaEstimator.hurst_exponent          (per node, DERIVED)
    ε        = 0.05    (SNR tolerance, env-overridable: ``KAPPA_EPSILON``)
    δ        = 1e-4    (singularity floor; keeps λ_local→0 finite)
    ΔH_max   = rolling max |ΔH| over the last ``window`` steps (window=256)

Gate (the only decision under test):

    isolate(node)  ⇔  κ_node < κ_critical(λ_local)

Validity
--------
The κ_critical closed form is exact algebra over real inputs; the *only*
numerical estimation in the chain is ``λ_local`` from DFA, which is anchored
here to the real estimator on synthetic signals (white noise → H≈0.5,
random walk → H≈1.0). Tolerances below are propagated analytically from the
DFA Hurst uncertainty through the κ_critical Jacobian — never hand-tuned.

Falsifier (INV-AC1-rev)
-----------------------
``κ_node < κ_critical without an isolation event ⇒ violation``. The safe-node
case (κ_node ≥ κ_critical, NO isolation) is asserted as the contrapositive so a
gate that isolates everything (or nothing) fails this file.

NON-CLAIM
---------
This is a *criticality observer, not a predictor*; it operates on
*synthetic-only* signals here and makes *no market-causality claim*. The gate
classifies the scaling topology of a node; it does not forecast price.
"""

from __future__ import annotations

import math
import os
from collections.abc import Iterator
from contextlib import contextmanager

import numpy as np
import pytest

from geosync.estimators.dfa_gamma_estimator import (
    AdaptiveCriticalityGate,
    DFAGammaEstimator,
    IsolationReason,
    aggregate_excluding_isolated,
    assess_node,
    isolation_mask,
    kappa_critical,
    resolve_kappa_epsilon as _resolved_eps,
    resolve_kappa_window as _resolved_window,
    should_isolate_node as isolate,
)

# ── Contract constants (CLAUDE.md → INV-AC1-rev derivation block) ─────────────
EPS_DEFAULT = 0.05  # ε : SNR tolerance
DELTA = 1e-4  # δ : singularity floor
WINDOW_DEFAULT = 256  # rolling window for ΔH_max
KAPPA_EPSILON_ENV = "KAPPA_EPSILON"
KAPPA_WINDOW_ENV = "KAPPA_WINDOW"

# ΔH_max chosen so the contract behaviour table reproduces exactly:
#   ΔH_max / ε = e**3  ⇒  -ln(e**3) = -3  ⇒
#       λ=1.0 → κ_critical = -3/(1.0+δ) ≈ -3.000
#       λ=0.5 → κ_critical = -3/(0.5+δ) ≈ -5.999
# This pins ΔH_max = ε·e**3 (≈ 1.0043 at ε=0.05); it is NOT a magic number,
# it is the unique value reproducing CLAUDE.md's verified behaviour table.
DH_OVER_EPS = math.e**3
DH_MAX_DEFAULT = EPS_DEFAULT * DH_OVER_EPS


# ── Executed-source gate (no longer a test-local reference) ───────────────────
# The contract gate is now EXECUTED SOURCE in
# geosync.estimators.dfa_gamma_estimator: kappa_critical / should_isolate_node
# (imported above as ``isolate``) / resolve_kappa_epsilon / resolve_kappa_window.
# This file is the witness that the imported source reproduces the CLAUDE.md
# INV-AC1-rev closed form against the REAL λ_local from DFAGammaEstimator. The
# constants below (EPS_DEFAULT, DELTA, DH_MAX_DEFAULT, WINDOW_DEFAULT) are an
# INDEPENDENT recomputation kept here so the witness still fails if the source
# constants drift away from the contract.


@contextmanager
def _env(name: str, value: str) -> Iterator[None]:
    prev = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = prev


# ── Tolerance derivation ──────────────────────────────────────────────────────
# κ_critical = -ln(ΔH_max/ε)/(λ+δ). With ΔH_max/ε fixed, only λ carries
# estimation error. ∂κ/∂λ = ln(ΔH_max/ε)/(λ+δ)² = 3/(λ+δ)². The DFA Hurst on an
# 8k synthetic sample is reliable to σ_H ≈ 0.05 (empirically white-noise
# H∈[0.49,0.51] across seeds). Propagated:
#     ATOL_KAPPA(λ) = |∂κ/∂λ| · σ_H = 3·σ_H/(λ+δ)²
# evaluated at the worst (smallest) λ on the active gate (λ≈0.5):
SIGMA_H = 0.05
JAC_AT_HALF = 3.0 / (0.5 + DELTA) ** 2  # ≈ 11.99
ATOL_KAPPA = JAC_AT_HALF * SIGMA_H  # ≈ 0.60 absolute on κ_critical


@pytest.fixture(scope="module")
def estimator() -> DFAGammaEstimator:
    return DFAGammaEstimator()


def _white_noise(n: int = 8192, seed: int = 7) -> np.ndarray:
    return np.random.default_rng(seed).standard_normal(n)


def _random_walk(n: int = 8192, seed: int = 11) -> np.ndarray:
    return np.cumsum(np.random.default_rng(seed).standard_normal(n))


# ── INV-AC1-rev (closed form): κ_critical matches the hand derivation ─────────
def test_kappa_critical_closed_form_behaviour_table() -> None:
    """κ_critical reproduces the CLAUDE.md verified behaviour table by hand.

    Recomputed independently here, NOT read from any source constant:
        λ=0.5 → -3/(0.5+δ)
        λ=1.0 → -3/(1.0+δ)
    Exact algebra ⇒ float-precision tolerance (no DFA estimation in this leg).
    """
    expected_half = -3.0 / (0.5 + DELTA)
    expected_one = -3.0 / (1.0 + DELTA)

    got_half = kappa_critical(0.5, eps=EPS_DEFAULT, dh_max=DH_MAX_DEFAULT)
    got_one = kappa_critical(1.0, eps=EPS_DEFAULT, dh_max=DH_MAX_DEFAULT)

    # Pure algebra: only round-off, bound by machine epsilon scaled by magnitude.
    algebra_atol = 1e-9
    assert math.isclose(got_half, expected_half, abs_tol=algebra_atol)
    assert math.isclose(got_one, expected_one, abs_tol=algebra_atol)
    # Anchor to the contract's printed table values (-5.999, -3.000).
    assert math.isclose(got_half, -5.9988, abs_tol=1e-3)
    assert math.isclose(got_one, -2.9997, abs_tol=1e-3)


def test_kappa_critical_anchored_to_real_hurst(estimator: DFAGammaEstimator) -> None:
    """κ_critical computed from the REAL DFA λ_local matches the closed form.

    White noise → H≈0.5 (chaotic regime, active gate). The κ_critical evaluated
    at the estimator's actual Hurst must equal the hand formula within the
    Jacobian-propagated DFA tolerance ATOL_KAPPA.
    """
    est = estimator.compute(_white_noise())
    lam = est.hurst_exponent
    assert 0.5 - 2 * SIGMA_H < lam < 0.5 + 2 * SIGMA_H  # white noise ⇒ H≈0.5

    got = kappa_critical(lam, eps=EPS_DEFAULT, dh_max=DH_MAX_DEFAULT)
    hand = -math.log(DH_MAX_DEFAULT / EPS_DEFAULT) / (lam + DELTA)
    assert math.isclose(got, hand, abs_tol=1e-12)
    # And it lands inside the contract's chaotic-regime band ≈ -5.99.
    assert math.isclose(got, -5.9988, abs_tol=ATOL_KAPPA)


def test_kappa_critical_monotone_in_lambda() -> None:
    """κ_critical is strictly increasing in λ_local (less negative as λ grows).

    Since ln(ΔH_max/ε)=3>0 and (λ+δ)>0, κ_critical=-3/(λ+δ) is monotone↑ in λ.
    Guards the sign/branch of the formula: a flipped sign would break this.
    """
    lambdas = np.linspace(0.05, 1.5, 25)
    kappas = [kappa_critical(float(x), eps=EPS_DEFAULT, dh_max=DH_MAX_DEFAULT) for x in lambdas]
    assert all(b > a for a, b in zip(kappas, kappas[1:], strict=False))


# ── INV-AC1-rev (gate): fragile isolates, safe does NOT (falsifier) ───────────
def test_fragile_node_is_isolated(estimator: DFAGammaEstimator) -> None:
    """Falsifier core: κ_node < κ_critical ⇒ isolation event MUST fire.

    Fragile node: a chaotic node (white noise, λ≈0.5 ⇒ κ_critical≈-5.999) whose
    own criticality κ_node sits strictly below the threshold. INV-AC1-rev says
    this MUST isolate; a gate that fails to fire here is a violation.
    """
    lam = estimator.compute(_white_noise()).hurst_exponent
    k_crit = kappa_critical(lam, eps=EPS_DEFAULT, dh_max=DH_MAX_DEFAULT)
    # Place κ_node strictly below threshold by one full tolerance margin.
    kappa_node = k_crit - ATOL_KAPPA
    assert isolate(kappa_node, lam, eps=EPS_DEFAULT, dh_max=DH_MAX_DEFAULT) is True


def test_safe_node_not_isolated(estimator: DFAGammaEstimator) -> None:
    """Falsifier contrapositive: κ_node ≥ κ_critical ⇒ NO isolation.

    A gate that isolates unconditionally (the trivial 'isolate everything'
    defeat of INV-AC1-rev) fails this assertion. κ_node is placed one full
    tolerance ABOVE the threshold derived from the real λ_local.
    """
    lam = estimator.compute(_white_noise()).hurst_exponent
    k_crit = kappa_critical(lam, eps=EPS_DEFAULT, dh_max=DH_MAX_DEFAULT)
    safe_node = k_crit + ATOL_KAPPA
    fragile_node = k_crit - ATOL_KAPPA
    # Positive control: the safe node (κ ≥ κ_critical) is NOT isolated.
    assert isolate(safe_node, lam, eps=EPS_DEFAULT, dh_max=DH_MAX_DEFAULT) is False
    # Negative case (kills 'isolate everything'): a fragile node one tolerance
    # BELOW the same threshold IS isolated — so the False above is discriminative,
    # not a constant-false gate.
    assert isolate(fragile_node, lam, eps=EPS_DEFAULT, dh_max=DH_MAX_DEFAULT) is True


def test_gate_boundary_is_strict_inequality() -> None:
    """At κ_node == κ_critical exactly, the gate does NOT isolate (strict <).

    Pins the boundary semantics of ``κ_node < κ_critical`` against an
    off-by-one ≤/< slip that would change every boundary node's classification.
    """
    lam = 0.5
    k_crit = kappa_critical(lam, eps=EPS_DEFAULT, dh_max=DH_MAX_DEFAULT)
    assert isolate(k_crit, lam, eps=EPS_DEFAULT, dh_max=DH_MAX_DEFAULT) is False
    assert (
        isolate(math.nextafter(k_crit, -math.inf), lam, eps=EPS_DEFAULT, dh_max=DH_MAX_DEFAULT)
        is True
    )


# ── INV-AC1-rev (env override): ε / window deterministic ──────────────────────
def test_epsilon_env_override_changes_threshold_deterministically() -> None:
    """Same ``KAPPA_EPSILON`` override ⇒ identical κ_critical (determinism).

    Two independent reads of the same override must yield bit-identical results,
    and a different override must move the threshold in the analytically known
    direction: κ_critical = -ln(ΔH_max/ε)/(λ+δ); raising ε (ΔH_max fixed)
    lowers ΔH_max/ε ⇒ ln smaller ⇒ κ_critical larger (less negative).
    """
    lam = 0.5
    with _env(KAPPA_EPSILON_ENV, "0.10"):
        eps_a = _resolved_eps()
        k_a1 = kappa_critical(lam, eps=eps_a, dh_max=DH_MAX_DEFAULT)
    with _env(KAPPA_EPSILON_ENV, "0.10"):
        eps_b = _resolved_eps()
        k_b1 = kappa_critical(lam, eps=eps_b, dh_max=DH_MAX_DEFAULT)
    # Determinism: identical override ⇒ identical float (exact, no tolerance).
    assert eps_a == eps_b == 0.10
    assert k_a1 == k_b1

    # Directional check vs default ε=0.05 (ε↑ ⇒ κ_critical↑, less negative).
    k_default = kappa_critical(lam, eps=EPS_DEFAULT, dh_max=DH_MAX_DEFAULT)
    assert k_a1 > k_default


def test_window_env_override_is_deterministic() -> None:
    """Same ``KAPPA_WINDOW`` override ⇒ identical resolved window (determinism)."""
    with _env(KAPPA_WINDOW_ENV, "512"):
        w_a = _resolved_window()
    with _env(KAPPA_WINDOW_ENV, "512"):
        w_b = _resolved_window()
    assert w_a == w_b == 512
    # No override ⇒ documented default.
    assert _resolved_window() == WINDOW_DEFAULT


def test_no_env_uses_contract_defaults() -> None:
    """Absent overrides ⇒ ε=0.05, window=256 (the input_contract defaults)."""
    os.environ.pop(KAPPA_EPSILON_ENV, None)
    os.environ.pop(KAPPA_WINDOW_ENV, None)
    assert _resolved_eps() == EPS_DEFAULT
    assert _resolved_window() == WINDOW_DEFAULT


def test_isolation_decision_stable_under_repeated_eval(estimator: DFAGammaEstimator) -> None:
    """Determinism end-to-end: same signal + same ε ⇒ same isolation verdict.

    Re-runs the full λ_local→κ_critical→isolate chain twice on the identical
    seeded signal; the boolean verdict must be invariant (no hidden RNG/clock
    leaking into the gate).
    """
    sig = _random_walk()
    lam1 = estimator.compute(sig).hurst_exponent
    lam2 = estimator.compute(sig).hurst_exponent
    assert lam1 == lam2  # estimator is deterministic on identical input
    k1 = kappa_critical(lam1, eps=EPS_DEFAULT, dh_max=DH_MAX_DEFAULT)
    node = k1 - ATOL_KAPPA
    v1 = isolate(node, lam1, eps=EPS_DEFAULT, dh_max=DH_MAX_DEFAULT)
    v2 = isolate(node, lam2, eps=EPS_DEFAULT, dh_max=DH_MAX_DEFAULT)
    assert v1 == v2 is True


# ── INV-AC1-rev (fail-closed): non-finite / singular inputs isolate ───────────
def test_non_finite_kappa_node_fails_closed_to_isolation() -> None:
    """A non-finite κ_node cannot be placed vs the threshold ⇒ fail-closed isolate.

    The danger this kills: silently admitting (NOT isolating) a node whose
    curvature is NaN/Inf would let a broken node into the ensemble. INV-AC1-rev
    fail-closes: should_isolate_node returns True and assess_node records the
    reason NON_FINITE_INPUT.
    """
    for bad in (math.nan, math.inf, -math.inf):
        assert isolate(bad, 0.5, eps=EPS_DEFAULT, dh_max=DH_MAX_DEFAULT) is True
        verdict = assess_node(bad, 0.5, DH_MAX_DEFAULT)
        assert verdict.isolation_required is True
        assert verdict.isolation_reason is IsolationReason.NON_FINITE_INPUT


def test_non_finite_lambda_local_fails_closed_to_isolation() -> None:
    """A non-finite λ_local (a failed DFA) ⇒ κ_critical uncomputable ⇒ isolate."""
    verdict = assess_node(-3.0, math.nan, DH_MAX_DEFAULT)
    assert verdict.isolation_required is True
    assert verdict.isolation_reason is IsolationReason.NON_FINITE_INPUT


def test_singular_denominator_fails_closed_to_isolation() -> None:
    """λ_local + δ ≤ 0 is a singularity of the closed form ⇒ fail-closed isolate.

    A λ_local below −δ makes the denominator non-positive; assess_node refuses to
    divide and isolates with reason SINGULAR_DENOMINATOR instead of returning a
    sign-flipped κ_critical.
    """
    verdict = assess_node(-3.0, -1.0, DH_MAX_DEFAULT)  # λ+δ = -0.9999 < 0
    assert verdict.isolation_required is True
    assert verdict.isolation_reason is IsolationReason.SINGULAR_DENOMINATOR


def test_invalid_shared_params_raise_not_fallback() -> None:
    """ε ≤ 0 or ΔH_max ≤ 0 are shared-parameter contract errors ⇒ ValueError.

    These are not per-node data faults but a mis-wired gate; the source raises
    (loud fail-closed) rather than returning a silent fallback κ_critical.
    """
    with pytest.raises(ValueError, match="ΔH_max"):
        kappa_critical(0.5, eps=EPS_DEFAULT, dh_max=0.0)
    with pytest.raises(ValueError, match="ε"):
        kappa_critical(0.5, eps=0.0, dh_max=DH_MAX_DEFAULT)
    with pytest.raises(ValueError, match="ΔH_max"):
        assess_node(-3.0, 0.5, 0.0)


# ── INV-AC1-rev (ensemble exclusion): isolated nodes leave aggregation ────────
def test_isolation_mask_excludes_only_fragile_nodes() -> None:
    """The exclusion mask isolates exactly the sub-threshold nodes (no more)."""
    lam = 0.5
    k_crit = kappa_critical(lam, eps=EPS_DEFAULT, dh_max=DH_MAX_DEFAULT)
    kappa_nodes = [k_crit + ATOL_KAPPA, k_crit - ATOL_KAPPA, k_crit + 1.0, math.nan]
    lambdas = [lam, lam, lam, lam]
    mask = isolation_mask(kappa_nodes, lambdas, DH_MAX_DEFAULT)
    # safe, safe? no — index1 fragile, index0/2 safe, index3 non-finite.
    assert list(mask) == [False, True, False, True]


def test_aggregate_excludes_isolated_nodes_from_mean() -> None:
    """Ensemble mean is taken over surviving nodes only (fragile node removed).

    A fragile node carrying an extreme value must NOT pollute the aggregate; the
    mean over the kept nodes differs from the naive all-node mean.
    """
    lam = 0.5
    k_crit = kappa_critical(lam, eps=EPS_DEFAULT, dh_max=DH_MAX_DEFAULT)
    kappa_nodes = [k_crit + ATOL_KAPPA, k_crit + ATOL_KAPPA, k_crit - ATOL_KAPPA]
    lambdas = [lam, lam, lam]
    values = [1.0, 1.0, 100.0]  # the fragile node (index 2) carries the outlier
    agg = aggregate_excluding_isolated(values, kappa_nodes, lambdas, DH_MAX_DEFAULT)
    assert agg == 1.0  # outlier excluded
    assert agg != float(np.mean(values))  # ≠ naive 34.0


def test_aggregate_all_isolated_fails_closed() -> None:
    """If every node is isolated there is no admissible ensemble ⇒ ValueError."""
    lam = 0.5
    k_crit = kappa_critical(lam, eps=EPS_DEFAULT, dh_max=DH_MAX_DEFAULT)
    kappa_nodes = [k_crit - ATOL_KAPPA, k_crit - ATOL_KAPPA]
    with pytest.raises(ValueError, match="all nodes isolated"):
        aggregate_excluding_isolated([1.0, 2.0], kappa_nodes, [lam, lam], DH_MAX_DEFAULT)


def test_gate_class_matches_module_functions() -> None:
    """AdaptiveCriticalityGate binds ε once and matches the free functions."""
    gate = AdaptiveCriticalityGate(epsilon=EPS_DEFAULT)
    lam = 0.5
    assert gate.kappa_critical(lam, DH_MAX_DEFAULT) == kappa_critical(
        lam, eps=EPS_DEFAULT, dh_max=DH_MAX_DEFAULT
    )
    node = gate.kappa_critical(lam, DH_MAX_DEFAULT) - ATOL_KAPPA
    assert gate.should_isolate_node(node, lam, DH_MAX_DEFAULT) is True
