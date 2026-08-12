# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002G-M3 — Invariant tests (M3-INV-1..8 from the pre-reg §4).

One test per invariant. All eight must pass green before M3 may be
considered for any B1 eligibility-closure claim.

Invariant ledger
----------------
* M3-INV-1: deterministic RNG. ``np.random.default_rng(deterministic_mix
  (...))`` for all M3 randomness; no global state, no time seeds.
* M3-INV-2: marginal-match within locked tolerances.
* M3-INV-3: K_null is float64, symmetric, finite.
* M3-INV-4: bit-identical replay under same seed inputs.
* M3-INV-5: different null_seed → different K_null for non-degenerate cells.
* M3-INV-6: verifier emits one literal from the locked enum.
* M3-INV-7: failure ⇒ fail-closed; no silent downgrade.
* M3-INV-8: locked governance unchanged (sha pins).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from research.systemic_risk.d002c_substrates import (
    BlockStructuredSubstrate,
    RicciFlowSubstrate,
    TemporalKtSubstrate,
)
from research.systemic_risk.d002g_null_mechanisms import (
    M2_INJECTION_SEQUENCE_SALT,
    M2_NODE_PAYLOAD_SALT,
    M2_PLACEBO_SALT,
    M3_GENERATOR_MAX_ITERATIONS,
    M3_NULL_STRATEGY,
    M3_PRECURSOR_ENSEMBLE_SIZE,
    M3_TOL_DEGREE_WASSERSTEIN,
    M3_TOL_DENSITY,
    M3_TOL_SPECTRAL_RADIUS,
    M3_TOPOLOGY_CONDITIONED_SALT,
    M6_PLACEBO_SALT,
    NULL_SEED_OFFSET,
    M3EligibilityVerdict,
    M3NotEligibleError,
    realize_null,
    verify_m3_eligibility,
)

_LAMBDA = 0.4
_BASE_SEED = 42
_NULL_SEED = 12345
REPO_ROOT = Path(__file__).resolve().parents[2]

# Locked literals — verifier must emit exactly one of these.
_LOCKED_M3_VERDICT_LITERALS: frozenset[str] = frozenset(
    {
        "ELIGIBLE_M3",
        "INELIGIBLE_M3_MARGINAL_MISMATCH",
        "INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC",
        "INELIGIBLE_M3_DEGENERATE_DISTANCE",
        "INELIGIBLE_M3_GENERATOR_DIVERGENT",
        "INELIGIBLE_M3_TOPOLOGY_SUMMARY_MISSING",
        "INELIGIBLE_M3_NUMERICAL_NONFINITE",
        "INELIGIBLE_M3_SHAPE_CONTRACT_VIOLATION",
        "INDETERMINATE_M3_PROVENANCE_MISSING",
    }
)


# ---- M3-INV-1: deterministic RNG, no global state -------------------


def test_m3_inv_1_no_global_rng_dependency() -> None:
    """M3 output independent of np.random global state."""
    sub = RicciFlowSubstrate()
    real_a = realize_null(
        sub,
        strategy="M3_TOPOLOGY_CONDITIONED",
        base_seed=_BASE_SEED,
        N=50,
        lambda_value=_LAMBDA,
        null_seed=_NULL_SEED,
    )
    # Perturb the global RNG between calls.
    np.random.seed(31415)
    np.random.random(size=1000)
    real_b = realize_null(
        sub,
        strategy="M3_TOPOLOGY_CONDITIONED",
        base_seed=_BASE_SEED,
        N=50,
        lambda_value=_LAMBDA,
        null_seed=_NULL_SEED,
    )
    assert np.array_equal(real_a.K_baseline, real_b.K_baseline)
    assert real_a.payload_sha256 == real_b.payload_sha256


def test_m3_inv_1_salt_is_523_locked() -> None:
    assert M3_TOPOLOGY_CONDITIONED_SALT == 523
    assert M3_NULL_STRATEGY == "M3_TOPOLOGY_CONDITIONED"


# ---- M3-INV-2: marginals match within locked tolerance --------------


