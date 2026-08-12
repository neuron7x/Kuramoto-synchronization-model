"""Tests for purged K-fold CV module."""

from __future__ import annotations

import numpy as np
import pytest

from research.microstructure.cv import (
    PurgedKFoldReport,
    purged_kfold_ic,
    purged_kfold_indices,
)


def test_purged_indices_covers_all_rows_exactly_once_in_test() -> None:
    """Each row belongs to exactly one test fold."""
    n = 1000
    test_rows: list[int] = []
    for _, test_idx in purged_kfold_indices(n, k=5, horizon_rows=20, embargo_rows=10):
        test_rows.extend(test_idx.tolist())
    assert sorted(test_rows) == list(range(n))


def test_purged_indices_train_disjoint_from_test() -> None:
    """Training indices exclude test rows and purge/embargo zones."""
    n = 1000
    horizon = 30
    embargo = 20
    for train_idx, test_idx in purged_kfold_indices(
        n, k=5, horizon_rows=horizon, embargo_rows=embargo
    ):
        assert np.intersect1d(train_idx, test_idx).size == 0
        test_start = int(test_idx.min())
        test_end = int(test_idx.max()) + 1
        purge_lo = max(0, test_start - horizon)
        embargo_hi = min(n, test_end + embargo)
        # No training row may fall inside [purge_lo, embargo_hi)
        in_zone = np.logical_and(train_idx >= purge_lo, train_idx < embargo_hi)
        assert not bool(in_zone.any())


def test_purged_indices_rejects_k_less_than_two() -> None:
    with pytest.raises(ValueError):
        list(purged_kfold_indices(100, k=1, horizon_rows=10))


def test_purged_indices_rejects_n_less_than_k() -> None:
    with pytest.raises(ValueError):
        list(purged_kfold_indices(3, k=5, horizon_rows=1))


def test_purged_indices_rejects_negative_horizon() -> None:
    with pytest.raises(ValueError):
        list(purged_kfold_indices(100, k=5, horizon_rows=-1))


def test_purged_indices_rejects_negative_embargo() -> None:
    with pytest.raises(ValueError):
        list(purged_kfold_indices(100, k=5, horizon_rows=10, embargo_rows=-1))


def test_purged_indices_number_of_folds_equals_k() -> None:
    for k in (2, 3, 5, 10):
        folds = list(purged_kfold_indices(2000, k=k, horizon_rows=30))
        assert len(folds) == k


def test_purged_indices_zero_purge_zero_embargo_covers_complement() -> None:
    """With horizon=0 embargo=0, train should equal set(all_rows) − test."""
    n = 500
    for train_idx, test_idx in purged_kfold_indices(n, k=5, horizon_rows=0, embargo_rows=0):
        expected_train = np.setdiff1d(np.arange(n), test_idx)
        assert np.array_equal(train_idx, expected_train)


def test_purged_kfold_ic_strong_correlation_reports_high_mean() -> None:
    rng = np.random.default_rng(42)
    n, n_sym = 2000, 3
    sig1d = rng.normal(0.0, 1.0, size=n)
    signal_panel = np.repeat(sig1d[:, None], n_sym, axis=1)
    noise = rng.normal(0.0, 0.1, size=(n, n_sym))
    target_panel = signal_panel + noise
    report = purged_kfold_ic(signal_panel, target_panel, k=5, horizon_rows=30, embargo_rows=10)
    assert isinstance(report, PurgedKFoldReport)
    assert report.ic_mean > 0.9
    assert report.pos_fold_frac == 1.0


def test_purged_kfold_ic_null_reports_mean_near_zero() -> None:
    rng = np.random.default_rng(42)
    n, n_sym = 3000, 3
    signal = rng.normal(0.0, 1.0, size=(n, n_sym))
    target = rng.normal(0.0, 1.0, size=(n, n_sym))
    report = purged_kfold_ic(signal, target, k=5, horizon_rows=30)
    assert abs(report.ic_mean) < 0.1


def test_purged_kfold_ic_schema_contains_all_keys() -> None:
    rng = np.random.default_rng(42)
    n, n_sym = 1500, 2
    signal = rng.normal(0.0, 1.0, size=(n, n_sym))
    target = signal + rng.normal(0.0, 0.5, size=(n, n_sym))
    report = purged_kfold_ic(signal, target, k=3, horizon_rows=30)
    assert len(report.ic_per_fold) == 3
    assert len(report.n_train_rows_per_fold) == 3
    assert len(report.n_test_rows_per_fold) == 3
    assert report.n_rows_total == n
    assert sum(report.n_test_rows_per_fold) == n


def test_purged_kfold_ic_shape_mismatch_raises() -> None:
    a = np.zeros((100, 3), dtype=np.float64)
    b = np.zeros((100, 2), dtype=np.float64)
    with pytest.raises(ValueError):
        purged_kfold_ic(a, b, k=5, horizon_rows=10)


def test_purged_kfold_train_shrinks_with_larger_horizon() -> None:
    """More purging ⇒ fewer training rows."""
    n = 2000
    folds_small = list(purged_kfold_indices(n, k=5, horizon_rows=10, embargo_rows=10))
    folds_big = list(purged_kfold_indices(n, k=5, horizon_rows=300, embargo_rows=100))
    for (tr_s, _), (tr_b, _) in zip(folds_small, folds_big, strict=False):
        assert tr_s.size > tr_b.size
