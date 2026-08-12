# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Asymmetric coupling matrix + intrinsic frequency estimation.

The Sakaguchi–Kuramoto model with directed coupling and per-pair phase
lag :math:`\\alpha_{ij}` is

.. math::

    \\dot\\theta_i = \\omega_i + \\sum_{j \\ne i}
                    K_{ij} \\sin(\\theta_j - \\theta_i - \\alpha_{ij})

**Canonical orientation invariant** (single source of truth — every
caller must respect this):

::

    E[i, j]  =  exposure of *i* to *j*  =  i has lent to j
                (lending channel  i → j;
                 i is at risk if j defaults)

    K[i, j]  =  stress felt by i from j
                ∝ E[i, j] (i's claim on j; if j fails, i is hurt
                           proportionally to its loan to j)

So ``K = f(E)`` *without* a transpose: the row index is the bank
that *feels* the stress; the column index is the bank whose
default would cause it. Every test in this module's regression
suite asserts the canonical orientation on a 2×2 directed example
to catch any future transpose bug.

v1 of this module assumed symmetric :math:`K`; v2 builds it
directly from the asymmetric exposure matrix without symmetrising.
Per-pair phase lag is supported but defaults to the symmetric
Kuramoto limit (:math:`\\alpha_{ij} = 0`) because joint estimation
of α from interbank data is a separate inverse problem (delegated
to ``core.kuramoto.frustration``).

Three pure functions:

* :func:`coupling_from_exposures` — build :math:`K` from a directed
  exposure matrix with optional row-stochastic or capital-ratio
  normalisation.
* :func:`omega_from_volatility` — estimate :math:`\\omega_i` from the
  rolling-volatility cycle of each bank's balance-sheet returns.
* :func:`sakaguchi_alpha_zero` — convenience zero matrix matching a
  given coupling shape.

Pure-function API. No I/O.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "coupling_from_exposures",
    "omega_from_volatility",
    "sakaguchi_alpha_zero",
]


Normalisation = Literal["row_stochastic", "capital_weighted", "raw"]


def coupling_from_exposures(
    exposures: NDArray[np.float64],
    *,
    normalisation: Normalisation = "row_stochastic",
    capital: NDArray[np.float64] | None = None,
    floor: float = 0.0,
) -> NDArray[np.float64]:
    """Build an asymmetric coupling matrix :math:`K` from exposures.

    Parameters
    ----------
    exposures
        Real, non-negative matrix shape ``(N, N)`` where
        ``exposures[i, j]`` is *i*'s exposure to *j* (lending volume).
    normalisation
        ``"row_stochastic"`` (default) divides each row by its row
        sum: ``K[i, j] = E[i, j] / Σ_j E[i, j]``. Per the canonical
        orientation invariant declared in the module docstring,
        ``K[i, j]`` then expresses the **share of bank i's total
        exposure that is concentrated in counterparty j** — i.e. the
        fraction of i's claims at risk if j defaults. Rows whose sum
        is zero stay zero (no edges originate from that bank).
        ``"capital_weighted"`` divides each row by the lender's
        capital, so the coupling expresses exposure-to-capital ratio
        (Battiston et al. 2012, *Sci. Rep.* 2: 541). ``"raw"`` returns
        the exposure matrix unchanged (only the diagonal cleared).
    capital
        Length-``N`` capital vector, required when
        ``normalisation == "capital_weighted"``. Must be strictly
        positive (no zero capital).
    floor
        Inclusive lower bound on the *kept* set: entries strictly
        below ``floor`` after normalisation are clamped to zero;
        entries equal to ``floor`` are kept. Defaults to ``0.0`` —
        ``floor > 0`` is useful when the empirical matrix carries
        rounding noise.

    Returns
    -------
    Real matrix shape ``(N, N)``, zero diagonal, asymmetric in
    general. Non-negative everywhere.
    """
    e = np.asarray(exposures, dtype=np.float64)
    if e.ndim != 2 or e.shape[0] != e.shape[1]:
        raise ValueError(f"exposures must be square 2-D, got shape={e.shape}")
    if not np.isfinite(e).all():
        raise ValueError("exposures must be finite (no NaN/Inf)")
    if np.any(e < 0):
        raise ValueError("exposures must be non-negative")
    if floor < 0:
        raise ValueError(f"floor must be >= 0, got {floor}")
    n = e.shape[0]
    k_matrix = np.array(e, dtype=np.float64, copy=True)
    np.fill_diagonal(k_matrix, 0.0)
    if normalisation == "row_stochastic":
        row_sums = k_matrix.sum(axis=1, keepdims=True)
        # bounds: row_sums == 0 stays at 0 (no edges); avoid div-by-zero noise.
        safe = np.where(row_sums > 0, row_sums, 1.0)
        k_matrix = k_matrix / safe
    elif normalisation == "capital_weighted":
        if capital is None:
            raise ValueError("normalisation='capital_weighted' requires capital vector")
        c = np.asarray(capital, dtype=np.float64)
        if c.shape != (n,):
            raise ValueError(f"capital shape {c.shape} != (N,)=({n},)")
        if not np.all(c > 0) or not np.isfinite(c).all():
            raise ValueError("capital must be strictly positive and finite")
        k_matrix = k_matrix / c[:, None]
    elif normalisation == "raw":
        pass
    else:  # pragma: no cover - typing should prevent this path
        raise ValueError(f"unknown normalisation {normalisation!r}")
    if floor > 0:
        # Inclusive lower bound on the *kept* set: entries strictly
        # below ``floor`` are clamped to zero; entries equal to floor
        # are kept (they are by definition at the documented noise
        # threshold, not below it). Matches the docstring's
        # "Inclusive lower bound" wording.
        k_matrix = np.where(k_matrix >= floor, k_matrix, 0.0)
    np.fill_diagonal(k_matrix, 0.0)
    return k_matrix


