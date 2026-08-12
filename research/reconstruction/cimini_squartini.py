# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Cimini-Squartini fitness reconstruction (Squartini-Garlaschelli MLE).

Operational contract — see Protocol X-10R, "MATHEMATICAL CONTRACT":

  p_ij = z · x_i · y_j / (1 + z · x_i · y_j)   for i ≠ j;  p_ii := 0

Hidden out-fitness x_i ∝ s_i^out, in-fitness y_j ∝ s_j^in. The
fitness-only model collapses the N-dim nonlinear MLE to a single
1-D root in z. This module returns the calibrated z + normalised
fitness vectors so downstream weighted_allocation + recovery_audit
can sample / verify.

TARGET OBJECT (FIX B3, 2026-05-09)
==================================
The reconstruction operates over **whatever node ontology the
caller supplies via (s_out, s_in)**. The pipeline cannot, and does
not, infer node ontology from the marginals — it can only honour
what is fed in.

Specifically, when the inputs are BIS Locational Banking Statistics
country-aggregate marginals, the *target object* of this
reconstruction is the **latent country-aggregate exposure network**
consistent with those marginals and with the Cimini-Squartini
fitness prior. **It is NOT a bank-level interbank network.** BIS
LBS marginals are residence-based, country-aggregate, and include
intragroup positions; lifting from country aggregates to bank-level
inference is a separate two-step inverse problem that requires a
country-to-bank allocator with its own prior and own validation
(epic X-10R-1, deferred to PR #599+).

For PR #635 the reconstruction therefore operates on:

  * Synthetic substrates at N=200 (positive controls, ground-truth
    recovery — Gate 5 in synthetic mode).
  * Real BIS LBS country-aggregate marginals (domain-of-validity
    check only — see `recovery_audit.check_domain_of_validity`).
    Recovery in the literal sense is undefined here because the
    bank-level truth is unobserved; the strongest available gate
    is whether real inputs fall inside the regime where synthetic
    recovery has been demonstrated.

Real-data interpretation contract: any precursor signal recovered
on real BIS through this pipeline binds to the latent country-
aggregate network class, NOT to bank-level structure. Any human-
facing claim text MUST carry the qualifier
``via_max_entropy_reconstruction_at_country_aggregate``.

Citations (reviewer traceability only — gates are operational):
  * Cimini, Squartini, Garlaschelli, Gabrielli (2015), "Estimating
    topological properties of weighted networks from limited
    information."
  * Squartini & Garlaschelli (2011), "Analytical maximum-likelihood
    method to detect patterns in real networks."
  * Bank for International Settlements (2019), "Reporting Guidelines
    for the BIS International Banking Statistics" — for the LBS
    residence-based / aggregate / intragroup-inclusive contract
    that the target-object reframing rests on.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_TOL: float = 1e-10
_MAX_BRENTQ_ITER: int = 200


@dataclass(frozen=True)
class HiddenFitness:
    x: np.ndarray  # out-fitness, shape (N,)
    y: np.ndarray  # in-fitness, shape (N,)
    z: float  # global density parameter
    log_likelihood: float
    converged: bool


def p_link(x: np.ndarray, y: np.ndarray, z: float) -> np.ndarray:
    """Per-edge link probability p_ij = z·x_i·y_j / (1 + z·x_i·y_j).

    Diagonal forced to zero (no self-loops).
    """
    if x.ndim != 1 or y.ndim != 1 or x.shape[0] != y.shape[0]:
        raise ValueError(
            f"x and y must be matching 1-D vectors; got x.shape={x.shape}, y.shape={y.shape}"
        )
    if not np.isfinite(z) or z < 0:
        raise ValueError(f"z must be non-negative finite; got z={z}")
    if np.any(x < 0) or np.any(y < 0):
        raise ValueError("x and y must be non-negative")
    outer = np.outer(x, y)
    p: np.ndarray = (z * outer / (1.0 + z * outer)).astype(np.float64)
    np.fill_diagonal(p, 0.0)
    return p


def _expected_edge_count(x: np.ndarray, y: np.ndarray, z: float) -> float:
    p = p_link(x, y, z)
    return float(p.sum())


def _normalise_fitness(s: np.ndarray) -> np.ndarray:
    """Strength-proportional fitness, unit-mean (stable across scales)."""
    arr = np.asarray(s, dtype=np.float64)
    mean = arr.mean()
    if mean <= 0 or not np.isfinite(mean):
        raise ValueError(f"fitness normalisation requires positive finite mean; got mean={mean}")
    out: np.ndarray = (arr / mean).astype(np.float64)
    return out


def _solve_z(x: np.ndarray, y: np.ndarray, target_density: float) -> tuple[float, bool]:
    """Solve for z so that E[#edges] / N(N-1) == target_density.

    Uses ``scipy.optimize.brentq`` with explicit bracket. Falls back to
    a deterministic bisection if scipy is unavailable.
    """
    n = x.shape[0]
    target_edges = target_density * n * (n - 1)

    def residual(z: float) -> float:
        return float(_expected_edge_count(x, y, z) - target_edges)

    # Bracket: z_lo where residual << 0, z_hi where residual >> 0.
    z_lo = 1e-12
    z_hi = 1.0
    while residual(z_hi) < 0 and z_hi < 1e12:
        z_hi *= 10.0
    if residual(z_hi) < 0:
        return float(z_hi), False

    try:
        from scipy.optimize import brentq

        z = float(brentq(residual, z_lo, z_hi, xtol=_TOL, maxiter=_MAX_BRENTQ_ITER))
        return z, True
    except ImportError:
        # Deterministic bisection fallback.
        for _ in range(_MAX_BRENTQ_ITER):
            mid = 0.5 * (z_lo + z_hi)
            r = residual(mid)
            if abs(r) < _TOL:
                return float(mid), True
            if r < 0:
                z_lo = mid
            else:
                z_hi = mid
        return float(0.5 * (z_lo + z_hi)), False


def _log_likelihood(p: np.ndarray) -> float:
    """Log-likelihood of the Bernoulli graph model under p_ij."""
    eps = 1e-12
    safe = np.clip(p, eps, 1.0 - eps)
    log_p = np.log(safe)
    log_1mp = np.log1p(-safe)
    # Expected log-likelihood under E[a_ij] = p_ij gives:
    #   p · log p + (1-p) · log (1-p)
    ll = (safe * log_p + (1.0 - safe) * log_1mp).sum()
    np.fill_diagonal(p, 0.0)
    return float(ll)


def fit_cimini_squartini(
    s_out: np.ndarray,
    s_in: np.ndarray,
    *,
    target_density: float | None = None,
) -> HiddenFitness:
    """Fit the Cimini-Squartini fitness-only model to marginal strengths.

    Returns ``HiddenFitness`` with normalised x, y and calibrated z.
    """
    s_out_arr = np.asarray(s_out, dtype=np.float64)
    s_in_arr = np.asarray(s_in, dtype=np.float64)
    if s_out_arr.shape != s_in_arr.shape or s_out_arr.ndim != 1:
        raise ValueError(
            f"s_out and s_in must be matching 1-D vectors; got "
            f"s_out.shape={s_out_arr.shape}, s_in.shape={s_in_arr.shape}"
        )
    if not np.all(np.isfinite(s_out_arr)) or not np.all(np.isfinite(s_in_arr)):
        raise ValueError("s_out / s_in must be finite (no NaN/Inf)")
    if np.any(s_out_arr < 0) or np.any(s_in_arr < 0):
        raise ValueError("s_out / s_in must be non-negative")
    n = s_out_arr.shape[0]
    if n < 2:
        raise ValueError(f"need N >= 2; got N={n}")
    target = 0.05 if target_density is None else float(target_density)
    if not (0.0 < target < 1.0):
        raise ValueError(f"target_density out of (0, 1); got {target}")
    x = _normalise_fitness(s_out_arr)
    y = _normalise_fitness(s_in_arr)
    z, converged = _solve_z(x, y, target)
    p = p_link(x, y, z)
    ll = _log_likelihood(p)
    return HiddenFitness(
        x=x,
        y=y,
        z=float(z),
        log_likelihood=ll,
        converged=bool(converged),
    )
