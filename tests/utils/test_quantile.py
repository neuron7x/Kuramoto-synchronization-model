from __future__ import annotations

import numpy as np

from tradepulse.core.neuro.quantile import P2Quantile


def test_p2_quantile_converges_uniform():
    rng = np.random.default_rng(0)
    q = 0.8
    est = P2Quantile(q)
    xs = rng.uniform(-1, 1, 10000)
    for x in xs:
        est.update(float(x))
    true_q = float(np.quantile(xs, q))
    assert abs(est.quantile - true_q) < 0.02


def test_p2_quantile_monotone_updates():
    est = P2Quantile(0.5)
    for x in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]:
        est.update(x)
    assert 0 <= est.quantile <= 9
