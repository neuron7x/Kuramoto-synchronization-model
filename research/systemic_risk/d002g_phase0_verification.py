# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002G — Phase 0 pre-launch verification (HARD GATE).

This module implements the three Phase 0 checks locked in
``docs/governance/D002G_PREREGISTRATION.yaml`` § ``phase_0_verification``
and ``docs/governance/D002G_ACCEPTANCE_RULES.md`` § 4:

  * **Phase 0a — bit-identity broken**
      For every (substrate × N), the M1 null K_baseline is NOT
      ``np.array_equal`` identical to the precursor K_baseline at λ=0.

  * **Phase 0b — H0 preserved**
      50-seed paired null-vs-null t-test on metric values:
      ``|t| < 2.0`` (≈ p > 0.05). H0 ("no precursor effect at λ=0")
      must remain unrejected.

  * **Phase 0c — permutation discriminability non-trivial**
      ``run_null_audit`` with ``n_shuffles=1000`` on the 50-seed paired
      null-vs-null arrays yields ``0.05 < p_value_empirical < 0.95``.
      The permutation distribution must have finite width and the
      empirical p-value must not collapse to pathology.

Acceptance
==========
ALL three checks PASS for every (substrate × N) → Phase 0 PASS →
emit ``phase0_verification_capsule_v1`` with ``verdict="PASS"``.

ANY check FAIL → Phase 0 FAIL → capsule with ``verdict="FAIL"``,
per-cell evidence, plus ``fallback_recommendation="M2"`` per
pre-registration §4 fallback policy.

The capsule writer lives in :mod:`d002g_phase0_capsule` — this
module is the pure verification logic.

Strict scope
============
Verification protocol ONLY. NO sweep launch. NO claim layer. NO
threshold edits. This module CONSUMES the existing metric +
integrator + null-audit primitives from D-002C and the M1
realisation primitive from :mod:`d002g_null_mechanisms`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray
from scipy import stats as _scipy_stats

from .d002c_kuramoto import (
    DEFAULT_OMEGA_GAMMA,
    DEFAULT_STEPS_PER_QUARTER,
    simulate_kuramoto,
)
from .d002c_metrics import METRIC_BY_ID, Metric
from .d002c_null_audit import run_null_audit
from .d002c_substrates import SUBSTRATE_BY_ID, Substrate, SubstrateInvalid
from .d002g_null_mechanisms import (
    NULL_SEED_OFFSET,
    BitIdenticalNullError,
    realize_null,
)

# ---------------------------------------------------------------------------
# Locked Phase 0 parameters (frozen in the pre-registration)
# ---------------------------------------------------------------------------

#: 50-seed paired null-vs-null comparison.
PHASE0_N_SEEDS: Final[int] = 50

#: ``run_null_audit`` shuffle count for Phase 0c. The pre-registration
#: locks this at 1000 (NOT the 100 used by the canonical sweep audit).
PHASE0_N_SHUFFLES: Final[int] = 1000

#: t-statistic threshold for Phase 0b (locked in the pre-registration).
PHASE0_T_THRESHOLD: Final[float] = 2.0

#: Phase 0c p-value envelope (locked in the pre-registration).
PHASE0_P_LO: Final[float] = 0.05
PHASE0_P_HI: Final[float] = 0.95

#: Default metric used for Phase 0b / 0c. The pre-registration's
#: hypotheses target ``sync_auc``; we use the same metric here so
#: Phase 0 measures the same physical quantity that the canonical
#: sweep will measure.
DEFAULT_PHASE0_METRIC_ID: Final[str] = "sync_auc"

#: Default base seed for Phase 0a (the locked substrate_seed=42 in
#: the pre-registration's reproducibility envelope).
PHASE0_BASE_SEED: Final[int] = 42

#: Default null-audit RNG seed.
PHASE0_NULL_AUDIT_SEED: Final[int] = 42


class Phase0Invalid(RuntimeError):
    """Bad input to a Phase 0 routine (unknown substrate, etc.)."""


# ---------------------------------------------------------------------------
# Per-check result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Phase0aResult:
    """Phase 0a — bit-identity broken."""

    substrate_id: str
    N: int
    passed: bool
    array_equal: bool
    base_seed: int
    null_seed: int
    detail: str


