# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""ARC-017 closure: the numerical-stability gate has teeth.

POSITIVE
    * every trusted-baseline cross-check lands within its documented tolerance
      (Rosenstein MLE ≈ ln2, Lyapunov spectrum == Re(eig A), Σλ ≈ 0, DFA Hurst
      ≈ H_true);
    * every adversarial input (NaN / Inf / constant / all-zero / too-short /
      rank-deficient) produces an EXPLICIT refusal, never a silent number;
    * the frozen golden vectors reproduce; the gate exits GREEN.

NEGATIVE (the gate must be falsifiable — a test that cannot fail is not a test)
    * a mutated golden vector turns the verifier RED;
    * a hypothetical estimator that returns a number on a NaN input is flagged
      non-refusing by the same predicate the gate uses — proving the refusal
      check would catch a real fail-open estimator.

Run from the repo root::

    python -m pytest tests/ci/test_numerical_stability.py -q --timeout=120
"""

from __future__ import annotations

import copy
import math

import numpy as np
import pytest

from scripts.ci.check_numerical_stability import (
    GOLDEN_PATH,
    LN2,
    TOL_HURST,
    TOL_MLE_LN2,
    TOL_SPECTRUM,
    _load_json,
    adversarial_series,
    main,
    reference_crosschecks,
    refusal_table,
    refuses_via_exception,
    spectrum_contract_refusals,
    verify_golden,
)


# --- Shared, computed-once fixtures (JAX/estimator work is not cheap) ----------
@pytest.fixture(scope="module")
def crosschecks() -> list[dict]:
    return reference_crosschecks()


@pytest.fixture(scope="module")
def refusals() -> list[dict]:
    return refusal_table() + spectrum_contract_refusals()


@pytest.fixture(scope="module")
def golden_results() -> list[dict]:
    return verify_golden()


# --- POSITIVE ------------------------------------------------------------------
def test_all_crosschecks_pass(crosschecks: list[dict]) -> None:
    """Every trusted-baseline cross-check reports passed==True."""
    failed = [c["name"] for c in crosschecks if not c["passed"]]
    assert failed == [], f"cross-checks outside tolerance: {failed}"


def test_mle_core_recovers_ln2(crosschecks: list[dict]) -> None:
    """Rosenstein MLE (core) recovers ln2 on logistic r=4 within tol (INV-LE2)."""
    cc = next(c for c in crosschecks if c["name"] == "mle_core_logistic_ln2")
    assert abs(cc["achieved"] - LN2) <= TOL_MLE_LN2, (
        f"INV-LE2: λ_hat={cc['achieved']:.6f} vs ln2={LN2:.6f} "
        f"err={cc['abs_error']:.2e} > tol={TOL_MLE_LN2}"
    )
    assert cc["achieved"] > 0.0, "logistic r=4 is chaotic: λ must be positive"
    assert cc["r_squared"] >= 0.80, "INV-LE3: scaling-region R² gate must hold"


def test_mle_geosync_recovers_chaotic_sign(crosschecks: list[dict]) -> None:
    """Coarse geosync Rosenstein recovers a valid chaotic estimate (INV-LE2)."""
    cc = next(c for c in crosschecks if c["name"] == "mle_geosync_logistic_sign")
    lo, hi = cc["tol_band"]
    assert cc["is_valid"] and cc["is_chaotic"]
    assert lo <= cc["achieved"] <= hi, f"λ={cc['achieved']} outside band {cc['tol_band']}"


def test_spectrum_linear_matches_eigenvalues(crosschecks: list[dict]) -> None:
    """Benettin spectrum == Re(eig A) to 1e-3 (INV-LY1, bound NOT loosened)."""
    cc = next(c for c in crosschecks if c["name"] == "spectrum_linear_eig")
    assert cc["max_abs_error"] <= TOL_SPECTRUM, (
        f"INV-LY1: max|spectrum − Re(eig A)|={cc['max_abs_error']:.2e} > {TOL_SPECTRUM}"
    )


def test_spectrum_harmonic_sum_zero(crosschecks: list[dict]) -> None:
    """Harmonic oscillator Σλ ≈ 0 to 1e-3 (INV-LY2, O((ω·dt)⁴) regime)."""
    cc = next(c for c in crosschecks if c["name"] == "spectrum_harmonic_sum_zero")
    assert abs(cc["achieved_sum"]) <= TOL_SPECTRUM, (
        f"INV-LY2: |Σλ|={abs(cc['achieved_sum']):.2e} > {TOL_SPECTRUM} at ω·dt={cc['omega_dt']}"
    )


def test_dfa_recovers_known_hurst(crosschecks: list[dict]) -> None:
    """DFA recovers each target Hurst to 0.05 and derives γ=2H+1 (INV-DRO1)."""
    cc = next(c for c in crosschecks if c["name"] == "dfa_hurst_fgn")
    for row in cc["rows"]:
        assert row["abs_error"] <= TOL_HURST, (
            f"INV-DRO1: H_hat={row['H_hat']} vs H_true={row['H_true']} "
            f"err={row['abs_error']:.3f} > {TOL_HURST}"
        )
        assert row["gamma_derived_ok"], "γ must be DERIVED as 2H+1, never assigned"


def test_every_adversarial_input_is_refused(refusals: list[dict]) -> None:
    """No estimator returns a silent number on any adversarial input."""
    silent = [(r["estimator"], r["input"]) for r in refusals if not r["refused"]]
    assert silent == [], f"estimators returned a number instead of refusing: {silent}"


def test_refusal_coverage_is_complete(refusals: list[dict]) -> None:
    """Coverage: 3 scalar estimators × 6 adversarial inputs + 5 spectrum contracts."""
    scalar = [r for r in refusals if r["mechanism"] != "ValueError (INV-LY3)"]
    spectrum = [r for r in refusals if r["mechanism"] == "ValueError (INV-LY3)"]
    assert len(scalar) == 18, f"expected 3×6 scalar refusal checks, got {len(scalar)}"
    assert len(spectrum) == 5, f"expected 5 spectrum contract checks, got {len(spectrum)}"


def test_golden_vectors_reproduce(golden_results: list[dict]) -> None:
    """Frozen golden vectors reproduce bit-for-tol from their deterministic inputs."""
    bad = [(g["name"], g["detail"]) for g in golden_results if not g["ok"]]
    assert bad == [], f"golden vectors drifted: {bad}"


def test_gate_exits_green() -> None:
    """The end-to-end gate returns 0 (fail-closed contract satisfied)."""
    assert main([]) == 0


# --- NEGATIVE (falsifiability of the gate) -------------------------------------
def test_mutated_golden_vector_turns_verifier_red() -> None:
    """A tampered golden value must make verify_golden report ok==False (RED).

    This is the reason golden vectors exist: a numerical regression that shifts
    any estimator's frozen output beyond atol must fail the gate. We mutate the
    frozen copy in memory (never touching the committed file) and confirm the
    verifier catches exactly that vector.
    """
    frozen = copy.deepcopy(_load_json(GOLDEN_PATH)["vectors"])
    # Perturb the core-MLE golden by 1e-2 — far above its 1e-4 atol.
    frozen["mle_core_logistic"]["expected_lambda"] += 1.0e-2
    results = verify_golden(golden=frozen)
    mutated = next(g for g in results if g["name"] == "mle_core_logistic")
    assert mutated["ok"] is False, "mutated golden vector must turn the verifier RED"
    # And the untouched vectors stay green, so the failure is localised.
    others = [g for g in results if g["name"] != "mle_core_logistic"]
    assert all(g["ok"] for g in others), "mutation must not spuriously fail other vectors"


def test_fail_open_estimator_is_flagged_non_refusing() -> None:
    """A hypothetical estimator that returns a number on NaN is caught as RED.

    ``refuses_via_exception`` is the exact predicate the gate uses to decide
    whether an estimator failed closed. A fail-OPEN estimator (returns 0.0 on a
    NaN series instead of raising) must make that predicate return False — i.e.
    the gate would mark it non-refusing and go RED. The real estimator on the
    same input must return True. If both returned the same value the refusal
    check would be vacuous.
    """
    nan_input = adversarial_series()["nan"]

    def fail_open_mle(_x: np.ndarray) -> float:
        # The anti-pattern INV-LE1 forbids: a silent sentinel on a NaN input.
        return 0.0

    assert refuses_via_exception(fail_open_mle, nan_input) is False, (
        "a fail-open estimator must be flagged as NOT refusing"
    )

    from core.physics.lyapunov_exponent import maximal_lyapunov_exponent

    assert refuses_via_exception(
        lambda s: maximal_lyapunov_exponent(s, dim=3, tau=1), nan_input
    ) is True, "the real MLE must fail closed (raise) on a NaN input"


def test_nan_never_yields_a_finite_number_from_core_mle() -> None:
    """Direct INV-LE1 probe: the core MLE raises rather than returning a float."""
    from core.physics.lyapunov_exponent import maximal_lyapunov_exponent

    nan_series = np.concatenate([np.random.default_rng(0).standard_normal(300), [math.nan]])
    with pytest.raises(ValueError, match="INV-LE1"):
        maximal_lyapunov_exponent(nan_series)
