# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
r"""Graded identifiability front-gate for the swing coupling estimator.

The merged R1 persistent-excitation guard
(:class:`core.kuramoto.coupling_estimator.PersistentExcitationError`) is
**binary**: it raises only when the standardised swing design matrix is
numerically rank-deficient. That hard floor is blind to the dominant
calibration failure mode — additive phase noise, after the double
differentiation the swing identity requires, inflates the regression
residual variance by orders of magnitude and badly biases ``K̂`` while
*improving* the design conditioning.

This module adds a **graded self-knowledge layer** that sits *above* the
hard PE floor. It propagates the design conditioning (Fisher
information) and the measurement-noise floor (residual variance) into a
per-edge Cramér–Rao *lower-bound* variance band, a bias-sensitive
model-adequacy statistic (``R²``), and a single bounded identifiability
score; it returns a typed ``REFUSE`` verdict — never a point estimate —
when the weakest edge's best-case CI straddles zero **or** the linear
swing fit is noise-dominated.

**Honest scoping.** The CRLB band is a provable *lower bound* on the
standard error of any unbiased estimator, **not** a coverage-calibrated
interval: the merged R1 swing path is bias-dominated in the noiseless
regime (deterministic Savitzky–Golay derivative bias that the residual
variance cannot see). The front-gate is therefore built so its
ACCEPT/REFUSE decision does not rely on CI coverage — the decisive leg
is the bias-sensitive ``R²`` adequacy test; the precision leg uses the
CRLB only as a sound (conservative) one-sided sufficient condition. See
``research/calibration/grid_kuramoto/identifiability/THRESHOLD_PROVENANCE.md``
§ 2.

The exact score formula and the theory-derived REFUSE threshold are
documented and pre-committed in
``research/calibration/grid_kuramoto/identifiability/THRESHOLD_PROVENANCE.md``.
A no-peek drift test binds the constants here to that file.

Notation matches the swing identity (per node ``i``):

.. math::

    m_i\,\ddot\theta_i + d_i\,\dot\theta_i
        = P_i + \sum_{j\neq i} (-K_{ij})\,\sin(\theta_i - \theta_j) .
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "WALD_Z_0975",
    "REFUSE_SCORE",
    "PE_HARD_FLOOR",
    "R2_FLOOR",
    "IdentifiabilityVerdict",
    "EdgeUncertainty",
    "IdentifiabilityReport",
    "linearised_edge_covariance",
    "precision_leg",
    "identifiability_score",
    "front_gate_verdict",
]

# ---------------------------------------------------------------------------
# Theory-derived constants (pre-committed in THRESHOLD_PROVENANCE.md § 3).
# A no-peek drift test asserts these equal the documented theory values;
# changing either side without the other fails CI.
# ---------------------------------------------------------------------------

#: Standard-normal 0.975 quantile — the two-sided 95 % Wald CI half-width.
WALD_Z_0975: float = 1.959963984540054

#: REFUSE boundary: map the binding-edge Wald ratio ``w = z`` through the
#: bounded score ``w/(1+w)``. Below this the weakest edge's 95 % CI
#: contains zero, i.e. its point estimate is misleading not merely
#: imprecise. ``z/(1+z)`` with ``z = WALD_Z_0975``.
REFUSE_SCORE: float = WALD_Z_0975 / (1.0 + WALD_Z_0975)

#: Hard numerical floor on the reciprocal condition number of the
#: standardised design: ``sqrt(eps_float64)``. Below it the linear solve
#: has lost more than half the float64 mantissa — that extreme stays a
#: fail-closed :class:`PersistentExcitationError` (unchanged from the
#: merged code); the graded REFUSE sits above it.
PE_HARD_FLOOR: float = float(np.sqrt(np.finfo(np.float64).eps))

#: Model-adequacy floor on the linear swing fit's coefficient of
#: determination (provenance § 3 leg B). ``R² = ½`` is exactly
#: ``SSR = SST/2`` (explained variance equals unexplained); below it
#: more than half the swing-target variance is un-modelled noise and no
#: estimator can recover ``K``. Fixed theory constant, not fitted.
R2_FLOOR: float = 0.5


class IdentifiabilityVerdict(str, Enum):
    """Front-gate self-knowledge verdict.

    ``ACCEPT``  — every coupling entry's 95 % CI excludes zero; the
                  instrument is inside its operating envelope.
    ``REFUSE``  — the weakest coupling entry's 95 % CI straddles zero;
                  the instrument declares itself out of envelope and
                  withholds the point estimate as trustworthy output.
    """

    ACCEPT = "ACCEPT"
    REFUSE = "REFUSE"


@dataclass(frozen=True, slots=True)
class EdgeUncertainty:
    """Calibrated uncertainty of one unordered coupling edge ``(a, b)``.

    Attributes
    ----------
    a, b : int
        Node indices, ``a < b``.
    estimate : float
        Point estimate ``K̂_{ab}`` (signed).
    std_error : float
        Cramér–Rao *lower-bound* standard error ``SE_CRLB(K̂_{ab})``
        (eq. (3) of the provenance) in physical coupling units. This is
        a provable lower bound on the SE of any unbiased estimator, not
        a coverage-calibrated error — the noiseless swing path is
        bias-dominated (provenance § 2).
    ci_low, ci_high : float
        ``K̂ ± z_{0.975}·SE_CRLB`` — a CRLB *variance band*, **not** a
        95 % coverage interval (the deterministic Savitzky–Golay
        derivative bias is outside its scope; see provenance § 2).
    wald_ratio : float
        ``|K̂_{ab}| / SE(K̂_{ab})`` — the per-edge inverse coefficient
        of variation. ``+inf`` when ``SE`` is exactly zero (a perfectly
        determined edge).
    ci_contains_zero : bool
        ``True`` iff ``ci_low ≤ 0 ≤ ci_high`` — the edge is not
        statistically separable from "no coupling".
    """

    a: int
    b: int
    estimate: float
    std_error: float
    ci_low: float
    ci_high: float
    wald_ratio: float
    ci_contains_zero: bool


@dataclass(frozen=True, slots=True)
class IdentifiabilityReport:
    """Result of the graded identifiability front-gate.

    Attributes
    ----------
    verdict : IdentifiabilityVerdict
        ``ACCEPT`` or ``REFUSE``.
    score : float
        Bounded identifiability score
        ``min(s_A, s_B) ∈ [0, 1]`` (eq. (6) of the provenance): the
        minimum of the precision leg ``s_A = w_min/(1+w_min)`` and the
        adequacy leg ``s_B = max(R², 0)``. Monotone decreasing in
        measurement noise σ, increasing in record length.
    refuse_threshold : float
        The pre-committed :data:`REFUSE_SCORE` (echoed for transparency).
    reciprocal_condition : float
        Reciprocal condition number of the standardised design (the
        merged persistent-excitation diagnostic). Echoed so the caller
        can see why conditioning alone would have passed the noisy case.
    residual_variance : float
        Unbiased residual-variance estimate ``σ̂²`` (eq. (1)) — the
        measurement-noise floor that separates the regimes.
    r_squared : float
        Coefficient of determination of the linear swing fit (eq. (5)),
        the model-adequacy leg. Detects the *bias* failure mode the
        Wald ratio is blind to (provenance § 3 leg B / § 4).
    binding_edge : EdgeUncertainty
        The worst-identified edge (the one that set ``w_min``); this is
        the edge whose CI straddles zero on a ``REFUSE``.
    edges : tuple[EdgeUncertainty, ...]
        Per-edge calibrated uncertainty for every unordered edge.
    reason : str
        Human-readable explanation of the verdict.
    """

    verdict: IdentifiabilityVerdict
    score: float
    refuse_threshold: float
    reciprocal_condition: float
    residual_variance: float
    r_squared: float
    binding_edge: EdgeUncertainty
    edges: tuple[EdgeUncertainty, ...]
    reason: str

    @property
    def accepted(self) -> bool:
        """``True`` iff the front-gate accepted the point estimate."""
        return self.verdict is IdentifiabilityVerdict.ACCEPT


def linearised_edge_covariance(
    design_std: NDArray[np.float64],
    target: NDArray[np.float64],
    coef_std: NDArray[np.float64],
    column_scale: NDArray[np.float64],
    n_edges: int,
) -> tuple[NDArray[np.float64], float, float]:
    r"""Per-edge OLS standard errors and the residual-variance estimate.

    Implements eqs. (1)–(3) of ``THRESHOLD_PROVENANCE.md``:

    .. math::

        \hat\sigma^2 &= \lVert y - D_{\mathrm{std}}\hat c_{\mathrm{std}}
            \rVert^2 / (n_{\mathrm{obs}} - n_{\mathrm{param}}) \\
        \mathrm{Cov}(\hat c_{\mathrm{std}}) &= \hat\sigma^2\,
            (D_{\mathrm{std}}^\top D_{\mathrm{std}})^{+} \\
        \mathrm{SE}(\hat K_p) &= \sqrt{[\mathrm{Cov}]_{pp}} / s_p

    The Moore–Penrose pseudo-inverse keeps a rank-deficient design from
    raising here — that extreme is handled by the hard PE guard upstream.

    Parameters
    ----------
    design_std : np.ndarray, shape ``(n_obs, n_param)``
        Column-standardised global swing design matrix.
    target : np.ndarray, shape ``(n_obs,)``
        Stacked swing target ``m θ̈ + d θ̇``.
    coef_std : np.ndarray, shape ``(n_param,)``
        Standardised least-squares solution.
    column_scale : np.ndarray, shape ``(n_param,)``
        Per-column standardisation scale ``s_p`` (safe, no zeros).
    n_edges : int
        Number of leading edge-coupling columns (the remaining columns
        are per-node injection intercepts).

    Returns
    -------
    edge_std_error : np.ndarray, shape ``(n_edges,)``
        ``SE(K̂)`` per unordered edge in physical units.
    residual_variance : float
        Unbiased ``σ̂²``. ``+inf`` when the degrees of freedom are
        non-positive (under-determined design) so the gate refuses
        rather than reporting a spuriously tiny error.
    r_squared : float
        Coefficient of determination ``R² = 1 − SSR/SST`` of the linear
        swing fit (provenance eq. (5)) — the model-adequacy leg. ``0.0``
        when the target is constant (``SST = 0``): a constant target
        carries no coupling signal, so the adequacy leg fails closed.
    """
    n_obs, n_param = design_std.shape
    resid = target - design_std @ coef_std
    ssr = float(resid @ resid)
    centred = target - float(np.mean(target))
    sst = float(centred @ centred)
    # bounds: a constant target (SST=0) has no signal to explain; report
    # R²=0 so the adequacy leg fail-closes rather than dividing by zero.
    r_squared = 1.0 - ssr / sst if sst > 0.0 else 0.0
    dof = n_obs - n_param
    if dof <= 0:
        # bounds: an under-determined design has no unbiased noise-floor
        # estimate; report +inf so SE → +inf and the gate REFUSES rather
        # than emitting a misleadingly tight covariance.
        sigma2 = float("inf")
    else:
        sigma2 = ssr / float(dof)

    gram = design_std.T @ design_std
    gram_pinv = np.linalg.pinv(gram)
    cov_std = sigma2 * np.diag(gram_pinv)
    # bounds: the pseudo-inverse can yield a tiny negative diagonal from
    # round-off; clip at zero before the sqrt (variance is non-negative).
    var_std = np.clip(cov_std, 0.0, None)
    se_std = np.sqrt(var_std)
    se_phys = se_std / column_scale
    edge_std_error = np.asarray(se_phys[:n_edges], dtype=np.float64)
    return edge_std_error, sigma2, r_squared


def precision_leg(wald_ratios: NDArray[np.float64]) -> float:
    r"""Precision leg ``s_A = w_min/(1+w_min)`` (provenance eq. (6)).

    ``w_min = min_p |K̂_p|/SE(K̂_p)``. The map ``w ↦ w/(1+w)`` is
    strictly increasing on ``[0, ∞)``, so ``s_A ∈ [0, 1)``, monotone in
    the binding edge's signal-to-noise ratio and scale-free.

    Parameters
    ----------
    wald_ratios : np.ndarray
        Per-edge ``|K̂|/SE`` ratios (non-negative; may contain ``+inf``
        for perfectly determined edges).

    Returns
    -------
    float
        ``s_A``. ``1.0`` only in the degenerate all-``+inf`` limit.
    """
    if wald_ratios.size == 0:
        return 0.0
    w_min = float(np.min(wald_ratios))
    if not np.isfinite(w_min):
        return 1.0
    return w_min / (1.0 + w_min)


def identifiability_score(
    wald_ratios: NDArray[np.float64],
    r_squared: float,
) -> float:
    r"""Combined bounded identifiability score (provenance eq. (6)).

    ``IDENTIFIABILITY = min(s_A, s_B)`` with the precision leg
    ``s_A = w_min/(1+w_min)`` and the model-adequacy leg
    ``s_B = max(R², 0)``. The minimum makes the score a fail-closed
    conjunction: the instrument is identifiable only if every edge is
    precise (Wald CI excludes zero) *and* the linear swing model
    adequately explains the data (``R²`` not noise-dominated). The
    second leg is essential because ``s_A`` alone is blind to bias —
    noise can inflate both ``|K̂|`` and ``SE`` so the Wald ratio stays
    large while ``K̂`` is grossly wrong.

    Parameters
    ----------
    wald_ratios : np.ndarray
        Per-edge ``|K̂|/SE`` ratios.
    r_squared : float
        Coefficient of determination of the linear swing fit.

    Returns
    -------
    float
        ``min(s_A, s_B) ∈ [0, 1]``.
    """
    s_a = precision_leg(wald_ratios)
    s_b = max(r_squared, 0.0)
    return min(s_a, s_b)


def front_gate_verdict(
    k_hat: NDArray[np.float64],
    edges: list[tuple[int, int]],
    edge_std_error: NDArray[np.float64],
    reciprocal_condition: float,
    residual_variance: float,
    r_squared: float,
) -> IdentifiabilityReport:
    r"""Apply the graded front-gate decision lattice (provenance § 3).

    The hard ``PersistentExcitationError`` floor is enforced *upstream*
    in :func:`core.kuramoto.coupling_estimator.estimate_swing_coupling`;
    by the time this is called the design is at least minimally
    conditioned. The graded layer here decides ``ACCEPT`` vs ``REFUSE``
    on the combined two-leg score (precision ∧ model adequacy).

    Parameters
    ----------
    k_hat : np.ndarray, shape ``(N, N)``
        Symmetric signed coupling estimate.
    edges : list[tuple[int, int]]
        Unordered edges ``(a, b)`` with ``a < b`` in the same order as
        ``edge_std_error``.
    edge_std_error : np.ndarray, shape ``(n_edges,)``
        Per-edge ``SE(K̂)`` from :func:`linearised_edge_covariance`.
    reciprocal_condition : float
        Reciprocal condition number of the standardised design (echoed).
    residual_variance : float
        Unbiased ``σ̂²`` (echoed).
    r_squared : float
        Coefficient of determination of the linear swing fit — the
        model-adequacy leg.

    Returns
    -------
    IdentifiabilityReport
        ``REFUSE`` (with the offending edge + reason) when the weakest
        edge's 95 % Wald CI straddles zero **or** the linear model is
        noise-dominated (``R² < ½``); ``ACCEPT`` only if both legs pass.
    """
    edge_unc: list[EdgeUncertainty] = []
    wald: list[float] = []
    for (a, b), se in zip(edges, edge_std_error, strict=True):
        est = float(k_hat[a, b])
        se_f = float(se)
        if se_f > 0.0:
            ratio = abs(est) / se_f
        elif est == 0.0:
            # 0/0 — a structurally absent edge with zero error: it is
            # perfectly (trivially) determined as absent.
            ratio = float("inf")
        else:
            ratio = float("inf")
        half = WALD_Z_0975 * se_f
        lo, hi = est - half, est + half
        contains_zero = lo <= 0.0 <= hi
        edge_unc.append(
            EdgeUncertainty(
                a=a,
                b=b,
                estimate=est,
                std_error=se_f,
                ci_low=lo,
                ci_high=hi,
                wald_ratio=ratio,
                ci_contains_zero=bool(contains_zero),
            )
        )
        wald.append(ratio)

    wald_arr = np.asarray(wald, dtype=np.float64)
    s_a = precision_leg(wald_arr)
    s_b = max(r_squared, 0.0)
    score = min(s_a, s_b)
    binding_idx = int(np.argmin(wald_arr)) if wald_arr.size else 0
    binding = edge_unc[binding_idx]

    precision_fails = s_a < REFUSE_SCORE
    adequacy_fails = r_squared < R2_FLOOR

    if score < REFUSE_SCORE:
        if adequacy_fails and not precision_fails:
            leg = (
                f"model adequacy: R²={r_squared:.4f} < ½ — the linear "
                f"swing fit is noise-dominated (σ̂²={residual_variance:.4g}); "
                f"the per-edge Wald CIs are tight around a *biased* K̂ "
                f"(confidently wrong, not imprecise)"
            )
        elif adequacy_fails and precision_fails:
            leg = (
                f"both legs: R²={r_squared:.4f} < ½ (noise-dominated fit) "
                f"and weakest edge ({binding.a},{binding.b}) |K̂|/SE="
                f"{binding.wald_ratio:.3f} ≤ z_0.975 ({WALD_Z_0975:.3f})"
            )
        else:
            leg = (
                f"precision: weakest coupling edge "
                f"({binding.a},{binding.b}) |K̂|/SE="
                f"{binding.wald_ratio:.3f} ≤ z_0.975 ({WALD_Z_0975:.3f}); "
                f"its 95% CI [{binding.ci_low:.4g}, {binding.ci_high:.4g}] "
                f"straddles zero"
            )
        reason = (
            f"REFUSE [{leg}]. score min(s_A={s_a:.4f}, s_B={s_b:.4f})="
            f"{score:.4f} < refuse threshold {REFUSE_SCORE:.4f} "
            f"(1/cond={reciprocal_condition:.4g}). The point estimate is "
            f"misleading rather than imprecise; instrument out of "
            f"envelope — no trustworthy K̂ is promoted (graded "
            f"self-knowledge layer, not a tuning knob)."
        )
        verdict = IdentifiabilityVerdict.REFUSE
    else:
        reason = (
            f"ACCEPT: every coupling edge's 95% CI excludes zero "
            f"(binding edge ({binding.a},{binding.b}) |K̂|/SE="
            f"{binding.wald_ratio:.3f} > z_0.975) and the linear swing "
            f"fit is adequate (R²={r_squared:.4f} ≥ ½); "
            f"score min(s_A={s_a:.4f}, s_B={s_b:.4f})={score:.4f} ≥ "
            f"refuse threshold {REFUSE_SCORE:.4f} "
            f"(σ̂²={residual_variance:.4g})."
        )
        verdict = IdentifiabilityVerdict.ACCEPT

    return IdentifiabilityReport(
        verdict=verdict,
        score=score,
        refuse_threshold=REFUSE_SCORE,
        reciprocal_condition=reciprocal_condition,
        residual_variance=residual_variance,
        r_squared=r_squared,
        binding_edge=binding,
        edges=tuple(edge_unc),
        reason=reason,
    )
