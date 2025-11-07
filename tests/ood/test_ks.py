from __future__ import annotations

import numpy as np

from core.ood.ks import ood_score_ks


def test_ks_score_detects_shift() -> None:
    rng = np.random.default_rng(0)
    A = rng.normal(0, 1, size=(500, 3))
    B = rng.normal(0, 1, size=(500, 3))
    score_same = ood_score_ks(A, B, 0.05)
    C = rng.normal(1.5, 1, size=(500, 3))
    score_shift = ood_score_ks(A, C, 0.05)
    assert score_same < 0.2
    assert score_shift > 0.5