def test_m3_inv_2_marginal_match_within_tolerance_on_eligible() -> None:
    """ELIGIBLE_M3 verdict carries a match_report inside tolerances."""
    v = verify_m3_eligibility(
        RicciFlowSubstrate(),
        N=50,
        lambda_value=_LAMBDA,
        base_seed=_BASE_SEED,
        null_seed=_NULL_SEED,
    )
    assert v.status == "ELIGIBLE_M3"
    assert v.match_report is not None
    assert v.match_report.all_within_tolerance, (
        f"M3-INV-2 VIOLATED: ELIGIBLE_M3 verdict carries match_report with "
        f"failed_marginal={v.match_report.failed_marginal!r}; comparator "
        f"shouldn't promote a tolerance-failing cell"
    )
    assert v.match_report.density_rel_err < M3_TOL_DENSITY + 1e-9
    assert v.match_report.spectral_radius_rel_err < M3_TOL_SPECTRAL_RADIUS + 1e-9
    assert v.match_report.degree_wasserstein < M3_TOL_DEGREE_WASSERSTEIN + 1e-9


# ---- M3-INV-3: K_null float64 + symmetric + finite -----------------


def test_m3_inv_3_k_null_shape_dtype_symmetric_finite() -> None:
    real = realize_null(
        RicciFlowSubstrate(),
        strategy="M3_TOPOLOGY_CONDITIONED",
        base_seed=_BASE_SEED,
        N=50,
        lambda_value=_LAMBDA,
        null_seed=_NULL_SEED,
    )
    K = real.K_baseline
    assert K.dtype == np.float64, "M3-INV-3: K_null must be float64"
    assert K.shape == (50, 50), "M3-INV-3: K_null must have shape (N, N)"
    asym = float(np.max(np.abs(K - K.T)))
    assert asym < 1e-9, f"M3-INV-3: K_null asymmetry={asym} > 1e-9"
    assert np.all(np.isfinite(K)), "M3-INV-3: K_null must be finite"


# ---- M3-INV-4: bit-identical replay ---------------------------------


def test_m3_inv_4_bit_identical_replay() -> None:
    sub = RicciFlowSubstrate()
    r1 = realize_null(
        sub,
        strategy="M3_TOPOLOGY_CONDITIONED",
        base_seed=_BASE_SEED,
        N=50,
        lambda_value=_LAMBDA,
        null_seed=_NULL_SEED,
    )
    r2 = realize_null(
        sub,
        strategy="M3_TOPOLOGY_CONDITIONED",
        base_seed=_BASE_SEED,
        N=50,
        lambda_value=_LAMBDA,
        null_seed=_NULL_SEED,
    )
    assert np.array_equal(r1.K_baseline, r2.K_baseline)
    assert r1.payload_sha256 == r2.payload_sha256


# ---- M3-INV-5: different seed → different K_null --------------------


def test_m3_inv_5_different_null_seed_yields_different_k_null() -> None:
    sub = RicciFlowSubstrate()
    r1 = realize_null(
        sub,
        strategy="M3_TOPOLOGY_CONDITIONED",
        base_seed=_BASE_SEED,
        N=50,
        lambda_value=_LAMBDA,
        null_seed=_NULL_SEED,
    )
    r2 = realize_null(
        sub,
        strategy="M3_TOPOLOGY_CONDITIONED",
        base_seed=_BASE_SEED,
        N=50,
        lambda_value=_LAMBDA,
        null_seed=_NULL_SEED + 7,
    )
    assert not np.array_equal(r1.K_baseline, r2.K_baseline)
    assert r1.payload_sha256 != r2.payload_sha256


# ---- M3-INV-6: verifier emits exactly one locked literal -----------


def test_m3_inv_6_verifier_emits_locked_literal() -> None:
    """The verifier emits a status from the locked enum on every cell."""
    for sub in (RicciFlowSubstrate(), BlockStructuredSubstrate(), TemporalKtSubstrate()):
        v = verify_m3_eligibility(
            sub,
            N=50,
            lambda_value=_LAMBDA,
            base_seed=_BASE_SEED,
            null_seed=_NULL_SEED,
        )
        assert isinstance(v, M3EligibilityVerdict)
        assert v.status in _LOCKED_M3_VERDICT_LITERALS, (
            f"M3-INV-6 VIOLATED: verifier emitted non-locked literal "
            f"{v.status!r}; allowed set: {sorted(_LOCKED_M3_VERDICT_LITERALS)}"
        )


# ---- M3-INV-7: fail-closed, no silent downgrade ---------------------


def test_m3_inv_7_ineligible_raises_no_silent_m1_or_m2() -> None:
    """M3 INELIGIBLE substrates must raise, not silently return M1/M2 output."""
    for sub in (BlockStructuredSubstrate(), TemporalKtSubstrate()):
        with pytest.raises(M3NotEligibleError):
            realize_null(
                sub,
                strategy="M3_TOPOLOGY_CONDITIONED",
                base_seed=_BASE_SEED,
                N=50,
                lambda_value=_LAMBDA,
                null_seed=_NULL_SEED,
            )


