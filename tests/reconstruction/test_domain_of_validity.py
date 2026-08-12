# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the real-data domain-of-validity gate (FIX B2).

INV-RECONSTRUCTION-2:
    "Recovery" is defined only on synthetic substrates with known
    ground truth. On real data with unobserved truth, the strongest
    available gate is DOMAIN-OF-VALIDITY: do real inputs fall inside
    the regime where synthetic recovery was demonstrated?

These tests pin the verdict surface for that gate (WITHIN_/OUT_OF_/
INSUFFICIENT_) and certify the contract that the real-data path is
FORBIDDEN from emitting GROUND_TRUTH_RECOVERED.
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from research.reconstruction.positive_control import (
    GroundTruthRecoveryCertificate,
    ground_truth_core_periphery,
    run_recovery_on_substrate,
)
from research.reconstruction.reconstruction_capsule import (
    ReconstructionStatus,
    assert_real_data_status_legal,
    assert_synthetic_status_legal,
)
from research.reconstruction.recovery_audit import (
    DomainCheck,
    DomainOfValidityStatus,
    _gini,
    _strength_pearson,
    check_domain_of_validity,
)

# Hypothesis strategy aliases used in property tests below.
_ALIVE_INT_SEED = st.integers(min_value=0, max_value=2**31 - 1)

# ---------------------------------------------------------------------------
# Helpers — synthesise marginals + a "real-like" certificate envelope
# ---------------------------------------------------------------------------


def _synthetic_certificate_at(n: int, seed: int = 42) -> GroundTruthRecoveryCertificate:
    """Real positive-control certificate at the requested N (Gate 5 path)."""
    w = ground_truth_core_periphery(n=n, core_frac=0.30, seed=seed)
    return run_recovery_on_substrate(f"CP_{n}", w, seed=seed)


# Module-scoped baseline certificate. The DoV tests are pure gate
# logic — they do not need a fresh Gate 5 sweep per test. Caching at
# (N=80, seed=42) once and reusing across the whole test module saves
# ~10 × 5-10s of `run_recovery_on_substrate` on CI without weakening
# the contract. The (N=80, seed=42) cell is specifically certified
# stable on `core_periphery` by the empirical recovery summary
# (X10R_EMPIRICAL_RECOVERY_SUMMARY.md row 1).
_CACHED_CERT_N80_SEED42: GroundTruthRecoveryCertificate | None = None


def _cached_cert_n80_seed42() -> GroundTruthRecoveryCertificate:
    global _CACHED_CERT_N80_SEED42
    if _CACHED_CERT_N80_SEED42 is None:
        _CACHED_CERT_N80_SEED42 = _synthetic_certificate_at(n=80, seed=42)
    return _CACHED_CERT_N80_SEED42


