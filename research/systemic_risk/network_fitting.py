# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""MLE fitting of interbank degree distributions to candidate generators.

The Barabási–Albert generator at fixed *m* is the topology-null
baseline of the systemic-risk falsification battery. v1 hard-coded
``m=3`` from Boss et al. 2004 / Soramäki et al. 2007; v2 fits *m*
(equivalently the power-law exponent α) directly to the empirical
degree sequence by maximum likelihood per Clauset, Shalizi & Newman
(2009), *SIAM Rev.* **51**: 661.

Two candidate models are compared on every fit:

* **Power law** (BA-like): :math:`P(k) \\propto k^{-\\alpha}` for
  :math:`k \\ge k_{\\min}`. MLE estimator
  :math:`\\hat{\\alpha} = 1 + n / \\sum_i \\ln(k_i / k_{\\min})`.
* **Exponential**: :math:`P(k) \\propto e^{-\\lambda k}` for
  :math:`k \\ge k_{\\min}`. MLE estimator
  :math:`\\hat{\\lambda} = 1 / (\\bar{k} - k_{\\min})`.

The Kolmogorov–Smirnov statistic and a parametric-bootstrap p-value
quantify the goodness-of-fit; the Akaike Information Criterion picks
between the two candidates without overfitting penalty drift.

Pure-function API. No I/O. Determinism via explicit seeds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from .topology import InterbankTopology

__all__ = [
    "MIN_TAIL_SIZE_VALIDATION",
    "MIN_RELATIVE_SE_VALIDATION",
    "PowerLawFit",
    "ExponentialFit",
    "ModelComparison",
    "fit_power_law",
    "fit_power_law_validation",
    "fit_exponential",
    "compare_power_law_vs_exponential",
    "fit_barabasi_albert",
    "fit_barabasi_albert_from_topology",
]


# ---------------------------------------------------------------------------
# Validation-mode constants — derived, not declared
# ---------------------------------------------------------------------------
#
# MIN_TAIL_SIZE_VALIDATION: at α≈2.5 the Cramér-Rao σ_α/α floor at
# n_tail=50 is 1.5/(2.5·√50) ≈ 0.085, giving a 95 % CI half-width of
# 1.96·0.085·α ≈ 0.42 — sufficient to distinguish α=2.0 from α=2.4.
# Below n_tail=50 the SE explodes and the implied minimum from the
# CRLB (see fit_power_law `min_relative_se` derivation) becomes
# brittle to a single-realisation seed.
#
# MIN_RELATIVE_SE_VALIDATION: 0.10 (10 % relative SE) is the bound
# at which Clauset-Shalizi-Newman 2009 fig. 3 reports the discrete
# power-law fit becoming reliably distinguishable from exponential
# alternatives at the AIC-Δ > 4 level on synthetic samples.

MIN_TAIL_SIZE_VALIDATION: int = 50
MIN_RELATIVE_SE_VALIDATION: float = 0.10


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PowerLawFit:
    """MLE fit of a discrete power-law tail :math:`P(k) \\propto k^{-\\alpha}`.

    Attributes
    ----------
    alpha
        Maximum-likelihood exponent. Standard error
        :math:`\\sigma_\\alpha = (\\alpha - 1) / \\sqrt{n}`
        (Clauset et al. 2009, eq. 3.2).
    alpha_se
        Asymptotic standard error of ``alpha``.
    k_min
        Lower-tail cutoff used by the fit.
    n_tail
        Number of degrees in the fit tail (``k >= k_min``).
    log_likelihood
        Log-likelihood of the tail under the fitted model.
    ks_statistic
        Kolmogorov–Smirnov distance between the empirical tail CDF
        and the fitted CDF.
    ks_p_value
        Parametric-bootstrap p-value: probability that a synthetic
        sample of size ``n_tail`` drawn from the fitted distribution
        produces a KS statistic at least as large as the observed one.
        ``None`` when the bootstrap was not requested.
    """

    alpha: float
    alpha_se: float
    k_min: int
    n_tail: int
    log_likelihood: float
    ks_statistic: float
    ks_p_value: float | None


