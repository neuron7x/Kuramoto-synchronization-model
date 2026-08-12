# SPDX-License-Identifier: MIT
"""Maximal Lyapunov Exponent (MLE) for time-series chaos detection.

The MLE measures the average exponential rate of divergence of
infinitesimally close trajectories in phase space:

    λ_max = lim_{t→∞} (1/t) · ln(|δx(t)| / |δx(0)|)

For a market-state trajectory (e.g. Kuramoto R(t)):
- λ_max > 0  →  chaotic / unpredictable regime (gradient alive but turbulent)
- λ_max ≈ 0  →  marginal / edge-of-chaos (critical transition zone)
- λ_max < 0  →  stable / predictable regime (gradient converging)

This module implements the Rosenstein (1993) algorithm for MLE estimation
from a scalar time series, which avoids computing tangent vectors and
works directly on delay-embedded phase-space reconstructions.

Algorithm:
1. Delay-embed the scalar series: x_i → (x_i, x_{i+τ}, ..., x_{i+(m-1)τ})
2. For each point, find its nearest neighbor (excluding temporal neighbors)
3. Track the divergence of these neighbor pairs over time
4. λ_max = mean slope of ln(divergence) vs time

Connection to GeoSync:
- Feed R(t) from Kuramoto → MLE tells you if synchronization is stable
- Feed portfolio returns → MLE tells you if the return process is chaotic
- MLE → Cryptobiosis: extreme positive MLE could trigger DORMANT
- MLE → Kelly: negative MLE = higher conviction → larger Kelly fraction

References:
    Rosenstein, Collins & De Luca (1993). "A practical method for
    calculating largest Lyapunov exponents from small data sets."
    Physica D, 65(1-2), 117-134.

    Wolf, Swift, Swinney & Vastano (1985). "Determining Lyapunov
    exponents from a time series." Physica D, 16(3), 285-317.

Invariants:
    INV-LE1: ``maximal_lyapunov_exponent`` returns a finite real for every
        *non-degenerate* bounded finite input, and FAILS CLOSED (raises
        ``ValueError``) on a degenerate input for which the Rosenstein
        divergence rate is mathematically undefined — a constant /
        zero-variance / all-zeros / two-value-collapsed series (no
        measurable neighbor divergence, Rosenstein 1993 §2.2) or an input
        carrying NaN/±Inf. It NEVER returns NaN/±Inf and NEVER masks a
        degenerate input as a spurious ``λ=0`` "stable regime".
    INV-LE2: MLE(noise) ≈ 0; MLE(stable oscillator) < 0; MLE(logistic chaos) > 0
    INV-LE3: the log-divergence linear fit must reach R² ≥ R2_MIN, otherwise
             the divergence curve is not in a clean Rosenstein scaling region
             and the slope is NOT a trustworthy λ — fail closed to the
             "no reliable estimate" sentinel (0.0), never a silent slope.
"""

from __future__ import annotations

import logging
import math
from typing import MutableMapping, Optional

import numpy as np
from numpy.typing import NDArray
from scipy.spatial import cKDTree

_LOGGER = logging.getLogger("geosync.physics.lyapunov")

# INV-LE3: minimum coefficient of determination R² for the least-squares fit
# of ln(divergence) vs time to be accepted as a Rosenstein scaling region.
#
# Basis. Rosenstein, Collins & De Luca (1993, Physica D 65:117) state the
# largest Lyapunov exponent is the slope of the "most linear region" of the
# average log-divergence curve ⟨ln d_j⟩ vs j·Δt; the method is only valid where
# that curve is genuinely linear. A noisy or curved window yields a slope with
# no dynamical meaning. R² = 1 − SS_res/SS_tot is the standard, unit-free
# goodness-of-linear-fit measure on exactly those (t, ln d) points. We require
# R² ≥ 0.80, i.e. the linear model must explain ≥ 80% of the variance of the
# log-divergence curve before its slope is reported as λ. 0.80 is the common
# "strong linear relationship" threshold used as the acceptance floor for
# scaling-region fits in the nonlinear-time-series literature (and matches the
# repo's own DRO regression floor R2_MIN = 0.90 family of fit gates; we use the
# slightly looser 0.80 here because the Rosenstein curve is an ensemble average
# over finitely many neighbor pairs and carries irreducible sampling noise even
# in clean chaos). Below the floor the estimate is flagged non-scaling and the
# function fails closed to 0.0 (the module's existing "no reliable estimate"
# sentinel, identical to the short-series / degenerate-fit paths), so a
# meaningless slope can never silently become a chaos/stability verdict.
R2_MIN: float = 0.80

