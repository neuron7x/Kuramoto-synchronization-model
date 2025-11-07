from __future__ import annotations

import numpy as np

from core.uq.ensembles import DeepEnsembles


def test_variance_contraction_and_expansion() -> None:
    rng = np.random.default_rng(0)
    X = rng.normal(0, 1, size=(200, 4))
    y = (X[:, 0] * 2.0 + X[:, 1]).astype(np.float32)
    ens = DeepEnsembles(state_dim=4, k=3, lr=1e-2, bootstrap=True)
    ens.update_batch(X, y)
    var_in = ens.predict_var(X[0])
    X_ood = rng.normal(5.0, 1, size=(50, 4))
    var_ood = ens.predict_var(X_ood[0])
    assert var_in < var_ood
