# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for SizeWeightedPrior — first concrete prior beating UniformPrior.

The contract under test:
  1. Protocol satisfaction (drop-in replacement for UniformPrior).
  2. Closed-form share = weight / Σ_country_weights, with mean
     imputation for banks missing from the weight dict.
  3. has_evidence semantics — True iff the country has positive
     total weight; False otherwise.
  4. **Falsification**: SizeWeightedPrior with weights ALIGNED to
     the ground-truth shares MUST recover the bank-level marginals
     materially better than UniformPrior on the same substrate.
     Otherwise the size-signal layer is doing no work.
  5. Symmetry: SizeWeightedPrior with EMPTY weight dict
     degenerates to UniformPrior behavior — same recovery error.
"""

from __future__ import annotations

import numpy as np
import pytest

from research.reconstruction.allocator import (
    AllocatorPrior,
    CountryToBankAllocator,
    SizeWeightedPrior,
    UniformPrior,
    bank_level_recovery_l1,
    synthetic_country_aggregates,
)


def _bcm() -> tuple[tuple[str, str], ...]:
    return (
        ("BankA1", "C1"),
        ("BankA2", "C1"),
        ("BankA3", "C1"),
        ("BankB1", "C2"),
        ("BankB2", "C2"),
    )


# ---------------------------------------------------------------------------
# Protocol satisfaction
# ---------------------------------------------------------------------------


def test_size_weighted_prior_satisfies_protocol() -> None:
    p = SizeWeightedPrior(bank_country_map=_bcm(), bank_weights={})
    assert isinstance(p, AllocatorPrior)


def test_size_weighted_prior_id_is_configurable() -> None:
    assert SizeWeightedPrior(bank_country_map=_bcm()).prior_id == "size_weighted"
    custom = SizeWeightedPrior(bank_country_map=_bcm(), prior_id_tag="eba_2024Q4")
    assert custom.prior_id == "eba_2024Q4"


def test_size_weighted_prior_banks_in_matches_registry() -> None:
    p = SizeWeightedPrior(bank_country_map=_bcm())
    assert p.banks_in("C1") == ("BankA1", "BankA2", "BankA3")
    assert p.banks_in("C2") == ("BankB1", "BankB2")
    assert p.banks_in("UNKNOWN") == ()


# ---------------------------------------------------------------------------
# Closed-form share contract
# ---------------------------------------------------------------------------


def test_share_equals_weight_over_country_total() -> None:
    weights = {"BankA1": 30.0, "BankA2": 20.0, "BankA3": 50.0}
    p = SizeWeightedPrior(bank_country_map=_bcm(), bank_weights=weights)
    assert p.expected_share(country="C1", bank_id="BankA1") == pytest.approx(0.30)
    assert p.expected_share(country="C1", bank_id="BankA2") == pytest.approx(0.20)
    assert p.expected_share(country="C1", bank_id="BankA3") == pytest.approx(0.50)
    total = sum(p.expected_share(country="C1", bank_id=b) for b in p.banks_in("C1"))
    assert total == pytest.approx(1.0, abs=1e-12)


def test_missing_bank_imputed_at_country_mean() -> None:
    """Banks resident in a country but missing from the weight dict
    get the per-country mean weight as imputation. Effective shares
    still sum to 1."""
    weights = {"BankA1": 30.0, "BankA2": 20.0}  # BankA3 missing
    p = SizeWeightedPrior(bank_country_map=_bcm(), bank_weights=weights)
    # mean over (30, 20) = 25 → BankA3 gets share 25 / (30+20+25) = 1/3
    assert p.expected_share(country="C1", bank_id="BankA3") == pytest.approx(25.0 / 75.0, rel=1e-12)
    total = sum(p.expected_share(country="C1", bank_id=b) for b in p.banks_in("C1"))
    assert total == pytest.approx(1.0, abs=1e-12)


def test_zero_weight_bank_gets_zero_share() -> None:
    """Explicit zero weight is treated as zero share — distinct from
    "missing" which gets imputed."""
    weights = {"BankA1": 0.0, "BankA2": 50.0, "BankA3": 50.0}
    p = SizeWeightedPrior(bank_country_map=_bcm(), bank_weights=weights)
    assert p.expected_share(country="C1", bank_id="BankA1") == 0.0
    assert p.expected_share(country="C1", bank_id="BankA2") == pytest.approx(0.5)
    assert p.expected_share(country="C1", bank_id="BankA3") == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# has_evidence semantics
# ---------------------------------------------------------------------------


def test_has_evidence_true_when_any_bank_in_country_has_weight() -> None:
    weights = {"BankA1": 10.0}  # only one of three C1 banks
    p = SizeWeightedPrior(bank_country_map=_bcm(), bank_weights=weights)
    assert p.has_evidence("C1") is True


def test_has_evidence_false_when_country_has_zero_total_weight() -> None:
    """Country without any positive-weight bank ⇒ no evidence (allocator
    will fall back per its policy)."""
    p = SizeWeightedPrior(bank_country_map=_bcm(), bank_weights={})
    assert p.has_evidence("C1") is False
    assert p.has_evidence("C2") is False


def test_has_evidence_false_for_unknown_country() -> None:
    p = SizeWeightedPrior(bank_country_map=_bcm(), bank_weights={"BankA1": 1.0})
    assert p.has_evidence("UNKNOWN") is False


# ---------------------------------------------------------------------------
# Input contract
# ---------------------------------------------------------------------------


def test_rejects_negative_weight() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        SizeWeightedPrior(bank_country_map=_bcm(), bank_weights={"BankA1": -1.0})


def test_rejects_nan_weight() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        SizeWeightedPrior(bank_country_map=_bcm(), bank_weights={"BankA1": float("nan")})


def test_rejects_empty_bank_country_map() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        SizeWeightedPrior(bank_country_map=())


def test_share_rejects_unknown_country() -> None:
    p = SizeWeightedPrior(bank_country_map=_bcm())
    with pytest.raises(ValueError, match="no banks"):
        p.expected_share(country="UNKNOWN", bank_id="X")


def test_share_rejects_non_resident_bank() -> None:
    p = SizeWeightedPrior(bank_country_map=_bcm())
    with pytest.raises(ValueError, match="not resident"):
        p.expected_share(country="C1", bank_id="BankB1")


# ---------------------------------------------------------------------------
# Falsification anchor — does the size signal beat UniformPrior?
# ---------------------------------------------------------------------------


def test_aligned_size_weighted_prior_beats_uniform_on_lognormal() -> None:
    """When the size weights ARE the ground-truth bank sizes, the
    size-weighted prior MUST recover the bank-level marginals
    materially better than UniformPrior. Otherwise the size signal
    is doing no work and the prior is method theatre."""
    agg_in, agg_out, gt_in, _gt_out, bcm = synthetic_country_aggregates(
        n_countries=4,
        n_banks_per_country=8,
        share_distribution="lognormal",
        seed=42,
    )
    # Size weights = ground-truth s_in (the prior is "informed" about
    # the size signal). On lognormal substrates this should crush
    # UniformPrior by a wide margin.
    weights = {bank: float(gt_in[i]) for i, (bank, _) in enumerate(bcm)}

    cert_uniform = CountryToBankAllocator(prior=UniformPrior(bank_country_map=bcm)).allocate(
        agg_in, agg_out, bank_country_map=bcm
    )
    cert_sw = CountryToBankAllocator(
        prior=SizeWeightedPrior(bank_country_map=bcm, bank_weights=weights)
    ).allocate(agg_in, agg_out, bank_country_map=bcm)

    err_uniform = bank_level_recovery_l1(ground_truth=gt_in, allocated=cert_uniform.s_in)
    err_sw = bank_level_recovery_l1(ground_truth=gt_in, allocated=cert_sw.s_in)

    # Aligned size-weighted on s_in must recover s_in nearly perfectly.
    assert err_sw < 1e-9, f"aligned SizeWeightedPrior should be exact; got {err_sw}"
    # And uniform must be far worse.
    assert err_uniform > err_sw * 1e6, (
        f"falsification anchor broken: SizeWeightedPrior aligned "
        f"err={err_sw:.6e} vs UniformPrior err={err_uniform:.6e}"
    )


def test_misaligned_size_weighted_prior_does_not_beat_uniform() -> None:
    """Negative direction: SizeWeightedPrior with weights ANTI-aligned
    to ground truth must NOT recover the marginals better than
    UniformPrior. Otherwise the prior is somehow extracting signal
    from a contradiction — which would be a numerical accident, not
    real information."""
    agg_in, agg_out, gt_in, _gt_out, bcm = synthetic_country_aggregates(
        n_countries=4,
        n_banks_per_country=8,
        share_distribution="lognormal",
        seed=43,
    )
    # Anti-aligned: largest bank gets smallest weight, etc.
    sorted_truth = sorted(gt_in)
    inverted = sorted_truth[::-1]
    # Map: i-th bank in bcm ↔ i-th rank in gt_in ↔ swapped weight.
    rank_by_bank: dict[str, int] = {}
    sorted_idx = sorted(range(len(gt_in)), key=lambda i: gt_in[i])
    for rank, idx in enumerate(sorted_idx):
        bank_id = bcm[idx][0]
        rank_by_bank[bank_id] = rank
    weights = {bank: float(inverted[rank]) for bank, rank in rank_by_bank.items()}

    cert_uniform = CountryToBankAllocator(prior=UniformPrior(bank_country_map=bcm)).allocate(
        agg_in, agg_out, bank_country_map=bcm
    )
    cert_sw = CountryToBankAllocator(
        prior=SizeWeightedPrior(bank_country_map=bcm, bank_weights=weights)
    ).allocate(agg_in, agg_out, bank_country_map=bcm)

    err_uniform = bank_level_recovery_l1(ground_truth=gt_in, allocated=cert_uniform.s_in)
    err_sw = bank_level_recovery_l1(ground_truth=gt_in, allocated=cert_sw.s_in)

    # Anti-aligned must be at least as bad as uniform.
    assert err_sw >= err_uniform * 0.95, (
        f"anti-aligned size weights should NOT beat UniformPrior; "
        f"got err_sw={err_sw:.4f} vs err_uniform={err_uniform:.4f}"
    )


def test_empty_weight_dict_degenerates_to_uniform_recovery() -> None:
    """SizeWeightedPrior with no weights at all has no evidence;
    via fallback_policy='uniform_within_country' it places 1/k —
    indistinguishable from UniformPrior in recovery error."""
    agg_in, agg_out, gt_in, _gt_out, bcm = synthetic_country_aggregates(
        n_countries=3,
        n_banks_per_country=6,
        share_distribution="lognormal",
        seed=44,
    )
    cert_uniform = CountryToBankAllocator(prior=UniformPrior(bank_country_map=bcm)).allocate(
        agg_in, agg_out, bank_country_map=bcm
    )
    cert_empty_sw = CountryToBankAllocator(
        prior=SizeWeightedPrior(bank_country_map=bcm, bank_weights={})
    ).allocate(agg_in, agg_out, bank_country_map=bcm)

    err_uniform = bank_level_recovery_l1(ground_truth=gt_in, allocated=cert_uniform.s_in)
    err_empty_sw = bank_level_recovery_l1(ground_truth=gt_in, allocated=cert_empty_sw.s_in)

    # Two priors with the same effective shares should produce the
    # same recovery error to numerical tolerance.
    assert err_uniform == pytest.approx(err_empty_sw, rel=1e-9)


# ---------------------------------------------------------------------------
# Integration: cert_id distinguishes priors with different signals
# ---------------------------------------------------------------------------


def test_cert_id_distinguishes_size_weighted_from_uniform() -> None:
    """Same aggregates + different priors ⇒ different cert_id.

    This is the GATE_A4 surface for the prior-id field — the
    allocator's certificate must hash the prior_id, otherwise
    two different priors collapse to the same provenance hash."""
    agg_in, agg_out, _gt_in, _gt_out, bcm = synthetic_country_aggregates(
        n_countries=2, n_banks_per_country=3, seed=45
    )
    cert_uniform = CountryToBankAllocator(prior=UniformPrior(bank_country_map=bcm)).allocate(
        agg_in, agg_out, bank_country_map=bcm
    )
    weights = {b: float(i + 1) for i, (b, _) in enumerate(bcm)}
    cert_sw = CountryToBankAllocator(
        prior=SizeWeightedPrior(bank_country_map=bcm, bank_weights=weights)
    ).allocate(agg_in, agg_out, bank_country_map=bcm)
    assert cert_uniform.cert_id != cert_sw.cert_id
    assert cert_uniform.prior_id == "uniform"
    assert cert_sw.prior_id == "size_weighted"


# ---------------------------------------------------------------------------
# Verify the allocator's GATE_A1 (conservation) holds under SW prior
# ---------------------------------------------------------------------------


def test_size_weighted_allocator_conserves_per_country() -> None:
    agg_in, agg_out, gt_in, _gt_out, bcm = synthetic_country_aggregates(
        n_countries=3, n_banks_per_country=5, seed=46
    )
    weights = {bank: float(gt_in[i]) for i, (bank, _) in enumerate(bcm)}
    cert = CountryToBankAllocator(
        prior=SizeWeightedPrior(bank_country_map=bcm, bank_weights=weights)
    ).allocate(agg_in, agg_out, bank_country_map=bcm)

    bank_to_idx = {b: i for i, (b, _) in enumerate(bcm)}
    for country in agg_in:
        in_sum = sum(cert.s_in[bank_to_idx[b]] for b, c in bcm if c == country)
        assert in_sum == pytest.approx(agg_in[country], rel=1e-9)
    np.testing.assert_array_compare(np.greater_equal, cert.s_in, 0.0)
    np.testing.assert_array_compare(np.greater_equal, cert.s_out, 0.0)