@dataclass(frozen=True, slots=True)
class ExponentialFit:
    """MLE fit of a discrete shifted exponential :math:`P(k) \\propto e^{-\\lambda k}`."""

    lambda_: float
    k_min: int
    n_tail: int
    log_likelihood: float
    ks_statistic: float


@dataclass(frozen=True, slots=True)
class ModelComparison:
    """AIC-based comparison of power-law vs exponential.

    ``preferred`` is the model with the lower AIC. ``aic_delta`` is
    the absolute AIC gap (smaller is more decisive — Burnham &
    Anderson 2002 conventionally read Δ < 2 as roughly equivalent,
    Δ ∈ (4, 7) as strong, Δ > 10 as decisive).
    """

    power_law: PowerLawFit
    exponential: ExponentialFit
    aic_power_law: float
    aic_exponential: float
    preferred: Literal["power_law", "exponential"]
    aic_delta: float


# ---------------------------------------------------------------------------
# MLE estimators
# ---------------------------------------------------------------------------


def _validate_degrees(degrees: NDArray[np.int64]) -> NDArray[np.int64]:
    d = np.asarray(degrees, dtype=np.int64)
    if d.ndim != 1:
        raise ValueError(f"degrees must be 1-D, got shape={d.shape}")
    if d.size < 4:
        raise ValueError(f"degrees must contain at least 4 entries, got n={d.size}")
    if np.any(d < 0):
        raise ValueError("degrees must be non-negative")
    return d


def fit_power_law(
    degrees: NDArray[np.int64],
    *,
    k_min: int | None = None,
    n_bootstrap: int = 0,
    seed: int = 42,
    min_relative_se: float | None = None,
) -> PowerLawFit:
    """Fit a discrete power-law tail by maximum likelihood.

    Parameters
    ----------
    degrees
        1-D array of non-negative degree observations.
    k_min
        Tail cutoff. ``None`` (default) selects the cutoff that
        minimises the KS statistic over all admissible cutoffs
        (Clauset, Shalizi, Newman 2009 §3.3 — discrete grid scan).
    n_bootstrap
        Number of parametric-bootstrap resamples for the p-value.
        ``0`` (default) skips the bootstrap and returns ``ks_p_value=None``.
    seed
        RNG seed for the bootstrap.
    min_relative_se
        Optional Cramér-Rao precision floor: after fit, if the
        relative asymptotic standard error
        :math:`\\sigma_\\alpha / \\hat\\alpha = (\\hat\\alpha - 1) /
        (\\hat\\alpha \\sqrt{n_\\text{tail}})` exceeds this value, raise
        :class:`ValueError`. ``None`` (default) skips the check —
        the caller can read ``alpha_se`` from the result and decide
        their own tolerance. Derivation (Clauset et al. 2009, eq. 3.2,
        and the discrete-power-law Fisher information
        :math:`I(\\alpha) = n_\\text{tail} / (\\alpha-1)^2`):

            σ_α    α − 1
            ─── = ─────────  must be ≤ ``min_relative_se``.
             α    α · √n_t

        Solving for the implied minimum tail size at a given α:
        :math:`n_\\text{tail} \\ge \\bigl[(\\alpha-1)/(\\alpha
        \\cdot \\text{tol})\\bigr]^2`. e.g. α=2.5, tol=0.10 → n ≥ 36;
        α=2.0, tol=0.10 → n ≥ 25.
    """
    d = _validate_degrees(degrees)
    if k_min is None:
        chosen = _select_k_min(d)
    else:
        if k_min < 1:
            raise ValueError(f"k_min must be >= 1, got {k_min}")
        chosen = int(k_min)
    tail = d[d >= chosen]
    if tail.size < 2:
        raise ValueError(f"only {tail.size} observations >= k_min={chosen}; need >=2 to fit")
    # Continuous-approximation MLE — bias-stable for k_min >= 6 (Clauset 2009).
    log_ratio = float(np.log(tail.astype(np.float64) / (chosen - 0.5)).sum())
    if log_ratio <= 0:
        raise ValueError("non-positive log-ratio sum — degenerate tail")
    alpha = 1.0 + tail.size / log_ratio
    alpha_se = (alpha - 1.0) / math.sqrt(tail.size)
    if min_relative_se is not None:
        if min_relative_se <= 0.0:
            raise ValueError(f"min_relative_se must be > 0, got {min_relative_se}")
        rel_se = alpha_se / alpha
        if rel_se > min_relative_se:
            implied_n = math.ceil(((alpha - 1.0) / (alpha * min_relative_se)) ** 2)
            raise ValueError(
                f"power-law fit fails Cramér-Rao precision floor: "
                f"σ_α/α = {rel_se:.4f} > {min_relative_se:.4f} "
                f"at α̂={alpha:.4f}, n_tail={tail.size}, k_min={chosen}; "
                f"need n_tail ≥ {implied_n} for that α to clear the floor."
            )
    log_likelihood = (
        tail.size * math.log(alpha - 1.0)
        - tail.size * math.log(chosen - 0.5)
        - alpha * float(np.log(tail.astype(np.float64) / (chosen - 0.5)).sum())
    )
    ks = _ks_statistic_power_law(tail, alpha, chosen)
    p_value: float | None = None
    if n_bootstrap > 0:
        p_value = _ks_p_value_power_law(
            tail.size, alpha, chosen, observed_ks=ks, n_bootstrap=n_bootstrap, seed=seed
        )
    return PowerLawFit(
        alpha=float(alpha),
        alpha_se=float(alpha_se),
        k_min=int(chosen),
        n_tail=int(tail.size),
        log_likelihood=float(log_likelihood),
        ks_statistic=float(ks),
        ks_p_value=p_value,
    )


