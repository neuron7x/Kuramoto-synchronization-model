# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C C2.4-B — Negative-control (false-positive) pre-flight gate.

Mission
=======
Before the 69 120-cell sweep launches, prove the pipeline does
NOT raise the alarm where there is **no signal by construction**.
For each (substrate, metric, N) at λ=0 (no precursor anywhere)
draw ``n_seeds`` independent realisations, integrate two
Kuramoto trajectories on ``K_baseline`` with independent
integrator seeds, take per-seed metric differences, and check
that the empirical false-positive rate at the Bonferroni-
corrected significance bound does not exceed
``alpha_bonferroni + tolerance``.

A cell that exceeds the FPR bound is **EXCLUDED** — it would
generate false alarms in the sweep, and any "signal" it
reported could not be trusted. The verdict's
``excluded_cells`` list is the gate output the sweep runner
consumes.

Bonferroni discipline
=====================
The full sweep has 216 ``(substrate × metric × N × λ)`` cells.
The family-wise α at the standard 0.05 single-hypothesis
threshold gives a Bonferroni-corrected per-cell bound of
``0.05 / 216 ≈ 2.31e-4``. The neg-control gate uses this
exact value as the **target FPR**; a cell whose empirical
FPR exceeds ``α_b + tolerance`` (tolerance default 1e-3,
generous to absorb small-sample noise at n_seeds=50) is
excluded.

z-test FPR calculation
======================
Per seed, the null distribution of the metric difference has
unknown variance. We compute the cohort's sample std with
``ddof=1`` and form per-seed z-scores

    z_i = (diff_i - mean(diffs)) / std(diffs)

A seed is a "false positive" iff ``|z_i| > Φ^{-1}(1 - α_b / 2)``,
the two-sided Bonferroni-corrected critical value. The
empirical FPR is the fraction of false-positive seeds.
Under the null, this fraction converges to α_b as
``n_seeds → ∞``; finite-sample noise is absorbed by
``tolerance``.

Strict scope
============
Pre-flight gate ONLY. NO sweep launch. NO claim layer. NO
threshold tuning. The verdict is the gate input the sweep
runner reads; the gate emits no claim of its own.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

from .d002c_kuramoto import (
    DEFAULT_OMEGA_GAMMA,
    DEFAULT_STEPS_PER_QUARTER,
    simulate_kuramoto,
)
from .d002c_metrics import (
    ALL_METRICS,
    Metric,
)
from .d002c_substrates import (
    ALL_SUBSTRATES,
    Substrate,
)

# ---------------------------------------------------------------------------
# Locked defaults — match the D-002C C2.4 negative-control contract.
# 0.05 / 216 = 2.314814...e-4 — Bonferroni at the sweep family size.
# ---------------------------------------------------------------------------
DEFAULT_NEG_N_SEEDS: Final[int] = 50
DEFAULT_NEG_LAMBDA: Final[float] = 0.0  # locked: no precursor anywhere
DEFAULT_NEG_ALPHA_BONFERRONI: Final[float] = 2.31e-4  # 0.05 / 216
DEFAULT_NEG_TOLERANCE: Final[float] = 1e-3
DEFAULT_NEG_RNG_SEED_BASE: Final[int] = 42
# Large prime offset to decorrelate the second integrator stream
# from the first while keeping reproducibility under the same
# rng_seed_base.
DEFAULT_NEG_INDEPENDENT_SEED_STRIDE: Final[int] = 10_000
# Pre-registered N grid for the sweep.
DEFAULT_NEG_N_GRID: Final[tuple[int, ...]] = (50, 100, 200)


class NegControlInvalid(RuntimeError):
    """Bad input to the negative-control gate."""


@dataclass(frozen=True)
class NegControlCellResult:
    """Per-cell negative-control result.

    ``fpr`` is the load-bearing field. The verdict is ``"PASS"``
    iff ``fpr <= alpha_bonferroni + threshold_tolerance``;
    otherwise ``"EXCLUDE"`` and the sweep runner skips the cell.
    """

    substrate_id: str
    metric_id: str
    N: int
    lambda_: float
    n_seeds: int
    false_positive_count: int
    fpr: float
    alpha_bonferroni: float
    threshold_tolerance: float
    verdict: str  # "PASS" | "EXCLUDE"
    wallclock_seconds: float
    sha256: str


