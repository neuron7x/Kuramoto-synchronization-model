import numpy as np


def cvar_es(returns, alpha=0.95) -> float:
    r = np.asarray(returns, dtype=float)
    if r.size == 0:
        return 0.0
    q = np.quantile(r, 1.0 - alpha)
    tail = r[r <= q]
    return 0.0 if tail.size == 0 else -float(tail.mean())
