# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deterministic null-baseline descriptor fixtures.

This module is a *null generator*, not a forecaster. It produces
reproducible null / surrogate numeric series that a descriptor can be
compared against, so that an observed descriptor value can be read
relative to a declared, structureless baseline rather than in isolation.

Three generators are provided:

* :func:`make_gaussian_null` — seeded i.i.d. Gaussian noise (a finite,
  exchangeable series with no temporal structure);
* :func:`make_constant_null` — a degenerate constant series (zero
  variance, the trivial null);
* :func:`make_phase_shuffled_surrogate` — a phase-randomised surrogate
  of an input series that preserves its power spectrum (and hence its
  linear autocorrelation) while destroying any nonlinear / phase
  structure.

Every generator returns ``(array, metadata)`` where ``array`` is a
``float64`` :class:`numpy.ndarray` and ``metadata`` is an immutable
mapping that pins the method, the seed, the length, and an explicit
boundary disclaimer (``claim_boundary="descriptor_only_not_predictor"``,
``not_predictive_claim=True``). The series carry no directional or
financial meaning: the contract asserts nothing about future prices,
returns, or profitability, and is research-only descriptor
infrastructure.

Determinism
-----------
All randomness flows through :func:`numpy.random.default_rng` keyed on
an explicit integer seed. There is no module-level or process-global
random state, so two calls with the same arguments produce byte-identical
arrays. No non-finite value (NaN or infinity) is ever emitted: a request
that could only be satisfied with a non-finite series fails closed with a
:class:`ValueError`.

Worked example
--------------
>>> arr, meta = make_gaussian_null(n=4, seed=7)
>>> arr.shape
(4,)
>>> meta["method"], meta["seed"], meta["length"]
('gaussian_null', 7, 4)
>>> meta["claim_boundary"]
'descriptor_only_not_predictor'
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "CLAIM_BOUNDARY",
    "make_gaussian_null",
    "make_constant_null",
    "make_phase_shuffled_surrogate",
]

#: The single declared boundary string shared by every generator's metadata.
CLAIM_BOUNDARY: str = "descriptor_only_not_predictor"


def _validate_length(n: int) -> int:
    """Return ``n`` as a positive ``int`` or fail closed.

    A non-integer, boolean, or non-positive length is rejected rather than
    silently coerced, so a degenerate request is visible at the call site.
    """
    if isinstance(n, bool) or not isinstance(n, int):
        raise ValueError(f"length n must be a positive int, got {n!r}")
    if n <= 0:
        raise ValueError(f"length n must be > 0, got {n}")
    return n


def _validate_seed(seed: int) -> int:
    """Return ``seed`` as a non-negative ``int`` or fail closed.

    A boolean, non-integer, or negative seed is rejected; ``default_rng``
    would otherwise accept some of these and silently change the stream.
    """
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError(f"seed must be a non-negative int, got {seed!r}")
    if seed < 0:
        raise ValueError(f"seed must be >= 0, got {seed}")
    return seed


def _guard_finite(array: NDArray[np.float64], method: str) -> NDArray[np.float64]:
    """Fail closed if ``array`` holds any NaN or infinity.

    No generator should ever be able to emit a non-finite series; this is
    a defensive post-condition, not a silent filter.
    """
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{method} produced a non-finite value; refusing to emit")
    return array


def _base_metadata(method: str, seed: int | None, length: int) -> dict[str, Any]:
    """Build the disclaimer-bearing metadata common to every generator."""
    return {
        "method": method,
        "seed": seed,
        "length": length,
        "dtype": "float64",
        "claim_boundary": CLAIM_BOUNDARY,
        "not_predictive_claim": True,
        "not_financial_advice": True,
        "research_only": True,
    }


