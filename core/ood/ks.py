"""OOD detection via per-feature KS-tests."""

from __future__ import annotations

import numpy as np
from scipy.stats import ks_2samp


def ood_score_ks(A: np.ndarray, B: np.ndarray, alpha: float) -> float:
    """Return the fraction of features flagged as out-of-distribution."""

    if A.ndim == 1:
        A = A[:, None]
    if B.ndim == 1:
        B = B[:, None]
    if A.shape[1] != B.shape[1]:
        raise ValueError("Feature dimension mismatch for KS test")
    flags = []
    for i in range(A.shape[1]):
        a = np.asarray(A[:, i], dtype=float)
        b = np.asarray(B[:, i], dtype=float)
        if len(a) == 0 or len(b) == 0:
            continue
        statistic = ks_2samp(a, b, method="asymp")
        flags.append(float(statistic.pvalue < alpha))
    if not flags:
        return 0.0
    return float(np.mean(flags))


__all__ = ["ood_score_ks"]
