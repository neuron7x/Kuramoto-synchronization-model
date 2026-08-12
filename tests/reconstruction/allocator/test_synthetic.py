# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for synthetic country aggregates with known bank-level truth."""

from __future__ import annotations

import numpy as np
import pytest

from research.reconstruction.allocator.synthetic import (
    bank_level_recovery_l1,
    synthetic_country_aggregates,
)


def test_synthetic_default_shape_and_round_trip() -> None:
    agg_in, agg_out, gt_in, gt_out, bcm = synthetic_country_aggregates(
        n_countries=3, n_banks_per_country=4, seed=0
    )
    assert len(agg_in) == 3
    assert len(agg_out) == 3
    assert gt_in.shape == (12,)
    assert gt_out.shape == (12,)
    assert len(bcm) == 12
    # Round trip: country aggregate ≡ Σ ground-truth marginals over residents.
    for c_idx, country in enumerate(sorted(agg_in.keys())):
        offset = c_idx * 4
        in_sum = float(gt_in[offset : offset + 4].sum())
        out_sum = float(gt_out[offset : offset + 4].sum())
        assert in_sum == pytest.approx(agg_in[country], rel=1e-12)
        assert out_sum == pytest.approx(agg_out[country], rel=1e-12)


def test_synthetic_bank_country_map_is_deterministic_per_seed() -> None:
    a = synthetic_country_aggregates(n_countries=2, n_banks_per_country=3, seed=42)
    b = synthetic_country_aggregates(n_countries=2, n_banks_per_country=3, seed=42)
    assert a[4] == b[4]  # bank_country_map identical
    np.testing.assert_array_equal(a[2], b[2])  # ground-truth s_in identical


def test_synthetic_seed_sensitive() -> None:
    a = synthetic_country_aggregates(n_countries=2, n_banks_per_country=3, seed=1)
    b = synthetic_country_aggregates(n_countries=2, n_banks_per_country=3, seed=2)
    # Different seeds ⇒ different country aggregate values.
    a_keys = sorted(a[0].keys())
    assert any(a[0][k] != b[0][k] for k in a_keys)


@pytest.mark.parametrize("dist", ["uniform", "lognormal", "pareto"])
def test_synthetic_supports_named_share_distributions(dist: str) -> None:
    agg_in, _agg_out, gt_in, _gt_out, _bcm = synthetic_country_aggregates(
        n_countries=2,
        n_banks_per_country=4,
        share_distribution=dist,  # type: ignore[arg-type]
        seed=11,
    )
    assert all(v >= 0 for v in agg_in.values())
    assert np.all(gt_in >= 0)


def test_synthetic_rejects_invalid_distribution() -> None:
    with pytest.raises(ValueError, match="unknown distribution"):
        synthetic_country_aggregates(
            n_countries=1,
            n_banks_per_country=2,
            share_distribution="bogus",  # type: ignore[arg-type]
        )


def test_synthetic_rejects_zero_n_countries() -> None:
    with pytest.raises(ValueError, match="n_countries"):
        synthetic_country_aggregates(n_countries=0, n_banks_per_country=2)


def test_synthetic_rejects_zero_n_banks() -> None:
    with pytest.raises(ValueError, match="n_banks_per_country"):
        synthetic_country_aggregates(n_countries=2, n_banks_per_country=0)


def test_bank_level_recovery_l1_zero_for_perfect() -> None:
    rng = np.random.default_rng(0)
    gt = rng.lognormal(size=20)
    assert bank_level_recovery_l1(ground_truth=gt, allocated=gt) == 0.0


def test_bank_level_recovery_l1_positive_for_mismatch() -> None:
    gt = np.array([1.0, 2.0, 3.0, 4.0])
    al = np.array([2.0, 1.0, 4.0, 3.0])  # permutation, same totals
    err = bank_level_recovery_l1(ground_truth=gt, allocated=al)
    assert err > 0


def test_bank_level_recovery_l1_safe_on_zero_truth() -> None:
    """Σ |gt| = 0 ⇒ return 0 (denominator-safe), regardless of `allocated`.

    Two distinct allocation profiles must both collapse to 0.0:
      * `al = ones` (pure mismatch)
      * `al = zeros` (pure match)
    Otherwise the safe-on-zero path is conditional, not denominator-safe.
    """
    gt = np.zeros(5)
    assert bank_level_recovery_l1(ground_truth=gt, allocated=np.ones(5)) == 0.0
    assert bank_level_recovery_l1(ground_truth=gt, allocated=np.zeros(5)) == 0.0


def test_bank_level_recovery_l1_rejects_shape_mismatch() -> None:
    with pytest.raises(ValueError, match="shape mismatch"):
        bank_level_recovery_l1(ground_truth=np.zeros(3), allocated=np.zeros(4))
