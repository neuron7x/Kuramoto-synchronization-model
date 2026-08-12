# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""End-to-end tests over the frozen MFI demo fixture (X-10R-1 PR #5).

The fixture lives at
``research/reconstruction/allocator/data/mfi_demo.tsv`` and ships
25 banks across 5 EU countries with illustrative ``total_assets``
values. These tests certify the *whole* PR-#642…#645 stack hangs
together end-to-end on a stable, license-clean dataset:

    load_mfi_registry        (PR #645 — TSV/CSV ingestion)
        ⬇
    SizeWeightedPrior        (PR #643 — concrete prior)
        ⬇
    CountryToBankAllocator   (PR #642 — split + GATE_A1..A4)
        ⬇
    audit_bank_level_recovery  (PR #644 — Gate-5-style audit)

The fixture is frozen — its hash is one of the things this test
pins. If a future PR rewrites the fixture, this test will fail
loudly, and the rewrite must update the hash explicitly.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pytest

from research.reconstruction.allocator import (
    MFI_DEMO_TSV,
    BankLevelRecoveryReport,
    CountryToBankAllocator,
    SizeWeightedPrior,
    UniformPrior,
    audit_bank_level_recovery,
    bank_level_recovery_l1,
    load_mfi_registry,
)

# ---------------------------------------------------------------------------
# Fixture integrity
# ---------------------------------------------------------------------------


def test_demo_fixture_exists_and_is_readable() -> None:
    assert MFI_DEMO_TSV.exists()
    text = MFI_DEMO_TSV.read_text(encoding="utf-8")
    assert text.startswith("bank_id\tcountry\tname\ttotal_assets\n")
    assert "DE-DEMO-001" in text


def test_demo_fixture_loads_to_25_banks_5_countries() -> None:
    out = load_mfi_registry(MFI_DEMO_TSV)
    assert out.n_rows == 25
    assert out.n_with_assets == 25  # every demo row carries a weight
    countries = {c for _, c in out.bank_country_map}
    assert countries == {"DE", "FR", "IT", "ES", "NL"}
    # 5 banks per country.
    for country in countries:
        n = sum(1 for _, c in out.bank_country_map if c == country)
        assert n == 5


def test_demo_fixture_country_order_is_alphabetical() -> None:
    """The canonical bank_country_map is sorted by country
    alphabetically — bit-exact replay contract for the allocator."""
    out = load_mfi_registry(MFI_DEMO_TSV)
    countries_seen: list[str] = []
    for _, c in out.bank_country_map:
        if not countries_seen or countries_seen[-1] != c:
            countries_seen.append(c)
    assert countries_seen == ["DE", "ES", "FR", "IT", "NL"]


def test_demo_fixture_content_hash_is_pinned() -> None:
    """Locks the fixture's exact byte content. Any rewrite of the
    fixture must intentionally update this hash — it is the canonical
    "the demo data has changed" signal in the regression surface.

    Recompute on rewrite via::

        python -c "import hashlib, pathlib; \\
            print(hashlib.sha256(pathlib.Path( \\
                'research/reconstruction/allocator/data/mfi_demo.tsv' \\
            ).read_bytes()).hexdigest())"
    """
    blob = MFI_DEMO_TSV.read_bytes()
    actual = hashlib.sha256(blob).hexdigest()
    expected = "304612f1c45aa433522f221b4fcf28fc15d4969dac155013783b1e2f384c2e2b"  # pragma: allowlist secret
    assert actual == expected, (
        f"demo fixture drift: actual sha256 = {actual}, pinned = {expected}; "
        "intentionally update the pinned hash if the rewrite is expected."
    )


# ---------------------------------------------------------------------------
# E2E pipeline
# ---------------------------------------------------------------------------


def _country_aggregates_for_demo() -> tuple[dict[str, float], dict[str, float]]:
    """Return illustrative country aggregates aligned with the demo
    fixture's countries. Values chosen so the resulting bank-level
    marginals are realistic in scale (EUR billions)."""
    agg_in = {"DE": 800.0, "FR": 700.0, "IT": 500.0, "ES": 450.0, "NL": 350.0}
    agg_out = {"DE": 750.0, "FR": 660.0, "IT": 470.0, "ES": 420.0, "NL": 320.0}
    return agg_in, agg_out


def test_e2e_demo_to_allocator_conserves_per_country() -> None:
    out = load_mfi_registry(MFI_DEMO_TSV)
    agg_in, agg_out = _country_aggregates_for_demo()
    cert = CountryToBankAllocator(
        prior=SizeWeightedPrior(
            bank_country_map=out.bank_country_map,
            bank_weights=out.bank_weights,
            prior_id_tag="mfi_demo_v1",
        )
    ).allocate(agg_in, agg_out, bank_country_map=out.bank_country_map)
    bank_to_idx = {b: i for i, (b, _) in enumerate(out.bank_country_map)}
    for country in agg_in:
        in_sum = sum(cert.s_in[bank_to_idx[b]] for b, c in out.bank_country_map if c == country)
        out_sum = sum(cert.s_out[bank_to_idx[b]] for b, c in out.bank_country_map if c == country)
        assert in_sum == pytest.approx(agg_in[country], rel=1e-9)
        assert out_sum == pytest.approx(agg_out[country], rel=1e-9)
    assert cert.prior_id == "mfi_demo_v1"
    assert cert.coverage_ratio == 1.0


def test_e2e_demo_size_weighted_beats_uniform_when_sizes_align() -> None:
    """If the ground-truth bank-level marginals match the fixture's
    total_assets up to the country scale, the SizeWeightedPrior
    prediction is exact and crushes UniformPrior on the bank-level
    audit. Real falsification anchor on a real-shape registry."""
    out = load_mfi_registry(MFI_DEMO_TSV)
    agg_in, agg_out = _country_aggregates_for_demo()

    # Construct ground truth: each bank's true marginal is its
    # (total_assets / Σ_country_assets) × country_aggregate.
    bank_to_idx = {b: i for i, (b, _) in enumerate(out.bank_country_map)}
    n = len(out.bank_country_map)
    gt_in = np.zeros(n, dtype=np.float64)
    gt_out = np.zeros(n, dtype=np.float64)
    for country in agg_in:
        country_banks = [b for b, c in out.bank_country_map if c == country]
        country_total = sum(out.bank_weights[b] for b in country_banks)
        for b in country_banks:
            share = out.bank_weights[b] / country_total
            gt_in[bank_to_idx[b]] = share * agg_in[country]
            gt_out[bank_to_idx[b]] = share * agg_out[country]

    cert_sw = CountryToBankAllocator(
        prior=SizeWeightedPrior(
            bank_country_map=out.bank_country_map,
            bank_weights=out.bank_weights,
        )
    ).allocate(agg_in, agg_out, bank_country_map=out.bank_country_map)
    cert_un = CountryToBankAllocator(
        prior=UniformPrior(bank_country_map=out.bank_country_map)
    ).allocate(agg_in, agg_out, bank_country_map=out.bank_country_map)

    err_sw = bank_level_recovery_l1(ground_truth=gt_in, allocated=cert_sw.s_in)
    err_un = bank_level_recovery_l1(ground_truth=gt_in, allocated=cert_un.s_in)
    # SW is exact; UniformPrior loses by ≥ 6 OoM.
    assert err_sw < 1e-9
    assert err_un / max(err_sw, 1e-30) > 1e6


def test_e2e_demo_audit_passes_on_aligned_size_weighted() -> None:
    """Run the full Gate-5-style audit on the aligned scenario.
    The four-metric report must come back passed=True."""
    out = load_mfi_registry(MFI_DEMO_TSV)
    agg_in, agg_out = _country_aggregates_for_demo()
    bank_to_idx = {b: i for i, (b, _) in enumerate(out.bank_country_map)}
    n = len(out.bank_country_map)
    gt_in = np.zeros(n, dtype=np.float64)
    gt_out = np.zeros(n, dtype=np.float64)
    for country in agg_in:
        country_banks = [b for b, c in out.bank_country_map if c == country]
        country_total = sum(out.bank_weights[b] for b in country_banks)
        for b in country_banks:
            share = out.bank_weights[b] / country_total
            gt_in[bank_to_idx[b]] = share * agg_in[country]
            gt_out[bank_to_idx[b]] = share * agg_out[country]

    cert = CountryToBankAllocator(
        prior=SizeWeightedPrior(
            bank_country_map=out.bank_country_map,
            bank_weights=out.bank_weights,
        )
    ).allocate(agg_in, agg_out, bank_country_map=out.bank_country_map)

    report = audit_bank_level_recovery(
        ground_truth_s_in=gt_in,
        ground_truth_s_out=gt_out,
        allocated_s_in=cert.s_in,
        allocated_s_out=cert.s_out,
        bank_country_map=out.bank_country_map,
    )
    assert isinstance(report, BankLevelRecoveryReport)
    assert report.passed is True
    assert report.failure_reasons == ()


def test_e2e_demo_audit_fails_on_uniform_when_sizes_skewed() -> None:
    """Mirror direction: with sizes skewed enough that UniformPrior
    is off by > 20% on aggregate L1 (it is, on the demo fixture's
    skewed sizes), the audit MUST surface a failure. End-to-end
    falsification anchor over the frozen fixture."""
    out = load_mfi_registry(MFI_DEMO_TSV)
    agg_in, agg_out = _country_aggregates_for_demo()
    bank_to_idx = {b: i for i, (b, _) in enumerate(out.bank_country_map)}
    n = len(out.bank_country_map)
    gt_in = np.zeros(n, dtype=np.float64)
    gt_out = np.zeros(n, dtype=np.float64)
    for country in agg_in:
        country_banks = [b for b, c in out.bank_country_map if c == country]
        country_total = sum(out.bank_weights[b] for b in country_banks)
        for b in country_banks:
            share = out.bank_weights[b] / country_total
            gt_in[bank_to_idx[b]] = share * agg_in[country]
            gt_out[bank_to_idx[b]] = share * agg_out[country]

    cert_un = CountryToBankAllocator(
        prior=UniformPrior(bank_country_map=out.bank_country_map)
    ).allocate(agg_in, agg_out, bank_country_map=out.bank_country_map)
    report = audit_bank_level_recovery(
        ground_truth_s_in=gt_in,
        ground_truth_s_out=gt_out,
        allocated_s_in=cert_un.s_in,
        allocated_s_out=cert_un.s_out,
        bank_country_map=out.bank_country_map,
    )
    assert report.passed is False
    assert any(
        "total_relative_l1" in r or "per_country_relative_l1" in r for r in report.failure_reasons
    )


def test_e2e_demo_cert_id_is_replay_stable() -> None:
    """Same fixture + same aggregates ⇒ same cert_id (GATE_A4 over
    the full pipeline including TSV ingestion + size-weighted prior
    + allocator)."""
    out_a = load_mfi_registry(MFI_DEMO_TSV)
    out_b = load_mfi_registry(MFI_DEMO_TSV)
    agg_in, agg_out = _country_aggregates_for_demo()
    cert_a = CountryToBankAllocator(
        prior=SizeWeightedPrior(
            bank_country_map=out_a.bank_country_map,
            bank_weights=out_a.bank_weights,
            prior_id_tag="mfi_demo_v1",
        )
    ).allocate(agg_in, agg_out, bank_country_map=out_a.bank_country_map)
    cert_b = CountryToBankAllocator(
        prior=SizeWeightedPrior(
            bank_country_map=out_b.bank_country_map,
            bank_weights=out_b.bank_weights,
            prior_id_tag="mfi_demo_v1",
        )
    ).allocate(agg_in, agg_out, bank_country_map=out_b.bank_country_map)
    assert cert_a.cert_id == cert_b.cert_id
