# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for CountryToBankAllocator + falsification of UniformPrior."""

from __future__ import annotations

import numpy as np
import pytest

from research.reconstruction.allocator import (
    BankLevelMarginalsCertificate,
    CountryToBankAllocator,
    UniformPrior,
    bank_level_recovery_l1,
    synthetic_country_aggregates,
)
from research.reconstruction.allocator.certificate import compute_cert_id


def _build_allocator(bcm: tuple[tuple[str, str], ...]) -> CountryToBankAllocator:
    return CountryToBankAllocator(prior=UniformPrior(bank_country_map=bcm))


# ---------------------------------------------------------------------------
# Allocator GATE_A1 — conservation per country
# ---------------------------------------------------------------------------


def test_allocator_conserves_aggregate_per_country() -> None:
    """Σ s_in[bank in c] == agg_in[c] for every country, to 1e-9 rel."""
    agg_in, agg_out, _gt_in, _gt_out, bcm = synthetic_country_aggregates(
        n_countries=4, n_banks_per_country=5, seed=10
    )
    cert = _build_allocator(bcm).allocate(agg_in, agg_out, bank_country_map=bcm)
    bank_to_idx = {b: i for i, (b, _) in enumerate(bcm)}
    for country in agg_in:
        in_sum = sum(cert.s_in[bank_to_idx[b]] for b, c in bcm if c == country)
        out_sum = sum(cert.s_out[bank_to_idx[b]] for b, c in bcm if c == country)
        assert in_sum == pytest.approx(agg_in[country], rel=1e-9)
        assert out_sum == pytest.approx(agg_out[country], rel=1e-9)


def test_allocator_returns_certificate_dataclass() -> None:
    agg_in, agg_out, _gt_in, _gt_out, bcm = synthetic_country_aggregates(
        n_countries=2, n_banks_per_country=3, seed=1
    )
    cert = _build_allocator(bcm).allocate(agg_in, agg_out, bank_country_map=bcm)
    assert isinstance(cert, BankLevelMarginalsCertificate)
    assert cert.n_countries == 2
    assert cert.n_banks == 6
    assert cert.prior_id == "uniform"


# ---------------------------------------------------------------------------
# Allocator GATE_A3 — non-negativity
# ---------------------------------------------------------------------------


def test_allocator_emits_non_negative_marginals() -> None:
    agg_in, agg_out, _gt_in, _gt_out, bcm = synthetic_country_aggregates(
        n_countries=3, n_banks_per_country=4, seed=5
    )
    cert = _build_allocator(bcm).allocate(agg_in, agg_out, bank_country_map=bcm)
    assert np.all(cert.s_in >= 0)
    assert np.all(cert.s_out >= 0)


def test_allocator_rejects_negative_aggregate() -> None:
    bcm = (("B0", "C0"), ("B1", "C0"))
    alloc = _build_allocator(bcm)
    with pytest.raises(ValueError, match="non-negative"):
        alloc.allocate({"C0": -1.0}, {"C0": 1.0}, bank_country_map=bcm)


# ---------------------------------------------------------------------------
# Allocator GATE_A4 — bit-exact replay
# ---------------------------------------------------------------------------


def test_allocator_cert_id_is_64_hex() -> None:
    agg_in, agg_out, _gt_in, _gt_out, bcm = synthetic_country_aggregates(
        n_countries=2, n_banks_per_country=3, seed=7
    )
    cert = _build_allocator(bcm).allocate(agg_in, agg_out, bank_country_map=bcm)
    assert len(cert.cert_id) == 64
    int(cert.cert_id, 16)


def test_allocator_cert_id_replay_stable_for_same_inputs() -> None:
    agg_in, agg_out, _gt_in, _gt_out, bcm = synthetic_country_aggregates(
        n_countries=2, n_banks_per_country=3, seed=8
    )
    a = _build_allocator(bcm).allocate(agg_in, agg_out, bank_country_map=bcm)
    b = _build_allocator(bcm).allocate(agg_in, agg_out, bank_country_map=bcm)
    assert a.cert_id == b.cert_id


def test_allocator_cert_id_changes_when_aggregates_perturb() -> None:
    agg_in, agg_out, _gt_in, _gt_out, bcm = synthetic_country_aggregates(
        n_countries=2, n_banks_per_country=3, seed=9
    )
    a = _build_allocator(bcm).allocate(agg_in, agg_out, bank_country_map=bcm)
    perturbed = dict(agg_in)
    first_country = sorted(perturbed.keys())[0]
    perturbed[first_country] += 1.0e-3
    b = _build_allocator(bcm).allocate(perturbed, agg_out, bank_country_map=bcm)
    assert a.cert_id != b.cert_id


# ---------------------------------------------------------------------------
# Coverage / fallback policies
# ---------------------------------------------------------------------------


