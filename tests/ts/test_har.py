from __future__ import annotations

import numpy as np

from core.ts.har import fit_har, predict_har, update_har


def test_har_outperforms_naive() -> None:
    rng = np.random.default_rng(123)
    rv = np.cumsum(rng.normal(0, 0.1, size=200)) + 1.0
    state = fit_har(rv[:-20])
    preds = []
    naive = []
    for val in rv[-20:]:
        preds.append(predict_har(state))
        naive.append(rv.mean())
        update_har(state, val)
    mae_har = np.mean(np.abs(np.array(preds) - rv[-20:]))
    mae_naive = np.mean(np.abs(np.array(naive) - rv[-20:]))
    assert mae_har < mae_naive