def _marginals_for_n(n: int, *, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Generate balanced (Σs_in = Σs_out) lognormal marginals."""
    rng = np.random.default_rng(seed)
    s_out = rng.lognormal(mean=10.0, sigma=1.0, size=n)
    s_in = rng.lognormal(mean=10.0, sigma=1.0, size=n)
    # Re-balance to satisfy GATE_2 conservation of mass (cheap rescale).
    s_in = s_in * (s_out.sum() / s_in.sum())
    return s_out, s_in


def _stub_certificate_only_n(n_set: tuple[int, ...]) -> GroundTruthRecoveryCertificate:
    """Certificate with tested_at_n_nodes set, density envelope absent."""
    return GroundTruthRecoveryCertificate(
        substrate_name="stub",
        n_nodes=int(n_set[0]),
        target_density=0.05,
        sweep_densities=(),
        per_density_reports={},
        passed=True,
        failure_reasons=(),
        cert_id="0" * 64,
        tested_at_n_nodes=n_set,
        tested_at_densities=(),
        tested_at_reciprocity=(),
    )


def _empty_certificate() -> GroundTruthRecoveryCertificate:
    """Certificate with no evidence on any dimension (FIX B4 'silent' case)."""
    return GroundTruthRecoveryCertificate(
        substrate_name="empty",
        n_nodes=0,
        target_density=0.05,
        sweep_densities=(),
        per_density_reports={},
        passed=False,
        failure_reasons=("no sweep was run",),
        cert_id="0" * 64,
        tested_at_n_nodes=(),
        tested_at_densities=(),
        tested_at_reciprocity=(),
    )


# ---------------------------------------------------------------------------
# Verdict surface — the four canonical paths (per FIX B2 spec)
# ---------------------------------------------------------------------------


def test_within_domain_when_all_dims_inside_certified_range() -> None:
    """N inside [min, max] of tested_at_n_nodes AND density inside envelope
    ⇒ WITHIN_VALIDATED_DOMAIN."""
    cert = _cached_cert_n80_seed42()
    s_out, s_in = _marginals_for_n(n=80, seed=11)
    # Pick an inferred density inside the certified sweep envelope.
    densities = cert.tested_at_densities
    inside = float((min(densities) + max(densities)) / 2.0)
    check = check_domain_of_validity(s_out, s_in, cert, inferred_density=inside)
    assert isinstance(check, DomainCheck)
    assert check.status is DomainOfValidityStatus.WITHIN_VALIDATED_DOMAIN
    assert check.checks["n_nodes"] is True
    assert check.checks["density"] is True
    assert check.out_of_range_dims == ()


def test_out_of_domain_when_n_nodes_exceed_certified() -> None:
    """N outside the certificate's tested_at_n_nodes envelope ⇒ OUT_OF_."""
    cert = _cached_cert_n80_seed42()
    s_out, s_in = _marginals_for_n(n=600, seed=12)
    inside = float((min(cert.tested_at_densities) + max(cert.tested_at_densities)) / 2.0)
    check = check_domain_of_validity(s_out, s_in, cert, inferred_density=inside)
    assert check.status is DomainOfValidityStatus.OUT_OF_VALIDATED_DOMAIN
    assert "n_nodes" in check.out_of_range_dims
    assert check.checks["n_nodes"] is False


def test_out_of_domain_when_density_below_floor() -> None:
    """Inferred density well below the smallest tested density ⇒ OUT_OF_."""
    cert = _cached_cert_n80_seed42()
    s_out, s_in = _marginals_for_n(n=80, seed=13)
    floor = float(min(cert.tested_at_densities))
    check = check_domain_of_validity(s_out, s_in, cert, inferred_density=floor / 10.0)
    assert check.status is DomainOfValidityStatus.OUT_OF_VALIDATED_DOMAIN
    assert "density" in check.out_of_range_dims
    assert check.checks["density"] is False


def test_insufficient_when_certificate_lacks_tested_ranges() -> None:
    """Empty evidence surface AND a required-dim ask ⇒ INSUFFICIENT_."""
    cert = _empty_certificate()
    s_out, s_in = _marginals_for_n(n=80, seed=14)
    check = check_domain_of_validity(s_out, s_in, cert, inferred_density=0.05)
    assert check.status is DomainOfValidityStatus.INSUFFICIENT_CERTIFICATE
    assert "n_nodes" in check.missing_dims
    assert "density" in check.missing_dims


def test_partial_certificate_only_n_dim_yields_insufficient_for_density() -> None:
    """Certificate with only N evidence: density is missing ⇒ INSUFFICIENT_."""
    cert = _stub_certificate_only_n(n_set=(50, 200))
    s_out, s_in = _marginals_for_n(n=80, seed=15)
    check = check_domain_of_validity(s_out, s_in, cert, inferred_density=0.05)
    assert check.status is DomainOfValidityStatus.INSUFFICIENT_CERTIFICATE
    assert "density" in check.missing_dims
    assert check.checks.get("n_nodes") is True


# ---------------------------------------------------------------------------
# Real-data emission contract — the forbidden category error
# ---------------------------------------------------------------------------


def test_real_data_path_emits_within_or_out_never_recovered() -> None:
    """INV-RECONSTRUCTION-2: real-data status must be a domain-of-validity
    status; emitting GROUND_TRUTH_RECOVERED on real data is forbidden."""
    legal = {
        ReconstructionStatus.WITHIN_VALIDATED_DOMAIN,
        ReconstructionStatus.OUT_OF_VALIDATED_DOMAIN,
        ReconstructionStatus.INSUFFICIENT_CERTIFICATE,
    }
    for s in legal:
        assert_real_data_status_legal(s)

    forbidden = {
        ReconstructionStatus.GROUND_TRUTH_RECOVERED,
        ReconstructionStatus.GROUND_TRUTH_NOT_RECOVERED,
        ReconstructionStatus.INVALID_RECONSTRUCTION,
        ReconstructionStatus.OUT_OF_DENSITY_BOUND,
    }
    for s in forbidden:
        with pytest.raises(ValueError, match="INV-RECONSTRUCTION-2"):
            assert_real_data_status_legal(s)


def test_synthetic_path_emits_recovery_status_never_domain_status() -> None:
    """The mirror contract: synthetic path forbids domain-of-validity
    statuses (those are reserved for real data)."""
    legal = {
        ReconstructionStatus.GROUND_TRUTH_RECOVERED,
        ReconstructionStatus.GROUND_TRUTH_NOT_RECOVERED,
        ReconstructionStatus.INVALID_RECONSTRUCTION,
        ReconstructionStatus.OUT_OF_DENSITY_BOUND,
    }
    for s in legal:
        assert_synthetic_status_legal(s)

    forbidden = {
        ReconstructionStatus.WITHIN_VALIDATED_DOMAIN,
        ReconstructionStatus.OUT_OF_VALIDATED_DOMAIN,
        ReconstructionStatus.INSUFFICIENT_CERTIFICATE,
    }
    for s in forbidden:
        with pytest.raises(ValueError, match="INV-RECONSTRUCTION-1"):
            assert_synthetic_status_legal(s)


# ---------------------------------------------------------------------------
# DomainCheck behaviour & input contract
# ---------------------------------------------------------------------------


def test_domain_check_serialises_to_dict() -> None:
    cert = _cached_cert_n80_seed42()
    s_out, s_in = _marginals_for_n(n=80, seed=16)
    inside = float((min(cert.tested_at_densities) + max(cert.tested_at_densities)) / 2.0)
    check = check_domain_of_validity(s_out, s_in, cert, inferred_density=inside)
    payload = check.as_dict()
    assert payload["status"] == check.status.value
    assert "checks" in payload
    assert "measured" in payload
    assert "certified_envelope" in payload
    assert isinstance(payload["out_of_range_dims"], list)


def test_domain_check_rejects_shape_mismatch() -> None:
    cert = _cached_cert_n80_seed42()
    s_out = np.zeros(50)
    s_in = np.zeros(60)
    with pytest.raises(ValueError, match="shape mismatch"):
        check_domain_of_validity(s_out, s_in, cert)


def test_domain_check_rejects_too_small_n() -> None:
    cert = _cached_cert_n80_seed42()
    s = np.array([1.0])
    with pytest.raises(ValueError, match="at least 2 nodes"):
        check_domain_of_validity(s, s, cert)


def test_domain_check_rejects_non_finite_marginals() -> None:
    cert = _cached_cert_n80_seed42()
    s_out = np.array([1.0, np.nan, 3.0])
    s_in = np.array([1.0, 2.0, 3.0])
    with pytest.raises(ValueError, match="finite"):
        check_domain_of_validity(s_out, s_in, cert)


def test_evidence_envelope_reports_min_max() -> None:
    """The envelope helper returns (min, max) per dimension that has evidence.

    Post X-10R-2 (#636): reciprocity is now populated from the substrate's
    achieved ratio whenever the certificate passes. Default substrates
    (CP, hierarchical, BA) build both directions per edge, so the
    achieved ratio is 1.0 unless reciprocity_keep_p < 1.0.
    """
    cert = _cached_cert_n80_seed42()
    env = cert.evidence_envelope()
    assert "n_nodes" in env
    assert env["n_nodes"] == (80, 80)
    assert "density" in env
    lo, hi = env["density"]
    assert lo <= hi
    # Default CP substrate has full bidirectional symmetry → r=1.
    assert "reciprocity" in env
    r_lo, r_hi = env["reciprocity"]
    assert 0.99 <= r_lo <= r_hi <= 1.0


def test_within_domain_when_real_n_at_envelope_boundary() -> None:
    """N exactly at the envelope max passes (closed interval contract)."""
    cert = _stub_certificate_only_n(n_set=(50, 200))
    cert_with_density = GroundTruthRecoveryCertificate(
        substrate_name=cert.substrate_name,
        n_nodes=cert.n_nodes,
        target_density=cert.target_density,
        sweep_densities=cert.sweep_densities,
        per_density_reports=cert.per_density_reports,
        passed=cert.passed,
        failure_reasons=cert.failure_reasons,
        cert_id=cert.cert_id,
        tested_at_n_nodes=cert.tested_at_n_nodes,
        tested_at_densities=(0.05,),
        tested_at_reciprocity=cert.tested_at_reciprocity,
    )
    s_out, s_in = _marginals_for_n(n=200, seed=17)
    check = check_domain_of_validity(s_out, s_in, cert_with_density, inferred_density=0.05)
    assert check.status is DomainOfValidityStatus.WITHIN_VALIDATED_DOMAIN
    assert check.checks["n_nodes"] is True
    assert check.checks["density"] is True


def test_certified_envelope_is_populated_on_within_verdict() -> None:
    cert = _cached_cert_n80_seed42()
    s_out, s_in = _marginals_for_n(n=80, seed=18)
    inside = float((min(cert.tested_at_densities) + max(cert.tested_at_densities)) / 2.0)
    check = check_domain_of_validity(s_out, s_in, cert, inferred_density=inside)
    assert "n_nodes" in check.certified_envelope
    assert "density" in check.certified_envelope
    n_lo, n_hi = check.certified_envelope["n_nodes"]
    assert n_lo == n_hi == 80


def test_reciprocity_required_but_missing_returns_insufficient() -> None:
    """Caller can demand a reciprocity gate even though FIX B6 hasn't shipped;
    the gate must then report INSUFFICIENT_CERTIFICATE rather than a free pass."""
    cert = _cached_cert_n80_seed42()
    s_out, s_in = _marginals_for_n(n=80, seed=19)
    inside = float((min(cert.tested_at_densities) + max(cert.tested_at_densities)) / 2.0)
    check = check_domain_of_validity(
        s_out,
        s_in,
        cert,
        inferred_density=inside,
        require_dims=("n_nodes", "density", "reciprocity"),
    )
    assert check.status is DomainOfValidityStatus.INSUFFICIENT_CERTIFICATE
    assert "reciprocity" in check.missing_dims


# ---------------------------------------------------------------------------
# Property-based tests on the heterogeneity / reciprocity helpers used by
# the domain-of-validity gate. _gini and _strength_pearson are private but
# they sit at the load-bearing seam between input statistics and the
# domain-of-validity verdict — when reciprocity-aware controls (FIX B6)
# land, these are the helpers the gate will invoke.
# ---------------------------------------------------------------------------


_FLOAT_NN = st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False)
_FLOAT_R = st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False)