@dataclass(frozen=True)
class Phase0bResult:
    """Phase 0b — H0 preserved.

    Strike-R3 hardening: the original |t| < 2 test was mis-calibrated for
    the bounded skewed metrics (sync_auc bounded, tau_onset right-censored)
    used by D-002G. We now require BOTH:

      * Wilcoxon signed-rank ``p_value > 0.05`` (non-parametric, robust
        to skewed/bounded distributions).
      * Percentile bootstrap CI on ``mean(diffs)`` contains 0. (P1-3
        Codex review fix: the original contract advertised BCa
        bias-corrected accelerated CI; the implementation always was
        percentile bootstrap. Path 2 downgrade — the contract is now
        explicitly percentile. True BCa (bias-corrected accelerated)
        remains future hardening on skew/bounded paired-difference
        calibration.)

    The t-statistic is still emitted for diagnostic continuity with the
    pre-registration documentation, but it is NOT in the verdict path.
    """

    substrate_id: str
    N: int
    passed: bool
    n_seeds: int
    t_statistic: float
    mean_diff: float
    std_diff: float
    threshold: float
    detail: str
    # Strike-R3: robust-test fields, defaulted so legacy degenerate
    # branches that emit a Phase0bResult without running Wilcoxon /
    # bootstrap can do so without violating the constructor contract.
    # The default sentinels surface as "untested" in capsules.
    wilcoxon_pvalue: float = float("nan")
    wilcoxon_pvalue_floor: float = 0.05
    bootstrap_ci_lo: float = float("nan")
    bootstrap_ci_hi: float = float("nan")


@dataclass(frozen=True)
class Phase0cResult:
    """Phase 0c — permutation discriminability non-trivial."""

    substrate_id: str
    N: int
    passed: bool
    n_shuffles: int
    p_value_empirical: float
    p_lo: float
    p_hi: float
    detail: str


@dataclass(frozen=True)
class Phase0CellEvidence:
    """Per (substrate × N) evidence carrying all three checks."""

    substrate_id: str
    N: int
    phase_0a: Phase0aResult
    phase_0b: Phase0bResult
    phase_0c: Phase0cResult
    all_passed: bool


@dataclass(frozen=True)
class Phase0Verdict:
    """Aggregate verdict over a (substrate × N) grid."""

    verdict: str  # "PASS" | "FAIL"
    cell_evidence: tuple[Phase0CellEvidence, ...]
    fallback_recommendation: str  # "" if PASS; "M2" if FAIL
    metric_id: str
    base_seed: int
    null_seed_offset: int
    n_seeds: int
    n_shuffles: int
    t_threshold: float
    p_lo: float
    p_hi: float
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Adapter helpers
# ---------------------------------------------------------------------------


def _resolve_substrate(substrate_or_id: Substrate | str) -> Substrate:
    if isinstance(substrate_or_id, str):
        if substrate_or_id not in SUBSTRATE_BY_ID:
            raise Phase0Invalid(
                f"unknown substrate_id {substrate_or_id!r}; available={sorted(SUBSTRATE_BY_ID)}"
            )
        return SUBSTRATE_BY_ID[substrate_or_id]
    return substrate_or_id


def _resolve_metric(metric_or_id: Metric | str) -> Metric:
    if isinstance(metric_or_id, str):
        if metric_or_id not in METRIC_BY_ID:
            raise Phase0Invalid(
                f"unknown metric_id {metric_or_id!r}; available={sorted(METRIC_BY_ID)}"
            )
        return METRIC_BY_ID[metric_or_id]
    return metric_or_id


def _broadcast_to_trajectory(K_static: NDArray[np.float64], *, T: int) -> NDArray[np.float64]:
    """Broadcast an N×N matrix to a (T, N, N) trajectory for the integrator."""
    return np.broadcast_to(K_static[None, :, :], (T, K_static.shape[0], K_static.shape[1])).astype(
        np.float64
    )