# DS-16 (INV-LE1, availability/fail-closed): hard upper bound on the input
# series length for ``maximal_lyapunov_exponent``. The Rosenstein divergence
# tracker is a pure-Python O(N·S) double loop (S = ``max_divergence_steps``,
# default N//4), i.e. worst-case ≈ O(N²/4) scalar distance evaluations. An
# unbounded N is an availability/DoS vector: a 100k-sample series runs
# ≈1.9e9 inner evaluations (~3–4 h wall) — the length guards only caught
# degeneracy/shortness/non-finiteness, never length. We refuse fail-closed
# above this cap rather than silently changing the algorithm.
#
# Budget derivation. With the default S = N//4 the worst-case inner-loop work
# is n_candidates·S ≈ (¾N)·(N/4) ≈ 0.19·N². At the cap 20000 that is
# ≈7.5e7 distance evaluations — a bounded ceiling (order a minute), ~25× under
# the ungated 100k series' ≈1.9e9. Realistic GeoSync inputs (Kuramoto R(t),
# portfolio returns; the module's own tests use 400–2000 samples) sit far
# below 20000, so no legitimate series is refused. Callers who knowingly
# accept the O(N²) cost can raise the cap via the ``max_series_length`` param.
_MAX_SERIES_LENGTH: int = 20_000


def delay_embed(
    x: NDArray[np.float64],
    dim: int = 3,
    tau: int = 1,
) -> NDArray[np.float64]:
    """Delay-embed a scalar time series into a phase-space trajectory.

    Parameters
    ----------
    x : (T,) array
        Scalar time series.
    dim : int
        Embedding dimension (default 3).
    tau : int
        Delay in samples (default 1).

    Returns
    -------
    (T - (dim-1)*tau, dim) array
        Delay-embedded trajectory.
    """
    x = np.asarray(x, dtype=np.float64).ravel()
    n = x.size - (dim - 1) * tau
    if n <= 0:
        raise ValueError(
            f"Series too short ({x.size}) for dim={dim}, tau={tau}. "
            f"Need at least {(dim - 1) * tau + 1} samples."
        )
    # INV-HPC2: build the embedding matrix without overflow
    indices = np.arange(n)[:, None] + np.arange(dim)[None, :] * tau
    result: NDArray[np.float64] = x[indices]
    return result