def fit_power_law_validation(
    degrees: NDArray[np.int64],
    *,
    k_min: int | None = None,
    n_bootstrap: int = 1000,
    seed: int = 42,
) -> PowerLawFit:
    """Strict, fail-closed validation-mode wrapper around :func:`fit_power_law`.

    Validation mode enforces TWO floors that the exploratory API
    leaves opt-in:

    * ``n_tail >= MIN_TAIL_SIZE_VALIDATION = 50`` — derived from the
      Cramér-Rao bound at α≈2.5 (95 % CI half-width ≤ 0.42, sufficient
      to separate α=2.0 from α=2.4 — see module-level constant
      derivation block).
    * ``σ_α / α <= MIN_RELATIVE_SE_VALIDATION = 0.10`` — Clauset-
      Shalizi-Newman 2009 fig. 3 reports this as the bound where the
      power-law fit becomes reliably distinguishable from the
      exponential alternative at AIC-Δ > 4.

    Both floors must hold simultaneously; failure of either raises
    :class:`ValueError` with the implied minimum sample size at the
    fitted α. ``n_bootstrap`` defaults to 1000 (KS-p resolves to
    ±0.001 by Davison-Hinkley) — also tighter than the exploratory
    default. ``min_relative_se`` is enforced internally; it is *not*
    a kwarg here so the validation contract is unambiguous.
    """
    d = _validate_degrees(degrees)
    if d.size < MIN_TAIL_SIZE_VALIDATION:
        raise ValueError(
            f"validation-mode power-law fit requires "
            f"n_observations >= {MIN_TAIL_SIZE_VALIDATION}; got n={d.size}. "
            f"For exploratory use, call fit_power_law directly."
        )
    return fit_power_law(
        d,
        k_min=k_min,
        n_bootstrap=n_bootstrap,
        seed=seed,
        min_relative_se=MIN_RELATIVE_SE_VALIDATION,
    )


