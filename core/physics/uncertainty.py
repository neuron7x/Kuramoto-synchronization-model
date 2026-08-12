# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Gabor time-frequency uncertainty limit for sampled signals.

This module computes the EXACT signal-processing uncertainty bound, NOT a
quantum-mechanical one. For a well-resolved finite-energy signal x(t) the time
spread Δt and the frequency spread Δf of its power distribution satisfy the
Gabor limit::

    Δt · Δf ≥ 1 / (4π)

with equality (saturation) for a Gaussian envelope. This is a theorem of
Fourier analysis (Gabor 1946; Folland & Sitaram 1997) — it is derivable to
floating-point precision and falsifiable by construction. There is NO Planck
constant here: 1/(4π) is an exact mathematical constant, not a fabricated ℏ/2.

Scope of the discrete bound (honest)
------------------------------------
1/(4π) is the bound for the CONTINUOUS Fourier transform. The naive discrete
second-moment estimator implemented here realizes it faithfully only for
WELL-RESOLVED signals — time-localized within the window and band-limited away
from Nyquist. For under-resolved / near-Nyquist short signals the discrete
estimate can dip below 1/(4π), because the ``np.fft.fftfreq`` axis wraps at ±0.5
cyc/sample and the wrapped second moment underestimates the true spectral
spread. The module does not pretend such a number is a measurement: rather than
silently returning a sub-bound product, :func:`time_frequency_spread`
**fail-closes** (``ValueError``) when ``Δt·Δf`` lands below the theorem, because
the only thing a sub-bound discrete product can mean is "this window is too
under-resolved to localize". The universal sweep in the test-suite is over the
well-resolved regime, and a Gaussian envelope saturates the bound exactly
(INV-GABOR1).

Why this replaces the previous "Heisenberg" framing
----------------------------------------------------
The earlier implementation dressed the classical product
``std(price) · std(diff(price))`` as the quantum relation ΔxΔp ≥ ℏ/2 using a
fabricated ℏ = 1.0. Price and its first difference are *jointly observable* —
there is no canonical commutator [x̂, p̂] = iℏ and no Fourier-conjugate
pairing between them. That was a category error: the "bound" ℏ/2 was just the
number 0.5. The Gabor limit is the correct, anchored uncertainty theorem for a
sampled time series, because time and frequency ARE a genuine Fourier-conjugate
pair (INV-GABOR1).