@given(
    n=st.integers(min_value=2, max_value=200),
    seed=st.integers(min_value=0, max_value=2**31 - 1),
)
@settings(max_examples=40, deadline=None)
def test_gini_is_in_unit_interval_on_lognormal_inputs(n: int, seed: int) -> None:
    """Gini is bounded in [0, 1] on any non-negative non-zero vector.

    Tested on lognormal samples — the canonical heavy-tailed analogue
    of bank-strength distributions, the regime check_domain_of_validity
    sees on real BIS data.
    """
    rng = np.random.default_rng(seed)
    x = rng.lognormal(mean=10.0, sigma=2.0, size=n)
    g = _gini(x)
    assert 0.0 <= g <= 1.0


def test_gini_zero_for_constant_vector() -> None:
    """Gini = 0 ⇔ perfect equality. Required at the lower bound."""
    assert _gini(np.array([3.0, 3.0, 3.0, 3.0])) == 0.0


def test_gini_approaches_one_for_extreme_concentration() -> None:
    """Gini → 1 as one entry dominates — required at the upper bound."""
    n = 100
    x = np.zeros(n)
    x[0] = 1.0
    g = _gini(x)
    # The exact upper bound on n=100 with one positive entry is (n-1)/n = 0.99.
    assert g >= 0.95


