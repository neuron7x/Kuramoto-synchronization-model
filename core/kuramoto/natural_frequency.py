# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Natural-frequency ω_i estimation (protocol M1.4).

Given a :class:`~core.kuramoto.contracts.PhaseMatrix` we compute the
per-oscillator natural frequency as a robust location estimate of the
instantaneous frequency ``θ̇_i(t) = d/dt unwrap(θ_i(t))``.

The module exposes three estimators:

- ``"median"``  — default, breakdown point 50%, dimension-free.
- ``"trimmed"`` — trimmed mean with configurable tail fraction.
- ``"mean"``    — simple mean (for unit tests / reference only).

The returned ``(N,)`` array is ready to drop into
:class:`NetworkState.natural_frequencies`.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from scipy import stats

from .contracts import PhaseMatrix

__all__ = [
    "NaturalFrequencyMethod",
    "estimate_natural_frequencies",
    "estimate_natural_frequencies_from_theta",
]

NaturalFrequencyMethod = Literal["median", "trimmed", "mean"]


def _instantaneous_frequencies(theta: np.ndarray, dt: float) -> np.ndarray:
    """Finite-difference instantaneous frequency of unwrapped phases.

    Uses ``np.gradient`` along the time axis, which internally applies
    central differences in the interior and one-sided differences at
    the boundaries — more accurate than plain ``np.diff``.
    """
    unwrapped = np.unwrap(theta, axis=0)
    return np.asarray(np.gradient(unwrapped, dt, axis=0), dtype=np.float64)


def estimate_natural_frequencies_from_theta(
    theta: np.ndarray,
    dt: float,
    *,
    method: NaturalFrequencyMethod = "median",
    trim: float = 0.1,
) -> np.ndarray:
    """Robust natural-frequency estimator operating on a raw phase array.

    Parameters
    ----------
    theta
        Phase matrix of shape ``(T, N)``, wrapped or unwrapped.
    dt
        Sampling interval in the same units you want ω_i returned in
        (e.g. seconds → ω in rad/s; days → rad/day).
    method
        Location estimator. ``"median"`` is the default and the only
        estimator that tolerates up to 50 % outliers (e.g. phase-slip
        artefacts); ``"trimmed"`` uses ``scipy.stats.trim_mean`` with
        a configurable tail fraction; ``"mean"`` is provided purely
        for unit-test reference.
    trim
        Tail fraction for ``"trimmed"``. Must lie in ``[0, 0.5)``.

    Returns
    -------
    omega : np.ndarray
        ``(N,)`` float64 array of natural frequencies.
    """
    if dt <= 0:
        raise ValueError(f"dt must be > 0; got {dt}")
    if theta.ndim != 2:
        raise ValueError(f"theta must be 2-D (T, N); got {theta.ndim}-D")
    if theta.shape[0] < 3:
        # np.gradient needs ≥2 samples; require ≥3 for a meaningful frequency
        # (raise a clear contract error instead of an opaque numpy message).
        raise ValueError(f"theta must have ≥3 timesteps; got T={theta.shape[0]}")
    if not bool(np.all(np.isfinite(theta))):
        # Fail-closed: a non-finite phase is a contract violation, not an
        # outlier. `np.median` is NOT nan-aware, so a single NaN would silently
        # poison the whole-column estimate — the "tolerates 50% outliers" claim
        # holds only for FINITE phase-slips, not NaN/Inf.
        raise ValueError("theta must be finite (non-finite phase is not an outlier)")
    omega_inst = _instantaneous_frequencies(theta, dt)

    if method == "median":
        return np.asarray(np.median(omega_inst, axis=0), dtype=np.float64)
    if method == "mean":
        return np.asarray(np.mean(omega_inst, axis=0), dtype=np.float64)
    if method == "trimmed":
        if not 0.0 <= trim < 0.5:
            raise ValueError(f"trim must be in [0, 0.5); got {trim}")
        return np.asarray(
            stats.trim_mean(omega_inst, proportiontocut=trim, axis=0),
            dtype=np.float64,
        )
    raise ValueError(f"Unknown method {method!r}")


def estimate_natural_frequencies(
    phases: PhaseMatrix,
    *,
    method: NaturalFrequencyMethod = "median",
    trim: float = 0.1,
    dt: float | None = None,
) -> np.ndarray:
    """Estimate ω_i from a contract-compliant :class:`PhaseMatrix`.

    The sampling interval is inferred from ``phases.timestamps`` unless
    it is passed explicitly via ``dt`` — the latter is useful for
    non-numeric timestamp dtypes (e.g. ``datetime64``) where the user
    supplies the appropriate unit conversion.
    """
    if dt is None:
        ts = np.asarray(phases.timestamps, dtype=np.float64)
        if ts.shape[0] < 2:
            raise ValueError("Need at least two timestamps to infer dt")
        dt = float(ts[1] - ts[0])
    return estimate_natural_frequencies_from_theta(phases.theta, dt=dt, method=method, trim=trim)