def _metric_value_for_null_K(
    *,
    K_null: NDArray[np.float64],
    metric: Metric,
    seed: int,
    steps_per_quarter: int,
    omega_gamma: float,
    T: int,
) -> float:
    """Run ``simulate_kuramoto`` on the null K and return ``metric.value``."""
    traj = simulate_kuramoto(
        _broadcast_to_trajectory(K_null, T=T),
        seed=int(seed),
        steps_per_quarter=int(steps_per_quarter),
        omega_gamma=float(omega_gamma),
    )
    return float(metric.evaluate(traj).value)


# ---------------------------------------------------------------------------
# Phase 0a — bit-identity broken
# ---------------------------------------------------------------------------


def check_phase_0a(
    substrate: Substrate,
    *,
    N: int,
    base_seed: int = PHASE0_BASE_SEED,
) -> Phase0aResult:
    """Phase 0a: verify M1 null is NOT bit-identical to the precursor.

    Procedure:
      1. Realise precursor at ``(N, lambda=0, base_seed)``.
      2. Realise M1 null at ``(N, lambda=0)`` via :func:`realize_null`.
      3. Assert ``not np.array_equal(K_precursor, K_null)``.

    PASS iff the two matrices differ.
    """
    precursor_real = substrate.realize(N=int(N), lambda_=0.0, seed=int(base_seed))
    K_p = np.asarray(precursor_real.K_baseline[0], dtype=np.float64)

    try:
        null_real = realize_null(
            substrate,
            strategy="M1_INDEPENDENT_SEED",
            base_seed=int(base_seed),
            N=int(N),
            lambda_value=0.0,
        )
    except BitIdenticalNullError as exc:
        return Phase0aResult(
            substrate_id=substrate.id,
            N=int(N),
            passed=False,
            array_equal=True,
            base_seed=int(base_seed),
            null_seed=int(base_seed) + NULL_SEED_OFFSET,
            detail=(
                f"BitIdenticalNullError at Phase 0a: {exc}. "
                "Substrate is M1-INELIGIBLE at this (N, lambda=0)."
            ),
        )

    equal = bool(np.array_equal(K_p, null_real.K_baseline))
    return Phase0aResult(
        substrate_id=substrate.id,
        N=int(N),
        passed=not equal,
        array_equal=equal,
        base_seed=int(base_seed),
        null_seed=int(null_real.null_seed),
        detail=(
            "K_precursor == K_null bit-identically — pathology preserved"
            if equal
            else "bit-identity broken (M1 OK)"
        ),
    )


# ---------------------------------------------------------------------------
# Phase 0b — H0 preserved (paired null-vs-null t-test)
# ---------------------------------------------------------------------------