def test_gini_rejects_non_finite() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        _gini(np.array([1.0, np.nan, 3.0]))


def test_gini_rejects_negative() -> None:
    with pytest.raises(ValueError, match="negative"):
        _gini(np.array([1.0, -2.0, 3.0]))


@given(
    n=st.integers(min_value=2, max_value=200),
    seed=st.integers(min_value=0, max_value=2**31 - 1),
)
@settings(max_examples=40, deadline=None)
def test_strength_pearson_is_in_correlation_range(n: int, seed: int) -> None:
    """Pearson(s_out, s_in) ∈ [-1, 1] on any pair of finite vectors of
    equal length. Numerical drift under tiny variances must not push the
    result outside the analytic bound."""
    rng = np.random.default_rng(seed)
    a = rng.lognormal(mean=10.0, sigma=1.0, size=n)
    b = rng.lognormal(mean=10.0, sigma=1.0, size=n)
    r = _strength_pearson(a, b)
    assert -1.0 - 1e-9 <= r <= 1.0 + 1e-9


def test_strength_pearson_constant_vector_is_zero() -> None:
    """Pearson is undefined for zero-variance inputs; we return 0
    rather than NaN so the downstream gate can fail predictably."""
    a = np.array([5.0, 5.0, 5.0])
    b = np.array([1.0, 2.0, 3.0])
    assert _strength_pearson(a, b) == 0.0