# ---- M3-INV-8: locked governance unchanged --------------------------


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def test_m3_inv_8_d002c_claim_ledger_unchanged() -> None:
    ledger = REPO_ROOT / "docs" / "governance" / "D002C_CLAIM_LEDGER.yaml"
    # fmt: off
    pinned: str = "eb0b7151d76e5409e6dc9bb4a023551de5e0704673d5ac9f726319ef84a32387"  # noqa: E501  # pragma: allowlist secret  # post-D-002H-REFUSED-append (PR #692)
    # fmt: on
    assert _sha256(ledger) == pinned, (
        "M3-INV-8 VIOLATED: D002C_CLAIM_LEDGER.yaml sha drifted from "
        f"pinned {pinned}; M3 PR must not touch the ledger."
    )


def test_m3_inv_8_m3_prereg_unchanged() -> None:
    """M3 pre-registration file is locked at #680 merge sha."""
    prereg = REPO_ROOT / "docs" / "governance" / "D002G_P3_M3_PREREGISTRATION.md"
    # fmt: off
    pinned: str = "0f11a0c890374c35e4dedecc66caec52ae867f49a8f8b3be2374f1464712c1f8"  # noqa: E501  # pragma: allowlist secret
    # fmt: on
    assert _sha256(prereg) == pinned, (
        "M3-INV-8 VIOLATED: D002G_P3_M3_PREREGISTRATION.md sha drifted "
        "from #680 merge anchor; this PR must NOT touch the M3 pre-reg "
        "(touching it constitutes a fresh M4 pre-registration, not an "
        "M3 implementation PR)."
    )


def test_m3_constants_distinct_from_prior_salts() -> None:
    """Salt domain-separation is a structural M3 invariant."""
    prior = {
        NULL_SEED_OFFSET,
        M6_PLACEBO_SALT,
        M2_PLACEBO_SALT,
        M2_NODE_PAYLOAD_SALT,
        M2_INJECTION_SEQUENCE_SALT,
    }
    assert M3_TOPOLOGY_CONDITIONED_SALT not in prior


def test_m3_constants_max_iterations_locked() -> None:
    """Generator max iterations is a locked constant at 100.

    Positive: exact pin. Negative: rejects degenerate values and common
    drift targets so a silent constant retune cannot pass under the cover
    of "refinement". M3 pre-reg §9.1 explicitly forbids salt / constant
    drift without a fresh M4 pre-registration.
    """
    # Positive — exact value pinned.
    assert M3_GENERATOR_MAX_ITERATIONS == 100
    # Negative — must not be a degenerate value that defeats the
    # generator's fail-closed contract.
    assert M3_GENERATOR_MAX_ITERATIONS > 0, "max_iterations must be positive"
    assert M3_GENERATOR_MAX_ITERATIONS != 1, "max_iterations must permit ≥1 rebalance"
    # Drift sentinel — common-default values that would indicate a silent
    # constant retune rather than an intentional M4 pre-registration.
    assert M3_GENERATOR_MAX_ITERATIONS not in {10, 50, 200, 500, 1000}, "drift"


def test_m3_constants_precursor_ensemble_size_locked() -> None:
    """Precursor-specificity ensemble size is a locked constant at 100.

    Positive: exact pin. Negative: rejects degenerate values, enforces
    even-ness so the 50% majority threshold in criterion 3 is exact
    integer (not a floor-rounded approximation), and catches drift to
    common-default values.
    """
    # Positive — exact value pinned.
    assert M3_PRECURSOR_ENSEMBLE_SIZE == 100
    # Negative — ensemble must be large enough for the 50/100 majority
    # threshold in admissibility criterion 3 to be statistically meaningful.
    assert M3_PRECURSOR_ENSEMBLE_SIZE >= 30, "ensemble size < 30 is uninformative"
    # Even-ness — the 50% majority cut must be an integer, not floor(N/2).
    assert M3_PRECURSOR_ENSEMBLE_SIZE % 2 == 0, "ensemble size must be even"
    # Drift sentinel — common-default values that would indicate a silent
    # constant retune rather than an intentional M4 pre-registration.
    assert M3_PRECURSOR_ENSEMBLE_SIZE not in {10, 20, 50, 200, 500, 1000}, "drift"