def fit_exponential(
    degrees: NDArray[np.int64],
    *,
    k_min: int | None = None,
) -> ExponentialFit:
    """Fit a shifted exponential tail by maximum likelihood."""
    d = _validate_degrees(degrees)
    chosen = int(k_min) if k_min is not None else int(d[d > 0].min()) if (d > 0).any() else 1
    if chosen < 1:
        raise ValueError(f"k_min must be >= 1, got {chosen}")
    tail = d[d >= chosen].astype(np.float64)
    if tail.size < 2:
        raise ValueError(f"only {tail.size} observations >= k_min={chosen}; need >=2 to fit")
    mean_excess = float(tail.mean()) - chosen
    if mean_excess <= 0:
        raise ValueError(f"mean degree {tail.mean():.3f} <= k_min={chosen}; cannot fit")
    lam = 1.0 / mean_excess
    log_likelihood = float(tail.size * math.log(lam) - lam * float((tail - chosen).sum()))
    ks = _ks_statistic_exponential(tail, lam, chosen)
    return ExponentialFit(
        lambda_=float(lam),
        k_min=int(chosen),
        n_tail=int(tail.size),
        log_likelihood=float(log_likelihood),
        ks_statistic=float(ks),
    )


def compare_power_law_vs_exponential(
    degrees: NDArray[np.int64],
    *,
    k_min: int | None = None,
    n_bootstrap: int = 0,
    seed: int = 42,
) -> ModelComparison:
    """Fit both candidates and pick by AIC.

    AIC = 2 k − 2 ℓ̂ where *k* is the number of free parameters
    (1 for both models given a fixed ``k_min``) and ℓ̂ is the maximum
    log-likelihood. Lower is better.
    """
    pl = fit_power_law(degrees, k_min=k_min, n_bootstrap=n_bootstrap, seed=seed)
    exp_fit = fit_exponential(degrees, k_min=k_min)
    aic_pl = 2.0 * 1 - 2.0 * pl.log_likelihood
    aic_exp = 2.0 * 1 - 2.0 * exp_fit.log_likelihood
    preferred: Literal["power_law", "exponential"] = (
        "power_law" if aic_pl < aic_exp else "exponential"
    )
    return ModelComparison(
        power_law=pl,
        exponential=exp_fit,
        aic_power_law=float(aic_pl),
        aic_exponential=float(aic_exp),
        preferred=preferred,
        aic_delta=float(abs(aic_pl - aic_exp)),
    )


def fit_barabasi_albert(
    degrees: NDArray[np.int64],
    *,
    n_bootstrap: int = 0,
    seed: int = 42,
    min_relative_se: float | None = None,
) -> tuple[int, PowerLawFit]:
    """Fit a BA-compatible *m* parameter to an empirical degree sequence.

    The Barabási–Albert generator produces a power-law tail with
    exponent α = 3 in the thermodynamic limit; finite-size and
    direction-asymmetry effects shift α typically into [2, 3]
    (Albert & Barabási 2002, *Rev. Mod. Phys.* 74: 47). Once the
    empirical α is fitted, *m* is recovered from the BA mean-degree
    identity ``<k> = 2m`` (Albert-Barabási 2002, eq. 4.7):
    rounding ``mean(k) / 2`` to the nearest positive integer.

    Parameters
    ----------
    degrees
        1-D array of **undirected per-node degree counts** (each
        undirected edge contributes 1 to each of its two endpoints,
        and the BA mean-degree identity ``<k> = 2m`` assumes this
        convention). Direct ``InterbankTopology.degree`` from a
        symmetric topology counts each undirected edge **twice** —
        once via ``in_degree`` and once via ``out_degree`` — and so
        produces ``<k>_directed = 4m`` and a doubled ``m̂``. Use
        :func:`fit_barabasi_albert_from_topology` to handle the
        symmetric/asymmetric switch automatically, or pass
        ``topo.out_degree`` for symmetric inputs.
    """
    d = _validate_degrees(degrees)
    if np.unique(d).size < 2:
        raise ValueError(
            f"degenerate input: all observations equal ({int(d[0])}); cannot fit a power-law tail"
        )
    mean_k = float(d.mean())
    if mean_k < 2.0:
        # BA with m >= 1 generates <k> >= 2 by construction; mean<2
        # means input is incompatible with the BA generator, not a
        # finite-size artefact. Fail-closed instead of silently
        # returning m=1 via the floor.
        raise ValueError(
            f"BA-incompatible input: <k>={mean_k:.4f} < 2; "
            f"BA(m≥1) requires <k> ≥ 2 by Albert-Barabási 2002 eq. 4.7"
        )
    pl = fit_power_law(d, n_bootstrap=n_bootstrap, seed=seed, min_relative_se=min_relative_se)
    m = int(round(mean_k / 2.0))
    if m < 1:  # unreachable given mean_k>=2 above; fail-closed assertion
        raise ValueError(f"BA m must satisfy m ≥ 1; got m={m} from <k>={mean_k:.4f}")
    return m, pl


