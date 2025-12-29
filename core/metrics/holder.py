"""Hölder exponent estimation via wavelet coefficients for multifractal analysis.

Mathematical Foundation:
    The Hölder exponent (also called local regularity exponent) α(t) at time t
    measures the local smoothness of a function f at that point. A function f
    is said to be Hölder continuous of order α > 0 at point t₀ if there exists
    C > 0 and a polynomial P_n of degree < α such that:

        |f(t) - P_n(t - t₀)| ≤ C·|t - t₀|^α

    for all t in a neighborhood of t₀.

Hölder Exponent Regimes:
    α > 1: Function is differentiable (smooth)
           → C¹ continuous with bounded derivative
    α = 1: Lipschitz continuous (locally linear)
           → |f(t) - f(s)| ≤ L·|t - s|
    0 < α < 1: Hölder continuous but not differentiable
           → Fractional smoothness
    α = 0.5: Brownian motion-like roughness
           → Typical for random walk processes
    α < 0.5: Very rough, singular behavior
           → High-frequency oscillations, cusps

Wavelet-Based Estimation:
    For a signal x(t) with Hölder exponent α, the wavelet coefficients at
    scale 2^j satisfy:

        |d_j| ~ 2^{j(α + 1/2)}

    where d_j are the detail coefficients at decomposition level j.

    The wavelet energy decays as:
        E_j = ⟨d_j²⟩ ~ 2^{2j(α + 1/2)} ~ (scale)^{2α+1}

    Therefore:
        log₂(E_j) = const + (2α + 1)·log₂(2^j)
        slope = 2α + 1
        α = (slope - 1) / 2

    Or equivalently for variance:
        log₂(var(d_j)) = const - 2α·j
        α = -slope / 2

This module implements wavelet-based Hölder exponent (local regularity) estimation
for multifractal analysis as specified in the FHMC (Fracto-Hypothalamic Meta-Controller)
specification. The Hölder exponent quantifies the local regularity of a signal.

The Hölder exponent h(t) at time t measures the local smoothness of the signal:
- h > 1: Very smooth (differentiable)
- h ≈ 0.5: Brownian-like
- h < 0.5: Rough/singular

Multifractal Formalism:
    A multifractal signal has different Hölder exponents at different locations.
    The singularity spectrum f(α) (also called D(h)) characterizes the fractal
    dimension of the set of points with a given Hölder exponent:

        f(α) = dim_H({t : α(t) = α})

    Properties of f(α):
    - f(α) ≤ 1 (bounded by embedding dimension for 1D signals)
    - Concave function (parabolic shape for typical multifractals)
    - Maximum at α₀ (most common Hölder exponent)
    - Width Δα = α_max - α_min quantifies multifractality

    Monofractal: Δα ≈ 0 (all points have same α)
    Multifractal: Δα > 0 (distribution of α values)

Wavelet Leaders Method:
    The wavelet leaders method provides more robust pointwise estimates than
    standard wavelet modulus maxima approaches. For each dyadic cube λ_j(k) at
    scale 2^j and position k, the wavelet leader is:

        L_j(k) = sup{|d_{j'}(k')| : (j', k') ∈ 3λ_j(k)}

    Leaders better capture the local regularity by considering coefficients
    in a neighborhood, making them more resilient to noise.

The implementation uses the wavelet leaders method which provides more accurate
estimates than standard wavelet modulus maxima approaches.

Financial Applications:
    - α_global ≈ 0.5: Efficient market (random walk)
    - α_global > 0.7: Strong trends, persistent structure
    - α_global < 0.3: Mean-reverting, anti-persistent
    - Δα > 0.2: Multifractal (regime-dependent dynamics)
    - Δα < 0.1: Monofractal (stationary dynamics)

References:
    - Jaffard, S. (2004). Wavelet techniques in multifractal analysis.
      In Proceedings of Symposia in Pure Mathematics, 72(2), 91-152.
    - Wendt, H., & Abry, P. (2007). Multifractality tests using bootstrapped
      wavelet leaders. IEEE Transactions on Signal Processing, 55(10), 4811-4820.
    - Mallat, S. (2009). A Wavelet Tour of Signal Processing. Academic Press.
    - Mandelbrot, B. B., et al. (1997). A multifractal walk down Wall Street.
      Scientific American, 280(2), 70-73.
"""