def make_gaussian_null(
    n: int,
    seed: int,
    *,
    loc: float = 0.0,
    scale: float = 1.0,
) -> tuple[NDArray[np.float64], Mapping[str, Any]]:
    """Return a seeded i.i.d. Gaussian null series and its metadata.

    Parameters
    ----------
    n:
        Length of the series; must be a positive ``int``.
    seed:
        Non-negative ``int`` seed routed through ``default_rng``.
    loc, scale:
        Finite Gaussian location and (non-negative) scale. A non-finite
        ``loc``/``scale`` or a negative ``scale`` fails closed.

    Returns
    -------
    tuple
        ``(array, metadata)`` with a length-``n`` ``float64`` array and an
        immutable mapping pinning the method, seed, length, and boundary
        disclaimer. The series has no temporal structure and makes no
        predictive or financial claim.
    """
    n = _validate_length(n)
    seed = _validate_seed(seed)
    if not np.isfinite(loc):
        raise ValueError(f"loc must be finite, got {loc!r}")
    if not np.isfinite(scale) or scale < 0.0:
        raise ValueError(f"scale must be finite and >= 0, got {scale!r}")

    rng = np.random.default_rng(seed)
    array = rng.normal(loc=loc, scale=scale, size=n).astype(np.float64, copy=False)
    _guard_finite(array, "make_gaussian_null")

    metadata = _base_metadata("gaussian_null", seed, n)
    metadata["loc"] = float(loc)
    metadata["scale"] = float(scale)
    return array, MappingProxyType(metadata)


def make_constant_null(
    n: int,
    *,
    value: float = 0.0,
) -> tuple[NDArray[np.float64], Mapping[str, Any]]:
    """Return a degenerate constant null series and its metadata.

    This is the trivial zero-variance null. It takes no seed because it
    carries no randomness; the ``seed`` field in its metadata is recorded
    as ``None`` to keep the metadata schema stable across generators.

    Parameters
    ----------
    n:
        Length of the series; must be a positive ``int``.
    value:
        The finite constant to repeat. A non-finite ``value`` fails closed.
    """
    n = _validate_length(n)
    if not np.isfinite(value):
        raise ValueError(f"value must be finite, got {value!r}")

    array = np.full(n, float(value), dtype=np.float64)
    _guard_finite(array, "make_constant_null")

    metadata = _base_metadata("constant_null", seed=None, length=n)
    metadata["value"] = float(value)
    return array, MappingProxyType(metadata)


def make_phase_shuffled_surrogate(
    series: Sequence[float],
    seed: int,
) -> tuple[NDArray[np.float64], Mapping[str, Any]]:
    """Return a phase-randomised surrogate of ``series`` and its metadata.

    The surrogate is built by FFT, replacing each non-DC/Nyquist phase
    with a seeded uniform random phase (in conjugate-symmetric pairs so
    the inverse transform is real), then inverse-transforming. It
    preserves the power spectrum — and hence the linear autocorrelation —
    of ``series`` while destroying nonlinear / phase structure. It is a
    structural null, not a forecast of ``series``.

    Parameters
    ----------
    series:
        Finite input sequence of length >= 1.
    seed:
        Non-negative ``int`` seed routed through ``default_rng``.

    Returns
    -------
    tuple
        ``(array, metadata)`` with a ``float64`` surrogate of the same
        length as ``series`` and an immutable boundary-bearing mapping.
    """
    seed = _validate_seed(seed)
    data = np.asarray(series, dtype=np.float64)
    if data.ndim != 1:
        raise ValueError(f"series must be one-dimensional, got ndim={data.ndim}")
    n = int(data.shape[0])
    if n <= 0:
        raise ValueError(f"series must be non-empty, got length {n}")
    if not np.all(np.isfinite(data)):
        raise ValueError("series must be finite; refusing to surrogate non-finite input")

    rng = np.random.default_rng(seed)
    spectrum = np.fft.rfft(data)
    magnitudes = np.abs(spectrum)
    # Indices 1..(end before Nyquist) carry randomisable phases. The DC term
    # (index 0) and, for even n, the Nyquist term must stay real-valued so
    # the inverse transform is real.
    n_freq = magnitudes.shape[0]
    random_phases = rng.uniform(0.0, 2.0 * np.pi, size=n_freq)
    random_phases[0] = 0.0
    if n % 2 == 0:
        random_phases[-1] = 0.0
    surrogate_spectrum = magnitudes * np.exp(1j * random_phases)
    array = np.fft.irfft(surrogate_spectrum, n=n).astype(np.float64, copy=False)
    _guard_finite(array, "make_phase_shuffled_surrogate")

    metadata = _base_metadata("phase_shuffled_surrogate", seed, n)
    metadata["preserves_power_spectrum"] = True
    return array, MappingProxyType(metadata)