def maximal_lyapunov_exponent(
    x: NDArray[np.float64],
    dim: int = 3,
    tau: int = 1,
    max_divergence_steps: Optional[int] = None,
    min_temporal_separation: Optional[int] = None,
    dt: float = 1.0,
    diagnostics: Optional[MutableMapping[str, float]] = None,
    max_series_length: Optional[int] = None,
) -> float:
    """Estimate the maximal Lyapunov exponent from a scalar time series.

    Uses the Rosenstein (1993) nearest-neighbor divergence algorithm.

    Parameters
    ----------
    x : (T,) array
        Scalar time series (e.g. Kuramoto R(t), portfolio returns).
    dim : int
        Embedding dimension (default 3). Rule of thumb: 2·ceil(correlation_dim)+1.
    tau : int
        Embedding delay (default 1). Use first minimum of mutual information.
    max_divergence_steps : int, optional
        Maximum number of steps to track divergence (default T//4).
    min_temporal_separation : int, optional
        Minimum index separation for nearest neighbors (default dim*tau).
        Prevents self-matching in the embedding.
    dt : float
        Time step between samples (default 1.0). Scales the exponent
        to physical units: λ has units of 1/dt.
    diagnostics : MutableMapping[str, float], optional
        If provided, populated with observability fields for the fit:
        ``"r_squared"`` (R² of the log-divergence linear fit; NaN when no
        fit was performed), ``"slope"`` (raw least-squares slope before the
        INV-LE3 gate; NaN when no fit), ``"n_fit"`` (number of points in the
        fit window), and ``"scaling_ok"`` (1.0 if R² ≥ R2_MIN and the slope
        was accepted as λ, else 0.0). Does not change the float return.
    max_series_length : int, optional
        DS-16 availability guard. Maximum accepted input length ``T``.
        Defaults to the module constant ``_MAX_SERIES_LENGTH`` (20000). The
        Rosenstein divergence loop is O(T²/4) pure Python, so an unbounded
        ``T`` is a DoS vector (a 100k series hangs ~3-4 h). A series longer
        than this cap raises ``ValueError`` fail-closed BEFORE any O(T²) work.
        The default is unchanged for every in-range input; pass a larger
        value only if you knowingly accept the quadratic cost.

    Returns
    -------
    float
        Estimated λ_max. Positive = chaos, negative = stability, ≈0 = marginal.
        Returns 0.0 ("no reliable estimate" sentinel) for series too short to
        estimate, degenerate fits, OR — INV-LE3 — when the log-divergence fit
        fails the R² ≥ R2_MIN scaling-region gate (curve not linear → slope is
        not a trustworthy λ; fail closed, never a silent slope).

    Raises
    ------
    ValueError
        INV-LE1, fail-closed. Raised when the series is too short for the
        requested embedding, when the input carries NaN/±Inf, or when the
        input is degenerate (constant / zero-variance / all-zeros /
        two-value-collapsed) so that every nearest-neighbor pair distance is
        zero and the Rosenstein divergence rate (1993 §2.2) is undefined.
        The estimator never returns NaN/±Inf and never reports a spurious
        ``λ=0`` for a series that has no divergence to measure.
        DS-16: also raised (fail-closed, before any O(T²) work) when the input
        length exceeds ``max_series_length`` — the O(T²) divergence loop is
        refused rather than allowed to hang as an availability/DoS vector.
    """

    def _record(r_squared: float, slope: float, n_fit: int, scaling_ok: bool) -> None:
        if diagnostics is not None:
            diagnostics["r_squared"] = r_squared
            diagnostics["slope"] = slope
            diagnostics["n_fit"] = float(n_fit)
            diagnostics["scaling_ok"] = 1.0 if scaling_ok else 0.0

    _record(math.nan, math.nan, 0, False)
    x = np.asarray(x, dtype=np.float64).ravel()

    # INV-LE1 (fail-closed): a non-finite input has no defined embedding and
    # would propagate NaN through every distance/log. Reject at the boundary
    # rather than emit a NaN MLE that silently disables downstream risk gating.
    if not np.all(np.isfinite(x)):
        raise ValueError(
            "INV-LE1 violated: input series contains NaN/±Inf; the Rosenstein "
            "MLE is undefined for a non-finite trajectory (likely cause: "
            "NaN/Inf embedded in the source series). Fail closed — clean the "
            "series before estimating λ_max."
        )

    # DS-16 / INV-LE1 (fail-closed, availability): refuse an over-long series
    # BEFORE the O(T²) pure-Python divergence loop runs. The nearest-neighbor
    # divergence tracker is ≈O(T²/4); an unbounded T is a DoS vector (a 100k
    # series hangs ~3-4 h). The prior guards caught degeneracy/shortness/
    # non-finiteness but never length. Fail closed with a clear message rather
    # than silently downsampling or changing the algorithm. This branch fires
    # in << 1 s (no divergence work is done) for any over-cap input.
    cap = _MAX_SERIES_LENGTH if max_series_length is None else int(max_series_length)
    if cap <= 0:
        raise ValueError(f"INV-LE1 violated: max_series_length must be positive, got {cap}.")
    if x.size > cap:
        raise ValueError(
            f"INV-LE: series length {x.size} exceeds max {cap} — refuse to "
            "avoid O(n^2) DoS in the Rosenstein divergence loop. Downsample the "
            "series, pass a smaller max_divergence_steps, or raise "
            "max_series_length only if you knowingly accept the O(n^2) cost."
        )

    # INV-LE1 (fail-closed): a series too short to delay-embed (e.g. a two-point
    # degenerate input) admits no divergence curve; raise rather than return a
    # placeholder 0.0 that reads as a "stable regime".
    min_samples = (dim - 1) * tau + 1
    if x.size < max(10, min_samples):
        raise ValueError(
            f"INV-LE1 violated: series length {x.size} is too short to estimate "
            f"the Rosenstein MLE for dim={dim}, tau={tau} (need at least "
            f"{max(10, min_samples)} samples; likely cause: two-point/degenerate "
            "input). Fail closed."
        )

    # Delay embedding
    embedded = delay_embed(x, dim=dim, tau=tau)
    n_points = embedded.shape[0]

    if n_points < 20:
        raise ValueError(
            f"INV-LE1 violated: only {n_points} delay-embedded points for "
            f"dim={dim}, tau={tau} — too few for a non-degenerate "
            "nearest-neighbor divergence fit (need ≥20). Fail closed."
        )

    if max_divergence_steps is None:
        # bounds: Rosenstein algorithm parameter, not a physics quantity —
        # ≥10 divergence steps are required for a meaningful log-divergence
        # slope fit. Non-physics algorithmic minimum (no INV-* applies).
        max_divergence_steps = max(10, n_points // 4)
    max_divergence_steps = min(max_divergence_steps, n_points - 1)

    if min_temporal_separation is None:
        min_temporal_separation = dim * tau
    # bounds: Theiler temporal-exclusion window must span ≥1 sample —
    # algorithmic guard against self-pairing, not a physics clamp.
    min_temporal_separation = max(1, min_temporal_separation)

    # For each point, find its nearest neighbor (excluding the Theiler temporal
    # vicinity). Nearest-neighbor search is done with a k-d tree — O(n log n)
    # versus the former brute-force O(n²) — and is EXACT: the Theiler window
    # excludes at most (2·w − 1) indices around i, so querying the k = 2·w + 2
    # nearest guarantees the true nearest valid neighbor is in the returned set;
    # we take the first returned index (distance-sorted) that clears the window.
    divergence_log = np.full(max_divergence_steps, np.nan, dtype=np.float64)
    counts = np.zeros(max_divergence_steps, dtype=np.int64)
    # INV-LE1: a constant / zero-variance / all-zeros / two-value-collapsed
    # series produces only zero-distance neighbor pairs. Track whether ANY
    # strictly-positive pair distance was observed; if none, there is no
    # divergence to measure (Rosenstein 1993 §2.2) and we must fail closed
    # rather than fall through to a spurious 0.0.
    saw_positive_divergence = False

    n_candidates = n_points - max_divergence_steps
    candidates = embedded[:n_candidates]
    w = min_temporal_separation
    k_query = min(n_candidates, 2 * w + 2)
    tree = cKDTree(candidates)
    nn_dist, nn_idx = tree.query(candidates, k=k_query)
    if k_query == 1:  # scipy returns 1-D arrays for k=1
        nn_dist = nn_dist[:, None]
        nn_idx = nn_idx[:, None]

    for i in range(n_candidates):
        # first distance-sorted neighbor outside the Theiler window (and self)
        j = -1
        for col in range(k_query):
            cand = int(nn_idx[i, col])
            if abs(cand - i) >= w and cand != i and math.isfinite(nn_dist[i, col]):
                j = cand
                break
        if j < 0:
            continue

        # Track how this pair diverges over time
        for step in range(max_divergence_steps):
            if i + step >= n_points or j + step >= n_points:
                break
            pair_dist = float(np.sqrt(np.sum((embedded[i + step] - embedded[j + step]) ** 2)))
            # Guard log(0): only finite, strictly-positive distances enter the
            # log-divergence accumulator. A zero distance carries no divergence
            # information and log(0) = −∞ would corrupt the slope fit.
            if pair_dist > 0.0 and math.isfinite(pair_dist):
                saw_positive_divergence = True
                if np.isnan(divergence_log[step]):
                    divergence_log[step] = 0.0
                divergence_log[step] += math.log(pair_dist)
                counts[step] += 1

    # INV-LE1 (fail-closed): zero measurable divergence ⇒ degenerate input.
    # Every nearest-neighbor pair collapsed to distance 0 (constant /
    # zero-variance / all-zeros / two-value-collapsed series). The Rosenstein
    # divergence rate is undefined here — raise instead of masking it as λ=0.
    if not saw_positive_divergence:
        raise ValueError(
            "INV-LE1 violated: no nearest-neighbor pair has a positive "
            "divergence distance — every embedded point is identical (likely "
            "cause: constant / zero-variance / all-zeros / two-value-collapsed "
            "series). A series with no divergence has no Lyapunov exponent to "
            "measure (Rosenstein 1993 §2.2). Fail closed."
        )

    # Average the log-divergence curves
    valid = counts > 0
    if valid.sum() < 5:
        raise ValueError(
            "INV-LE1 violated: fewer than 5 divergence steps accumulated a "
            "usable log-distance — the input is too degenerate for a "
            "non-vacuous Rosenstein slope fit (likely cause: near-constant / "
            "rank-deficient embedding). Fail closed."
        )

    mean_log_div = np.where(valid, divergence_log / counts, np.nan)

    # Linear regression on the valid portion to extract the slope = λ_max
    valid_indices = np.where(valid)[0]
    t_values = valid_indices.astype(np.float64) * dt
    y_values = mean_log_div[valid_indices]

    # Use only the initial linear region (first 40% of valid data).
    # bounds: ≥5 points are needed for a non-degenerate least-squares
    # slope — algorithmic regression minimum, not a physics quantity.
    n_use = max(5, len(valid_indices) * 2 // 5)
    t_fit = t_values[:n_use]
    y_fit = y_values[:n_use]

    # Remove any NaN/Inf
    finite_mask = np.isfinite(y_fit) & np.isfinite(t_fit)
    t_fit = t_fit[finite_mask]
    y_fit = y_fit[finite_mask]

    if len(t_fit) < 3:
        # Fewer than 3 finite points survived after we already accumulated ≥5
        # divergence steps ⇒ the log-divergence curve is itself degenerate.
        raise ValueError(
            "INV-LE1 violated: fewer than 3 finite log-divergence points remain "
            "for the slope fit despite ≥5 accumulated steps (likely cause: "
            "rank-deficient / near-constant embedding). Fail closed."
        )

    # Least-squares slope
    t_mean = float(np.mean(t_fit))
    y_mean = float(np.mean(y_fit))
    # INV-HPC2: protect against degenerate fits
    with np.errstate(over="ignore", invalid="ignore"):
        numerator = float(np.sum((t_fit - t_mean) * (y_fit - y_mean)))
        denominator = float(np.sum((t_fit - t_mean) ** 2))

    if denominator < 1e-30:
        # The time abscissa has collapsed (e.g. dt≈0 or a single distinct
        # fit index): the slope λ = num/denom would be ±Inf/NaN. Fail closed
        # rather than emit a non-finite MLE.
        raise ValueError(
            "INV-LE1 violated: degenerate slope-fit denominator "
            f"({denominator:.3e} < 1e-30) — the divergence-time abscissa has "
            "collapsed (likely cause: dt≈0 or a single distinct fit index), so "
            "λ_max would be non-finite. Fail closed."
        )

    slope = numerator / denominator

    # INV-LE1 (fail-closed): the estimator must never return NaN/±Inf. A
    # non-finite slope here is a residual degeneracy (constant / zero-variance /
    # rank-deficient input) that escaped the upstream traps — surface it.
    if not math.isfinite(slope):
        raise ValueError(
            f"INV-LE1 violated: computed λ_max = {slope} is not finite (likely "
            "cause: constant / zero-variance / rank-deficient input producing a "
            "degenerate log-divergence fit). The Rosenstein MLE must be a finite "
            "real for a valid trajectory; fail closed rather than emit NaN/±Inf."
        )

    # INV-LE3: goodness-of-fit / scaling-region gate.
    # The Rosenstein slope is only a valid λ on the LINEAR scaling region of
    # the log-divergence curve. Quantify linearity with the coefficient of
    # determination R² = 1 − SS_res/SS_tot on the (t, ln d) fit points. A
    # noisy or curved window gives a low R² and a meaningless slope.
    intercept = y_mean - slope * t_mean
    y_pred = slope * t_fit + intercept
    ss_res = float(np.sum((y_fit - y_pred) ** 2))
    ss_tot = float(np.sum((y_fit - y_mean) ** 2))
    n_fit = int(t_fit.size)
    # ss_tot == 0 ⟹ the log-divergence is flat (slope 0 already, no scaling):
    # there is no linear structure to trust → fail closed.
    if ss_tot < 1e-30:
        _record(0.0, slope, n_fit, False)
        return 0.0
    r_squared = 1.0 - ss_res / ss_tot
    if not math.isfinite(r_squared):
        _record(math.nan, slope, n_fit, False)
        return 0.0

    if r_squared < R2_MIN:
        # Fail closed: the divergence curve is not in a clean linear scaling
        # region, so the slope is not a trustworthy λ. Return the module's
        # existing "no reliable estimate" sentinel (0.0) — the same value the
        # short-series / degenerate-fit paths return — rather than a silent,
        # physically meaningless slope. Surface the event (OA-defect lesson:
        # a demoted physical quantity must be observable, not hidden).
        _LOGGER.warning(
            "maximal_lyapunov_exponent: log-divergence fit R²=%.4f < R2_MIN=%.2f "
            "(INV-LE3). Not a Rosenstein scaling region; demoting slope=%.4f to "
            "the no-reliable-estimate sentinel 0.0 over n_fit=%d points.",
            r_squared,
            R2_MIN,
            slope,
            n_fit,
        )
        _record(r_squared, slope, n_fit, False)
        return 0.0

    _record(r_squared, slope, n_fit, True)
    return float(slope)


def spectral_gap(
    adjacency: NDArray[np.float64],
) -> float:
    """Compute the Fiedler eigenvalue (spectral gap) of the graph Laplacian.

    The spectral gap λ₂ is the second-smallest eigenvalue of the
    combinatorial Laplacian L = D - A, where D is the degree matrix
    and A is the adjacency matrix. It controls:

    - **Synchronization rate**: larger λ₂ → faster Kuramoto convergence
    - **Algebraic connectivity**: λ₂ > 0 ⟺ graph is connected
    - **Mixing time**: random walks mix in O(1/λ₂) steps
    - **Cheeger inequality**: λ₂/2 ≤ h(G) ≤ √(2·λ₂) where h is
      the isoperimetric number (bottleneck measure)

    For GeoSync:
    - λ₂ of the asset correlation graph = how quickly market can
      synchronize. Low λ₂ = fragmented sectors = slow regime propagation.
    - λ₂ → 0 during crisis = graph is about to split = regime transition.
    - λ₂ feeds into Kuramoto K_c estimate: synchronization requires
      K > K_c ∝ 1/λ₂ (loosely — the exact relation is more complex).

    Parameters
    ----------
    adjacency : (N, N) array
        Symmetric non-negative adjacency matrix.

    Returns
    -------
    float
        λ₂ (Fiedler eigenvalue). Always ≥ 0 for valid graphs.
        Returns 0.0 for disconnected or trivially small graphs.

    Invariants:
        INV-SG1: λ₂ ≥ 0 always (Laplacian is positive semi-definite)
        INV-SG2: λ₂ > 0 ⟺ graph is connected
    """
    A = np.asarray(adjacency, dtype=np.float64)
    if A.ndim != 2 or A.shape[0] != A.shape[1]:
        raise ValueError(f"Expected square matrix, got shape {A.shape}")

    n = A.shape[0]
    if n < 2:
        return 0.0

    # Symmetrise (in case of rounding asymmetry)
    A = 0.5 * (A + A.T)

    # INV-HPC2: non-negative adjacency. Observability (OA-defect lesson:
    # a silent repair of a physical quantity must be surfaced): a
    # non-trivial negative entry is an upstream sign/data fault, not
    # mere expm round-off — log it before clamping. Behaviour unchanged.
    _neg_adj = float(-A[A < 0.0].sum()) if np.any(A < 0.0) else 0.0
    if _neg_adj > 1e-9:
        _LOGGER.warning(
            "spectral_gap: clamped %.3e of negative adjacency mass to 0 "
            "(INV-HPC2). Negative weights upstream of the Laplacian "
            "indicate a sign/data fault, not numerical noise.",
            _neg_adj,
        )
    A = np.maximum(A, 0.0)
    np.fill_diagonal(A, 0.0)

    # Combinatorial Laplacian: L = D - A
    degrees = A.sum(axis=1)
    L = np.diag(degrees) - A

    # Eigenvalues (real, sorted ascending for symmetric positive semi-definite)
    # INV-HPC2: protect against non-finite entries
    if not np.all(np.isfinite(L)):
        return 0.0

    eigenvalues = np.linalg.eigvalsh(L)

    # λ₂ = second smallest eigenvalue
    # eigenvalues[0] ≈ 0 (constant eigenvector), eigenvalues[1] = λ₂
    # INV-SG1: λ₂ ≥ 0 by positive semi-definiteness of L
    lambda_2 = float(max(0.0, eigenvalues[1]))

    return lambda_2
