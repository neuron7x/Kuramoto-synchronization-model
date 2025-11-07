"""Risk metrics used by the NaK validation harness.

Copyright (c) 2024 TradePulse Technologies. All rights reserved.
Licensed under the TradePulse Proprietary License Agreement (TPLA).
"""

from __future__ import annotations

from typing import Iterable

import numpy as np


def cvar_es(returns: Iterable[float] | np.ndarray, alpha: float = 0.95) -> float:
    r = np.asarray(returns, dtype=float)
    if r.size == 0:
        return 0.0
    q = np.quantile(r, 1.0 - alpha)
    tail = r[r <= q]
    return 0.0 if tail.size == 0 else -float(tail.mean())
