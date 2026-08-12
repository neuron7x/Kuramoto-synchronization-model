# SPDX-License-Identifier: MIT
"""Metric ↔ policy split invariant (fast lane).

Cross-system hardening (report take #1): a direction-sensitive metric and
a sign-invariant policy fold must be SEPARATE functions. Folding sign
inside the metric hides the 'anti-correlated by construction' failure.
"""

from __future__ import annotations

import numpy as np

from research.ctc_falsify.c5.oracle import _auc, _discriminability


def test_raw_auc_is_direction_sensitive_not_folded() -> None:
    perfect = np.array([3.0, 4.0, 1.0, 2.0])
    anti = np.array([1.0, 2.0, 3.0, 4.0])
    y = np.array([1, 1, 0, 0], dtype=np.float64)
    assert _auc(perfect, y) == 1.0
    # The whole point: anti-separation stays 0.0, NOT folded up to 1.0.
    assert _auc(anti, y) == 0.0


def test_discriminability_is_the_separate_sign_invariant_policy() -> None:
    anti = np.array([1.0, 2.0, 3.0, 4.0])
    y = np.array([1, 1, 0, 0], dtype=np.float64)
    assert _auc(anti, y) == 0.0
    assert _discriminability(_auc(anti, y)) == 1.0
    assert _discriminability(0.5) == 0.5
    for a in (0.0, 0.27, 0.5, 0.73, 1.0):
        assert _discriminability(a) == max(a, 1.0 - a)


def test_constant_scores_stay_chance_through_both_layers() -> None:
    s = np.full(6, 0.7)
    y = np.array([1, 1, 1, 0, 0, 0], dtype=np.float64)
    assert _auc(s, y) == 0.5
    assert _discriminability(_auc(s, y)) == 0.5  # never a false perfect