@dataclass(frozen=True)
class NegControlVerdict:
    """Aggregate over all (substrate × metric × N) cells."""

    all_pass: bool
    n_pass: int
    n_exclude: int
    excluded_cells: tuple[tuple[str, str, int], ...]
    results: tuple[NegControlCellResult, ...]
    sha256: str
    generated_at: str
    wallclock_seconds: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _capsule_sha256(payload: dict[str, Any]) -> str:
    """SHA-256 over the validator's exact canonical form.

    See :func:`research.systemic_risk.d002c_pos_control._capsule_sha256`
    for the contract — both writers MUST use the same formula or the
    preflight validator refuses launch with ``capsule_sha256_mismatch``.

    The :func:`canonical_preflight_json` import is deferred to the
    function body to break the circular import between
    :mod:`d002c_preflight` (which imports
    :data:`DEFAULT_NEG_N_GRID` from this module) and this module.
    """
    from .d002c_preflight import canonical_preflight_json

    return hashlib.sha256(canonical_preflight_json(payload).encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    """tmp + fsync + os.replace; orphan-tmp cleanup on any exception."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, sort_keys=True, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _phi_inv(p: float) -> float:
    """Inverse standard-normal CDF (probit). Beasley-Springer-Moro
    rational approximation good to ~1e-9 over (0, 1)."""
    if not (0.0 < p < 1.0):
        raise NegControlInvalid(f"_phi_inv argument must be in (0, 1); got {p}")
    # Coefficients from Peter Acklam's algorithm (public domain).
    a = (
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    )
    b = (
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    )
    c = (
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    )
    d = (
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    )
    p_low = 0.02425
    p_high = 1.0 - p_low
    if p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if p <= p_high:
        q = p - 0.5
        r = q * q
        return (
            (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
            * q
            / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
        )
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
    )


def _bonferroni_critical_value(alpha_bonferroni: float) -> float:
    """Two-sided z-critical value at the Bonferroni-corrected α.

    z_crit = Φ^{-1}(1 - α_b / 2).
    """
    if not math.isfinite(alpha_bonferroni) or not (0.0 < alpha_bonferroni < 1.0):
        raise NegControlInvalid(f"alpha_bonferroni must be in (0, 1); got {alpha_bonferroni}")
    return _phi_inv(1.0 - alpha_bonferroni / 2.0)


def _per_seed_diff(
    *,
    substrate: Substrate,
    metric: Metric,
    N: int,
    seed: int,
    independent_seed_stride: int,
    steps_per_quarter: int,
    omega_gamma: float,
) -> float:
    """One null-vs-null per-seed difference.

    Both integrations use ``K_baseline`` (λ=0 ⇒ K_precursor ==
    K_baseline anyway); the two integrator seeds differ by a
    large prime offset so the ω + θ(0) draws are independent.
    The metric difference is pure noise.
    """
    r = substrate.realize(N=N, lambda_=0.0, seed=seed)
    traj_a = simulate_kuramoto(
        r.K_baseline,
        seed=seed,
        steps_per_quarter=steps_per_quarter,
        omega_gamma=omega_gamma,
    )
    traj_b = simulate_kuramoto(
        r.K_baseline,
        seed=seed + independent_seed_stride,
        steps_per_quarter=steps_per_quarter,
        omega_gamma=omega_gamma,
    )
    return float(metric.evaluate(traj_a).value) - float(metric.evaluate(traj_b).value)


# ---------------------------------------------------------------------------
# Per-cell gate
# ---------------------------------------------------------------------------


def run_neg_control_cell(
    substrate: Substrate,
    metric: Metric,
    *,
    N: int,
    n_seeds: int = DEFAULT_NEG_N_SEEDS,
    rng_seed_base: int = DEFAULT_NEG_RNG_SEED_BASE,
    alpha_bonferroni: float = DEFAULT_NEG_ALPHA_BONFERRONI,
    tolerance: float = DEFAULT_NEG_TOLERANCE,
    steps_per_quarter: int = DEFAULT_STEPS_PER_QUARTER,
    omega_gamma: float = DEFAULT_OMEGA_GAMMA,
    independent_seed_stride: int = DEFAULT_NEG_INDEPENDENT_SEED_STRIDE,
) -> NegControlCellResult:
    """Run the negative-control gate on one (substrate, metric, N) cell.

    Protocol
    --------
    For seed in ``[rng_seed_base, rng_seed_base + n_seeds)``:

      1. Realise the substrate at ``(N, λ=0, seed)``.
      2. Integrate Kuramoto twice on ``K_baseline``; second
         integrator seed offset by a large prime so the two
         draws are independent.
      3. Per-seed signal = ``metric_a - metric_b`` — pure noise.

    Aggregation
    -----------
    Compute the cohort's sample mean and ``ddof=1`` std. The
    per-seed z-score is ``(diff_i - mean) / std``. A seed
    counts as a false positive iff ``|z_i| > z_crit`` where
    ``z_crit = Φ^{-1}(1 - α_b / 2)``.

    Verdict
    -------
    ``"PASS"`` iff ``fpr <= α_b + tolerance``, else
    ``"EXCLUDE"``.

    Raises
    ------
    NegControlInvalid
        On ``n_seeds < 2``, ``N < 2``, non-positive ``tolerance``,
        or ``alpha_bonferroni`` outside ``(0, 1)``.
    """
    if n_seeds < 2:
        raise NegControlInvalid(f"n_seeds must be >= 2 (need ddof=1 std); got {n_seeds}")
    if N < 2:
        raise NegControlInvalid(f"N must be >= 2; got {N}")
    if not math.isfinite(tolerance) or tolerance < 0.0:
        raise NegControlInvalid(f"tolerance must be finite and >= 0; got {tolerance}")
    if not math.isfinite(alpha_bonferroni) or not (0.0 < alpha_bonferroni < 1.0):
        raise NegControlInvalid(f"alpha_bonferroni must be in (0, 1); got {alpha_bonferroni}")

    t0 = time.monotonic()
    diffs: NDArray[np.float64] = np.empty(n_seeds, dtype=np.float64)
    for i in range(n_seeds):
        seed = rng_seed_base + i
        diffs[i] = _per_seed_diff(
            substrate=substrate,
            metric=metric,
            N=N,
            seed=seed,
            independent_seed_stride=independent_seed_stride,
            steps_per_quarter=steps_per_quarter,
            omega_gamma=omega_gamma,
        )

    mean = float(diffs.mean())
    std = float(np.std(diffs, ddof=1))
    z_crit = _bonferroni_critical_value(alpha_bonferroni)
    if std <= 0.0 or not math.isfinite(std):
        # Degenerate null distribution: every realisation produced
        # the same diff. The neg-control's purpose is to detect false
        # alarms — with zero variance the threshold cannot be
        # crossed by definition, so FPR == 0.
        false_positive_count = 0
    else:
        z_scores = np.abs((diffs - mean) / std)
        false_positive_count = int(np.sum(z_scores > z_crit))
    fpr = float(false_positive_count) / float(n_seeds)
    verdict = "PASS" if fpr <= alpha_bonferroni + tolerance else "EXCLUDE"
    wall = time.monotonic() - t0

    payload: dict[str, Any] = {
        "substrate_id": substrate.id,
        "metric_id": metric.id,
        "N": N,
        "lambda_": DEFAULT_NEG_LAMBDA,
        "n_seeds": n_seeds,
        "false_positive_count": false_positive_count,
        "fpr": fpr,
        "alpha_bonferroni": alpha_bonferroni,
        "threshold_tolerance": tolerance,
        "verdict": verdict,
        "rng_seed_base": rng_seed_base,
        "steps_per_quarter": steps_per_quarter,
        "omega_gamma": omega_gamma,
        "independent_seed_stride": independent_seed_stride,
    }
    # Per-cell sha uses the validator's canonical form for
    # forward-safety (no non-finite fields at present, but the
    # validator's _sanitize is the single source of truth).
    sha = _capsule_sha256(payload)
    return NegControlCellResult(
        substrate_id=substrate.id,
        metric_id=metric.id,
        N=N,
        lambda_=DEFAULT_NEG_LAMBDA,
        n_seeds=n_seeds,
        false_positive_count=false_positive_count,
        fpr=fpr,
        alpha_bonferroni=alpha_bonferroni,
        threshold_tolerance=tolerance,
        verdict=verdict,
        wallclock_seconds=wall,
        sha256=sha,
    )


# ---------------------------------------------------------------------------
# Full grid
# ---------------------------------------------------------------------------


def _result_to_dict(r: NegControlCellResult) -> dict[str, Any]:
    return {
        "substrate_id": r.substrate_id,
        "metric_id": r.metric_id,
        "N": r.N,
        "lambda_": r.lambda_,
        "n_seeds": r.n_seeds,
        "false_positive_count": r.false_positive_count,
        "fpr": r.fpr,
        "alpha_bonferroni": r.alpha_bonferroni,
        "threshold_tolerance": r.threshold_tolerance,
        "verdict": r.verdict,
        "wallclock_seconds": r.wallclock_seconds,
        "sha256": r.sha256,
    }


def run_neg_control_all(
    substrates: tuple[Substrate, ...] = ALL_SUBSTRATES,
    metrics: tuple[Metric, ...] = ALL_METRICS,
    *,
    N_grid: tuple[int, ...] = DEFAULT_NEG_N_GRID,
    n_seeds: int = DEFAULT_NEG_N_SEEDS,
    rng_seed_base: int = DEFAULT_NEG_RNG_SEED_BASE,
    alpha_bonferroni: float = DEFAULT_NEG_ALPHA_BONFERRONI,
    tolerance: float = DEFAULT_NEG_TOLERANCE,
    steps_per_quarter: int = DEFAULT_STEPS_PER_QUARTER,
    omega_gamma: float = DEFAULT_OMEGA_GAMMA,
    independent_seed_stride: int = DEFAULT_NEG_INDEPENDENT_SEED_STRIDE,
    output_path: Path | None = None,
) -> NegControlVerdict:
    """Run the neg-control gate over the full substrate × metric × N grid.

    Writes an atomic JSON capsule when ``output_path`` is given;
    returns the verdict regardless. The verdict carries the
    load-bearing ``excluded_cells`` list (each
    ``(substrate_id, metric_id, N)`` triple whose cell failed).
    """
    if not substrates:
        raise NegControlInvalid("substrates must be non-empty")
    if not metrics:
        raise NegControlInvalid("metrics must be non-empty")
    if not N_grid:
        raise NegControlInvalid("N_grid must be non-empty")

    t0 = time.monotonic()
    results: list[NegControlCellResult] = []
    for s in substrates:
        for m in metrics:
            for N in N_grid:
                results.append(
                    run_neg_control_cell(
                        s,
                        m,
                        N=N,
                        n_seeds=n_seeds,
                        rng_seed_base=rng_seed_base,
                        alpha_bonferroni=alpha_bonferroni,
                        tolerance=tolerance,
                        steps_per_quarter=steps_per_quarter,
                        omega_gamma=omega_gamma,
                        independent_seed_stride=independent_seed_stride,
                    )
                )
    wall = time.monotonic() - t0

    n_pass = sum(1 for r in results if r.verdict == "PASS")
    n_exclude = len(results) - n_pass
    excluded_cells: tuple[tuple[str, str, int], ...] = tuple(
        (r.substrate_id, r.metric_id, r.N) for r in results if r.verdict == "EXCLUDE"
    )
    all_pass = n_exclude == 0

    generated_at = _now_iso()

    # Build the FULL capsule body (every field except ``sha256``)
    # FIRST, then sha it via the validator's canonical form so the
    # preflight round-trip succeeds. Hashing a smaller aggregate
    # dict would drift from the validator's recompute and trigger
    # ``capsule_sha256_mismatch`` refusal.
    capsule_without_sha: dict[str, Any] = {
        "kind": "d002c_neg_control_capsule_v1",
        "all_pass": all_pass,
        "n_pass": n_pass,
        "n_exclude": n_exclude,
        "excluded_cells": [list(c) for c in excluded_cells],
        "n_seeds": n_seeds,
        "N_grid": list(N_grid),
        "alpha_bonferroni": alpha_bonferroni,
        "tolerance": tolerance,
        "steps_per_quarter": steps_per_quarter,
        "omega_gamma": omega_gamma,
        "rng_seed_base": rng_seed_base,
        "independent_seed_stride": independent_seed_stride,
        "wallclock_seconds": wall,
        "results": [_result_to_dict(r) for r in results],
        "generated_at": generated_at,
        "substrate_ids": [s.id for s in substrates],
        "metric_ids": [m.id for m in metrics],
    }
    sha = _capsule_sha256(capsule_without_sha)

    if output_path is not None:
        capsule = {**capsule_without_sha, "sha256": sha}
        _atomic_write(Path(output_path), capsule)

    return NegControlVerdict(
        all_pass=all_pass,
        n_pass=n_pass,
        n_exclude=n_exclude,
        excluded_cells=excluded_cells,
        results=tuple(results),
        sha256=sha,
        generated_at=generated_at,
        wallclock_seconds=wall,
    )


__all__ = [
    "DEFAULT_NEG_N_SEEDS",
    "DEFAULT_NEG_LAMBDA",
    "DEFAULT_NEG_ALPHA_BONFERRONI",
    "DEFAULT_NEG_TOLERANCE",
    "DEFAULT_NEG_RNG_SEED_BASE",
    "DEFAULT_NEG_INDEPENDENT_SEED_STRIDE",
    "DEFAULT_NEG_N_GRID",
    "NegControlInvalid",
    "NegControlCellResult",
    "NegControlVerdict",
    "run_neg_control_cell",
    "run_neg_control_all",
]
