from __future__ import annotations

import numpy as np


def rolling_std(data: np.ndarray, window: int = 50) -> np.ndarray:
    """Compute rolling standard deviation using stride tricks."""

    if window <= 0:
        raise ValueError("window must be positive")
    if data.size < window:
        raise ValueError("data must have at least `window` elements")
    return np.std(np.lib.stride_tricks.sliding_window_view(data, window), axis=1)