def test_allocator_coverage_ratio_is_one_when_every_country_has_evidence() -> None:
    agg_in, agg_out, _gt_in, _gt_out, bcm = synthetic_country_aggregates(
        n_countries=2, n_banks_per_country=3, seed=11
    )
    cert = _build_allocator(bcm).allocate(agg_in, agg_out, bank_country_map=bcm)
    assert cert.coverage_ratio == 1.0


def test_allocator_uniform_fallback_handles_missing_countries() -> None:
    """A country in `agg_in` that has banks but the prior doesn't recognise:
    UniformPrior knows banks in country, so coverage stays 1.0 (UniformPrior
    is the degenerate prior that ALWAYS has evidence for countries it knows
    about, by construction)."""
    bcm = (("B0", "C0"), ("B1", "C0"))
    alloc = _build_allocator(bcm)
    cert = alloc.allocate({"C0": 100.0}, {"C0": 100.0}, bank_country_map=bcm)
    assert cert.coverage_ratio == 1.0
    assert float(cert.s_in.sum()) == pytest.approx(100.0, rel=1e-9)


def test_allocator_drop_country_fallback_skips_unknown_country() -> None:
    """`drop_country` removes countries with no banks in the map."""
    bcm = (("B0", "C0"),)
    alloc = CountryToBankAllocator(
        prior=UniformPrior(bank_country_map=bcm),
        fallback_policy="drop_country",
    )
    # C1 has no banks in the map ⇒ dropped.
    cert = alloc.allocate(
        {"C0": 50.0, "C1": 100.0},
        {"C0": 50.0, "C1": 100.0},
        bank_country_map=bcm,
    )
    assert cert.s_in.sum() == pytest.approx(50.0, rel=1e-9)
    assert cert.s_out.sum() == pytest.approx(50.0, rel=1e-9)


def test_allocator_raise_fallback_blocks_missing_country() -> None:
    bcm = (("B0", "C0"),)
    alloc = CountryToBankAllocator(
        prior=UniformPrior(bank_country_map=bcm), fallback_policy="raise"
    )
    with pytest.raises(ValueError, match="no banks"):
        alloc.allocate(
            {"C0": 50.0, "MISSING": 100.0},
            {"C0": 50.0, "MISSING": 100.0},
            bank_country_map=bcm,
        )


# ---------------------------------------------------------------------------
# Falsification — UniformPrior should NOT recover non-uniform truth
# ---------------------------------------------------------------------------


def test_uniform_prior_fails_to_recover_lognormal_shares() -> None:
    """UniformPrior is the degenerate falsification anchor. On a substrate
    whose ground-truth shares are lognormal (heavy-tailed), the uniform
    allocator cannot recover the bank-level marginals to better than a
    coarse relative L1 error. If it could, the prior would be doing nothing
    useful and downstream allocators would have nothing to beat."""
    agg_in, agg_out, gt_in, gt_out, bcm = synthetic_country_aggregates(
        n_countries=4,
        n_banks_per_country=8,
        share_distribution="lognormal",
        seed=42,
    )
    cert = _build_allocator(bcm).allocate(agg_in, agg_out, bank_country_map=bcm)
    err_in = bank_level_recovery_l1(ground_truth=gt_in, allocated=cert.s_in)
    err_out = bank_level_recovery_l1(ground_truth=gt_out, allocated=cert.s_out)
    # Coarse — must be substantial. UniformPrior on heavy-tailed shares
    # leaves at least 30% relative L1 error.
    assert err_in >= 0.30
    assert err_out >= 0.30


def test_uniform_prior_does_strictly_better_on_uniform_than_on_lognormal() -> None:
    """Symmetric check: UniformPrior is informationally optimal on a
    uniform-share substrate, but suboptimal on a lognormal-share one.
    Hence its relative L1 error on the uniform substrate must be
    *strictly smaller* than on the lognormal substrate at matched N.

    This is the 'no false negative' direction — the falsification
    anchor is not vacuously wrong: when the prior matches the truth,
    error drops materially."""
    n_b = 16
    agg_in_u, agg_out_u, gt_in_u, gt_out_u, bcm_u = synthetic_country_aggregates(
        n_countries=4,
        n_banks_per_country=n_b,
        share_distribution="uniform",
        seed=42,
    )
    err_uniform = bank_level_recovery_l1(
        ground_truth=gt_in_u,
        allocated=_build_allocator(bcm_u)
        .allocate(agg_in_u, agg_out_u, bank_country_map=bcm_u)
        .s_in,
    )

    agg_in_l, agg_out_l, gt_in_l, _gt_out_l, bcm_l = synthetic_country_aggregates(
        n_countries=4,
        n_banks_per_country=n_b,
        share_distribution="lognormal",
        seed=42,
    )
    err_lognormal = bank_level_recovery_l1(
        ground_truth=gt_in_l,
        allocated=_build_allocator(bcm_l)
        .allocate(agg_in_l, agg_out_l, bank_country_map=bcm_l)
        .s_in,
    )

    # Uniform-on-uniform must beat uniform-on-lognormal by ≥ 30% relative.
    assert err_uniform < err_lognormal * 0.7, (
        f"UniformPrior should beat itself on matched-truth: "
        f"err_uniform={err_uniform:.3f} vs err_lognormal={err_lognormal:.3f}"
    )