def omega_from_volatility(
    log_returns: NDArray[np.float64],
    *,
    fs: float = 1.0,
) -> NDArray[np.float64]:
    """Estimate per-bank intrinsic frequency :math:`\\omega_i` from balance-sheet vol.

    Parameters
    ----------
    log_returns
        Shape ``(T, N_banks)``, finite log-returns of each bank's
        balance-sheet (or equity) value. Canonical (T, N) layout.
    fs
        Sampling rate in samples per day. Defaults to ``1.0`` for
        end-of-day observations. Output ``ω_i`` is in radians per day.

    Returns
    -------
    Real array shape ``(N_banks,)`` of intrinsic frequencies.

    Notes
    -----
    The intrinsic frequency is identified with the dominant
    spectral-power frequency of the bank's volatility envelope —
    proxied here by ``2π · σ_i · fs`` where ``σ_i`` is the sample
    standard deviation of the bank's returns. This is a *first-order*
    estimator: a higher-fidelity option (Lomb-Scargle on
    rolling-vol time series) is delegated to
    ``core.kuramoto.natural_frequency``.
    """
    r = np.asarray(log_returns, dtype=np.float64)
    if r.ndim != 2:
        raise ValueError(f"log_returns must be 2-D (T, N), got shape={r.shape}")
    if r.shape[0] < 2:
        raise ValueError(
            f"log_returns must have at least 2 time samples to compute "
            f"sample std (ddof=1), got T={r.shape[0]}"
        )
    if not np.isfinite(r).all():
        raise ValueError("log_returns must be finite (no NaN/Inf)")
    if fs <= 0:
        raise ValueError(f"fs must be > 0, got {fs}")
    sigma = r.std(axis=0, ddof=1)
    omega = 2.0 * np.pi * sigma * fs
    out: NDArray[np.float64] = np.asarray(omega, dtype=np.float64)
    return out


def sakaguchi_alpha_zero(n_nodes: int) -> NDArray[np.float64]:
    """Zero phase-lag matrix matching a coupling of size ``n_nodes``.

    The standard Kuramoto limit corresponds to :math:`\\alpha_{ij} = 0`.
    Joint estimation of a non-zero α-matrix from interbank-rate phases
    is delegated to :class:`core.kuramoto.frustration.FrustrationEstimator`.
    """
    if n_nodes < 1:
        raise ValueError(f"n_nodes must be >= 1, got {n_nodes}")
    return np.zeros((n_nodes, n_nodes), dtype=np.float64)
