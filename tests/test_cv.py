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
