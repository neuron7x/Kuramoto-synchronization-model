# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import numpy as np


def skewness(x: np.ndarray) -> float:
    """Calculate statistical skewness of a distribution.
    
    Args:
        x: Input array of values
    
    Returns:
        Skewness coefficient. Positive values indicate right-skewed distribution,
        negative values indicate left-skewed distribution
    """
    x = np.asarray(x, dtype=float)
    if x.std() == 0 or x.size == 0:
        return 0.0
    z = (x - x.mean()) / (x.std() + 1e-12)
    return float(np.mean(z**3))


def direction_index(
    skew: float, delta_curv: float, bias: float, lambdas=(0.5, 0.3, 0.2)
) -> float:
    """Calculate composite direction index from market characteristics.
    
    Combines skewness, curvature change, and bias to determine market direction.
    
    Args:
        skew: Distribution skewness
        delta_curv: Change in curvature
        bias: Directional bias indicator
        lambdas: Weighting factors for (skew, delta_curv, bias). Default: (0.5, 0.3, 0.2)
    
    Returns:
        Composite direction index value
    """
    l1, l2, l3 = lambdas
    return float(l1 * skew + l2 * delta_curv + l3 * bias)
