"""Fractal dimension estimators for self-similarity and complexity analysis.

Mathematical Foundation:
    The fractal (Hausdorff-Besicovitch) dimension D quantifies the scaling
    behavior of a set or signal across different resolutions. For a fractal
    object, the number of covering elements N(ε) scales with the resolution ε as:

        N(ε) ~ ε^(-D)

    Taking logarithms:
        log N(ε) ~ -D · log ε

    The dimension D is extracted as the slope of the log-log plot.

Box-Counting Dimension:
    For a 1D signal x(t), the box-counting dimension estimates the complexity
    by counting the minimum number of boxes (bins) N(ε) needed to cover the
    signal at resolution ε:

        D_box = lim_{ε→0} [log N(ε) / log(1/ε)]

    In practice, compute for multiple ε values and fit linear regression.

Interpretation:
    D = 1.0: Smooth curve (Euclidean dimension)
    D > 1.0: Fractal/rough curve
    D ≈ 1.5: Brownian motion (typical for financial time series)
    D → 2.0: Highly irregular, space-filling curve

Applications in Finance:
    - D > 1.5: High volatility, chaotic regime
    - D ≈ 1.0: Smooth trending regime
    - Δ(D) > 0: Increasing complexity (turbulence signal)

References:
    - Mandelbrot, B. B. (1982). The Fractal Geometry of Nature. W.H. Freeman.
    - Higuchi, T. (1988). Approach to an irregular time series on the basis of
      the fractal theory. Physica D, 31(2), 277-283.
"""

from __future__ import annotations

import numpy as np


def box_counting_dim(signal: np.ndarray, eps_list: np.ndarray | None = None) -> float:
    """Estimate the box-counting fractal dimension of a 1D signal.

    Mathematical Algorithm:
        1. For each resolution ε in eps_list:
           a. Compute bin size: Δ = (max(x) - min(x)) / ε
           b. Discretize signal into bins
           c. Count number of occupied bins: N(ε)

        2. Perform log-log linear regression:
           log N(ε) ~ -D · log ε + const
           
           where D is the fractal dimension (extracted as slope).

    Args:
        signal: 1D array of signal values (typically prices or returns).
        eps_list: Array of resolution scales ε > 0 (default: logarithmically
            spaced from 10⁻³ to 10⁻¹ with 8 points).
            Smaller ε → finer resolution (more boxes needed).

    Returns:
        float: Estimated box-counting dimension D ≥ 0.
            Typically D ∈ [1.0, 2.0] for time series signals.

    Numerical Stability:
        - Small epsilon (10⁻¹²) added to prevent log(0)
        - Bin count clamped to positive values
        - Handles constant signals (D → 1.0)

    Complexity:
        Time: O(M·N) where M = len(eps_list), N = len(signal)
        Space: O(N) for histogram computation

    Examples:
        >>> # Smooth sine wave (D ≈ 1.0)
        >>> t = np.linspace(0, 10, 1000)
        >>> signal = np.sin(t)
        >>> D = box_counting_dim(signal)
        >>> assert 0.9 < D < 1.1

        >>> # Random walk (D ≈ 1.5)
        >>> random_walk = np.cumsum(np.random.randn(1000))
        >>> D = box_counting_dim(random_walk)
        >>> assert 1.3 < D < 1.7

    References:
        - Liebovitch, L. S., & Toth, T. (1989). A fast algorithm to determine
          fractal dimensions by box counting. Physics Letters A, 141(8-9).
        - Theiler, J. (1990). Estimating fractal dimension. JOSA A, 7(6).
    """
    values = np.asarray(signal, dtype=float)
    if eps_list is None:
        eps_list = np.logspace(-3, -1, 8)
    counts = []
    for eps in eps_list:
        bins = int(np.ceil((values.max() - values.min()) / (eps + 1e-8))) + 1
        hist, _ = np.histogram(values, bins=bins)
        counts.append((hist > 0).sum())
    X = -np.log(eps_list + 1e-12)
    Y = np.log(np.array(counts, dtype=float) + 1e-12)
    slope, _ = np.polyfit(X, Y, 1)
    return float(slope)