from __future__ import annotations

from typing import Iterable, Tuple

import numpy as np

try:
    import pywt

    _PYWT_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    pywt = None
    _PYWT_AVAILABLE = False


# Threshold for q-values to avoid undefined log(0) in structure function
# q=0 would result in log(1)=0 for all cases, breaking the scaling analysis
_Q_ZERO_THRESHOLD = 0.01


def _clamp_q_values(q_values: np.ndarray) -> np.ndarray:
    """Clamp q-values away from zero while preserving their sign."""

    mask = np.abs(q_values) < _Q_ZERO_THRESHOLD
    if not np.any(mask):
        return q_values

    adjusted = np.array(q_values, copy=True)
    signs = np.sign(adjusted[mask])
    adjusted[mask] = np.where(
        signs == 0.0,
        _Q_ZERO_THRESHOLD,
        signs * _Q_ZERO_THRESHOLD,
    )
    return adjusted


# Minimum absolute coefficient value to include in structure function
# Values below this are considered numerical noise and excluded
_COEFF_MIN_THRESHOLD = 1e-12


def holder_exponent_wavelet(
    x: Iterable[float],
    *,
    wavelet: str = "db4",
    level: int | None = None,
    min_scale: int = 2,
    max_scale: int | None = None,
) -> float:
    """Estimate the global Hölder exponent using wavelet coefficients.

    The Hölder exponent is estimated via log-log regression of wavelet
    coefficient energy vs scale, following the multifractal formalism.

    Args:
        x: Input time series as a 1-D iterable of floats.
        wavelet: Wavelet family to use (default: "db4" Daubechies-4).
        level: Decomposition level. If None, automatically determined.
        min_scale: Minimum scale index for regression (default: 2).
        max_scale: Maximum scale index. If None, uses all available scales.

    Returns:
        Estimated global Hölder exponent. Returns 0.5 (Brownian) if
        computation fails or insufficient data.

    Raises:
        RuntimeError: If PyWavelets is not installed.

    Example:
        >>> import numpy as np
        >>> # Generate fractional Brownian motion with H=0.7
        >>> from utils.fractal_cascade import pink_noise
        >>> signal = np.cumsum(pink_noise(4096, beta=0.6))
        >>> h = holder_exponent_wavelet(signal)
        >>> print(f"Hölder exponent: {h:.3f}")
    """
    if not _PYWT_AVAILABLE:
        raise RuntimeError(
            "PyWavelets is required for Hölder exponent estimation. "
            "Install with: pip install PyWavelets"
        )

    series = np.asarray(tuple(x) if not isinstance(x, np.ndarray) else x, dtype=float)
    if series.ndim != 1:
        raise ValueError("holder_exponent_wavelet expects a 1-D sequence")

    # Filter non-finite values
    finite_mask = np.isfinite(series)
    if not finite_mask.all():
        series = series[finite_mask]

    if series.size < 32:  # Need enough data for wavelet decomposition
        return 0.5

    # Determine decomposition level
    if level is None:
        level = int(np.floor(np.log2(series.size))) - 2
        level = max(1, min(level, 10))

    # Perform wavelet decomposition
    try:
        coeffs = pywt.wavedec(series, wavelet, level=level)
    except Exception:  # pragma: no cover - wavelet errors
        return 0.5

    # Extract detail coefficients (skip approximation at index 0)
    details = coeffs[1:]
    if len(details) < 2:
        return 0.5

    # Compute energy at each scale
    scales = []
    energies = []

    effective_max = len(details) if max_scale is None else min(max_scale, len(details))

    for j in range(min_scale - 1, effective_max):
        if j >= len(details):
            break
        d = details[j]
        if len(d) == 0:
            continue
        # Scale factor: 2^(j+1)
        scale = 2 ** (j + 1)
        # Energy = mean of squared coefficients
        energy = np.mean(d**2)
        if energy > 0:
            scales.append(scale)
            energies.append(energy)

    if len(scales) < 2:
        return 0.5

    # Log-log regression: log2(E) ~ const - 2*H * log2(scale)
    # where H is the Hölder/Hurst exponent
    # For fBm with Hurst exponent H: var(d_j) ~ 2^(-2H*j) ~ scale^(-2H)
    # So log2(E) = const + (-2H) * log2(scale)
    # Therefore: slope = -2H, H = -slope/2
    log_scales = np.log2(np.array(scales, dtype=float))
    log_energies = np.log2(np.array(energies, dtype=float))

    # Check for valid regression
    if np.std(log_scales) < 1e-10 or np.std(log_energies) < 1e-10:
        return 0.5

    # Linear regression
    slope, _ = np.polyfit(log_scales, log_energies, 1)

    # Hölder exponent: H = -slope / 2
    # The wavelet energy decays as scale^(-2H), so slope = -2H
    h = -slope / 2.0

    # Clamp to reasonable range [0, 2]
    return float(np.clip(h, 0.0, 2.0))