def test_strength_pearson_perfect_positive_is_one() -> None:
    a = np.array([1.0, 2.0, 3.0, 4.0])
    b = a.copy()
    assert _strength_pearson(a, b) == pytest.approx(1.0, abs=1e-12)


def test_strength_pearson_perfect_negative_is_minus_one() -> None:
    a = np.array([1.0, 2.0, 3.0, 4.0])
    b = -a
    assert _strength_pearson(a, b) == pytest.approx(-1.0, abs=1e-12)


# ---------------------------------------------------------------------------
# Domain-of-validity gate — verdict surface partition under random
# perturbations. Hypothesis searches the cross-product of (real n) ×
# (inferred density) against the certificate envelope and verifies that
# every input lands on exactly one of the three verdicts. This is the
# *contract*-level guarantee the gate's docstring promises.
# ---------------------------------------------------------------------------


@pytest.mark.slow
@given(
    real_n=st.integers(min_value=10, max_value=400),
    real_density=st.floats(min_value=0.0001, max_value=0.5, allow_nan=False, allow_infinity=False),
    seed=st.integers(min_value=0, max_value=2**31 - 1),
)
@settings(max_examples=40, deadline=None)
def test_domain_check_returns_exactly_one_verdict_per_input(
    real_n: int, real_density: float, seed: int
) -> None:
    """For every (real_n, real_density) pair, the gate returns exactly
    one of {WITHIN, OUT_OF, INSUFFICIENT}; verdicts are mutually
    exclusive and exhaustive."""
    cert = _cached_cert_n80_seed42()
    rng = np.random.default_rng(seed)
    s_out = rng.lognormal(mean=10.0, sigma=1.0, size=real_n)
    s_in = rng.lognormal(mean=10.0, sigma=1.0, size=real_n)
    s_in = s_in * (s_out.sum() / s_in.sum())  # GATE_2 balance
    check = check_domain_of_validity(s_out, s_in, cert, inferred_density=real_density)

    seen = {
        check.status is DomainOfValidityStatus.WITHIN_VALIDATED_DOMAIN,
        check.status is DomainOfValidityStatus.OUT_OF_VALIDATED_DOMAIN,
        check.status is DomainOfValidityStatus.INSUFFICIENT_CERTIFICATE,
    }
    assert sum(seen) == 1


@pytest.mark.slow
def test_domain_check_negative_control_extreme_density_is_out() -> None:
    """A real-data run with density wildly outside the certified range
    MUST be flagged OUT, never WITHIN. This is the negative control
    that proves the gate has discriminative capacity."""
    cert = _cached_cert_n80_seed42()
    s_out, s_in = _marginals_for_n(n=120, seed=21)
    # Density 100x above any tested density.
    crazy = float(max(cert.tested_at_densities) * 100.0)
    check = check_domain_of_validity(s_out, s_in, cert, inferred_density=crazy)
    assert check.status is DomainOfValidityStatus.OUT_OF_VALIDATED_DOMAIN
    assert "density" in check.out_of_range_dims