def fit_barabasi_albert_from_topology(
    topology: "InterbankTopology",
    *,
    n_bootstrap: int = 0,
    seed: int = 42,
    min_relative_se: float | None = None,
) -> tuple[int, PowerLawFit]:
    """Calibrate BA *m* directly from an :class:`InterbankTopology`.

    Resolves the in+out-vs-undirected ambiguity introduced by
    :attr:`InterbankTopology.degree` (which is the **sum** of in- and
    out-degree, doubling undirected counts on symmetric graphs):

    * Symmetric graphs: ``out_degree == in_degree`` and equals the
      undirected per-node degree, so the BA identity ``<k>=2m``
      applies directly to ``out_degree``.
    * Asymmetric directed graphs: the natural BA analogue is the
      out-degree distribution (each new node attaches *m* outgoing
      edges); the BA identity again applies to ``out_degree``.

    Both cases reduce to ``fit_barabasi_albert(topology.out_degree)``.
    Reported *m* therefore matches the generator's *m* on
    :func:`barabasi_albert_null` outputs to within ±1 at finite *N*.
    """
    return fit_barabasi_albert(
        topology.out_degree,
        n_bootstrap=n_bootstrap,
        seed=seed,
        min_relative_se=min_relative_se,
    )


def fit_barabasi_albert_validation_from_topology(
    topology: "InterbankTopology",
    *,
    n_bootstrap: int = 1000,
    seed: int = 42,
) -> tuple[int, PowerLawFit]:
    """Strict, fail-closed BA calibration for validation-mode pipelines.

    Wraps :func:`fit_barabasi_albert_from_topology` with the
    validation-mode floors enforced by :func:`fit_power_law_validation`:

    * ``n_tail >= MIN_TAIL_SIZE_VALIDATION = 50`` (CRLB-derived)
    * ``σ_α / α <= MIN_RELATIVE_SE_VALIDATION = 0.10``
      (Clauset-Shalizi-Newman 2009 fig. 3 boundary)

    Both floors are applied internally; the kwarg surface
    deliberately offers no escape hatch (no ``min_relative_se=None``
    and no opt-out for the n-tail floor) so the validation contract
    is unambiguous. ``n_bootstrap`` defaults to 1000 (KS-p resolves
    to ±0.001 by Davison-Hinkley) — also tighter than exploratory.

    Always uses ``topology.out_degree`` per the canonical
    BA-orientation contract. Use the exploratory
    :func:`fit_barabasi_albert_from_topology` for permissive fits.
    """
    out_deg = topology.out_degree
    if out_deg.size < MIN_TAIL_SIZE_VALIDATION:
        raise ValueError(
            f"validation-mode BA fit requires "
            f"n_observations >= {MIN_TAIL_SIZE_VALIDATION}; "
            f"got n={out_deg.size}. "
            f"For exploratory use, call fit_barabasi_albert_from_topology."
        )
    return fit_barabasi_albert(
        out_deg,
        n_bootstrap=n_bootstrap,
        seed=seed,
        min_relative_se=MIN_RELATIVE_SE_VALIDATION,
    )


