# SPDX-License-Identifier: MIT
"""Regression suite for the C5 ROC-AUC metric (fast lane — not slow).

The C5 verdict (`C5_ESTIMATOR_QUALITY_GAP`) rests entirely on the OOS AUC
crossing a pre-registered band. A defective AUC would make the closure
conditional, not factual. Every edge case here is checked against the
*definitional* AUC = P(s+ > s-) + 0.5·P(s+ == s-) computed by brute force.
"""

from __future__ import annotations

import numpy as np

from research.ctc_falsify.c5.oracle import _auc


def _brute_auc(scores: np.ndarray, y: np.ndarray) -> float:
    pos = scores[y == 1]
    neg = scores[y == 0]
    if pos.size == 0 or neg.size == 0:
        return 0.5
    gt = 0.0
    for p in pos:
        for n in neg:
            gt += 1.0 if p > n else (0.5 if p == n else 0.0)
    return gt / (pos.size * neg.size)


def _check(scores: list[float], y: list[int]) -> None:
    s = np.asarray(scores, dtype=np.float64)
    yy = np.asarray(y, dtype=np.float64)
    assert abs(_auc(s, yy) - _brute_auc(s, yy)) < 1e-12


def test_constant_scores_give_chance_auc() -> None:
    # The old ordinal-rank bug returned 0.0 here (→ folded to a FALSE 1.0).
    _check([0.7] * 6, [1, 1, 1, 0, 0, 0])
    s = np.full(6, 0.7)
    y = np.array([1, 1, 1, 0, 0, 0], dtype=np.float64)
    assert _auc(s, y) == 0.5


def test_all_tied_subset_is_half_credited() -> None:
    _check([1.0, 1.0, 1.0, 1.0], [1, 0, 1, 0])
    _check([2, 2, 1, 1, 3, 3], [1, 0, 1, 0, 1, 0])


def test_perfect_and_anti_separation() -> None:
    assert _auc(np.array([3.0, 4.0, 1.0, 2.0]), np.array([1, 1, 0, 0])) == 1.0
    assert _auc(np.array([1.0, 2.0, 3.0, 4.0]), np.array([1, 1, 0, 0])) == 0.0


def test_reversed_labels_complement() -> None:
    s = np.array([0.1, 0.9, 0.4, 0.8, 0.2], dtype=np.float64)
    y = np.array([1, 0, 1, 0, 1], dtype=np.float64)
    assert abs(_auc(s, y) + _auc(s, 1.0 - y) - 1.0) < 1e-12


def test_unbalanced_classes_match_brute() -> None:
    rng = np.random.default_rng(7)
    s = rng.normal(size=40)
    y = np.array([1] * 7 + [0] * 33, dtype=np.float64)
    _check(list(s), list(y.astype(int)))


def test_randomised_with_injected_ties_match_brute() -> None:
    rng = np.random.default_rng(20260517)
    for _ in range(50):
        n = int(rng.integers(4, 30))
        s = np.round(rng.normal(size=n), 1)  # rounding forces many ties
        y = rng.integers(0, 2, size=n).astype(np.float64)
        if y.sum() == 0 or y.sum() == n:
            continue
        assert abs(_auc(s, y) - _brute_auc(s, y)) < 1e-12


def test_empty_class_is_chance() -> None:
    assert _auc(np.array([1.0, 2.0]), np.array([1.0, 1.0])) == 0.5
    assert _auc(np.array([1.0, 2.0]), np.array([0.0, 0.0])) == 0.5