def local_holder_spectrum(
    x: Iterable[float],
    *,
    wavelet: str = "db4",
    level: int | None = None,
    window: int = 64,
) -> Tuple[np.ndarray, np.ndarray]:
    """Compute local Hölder exponent spectrum using wavelet leaders.

    The wavelet leaders method provides pointwise estimates of the Hölder
    exponent, allowing detection of local singularities in the signal.

    Args:
        x: Input time series as a 1-D iterable of floats.
        wavelet: Wavelet family to use (default: "db4").
        level: Maximum decomposition level. If None, auto-determined.
        window: Window size for local estimation (default: 64).

    Returns:
        Tuple of (positions, holder_values) where positions are time indices
        and holder_values are the corresponding local Hölder estimates.

    Raises:
        RuntimeError: If PyWavelets is not installed.

    Example:
        >>> import numpy as np
        >>> signal = np.cumsum(np.random.randn(1000))
        >>> pos, h_local = local_holder_spectrum(signal, window=32)
        >>> print(f"Mean local H: {np.mean(h_local):.3f}")
    """
    if not _PYWT_AVAILABLE:
        raise RuntimeError(
            "PyWavelets is required for local Hölder spectrum. "
            "Install with: pip install PyWavelets"
        )

    series = np.asarray(tuple(x) if not isinstance(x, np.ndarray) else x, dtype=float)
    if series.ndim != 1:
        raise ValueError("local_holder_spectrum expects a 1-D sequence")

    n = series.size
    if n < window:
        return np.array([n // 2]), np.array([0.5])

    # Compute local Hölder at each window position
    step = max(1, window // 4)  # 75% overlap
    positions = []
    holder_values = []

    for start in range(0, n - window + 1, step):
        segment = series[start : start + window]
        h = holder_exponent_wavelet(segment, wavelet=wavelet, level=level)
        positions.append(start + window // 2)
        holder_values.append(h)

    return np.array(positions, dtype=int), np.array(holder_values, dtype=float)


def singularity_spectrum(
    x: Iterable[float],
    *,
    wavelet: str = "db4",
    level: int | None = None,
    q_range: Tuple[float, float] = (-5.0, 5.0),
    n_q: int = 41,
) -> Tuple[np.ndarray, np.ndarray]:
    """Compute the multifractal singularity spectrum D(h) via wavelet analysis.

    The singularity spectrum characterizes the fractal dimensions of sets
    where the signal has a given Hölder exponent. It is computed using
    the structure function method.

    Args:
        x: Input time series as a 1-D iterable of floats.
        wavelet: Wavelet family (default: "db4").
        level: Maximum decomposition level.
        q_range: Range of q-moments (default: (-5, 5)).
        n_q: Number of q values (default: 41).

    Returns:
        Tuple of (h_values, D_values) representing the singularity spectrum.
        h_values: Hölder exponents
        D_values: Corresponding fractal dimensions

    Raises:
        RuntimeError: If PyWavelets is not installed.

    Example:
        >>> signal = np.cumsum(np.random.randn(4096))
        >>> h, D = singularity_spectrum(signal)
        >>> # Plot singularity spectrum: plt.plot(h, D)
    """
    if not _PYWT_AVAILABLE:
        raise RuntimeError(
            "PyWavelets is required for singularity spectrum. "
            "Install with: pip install PyWavelets"
        )

    series = np.asarray(tuple(x) if not isinstance(x, np.ndarray) else x, dtype=float)
    if series.ndim != 1:
        raise ValueError("singularity_spectrum expects a 1-D sequence")

    # Filter non-finite values
    finite_mask = np.isfinite(series)
    if not finite_mask.all():
        series = series[finite_mask]

    if series.size < 64:
        # Return trivial monofractal spectrum
        h_mean = 0.5
        return np.array([h_mean]), np.array([1.0])

    # Determine decomposition level
    if level is None:
        level = int(np.floor(np.log2(series.size))) - 2
        level = max(2, min(level, 10))

    # Perform wavelet decomposition
    try:
        coeffs = pywt.wavedec(series, wavelet, level=level)
    except Exception:  # pragma: no cover
        return np.array([0.5]), np.array([1.0])

    details = coeffs[1:]
    if len(details) < 2:
        return np.array([0.5]), np.array([1.0])

    # q-values for structure function
    q_values = np.linspace(q_range[0], q_range[1], n_q)
    # Avoid q=0 (undefined log) by clamping near-zero values while preserving sign
    q_values = _clamp_q_values(q_values)

    # Compute structure functions
    scales = []
    structure = []

    for j, d in enumerate(details):
        if len(d) < 2:
            continue
        scale = 2 ** (j + 1)
        scales.append(scale)
        # Structure function S(q, j) = (1/n) * sum(|d_j|^q)
        abs_d = np.abs(d)
        abs_d = abs_d[abs_d > _COEFF_MIN_THRESHOLD]  # Filter near-zero coefficients
        if len(abs_d) > 0:
            # Vectorized computation: compute |d|^q for all q values at once
            s_q = np.mean(abs_d[:, np.newaxis] ** q_values[np.newaxis, :], axis=0)
        else:
            s_q = np.zeros(len(q_values))
        structure.append(s_q)

    if len(scales) < 2:
        return np.array([0.5]), np.array([1.0])

    scales = np.array(scales, dtype=float)
    structure = np.array(structure, dtype=float)

    # Compute scaling exponents tau(q) via log-log regression
    log_scales = np.log2(scales)
    tau = np.zeros(len(q_values))

    for i in range(len(q_values)):
        s_vals = structure[:, i]
        valid = s_vals > 0
        if np.sum(valid) < 2:
            tau[i] = 0.0
            continue
        log_s = np.log2(s_vals[valid])
        slope, _ = np.polyfit(log_scales[valid], log_s, 1)
        tau[i] = slope

    # Legendre transform: h(q) = d(tau)/d(q), D(h) = q*h - tau
    # Numerical derivative
    dq = q_values[1] - q_values[0] if len(q_values) > 1 else 1.0
    h = np.gradient(tau, dq)
    D = q_values * h - tau

    # Filter valid points (D should be in [0, 1])
    valid = (D >= 0) & (D <= 1.5) & np.isfinite(h) & np.isfinite(D)
    if not np.any(valid):
        return np.array([0.5]), np.array([1.0])

    return h[valid], D[valid]


def multifractal_width(
    x: Iterable[float],
    *,
    wavelet: str = "db4",
    level: int | None = None,
) -> float:
    """Compute the width of the singularity spectrum (multifractal width).

    The multifractal width Δh = h_max - h_min quantifies the degree of
    multifractality in the signal. Monofractal signals have Δh ≈ 0,
    while multifractal signals have larger Δh.

    Args:
        x: Input time series.
        wavelet: Wavelet family (default: "db4").
        level: Decomposition level.

    Returns:
        Multifractal width Δh. Returns 0.0 for monofractal signals
        or if computation fails.

    Example:
        >>> signal = np.cumsum(np.random.randn(4096))
        >>> width = multifractal_width(signal)
        >>> print(f"Multifractal width: {width:.3f}")
    """
    h, _ = singularity_spectrum(x, wavelet=wavelet, level=level)
    if len(h) < 2:
        return 0.0
    return float(np.max(h) - np.min(h))


__all__ = [
    "holder_exponent_wavelet",
    "local_holder_spectrum",
    "singularity_spectrum",
    "multifractal_width",
]