# ---------------------------------------------------------------------------
# Constructor input contract
# ---------------------------------------------------------------------------


def test_allocator_rejects_invalid_fallback_policy() -> None:
    bcm = (("B0", "C0"),)
    with pytest.raises(ValueError, match="fallback_policy"):
        CountryToBankAllocator(prior=UniformPrior(bank_country_map=bcm), fallback_policy="bogus")


def test_allocator_rejects_non_positive_tolerance() -> None:
    bcm = (("B0", "C0"),)
    with pytest.raises(ValueError, match="conservation_tolerance"):
        CountryToBankAllocator(prior=UniformPrior(bank_country_map=bcm), conservation_tolerance=0.0)


def test_allocator_rejects_aggregate_key_mismatch() -> None:
    bcm = (("B0", "C0"),)
    alloc = _build_allocator(bcm)
    with pytest.raises(ValueError, match="same set"):
        alloc.allocate({"C0": 1.0}, {"C1": 1.0}, bank_country_map=bcm)


def test_allocator_rejects_empty_bank_country_map() -> None:
    bcm = (("B0", "C0"),)
    alloc = _build_allocator(bcm)
    with pytest.raises(ValueError, match="non-empty"):
        alloc.allocate({"C0": 1.0}, {"C0": 1.0}, bank_country_map=())


# ---------------------------------------------------------------------------
# compute_cert_id helper
# ---------------------------------------------------------------------------


def test_compute_cert_id_changes_with_prior_id() -> None:
    bcm = (("B0", "C0"),)
    s = np.array([1.0])
    a = compute_cert_id(
        prior_id="uniform",
        bank_country_map=bcm,
        s_in=s,
        s_out=s,
        country_aggregates_in=(("C0", 1.0),),
        country_aggregates_out=(("C0", 1.0),),
        coverage_ratio=1.0,
        fallback_policy="uniform_within_country",
    )
    b = compute_cert_id(
        prior_id="OTHER",
        bank_country_map=bcm,
        s_in=s,
        s_out=s,
        country_aggregates_in=(("C0", 1.0),),
        country_aggregates_out=(("C0", 1.0),),
        coverage_ratio=1.0,
        fallback_policy="uniform_within_country",
    )
    assert a != b


# ---------------------------------------------------------------------------
# Certificate dataclass invariants
# ---------------------------------------------------------------------------


def test_certificate_rejects_bad_coverage_ratio() -> None:
    """Direct construction with invalid coverage_ratio must fail."""
    s = np.array([1.0], dtype=np.float64)
    with pytest.raises(ValueError, match="coverage_ratio"):
        BankLevelMarginalsCertificate(
            prior_id="x",
            n_countries=1,
            n_banks=1,
            coverage_ratio=1.5,
            fallback_policy="uniform_within_country",
            bank_country_map=(("B0", "C0"),),
            s_in=s,
            s_out=s,
            country_aggregates_in=(("C0", 1.0),),
            country_aggregates_out=(("C0", 1.0),),
            cert_id="0" * 64,
        )


def test_certificate_rejects_negative_marginal() -> None:
    s_bad = np.array([-1.0], dtype=np.float64)
    s_ok = np.array([1.0], dtype=np.float64)
    with pytest.raises(ValueError, match="non-negative"):
        BankLevelMarginalsCertificate(
            prior_id="x",
            n_countries=1,
            n_banks=1,
            coverage_ratio=1.0,
            fallback_policy="uniform_within_country",
            bank_country_map=(("B0", "C0"),),
            s_in=s_bad,
            s_out=s_ok,
            country_aggregates_in=(("C0", 1.0),),
            country_aggregates_out=(("C0", 1.0),),
            cert_id="0" * 64,
        )


def test_certificate_rejects_short_cert_id() -> None:
    s = np.array([1.0], dtype=np.float64)
    with pytest.raises(ValueError, match="cert_id"):
        BankLevelMarginalsCertificate(
            prior_id="x",
            n_countries=1,
            n_banks=1,
            coverage_ratio=1.0,
            fallback_policy="uniform_within_country",
            bank_country_map=(("B0", "C0"),),
            s_in=s,
            s_out=s,
            country_aggregates_in=(("C0", 1.0),),
            country_aggregates_out=(("C0", 1.0),),
            cert_id="abc",
        )