# ---------------------------------------------------------------------------
# Internals: k_min selection + KS statistic + bootstrap p
# ---------------------------------------------------------------------------


def _select_k_min(degrees: NDArray[np.int64]) -> int:
    """Clauset-Shalizi-Newman 2009 §3.3 k_min selection by KS minimisation."""
    candidates = np.unique(degrees[degrees >= 1])
    # The largest few candidates leave too few tail points to fit; cap.
    if candidates.size <= 4:
        return int(candidates[0]) if candidates.size > 0 else 1
    upper_idx = max(1, candidates.size - 4)
    candidates = candidates[:upper_idx]
    best_k_min = int(candidates[0])
    best_ks = math.inf
    for k_min in candidates:
        tail = degrees[degrees >= k_min]
        if tail.size < 4:
            continue
        log_ratio = float(np.log(tail.astype(np.float64) / (int(k_min) - 0.5)).sum())
        if log_ratio <= 0:
            continue
        alpha = 1.0 + tail.size / log_ratio
        ks = _ks_statistic_power_law(tail, alpha, int(k_min))
        if ks < best_ks:
            best_ks = ks
            best_k_min = int(k_min)
    return best_k_min


def _power_law_cdf(k: NDArray[np.int64], alpha: float, k_min: int) -> NDArray[np.float64]:
    """Continuous-approximation CDF for a discrete power-law tail."""
    k_arr = np.asarray(k, dtype=np.float64)
    return 1.0 - ((k_arr - 0.5) / (k_min - 0.5)) ** (1.0 - alpha)


def _ks_statistic_power_law(tail: NDArray[np.int64], alpha: float, k_min: int) -> float:
    sorted_tail = np.sort(tail)
    n = sorted_tail.size
    empirical_cdf = np.arange(1, n + 1, dtype=np.float64) / n
    fitted_cdf = _power_law_cdf(sorted_tail, alpha, k_min)
    return float(np.max(np.abs(empirical_cdf - fitted_cdf)))


def _exponential_cdf(k: NDArray[np.float64], lam: float, k_min: int) -> NDArray[np.float64]:
    k_arr = np.asarray(k, dtype=np.float64)
    return 1.0 - np.exp(-lam * (k_arr - k_min))


def _ks_statistic_exponential(tail: NDArray[np.float64], lam: float, k_min: int) -> float:
    sorted_tail = np.sort(tail)
    n = sorted_tail.size
    empirical_cdf = np.arange(1, n + 1, dtype=np.float64) / n
    fitted_cdf = _exponential_cdf(sorted_tail, lam, k_min)
    return float(np.max(np.abs(empirical_cdf - fitted_cdf)))


def _draw_power_law_sample(
    n: int, alpha: float, k_min: int, rng: np.random.Generator
) -> NDArray[np.int64]:
    """Inverse-CDF sampler for the continuous power-law approximation."""
    u = rng.random(n)
    raw = (k_min - 0.5) * (1.0 - u) ** (1.0 / (1.0 - alpha)) + 0.5
    return np.maximum(np.rint(raw).astype(np.int64), k_min)


def _ks_p_value_power_law(
    n: int,
    alpha: float,
    k_min: int,
    *,
    observed_ks: float,
    n_bootstrap: int,
    seed: int,
) -> float:
    rng = np.random.default_rng(seed)
    exceedances = 0
    for _ in range(n_bootstrap):
        synthetic = _draw_power_law_sample(n, alpha, k_min, rng)
        # Re-fit on the synthetic sample then compute its own KS.
        log_ratio = float(np.log(synthetic.astype(np.float64) / (k_min - 0.5)).sum())
        if log_ratio <= 0:
            continue
        synth_alpha = 1.0 + n / log_ratio
        synth_ks = _ks_statistic_power_law(synthetic, synth_alpha, k_min)
        if synth_ks >= observed_ks:
            exceedances += 1
    # Davison & Hinkley (1997) +1 continuity correction.
    return float((exceedances + 1) / (n_bootstrap + 1))
