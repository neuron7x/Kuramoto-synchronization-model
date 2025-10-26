"""Unit tests for purged cross-validation."""

from __future__ import annotations

import numpy as np

from neuropro.cv import purged_kfold


def test_purged_cv_disjoint() -> None:
    ends = np.arange(200)
    folds = list(purged_kfold(ends, n_folds=5, embargo=10))
    assert len(folds) == 5
    for train_idx, test_idx in folds:
        assert set(train_idx).isdisjoint(set(test_idx))


def test_purged_cv_drops_events_spanning_test_window() -> None:
    ends = np.array([1, 2, 5, 6, 9, 10])
    folds = list(purged_kfold(ends, n_folds=3, embargo=0))
    # Inspect the middle fold which should purge events that extend beyond the
    # test window boundaries.
    train_idx, test_idx = folds[1]
    test_start = test_idx.min()
    test_end = ends[test_idx].max()
    train_starts = train_idx
    train_ends = ends[train_idx]
    overlaps = (train_starts < test_end) & (train_ends > test_start)
    assert not overlaps.any()