def _draw_phase0_paired_arrays(
    substrate: Substrate,
    *,
    N: int,
    n_seeds: int,
    metric: Metric,
    steps_per_quarter: int,
    omega_gamma: float,
    T: int,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """50-seed paired (precursor-null-cohort, null-null-cohort) metric arrays.

    Both arrays measure the metric on the LAMBDA=0 baseline cohort.
    Array A uses the standard substrate seed; array B uses the M1
    independent-seed offset. Under H0 (no precursor effect at λ=0)
    the per-seed paired differences should distribute around 0.

    Returns (precursor_array, null_array) of shape ``(n_seeds,)``.
    """
    p_vals = np.empty(int(n_seeds), dtype=np.float64)
    n_vals = np.empty(int(n_seeds), dtype=np.float64)
    for s in range(int(n_seeds)):
        # "precursor" leg at λ=0 = the substrate's baseline draw under
        # the standard seed (this is what the canonical sweep ALSO
        # produces at λ=0).
        real_p = substrate.realize(N=int(N), lambda_=0.0, seed=int(s))
        K_p = np.asarray(real_p.K_baseline[0], dtype=np.float64)
        p_vals[s] = _metric_value_for_null_K(
            K_null=K_p,
            metric=metric,
            seed=int(s),
            steps_per_quarter=steps_per_quarter,
            omega_gamma=omega_gamma,
            T=T,
        )

        # "null" leg at λ=0 = the M1 independent-seed offset cohort.
        try:
            null_real = realize_null(
                substrate,
                strategy="M1_INDEPENDENT_SEED",
                base_seed=int(s),
                N=int(N),
                lambda_value=0.0,
            )
        except BitIdenticalNullError:
            # Phase 0b cannot meaningfully compare if M1 is degenerate
            # here — surface as NaN so the t-test fails closed.
            n_vals[s] = float("nan")
            continue
        n_vals[s] = _metric_value_for_null_K(
            K_null=null_real.K_baseline,
            metric=metric,
            seed=int(null_real.null_seed),
            steps_per_quarter=steps_per_quarter,
            omega_gamma=omega_gamma,
            T=T,
        )
    return p_vals, n_vals


#: Strike-R3: Wilcoxon signed-rank p-value floor (H0-not-rejected gate).
PHASE0B_WILCOXON_PVALUE_FLOOR: Final[float] = 0.05

#: Strike-R3: bootstrap CI alpha (95% CI on the diff-mean).
PHASE0B_BOOTSTRAP_ALPHA: Final[float] = 0.05

#: Strike-R3: bootstrap resample count for the diff-mean CI. Cheap; the
#: per-seed metric evaluation is the dominant cost, not the bootstrap.
PHASE0B_BOOTSTRAP_N: Final[int] = 2000

#: Strike-R3: bootstrap RNG seed (deterministic).
PHASE0B_BOOTSTRAP_SEED: Final[int] = 1729


def phase0b_robust(
    diffs: NDArray[np.float64],
    *,
    wilcoxon_floor: float = PHASE0B_WILCOXON_PVALUE_FLOOR,
    bootstrap_n: int = PHASE0B_BOOTSTRAP_N,
    bootstrap_alpha: float = PHASE0B_BOOTSTRAP_ALPHA,
    bootstrap_seed: int = PHASE0B_BOOTSTRAP_SEED,
) -> tuple[bool, float, float, float, str]:
    """Strike-R3 robust Phase 0b test on a paired-diff vector.

    Returns
    -------
    (passed, wilcoxon_p, ci_lo, ci_hi, detail)
        * ``passed`` is True iff Wilcoxon p > wilcoxon_floor AND the
          (1-alpha) percentile bootstrap CI on the mean contains 0.

    Both arms of the conjunction must hold. Failing either is failing
    H0-preservation; we do NOT mix the conjunction into a fudged
    threshold, fail-closed.
    """
    arr = np.asarray(diffs, dtype=np.float64)
    if arr.size < 2:
        return (False, float("nan"), float("nan"), float("nan"), "n_diffs < 2")
    # Wilcoxon: zero-diffs require ``zero_method`` to keep scipy happy.
    if float(np.all(arr == 0.0)):
        # All zeros: H0 trivially holds, but no power. Mark passed with
        # detail.
        return (True, 1.0, 0.0, 0.0, "all-zero diffs (degenerate, passes)")
    try:
        wilc = _scipy_stats.wilcoxon(arr, zero_method="wilcox", alternative="two-sided")
        p_w = float(wilc.pvalue)
    except (ValueError, RuntimeError):  # pragma: no cover - defensive
        p_w = float("nan")

    rng = np.random.default_rng(int(bootstrap_seed))
    boot_idx = rng.integers(0, arr.size, size=(int(bootstrap_n), arr.size))
    boot_means = arr[boot_idx].mean(axis=1)
    lo = float(np.quantile(boot_means, bootstrap_alpha / 2.0))
    hi = float(np.quantile(boot_means, 1.0 - bootstrap_alpha / 2.0))
    ci_contains_zero = lo <= 0.0 <= hi
    wilc_pass = math.isfinite(p_w) and p_w > float(wilcoxon_floor)
    passed = bool(wilc_pass and ci_contains_zero)
    detail_parts: list[str] = []
    if not wilc_pass:
        detail_parts.append(f"wilcoxon p={p_w:.4f} ≤ {wilcoxon_floor}")
    if not ci_contains_zero:
        detail_parts.append(f"bootstrap CI [{lo:.4e}, {hi:.4e}] excludes 0")
    detail = "; ".join(detail_parts) if detail_parts else "H0 preserved (Wilcoxon + CI)"
    return (passed, p_w, lo, hi, detail)


def check_phase_0b(
    substrate: Substrate,
    *,
    N: int,
    metric_id: str = DEFAULT_PHASE0_METRIC_ID,
    n_seeds: int = PHASE0_N_SEEDS,
    t_threshold: float = PHASE0_T_THRESHOLD,
    steps_per_quarter: int = DEFAULT_STEPS_PER_QUARTER,
    omega_gamma: float = DEFAULT_OMEGA_GAMMA,
) -> Phase0bResult:
    """Phase 0b: paired null-vs-null robust test (Wilcoxon + bootstrap CI).

    Strike-R3 hardening: the prereg locks ``t_threshold=2.0`` as a
    DIAGNOSTIC (still emitted), but verdict-grade PASS requires the
    Wilcoxon signed-rank and bootstrap-CI gates from
    :func:`phase0b_robust` — both tighter than the t-test on the
    bounded/right-censored metrics this module operates on.
    """
    metric = _resolve_metric(metric_id)
    # T_HORIZON is fixed at 8 in the substrate API; pull it from a
    # one-time realisation rather than re-importing the constant
    # (keeps coupling shallow).
    probe = substrate.realize(N=int(N), lambda_=0.0, seed=0)
    T = int(probe.K_baseline.shape[0])

    p_vals, n_vals = _draw_phase0_paired_arrays(
        substrate,
        N=int(N),
        n_seeds=int(n_seeds),
        metric=metric,
        steps_per_quarter=steps_per_quarter,
        omega_gamma=omega_gamma,
        T=T,
    )
    diffs = p_vals - n_vals
    finite_mask = np.isfinite(diffs)
    if int(np.count_nonzero(finite_mask)) < 2:
        return Phase0bResult(
            substrate_id=substrate.id,
            N=int(N),
            passed=False,
            n_seeds=int(n_seeds),
            t_statistic=float("nan"),
            mean_diff=float("nan"),
            std_diff=float("nan"),
            threshold=float(t_threshold),
            detail="insufficient finite paired differences (M1-INELIGIBLE)",
        )
    diffs_finite = diffs[finite_mask]
    mean_diff = float(np.mean(diffs_finite))
    std_diff = float(np.std(diffs_finite, ddof=1))
    # Diagnostic t-statistic (NOT in verdict path — Strike-R3).
    if std_diff <= 0.0 or not math.isfinite(std_diff):
        t_stat_diag = 0.0 if mean_diff == 0.0 else math.inf
    else:
        t_stat_diag = abs(mean_diff) / (std_diff / math.sqrt(float(diffs_finite.size)))
    # Strike-R3: verdict-grade test = Wilcoxon + bootstrap CI on mean.
    rob_passed, wilc_p, boot_lo, boot_hi, rob_detail = phase0b_robust(diffs_finite)
    return Phase0bResult(
        substrate_id=substrate.id,
        N=int(N),
        passed=bool(rob_passed),
        n_seeds=int(diffs_finite.size),
        t_statistic=float(t_stat_diag),
        mean_diff=mean_diff,
        std_diff=std_diff,
        threshold=float(t_threshold),
        detail=rob_detail,
        wilcoxon_pvalue=float(wilc_p),
        wilcoxon_pvalue_floor=float(PHASE0B_WILCOXON_PVALUE_FLOOR),
        bootstrap_ci_lo=float(boot_lo),
        bootstrap_ci_hi=float(boot_hi),
    )


# ---------------------------------------------------------------------------
# Phase 0c — permutation discriminability non-trivial
# ---------------------------------------------------------------------------


# Strike-R4: Phase 0c range check is necessary but not sufficient. A
# uniform-p degenerate null passes the (0.05, 0.95) band while being
# powerless. ``phase0c_power_calibration`` injects a known δ=0.1·σ
# shift into one arm and measures detection rate at α=0.05 over
# bootstrap replicates of the cohort. Caller can require detection rate
# above a floor (default 0.5) — explicit power gate, not range mask.
PHASE0C_POWER_DELTA_OVER_SIGMA: Final[float] = 0.10
PHASE0C_POWER_FLOOR: Final[float] = 0.50
PHASE0C_POWER_N_REPLICATES: Final[int] = 200
PHASE0C_POWER_SEED: Final[int] = 137


def phase0c_power_calibration(
    p_vals: NDArray[np.float64],
    n_vals: NDArray[np.float64],
    *,
    delta_over_sigma: float = PHASE0C_POWER_DELTA_OVER_SIGMA,
    n_replicates: int = PHASE0C_POWER_N_REPLICATES,
    n_shuffles: int = 200,
    rng_seed: int = PHASE0C_POWER_SEED,
    alpha: float = 0.05,
) -> float:
    """Strike-R4: empirical detection rate when a δ shift is injected.

    Parameters
    ----------
    p_vals, n_vals
        Original paired null-vs-null arrays at λ=0 (same shape).
    delta_over_sigma
        Shift magnitude as a multiple of the pooled std of the cohort.
        Default 0.1 (a SMALL effect — a higher detection rate means the
        permutation audit has more power than the threshold needs).
    n_replicates
        Number of bootstrap resamples of the cohort to estimate the
        detection rate. 200 is enough to resolve a power floor at 0.5.
    n_shuffles
        Inner-loop permutation shuffles per replicate. We use a small
        count (200) so the calibration is cheap; resolution 1/200 is
        sufficient for the α=0.05 boundary.
    rng_seed
        Deterministic seed.
    alpha
        Significance threshold for "detected" (one-sided lower tail of
        the permutation p-value).

    Returns
    -------
    detection_rate
        Fraction of bootstrap replicates where the permutation p-value
        was strictly less than ``alpha``.
    """
    p_arr = np.asarray(p_vals, dtype=np.float64)
    n_arr = np.asarray(n_vals, dtype=np.float64)
    if p_arr.shape != n_arr.shape:
        raise Phase0Invalid(
            f"phase0c_power_calibration: paired array shape mismatch "
            f"p={p_arr.shape} n={n_arr.shape}"
        )
    if p_arr.ndim != 1 or p_arr.size < 2:
        raise Phase0Invalid(
            f"phase0c_power_calibration: arrays must be 1-D with size>=2; got {p_arr.shape}"
        )
    pooled_sd = max(
        float(np.std(p_arr, ddof=1)),
        float(np.std(n_arr, ddof=1)),
        1e-12,
    )
    shift = float(delta_over_sigma) * pooled_sd
    rng = np.random.default_rng(int(rng_seed))
    n_seeds_local = p_arr.size
    n_detected = 0
    for r in range(int(n_replicates)):
        # Bootstrap resample preserving pairing.
        idx = rng.integers(0, n_seeds_local, size=n_seeds_local)
        p_r = p_arr[idx] + shift  # δ injected on the "precursor" arm
        n_r = n_arr[idx]
        # Inner permutation test on the (shifted) replicate.
        audit = run_null_audit(
            p_r,
            n_r,
            n_shuffles=int(n_shuffles),
            rng_seed=int(rng_seed) ^ (r + 1),
            p_value_threshold=float(alpha),
        )
        if float(audit.p_value_empirical) < float(alpha):
            n_detected += 1
    return float(n_detected) / float(n_replicates)


def check_phase_0c(
    substrate: Substrate,
    *,
    N: int,
    metric_id: str = DEFAULT_PHASE0_METRIC_ID,
    n_seeds: int = PHASE0_N_SEEDS,
    n_shuffles: int = PHASE0_N_SHUFFLES,
    p_lo: float = PHASE0_P_LO,
    p_hi: float = PHASE0_P_HI,
    rng_seed: int = PHASE0_NULL_AUDIT_SEED,
    steps_per_quarter: int = DEFAULT_STEPS_PER_QUARTER,
    omega_gamma: float = DEFAULT_OMEGA_GAMMA,
) -> Phase0cResult:
    """Phase 0c: ``run_null_audit`` p-value envelope check.

    Runs the 1000-shuffle permutation audit on the 50-seed paired
    null-vs-null arrays. PASS iff ``p_lo < p_value_empirical < p_hi``
    (default envelope (0.05, 0.95) — refuses both pathological
    collapse to 0/1 and degenerate flat distributions).
    """
    metric = _resolve_metric(metric_id)
    probe = substrate.realize(N=int(N), lambda_=0.0, seed=0)
    T = int(probe.K_baseline.shape[0])

    p_vals, n_vals = _draw_phase0_paired_arrays(
        substrate,
        N=int(N),
        n_seeds=int(n_seeds),
        metric=metric,
        steps_per_quarter=steps_per_quarter,
        omega_gamma=omega_gamma,
        T=T,
    )
    finite_mask = np.isfinite(p_vals) & np.isfinite(n_vals)
    if int(np.count_nonzero(finite_mask)) < 2:
        return Phase0cResult(
            substrate_id=substrate.id,
            N=int(N),
            passed=False,
            n_shuffles=int(n_shuffles),
            p_value_empirical=float("nan"),
            p_lo=float(p_lo),
            p_hi=float(p_hi),
            detail="insufficient finite paired arrays (M1-INELIGIBLE)",
        )
    audit = run_null_audit(
        p_vals[finite_mask],
        n_vals[finite_mask],
        n_shuffles=int(n_shuffles),
        rng_seed=int(rng_seed),
        # ``p_value_threshold`` is the PASS/FAIL boundary for the
        # main null audit but Phase 0c uses a two-sided envelope
        # check on the raw p-value field. We pass the default to
        # keep the audit happy and read p_value_empirical ourselves.
        p_value_threshold=0.05,
    )
    p_emp = float(audit.p_value_empirical)
    passed = float(p_lo) < p_emp < float(p_hi)
    return Phase0cResult(
        substrate_id=substrate.id,
        N=int(N),
        passed=bool(passed),
        n_shuffles=int(audit.n_shuffles),
        p_value_empirical=p_emp,
        p_lo=float(p_lo),
        p_hi=float(p_hi),
        detail=(
            f"p_emp={p_emp:.4f} inside ({p_lo}, {p_hi})"
            if passed
            else f"p_emp={p_emp:.4f} outside ({p_lo}, {p_hi}) — "
            "permutation discriminability pathological"
        ),
    )


# ---------------------------------------------------------------------------
# Per-cell aggregate
# ---------------------------------------------------------------------------


def verify_cell(
    substrate: Substrate | str,
    *,
    N: int,
    metric_id: str = DEFAULT_PHASE0_METRIC_ID,
    base_seed: int = PHASE0_BASE_SEED,
    n_seeds: int = PHASE0_N_SEEDS,
    n_shuffles: int = PHASE0_N_SHUFFLES,
    t_threshold: float = PHASE0_T_THRESHOLD,
    p_lo: float = PHASE0_P_LO,
    p_hi: float = PHASE0_P_HI,
    steps_per_quarter: int = DEFAULT_STEPS_PER_QUARTER,
    omega_gamma: float = DEFAULT_OMEGA_GAMMA,
) -> Phase0CellEvidence:
    """Run all three Phase 0 checks for one (substrate × N) cell."""
    sub = _resolve_substrate(substrate)
    a = check_phase_0a(sub, N=int(N), base_seed=int(base_seed))
    b = check_phase_0b(
        sub,
        N=int(N),
        metric_id=str(metric_id),
        n_seeds=int(n_seeds),
        t_threshold=float(t_threshold),
        steps_per_quarter=int(steps_per_quarter),
        omega_gamma=float(omega_gamma),
    )
    c = check_phase_0c(
        sub,
        N=int(N),
        metric_id=str(metric_id),
        n_seeds=int(n_seeds),
        n_shuffles=int(n_shuffles),
        p_lo=float(p_lo),
        p_hi=float(p_hi),
        steps_per_quarter=int(steps_per_quarter),
        omega_gamma=float(omega_gamma),
    )
    return Phase0CellEvidence(
        substrate_id=sub.id,
        N=int(N),
        phase_0a=a,
        phase_0b=b,
        phase_0c=c,
        all_passed=bool(a.passed and b.passed and c.passed),
    )


# ---------------------------------------------------------------------------
# Aggregate verifier
# ---------------------------------------------------------------------------


def verify_phase_0(
    cells: list[tuple[str, int]],
    *,
    metric_id: str = DEFAULT_PHASE0_METRIC_ID,
    base_seed: int = PHASE0_BASE_SEED,
    n_seeds: int = PHASE0_N_SEEDS,
    n_shuffles: int = PHASE0_N_SHUFFLES,
    t_threshold: float = PHASE0_T_THRESHOLD,
    p_lo: float = PHASE0_P_LO,
    p_hi: float = PHASE0_P_HI,
    steps_per_quarter: int = DEFAULT_STEPS_PER_QUARTER,
    omega_gamma: float = DEFAULT_OMEGA_GAMMA,
    metadata_extra: dict[str, Any] | None = None,
) -> Phase0Verdict:
    """Run Phase 0 verification over a (substrate_id, N) cell grid.

    ALL cells must pass 0a + 0b + 0c → verdict PASS. Any single FAIL →
    verdict FAIL with ``fallback_recommendation='M2'`` per the
    pre-registration §4 fallback policy.
    """
    evidence: list[Phase0CellEvidence] = []
    for substrate_id, N in cells:
        try:
            ev = verify_cell(
                substrate_id,
                N=int(N),
                metric_id=str(metric_id),
                base_seed=int(base_seed),
                n_seeds=int(n_seeds),
                n_shuffles=int(n_shuffles),
                t_threshold=float(t_threshold),
                p_lo=float(p_lo),
                p_hi=float(p_hi),
                steps_per_quarter=int(steps_per_quarter),
                omega_gamma=float(omega_gamma),
            )
        except SubstrateInvalid as exc:
            # A substrate that refuses the cell parameters surfaces as
            # FAIL with an explanatory detail; we never silently skip.
            ev = Phase0CellEvidence(
                substrate_id=str(substrate_id),
                N=int(N),
                phase_0a=Phase0aResult(
                    substrate_id=str(substrate_id),
                    N=int(N),
                    passed=False,
                    array_equal=False,
                    base_seed=int(base_seed),
                    null_seed=int(base_seed) + NULL_SEED_OFFSET,
                    detail=f"SubstrateInvalid: {exc}",
                ),
                phase_0b=Phase0bResult(
                    substrate_id=str(substrate_id),
                    N=int(N),
                    passed=False,
                    n_seeds=int(n_seeds),
                    t_statistic=float("nan"),
                    mean_diff=float("nan"),
                    std_diff=float("nan"),
                    threshold=float(t_threshold),
                    detail=f"SubstrateInvalid: {exc}",
                ),
                phase_0c=Phase0cResult(
                    substrate_id=str(substrate_id),
                    N=int(N),
                    passed=False,
                    n_shuffles=int(n_shuffles),
                    p_value_empirical=float("nan"),
                    p_lo=float(p_lo),
                    p_hi=float(p_hi),
                    detail=f"SubstrateInvalid: {exc}",
                ),
                all_passed=False,
            )
        evidence.append(ev)

    all_passed = all(ev.all_passed for ev in evidence) and len(evidence) > 0
    verdict_str = "PASS" if all_passed else "FAIL"
    fallback = "" if all_passed else "M2"

    return Phase0Verdict(
        verdict=verdict_str,
        cell_evidence=tuple(evidence),
        fallback_recommendation=fallback,
        metric_id=str(metric_id),
        base_seed=int(base_seed),
        null_seed_offset=int(NULL_SEED_OFFSET),
        n_seeds=int(n_seeds),
        n_shuffles=int(n_shuffles),
        t_threshold=float(t_threshold),
        p_lo=float(p_lo),
        p_hi=float(p_hi),
        metadata=dict(metadata_extra or {}),
    )


__all__ = [
    "DEFAULT_PHASE0_METRIC_ID",
    "PHASE0_BASE_SEED",
    "PHASE0_N_SEEDS",
    "PHASE0_N_SHUFFLES",
    "PHASE0_NULL_AUDIT_SEED",
    "PHASE0_P_HI",
    "PHASE0_P_LO",
    "PHASE0_T_THRESHOLD",
    "Phase0CellEvidence",
    "Phase0Invalid",
    "Phase0Verdict",
    "Phase0aResult",
    "Phase0bResult",
    "Phase0cResult",
    "check_phase_0a",
    "check_phase_0b",
    "check_phase_0c",
    "verify_cell",
    "verify_phase_0",
]
