# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Cross-validation helpers for purged K-fold splits."""

from __future__ import annotations

import numpy as np


def purged_kfold(
    events_end_idx: np.ndarray,
    n_folds: int = 5,
    embargo: int = 50,
    events_start_idx: np.ndarray | None = None,
):
    n = len(events_end_idx)
    if n_folds < 2:
        raise ValueError("n_folds must be at least 2")

    if events_start_idx is None:
        events_start_idx = np.arange(n)
    else:
        events_start_idx = np.asarray(events_start_idx)
        if events_start_idx.shape != (n,):
            raise ValueError("events_start_idx must be one-dimensional and match events_end_idx")

    fold_sizes = np.full(n_folds, n // n_folds, dtype=int)
    fold_sizes[: n % n_folds] += 1
    current = 0
    idx = np.arange(n)
    for fs in fold_sizes:
        start, stop = current, current + fs
        test_idx = idx[start:stop]
        test_end = events_end_idx[test_idx].max()
        test_start = events_start_idx[test_idx].min()
        train_mask = (events_end_idx <= test_start) | (events_start_idx >= test_end)
        emb_lo = max(0, start - embargo)
        emb_hi = min(n, stop + embargo)
        embargo_mask = np.ones(n, dtype=bool)
        embargo_mask[emb_lo:emb_hi] = False
        train_idx = idx[train_mask & embargo_mask]
        yield train_idx, test_idx
        current = stop