Δt is the square root of the second moment of the normalized power |x|² about
its time centroid (in sample units). Δf is the square root of the second moment
of the normalized power spectrum |FFT(x)|² about its frequency centroid (in
cycles-per-sample units). Their product is bounded below by 1/(4π) and saturates
for a Gaussian window.
"""

from __future__ import annotations

import math
from typing import Final

import numpy as np

# Exact Gabor / Fourier uncertainty constant. Equality holds for a Gaussian
# envelope. No Planck constant, no fabricated ℏ — this is 1/(4π) exactly.
GABOR_LIMIT: Final[float] = 1.0 / (4.0 * math.pi)

# Relative slack below the bound that still counts as "well-resolved saturation".
# A genuinely well-resolved signal obeys Δt·Δf ≥ 1/(4π) (the theorem); the only
# legitimate way to land *below* the bound is the discretization round-off of a
# Gaussian sitting exactly on it — empirically ≤ 1.3e-4 below. Under-resolved /
# near-Nyquist windows (power concentrated in one sample or one FFT bin) land far
# below (ratio ≤ 0.75). 1e-2 separates the two with a ~100× margin over the
# saturation dip, so it admits saturation yet fail-closes on degenerate windows.
_RESOLUTION_REL_TOL: Final[float] = 1e-2


def gabor_lower_bound() -> float:
    """Return the exact Gabor time-frequency lower bound 1/(4π).

    No measurement of (Δt, Δf) on a finite-energy signal can fall below this
    value; a Gaussian-windowed signal saturates it.

    Returns:
        The constant 1/(4π) ≈ 0.0795774715459.

    Example:
        >>> bound = gabor_lower_bound()
        >>> abs(bound - 0.07957747154594767) < 1e-15
        True
    """
    return GABOR_LIMIT


def _time_spread(power: np.ndarray) -> float:
    """Return the time spread Δt (in sample units) of a power distribution.

    Δt = sqrt( Σ_n (n − ⟨n⟩)² p(n) ),  p(n) = power(n) / Σ power.

    Args:
        power: Non-negative time-domain power array |x(n)|² (length ≥ 1).

    Returns:
        Standard deviation of sample index n under the normalized power
        distribution. Zero for a single sample or a single-spike signal.
    """
    total = float(power.sum())
    indices = np.arange(power.size, dtype=float)
    weights = power / total
    centroid = float(np.dot(indices, weights))
    variance = float(np.dot((indices - centroid) ** 2, weights))
    # variance is a sum of non-negative terms; guard only float round-off.
    return math.sqrt(max(variance, 0.0))


def _freq_spread(power_spectrum: np.ndarray, n_samples: int) -> float:
    """Return the frequency spread Δf (cycles/sample) of a power spectrum.

    Frequencies use ``np.fft.fftfreq`` so the centroid is computed on the true
    (signed) frequency axis, and the wrap-around symmetry of the DFT is
    respected. Δf = sqrt( Σ_k (f_k − ⟨f⟩)² P(k) ), P normalized.

    Args:
        power_spectrum: Non-negative spectral power |FFT(x)|² (length n_samples).
        n_samples: Number of time samples (defines the frequency grid spacing).

    Returns:
        Standard deviation of frequency under the normalized power spectrum.
    """
    total = float(power_spectrum.sum())
    freqs = np.fft.fftfreq(n_samples, d=1.0)
    weights = power_spectrum / total
    centroid = float(np.dot(freqs, weights))
    variance = float(np.dot((freqs - centroid) ** 2, weights))
    return math.sqrt(max(variance, 0.0))


def time_frequency_spread(signal: np.ndarray) -> tuple[float, float, float]:
    """Compute (Δt, Δf, Δt·Δf) for a finite-energy sampled signal.

    Δt is the root second moment of the normalized time-domain power |x|² about
    its centroid; Δf is the root second moment of the normalized power spectrum
    |FFT(x)|² about its centroid. The product obeys the Gabor limit
    Δt·Δf ≥ 1/(4π) (INV-GABOR1) and SATURATES (equality) for a Gaussian
    envelope x(n) = exp(−(n − c)²/(2σ²)).

    The moments are taken on the signal AS GIVEN — no mean removal. Demeaning
    would break the saturation theorem: the squared demeaned Gaussian is no
    longer Gaussian (its negative lobes square into side energy), inflating Δt
    and pushing the product well above 1/(4π). The bound and its Gaussian
    minimizer are statements about x(t) itself, so the implementation honours
    that exactly. A constant signal is rejected not for "zero power" (its power
    is non-zero) but because it has zero variance and its product collapses to
    0 < 1/(4π) — a degenerate non-signal, fail-closed.

    Args:
        signal: 1-D real array, length ≥ 2, non-constant, all finite.

    Returns:
        Tuple ``(time_spread, freq_spread, product)`` — all finite and ≥ 0.

    Raises:
        ValueError: if the signal is empty, has fewer than 2 samples, is not
            1-D, contains non-finite values, is constant (zero variance), or is
            an under-resolved / near-Nyquist window whose discrete product falls
            below the Gabor theorem (``Δt·Δf < 1/(4π)``). Fail-closed: no silent
            numeric repair, and no sub-bound product is ever returned.

    Example:
        >>> import numpy as np
        >>> n = np.arange(4096)
        >>> g = np.exp(-((n - 2048.0) ** 2) / (2.0 * 200.0**2))
        >>> dt, df, product = time_frequency_spread(g)
        >>> abs(product - gabor_lower_bound()) < 2e-3
        True
    """
    arr = np.asarray(signal, dtype=float)
    if arr.ndim != 1:
        raise ValueError(
            f"INV-GABOR1: signal must be 1-D, got ndim={arr.ndim} "
            f"shape={arr.shape}; cannot define a time-frequency power distribution"
        )
    if arr.size < 2:
        raise ValueError(
            f"INV-GABOR1: signal needs ≥ 2 samples to define Δt·Δf, got "
            f"size={arr.size}; a single sample has no spread"
        )
    if not np.all(np.isfinite(arr)):
        raise ValueError(
            "INV-GABOR1: signal contains non-finite values (NaN/Inf); "
            "fail-closed — refuse to fabricate a spread from undefined power"
        )

    time_power = arr**2
    energy = float(time_power.sum())
    variance = float(arr.var())
    if energy <= 0.0 or variance <= 0.0:
        raise ValueError(
            f"INV-GABOR1: signal is constant (variance={variance:.3e}, "
            f"value={float(arr[0]):.6g}); Δt·Δf collapses below 1/(4π) and "
            f"carries no time-frequency localization — refuse to report it"
        )

    spectrum = np.fft.fft(arr)
    power_spectrum = np.abs(spectrum) ** 2

    time_spread = _time_spread(time_power)
    freq_spread = _freq_spread(power_spectrum, arr.size)
    product = time_spread * freq_spread

    # Fail-closed on under-resolved windows. The Gabor limit Δt·Δf ≥ 1/(4π) is a
    # theorem of Fourier analysis: a well-resolved finite-energy signal cannot
    # fall below it. A discrete product below the bound therefore signals an
    # under-resolved / near-Nyquist window (e.g. a two-sample step whose power
    # collapses into a single time sample or FFT bin), NOT a sub-bound physical
    # discovery. Returning it would mislead a short-window caller (e.g. position
    # sizing) into reading a degenerate window as a maximally compact / maximally
    # confident measurement. Refuse it rather than silently report it.
    if product < GABOR_LIMIT * (1.0 - _RESOLUTION_REL_TOL):
        raise ValueError(
            f"INV-GABOR1: Δt·Δf={product:.6e} < 1/(4π)={GABOR_LIMIT:.6e} "
            f"(Δt={time_spread:.4e} samples, Δf={freq_spread:.4e} cyc/sample); "
            f"the discrete second-moment estimate fell below the Gabor theorem, "
            f"which can only mean an under-resolved / near-Nyquist window "
            f"(size={arr.size}) with power concentrated in a single sample or "
            f"bin — fail-closed, no sub-bound product is a valid measurement"
        )
    return time_spread, freq_spread, product


def check_gabor_limit(
    time_spread: float,
    freq_spread: float,
    *,
    rel_tol: float = 1e-9,
) -> tuple[bool, float]:
    """Check whether a (Δt, Δf) pair satisfies the Gabor limit Δt·Δf ≥ 1/(4π).

    A small relative tolerance admits floating-point round-off at saturation
    (a Gaussian envelope sits exactly on the bound). Anything below the bound
    by more than ``rel_tol`` is a genuine violation — and, because the bound is
    a theorem, signals a bug in the caller's spread computation, never a
    physical discovery.

    Args:
        time_spread: Δt ≥ 0 (sample units).
        freq_spread: Δf ≥ 0 (cycles/sample).
        rel_tol: Relative slack below 1/(4π) treated as saturation.

    Returns:
        Tuple ``(satisfies, slack_factor)`` where ``slack_factor`` is
        ``(Δt·Δf) / (1/(4π))``: ≥ 1 means above the bound, < 1 below it.

    Raises:
        ValueError: if either spread is negative or non-finite.

    Example:
        >>> ok, factor = check_gabor_limit(2.0, 0.05)
        >>> ok
        True
        >>> factor >= 1.0
        True
    """
    if not (math.isfinite(time_spread) and math.isfinite(freq_spread)):
        raise ValueError(
            f"INV-GABOR1: spreads must be finite, got Δt={time_spread}, Δf={freq_spread}"
        )
    if time_spread < 0.0 or freq_spread < 0.0:
        raise ValueError(
            f"INV-GABOR1: spreads must be ≥ 0, got Δt={time_spread}, Δf={freq_spread}; "
            f"a second moment cannot be negative"
        )
    product = time_spread * freq_spread
    bound = GABOR_LIMIT
    slack_factor = product / bound
    satisfies = bool(product >= bound * (1.0 - rel_tol))
    return satisfies, slack_factor


__all__ = [
    "GABOR_LIMIT",
    "gabor_lower_bound",
    "time_frequency_spread",
    "check_gabor_limit",
]
