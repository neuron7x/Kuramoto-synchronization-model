# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C C2.4-B — Positive-control pre-flight gate for the Signal Amplification Sweep.

Mission
=======
Before the 69 120-cell sweep launches, prove the pipeline can
**detect a signal that exists by construction**. For each
(substrate, metric) combination at the upper grid corner
(default N=400, λ=1.0, the maximum-strength precursor), draw
``n_seeds`` independent realisations, compute the per-seed
signal (precursor metric value minus baseline metric value),
and require the t-statistic-form CI ratio

    signal_ci_ratio = |mean(diffs)| / (std(diffs) / √n_seeds)

to exceed a locked threshold (default ``2.0``, the C2.4
contract's POS-detection bound). Cells that fail are
**EXCLUDED** from the downstream sweep — never silently
patched. Exclusion is a first-class output of the gate; the
sweep runner consumes ``excluded_combos`` and skips those
cells rather than allow a known-blind detector through.

Right-censoring
===============
``tau_onset`` and ``phase_lag`` can be right-censored. For
those metrics the per-seed signal value uses the
:func:`d002c_metrics.signal_mean` aggregator which falls back
to the Kaplan-Meier RMST when ANY cohort observation is
censored — so a censoring asymmetry between the two cohorts
does not bias the difference. The per-cell censoring fraction
across all realisations is reported in
:attr:`PosControlCellResult.censoring_fraction` so a reviewer
can flag pathologically censored cells even when they pass
the magnitude gate.

Strict scope
============
Pre-flight gate ONLY. NO sweep launch. NO claim layer. NO
metric tuning — thresholds are read from the locked C2.4
contract via module-level :data:`DEFAULT_POS_THRESHOLD`. The
verdict is the gate input the sweep runner reads; the gate
emits no claim of its own.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import time
from collections.abc import Sequence
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
    MetricEvaluation,
    signal_mean,
)
from .d002c_preflight import canonical_preflight_json
from .d002c_substrates import (
    ALL_SUBSTRATES,
    EVENT_QUARTER,
    PRE_EVENT_START_QUARTER,
    Substrate,
)

# ---------------------------------------------------------------------------
# Locked defaults — match the D-002C C2.4 positive-control contract.
# ---------------------------------------------------------------------------
DEFAULT_POS_N: Final[int] = 400
DEFAULT_POS_LAMBDA: Final[float] = 1.0
DEFAULT_POS_N_SEEDS: Final[int] = 50
DEFAULT_POS_THRESHOLD: Final[float] = 2.0
DEFAULT_POS_RNG_SEED_BASE: Final[int] = 42


class PosControlInvalid(RuntimeError):
    """Bad input to the positive-control gate."""


@dataclass(frozen=True)
class PosControlCellResult:
    """Per-cell positive-control result.

    ``signal_ci_ratio`` is the load-bearing field. The verdict is
    ``"PASS"`` iff ``signal_ci_ratio > threshold``; otherwise the
    cell is ``"EXCLUDE"`` and the sweep runner must skip it.
    """

    substrate_id: str
    metric_id: str
    N: int
    lambda_: float
    n_seeds: int
    signal_mean: float
    signal_std: float
    signal_ci_ratio: float
    threshold: float
    verdict: str  # "PASS" | "EXCLUDE"
    censoring_fraction: float
    wallclock_seconds: float
    sha256: str


@dataclass(frozen=True)
class PosControlVerdict:
    """Aggregate over all (substrate × metric) cells.

    ``all_pass`` is true iff every cell PASS. ``excluded_combos``
    is the gate output the sweep runner consumes — those
    (substrate, metric) pairs are skipped at sweep time.
    """

    all_pass: bool
    n_pass: int
    n_exclude: int
    excluded_combos: tuple[tuple[str, str], ...]
    results: tuple[PosControlCellResult, ...]
    sha256: str
    generated_at: str
    wallclock_seconds: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _capsule_sha256(payload: dict[str, Any]) -> str:
    """SHA-256 over the validator's exact canonical form.

    The pre-flight validator (:mod:`d002c_preflight`) recomputes
    each capsule's sha by re-encoding the capsule body (minus the
    ``sha256`` field) via :func:`canonical_preflight_json`. To
    survive validator round-trip, writers MUST use the SAME
    function — anything else (bare ``json.dumps``, smaller
    aggregate dicts, untouched non-finite floats) drifts and the
    validator refuses launch with ``capsule_sha256_mismatch``.
    """
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


def _evaluate_pair(
    *,
    substrate: Substrate,
    metric: Metric,
    N: int,
    lambda_: float,
    seed: int,
    steps_per_quarter: int,
    omega_gamma: float,
) -> tuple[MetricEvaluation, MetricEvaluation]:
    """Return (precursor_eval, null_eval) for one seed.

    CRN protocol: both Kuramoto integrations share the same seed
    so the natural-frequency and initial-phase draws are identical;
    only K differs between precursor and null trajectories. This
    cancels shared noise in the metric difference and matches the
    paired arm of :mod:`d002c_crn_validator`.
    """
    r = substrate.realize(N=N, lambda_=lambda_, seed=seed)
    traj_p = simulate_kuramoto(
        r.K_precursor,
        seed=seed,
        steps_per_quarter=steps_per_quarter,
        omega_gamma=omega_gamma,
    )
    traj_n = simulate_kuramoto(
        r.K_baseline,
        seed=seed,
        steps_per_quarter=steps_per_quarter,
        omega_gamma=omega_gamma,
    )
    return metric.evaluate(traj_p), metric.evaluate(traj_n)


def _per_seed_signal(
    eval_p: MetricEvaluation,
    eval_n: MetricEvaluation,
) -> tuple[float, bool]:
    """Per-seed precursor − null difference.

    Returns
    -------
    (diff, any_censored)
        ``diff`` is the raw difference (precursor minus null).
        ``any_censored`` reports whether either side of the pair
        was right-censored — surfaced upward so the cell can
        report its overall censoring fraction.
    """
    diff = float(eval_p.value) - float(eval_n.value)
    return diff, bool(eval_p.is_censored or eval_n.is_censored)


def _cohort_signal_mean(
    metric: Metric,
    evals_p: Sequence[MetricEvaluation],
    evals_n: Sequence[MetricEvaluation],
    *,
    horizon: float,
) -> float:
    """Right-censoring-honest cohort mean (KM RMST when censored)."""
    estimate = signal_mean(
        metric,
        list(evals_p),
        list(evals_n),
        horizon=horizon,
    )
    return float(estimate.signal_mean)


# ---------------------------------------------------------------------------
# Per-cell gate
# ---------------------------------------------------------------------------


def run_pos_control_cell(
    substrate: Substrate,
    metric: Metric,
    *,
    N: int = DEFAULT_POS_N,
    lambda_: float = DEFAULT_POS_LAMBDA,
    n_seeds: int = DEFAULT_POS_N_SEEDS,
    rng_seed_base: int = DEFAULT_POS_RNG_SEED_BASE,
    threshold: float = DEFAULT_POS_THRESHOLD,
    steps_per_quarter: int = DEFAULT_STEPS_PER_QUARTER,
    omega_gamma: float = DEFAULT_OMEGA_GAMMA,
) -> PosControlCellResult:
    """Run the positive-control gate on one (substrate, metric) cell.

    Protocol
    --------
    For seed in ``[rng_seed_base, rng_seed_base + n_seeds)``:

      1. Realise the substrate at ``(N, lambda_, seed)``.
      2. Integrate Kuramoto on ``K_precursor`` and ``K_baseline``
         with the SAME integrator seed (CRN-paired).
      3. Evaluate the metric on each trajectory.
      4. Per-seed signal = ``metric_p - metric_n``.

    Aggregation
    -----------
      * ``signal_mean`` = mean of per-seed diffs.
      * ``signal_std`` = sample std of per-seed diffs (``ddof=1``).
      * ``signal_ci_ratio`` = |signal_mean| / (signal_std / √n_seeds).
        This is the t-statistic form; threshold = 2.0 is roughly the
        two-sided 95% CI half-width over the SE.

    If any seed was right-censored the per-seed diffs are augmented
    by KM RMST aggregation (via :func:`d002c_metrics.signal_mean`)
    to keep ``signal_mean`` honest; the cell's overall censoring
    fraction is the fraction of (2 * n_seeds) metric evaluations
    that were censored.

    Verdict
    -------
    ``"PASS"`` iff ``signal_ci_ratio > threshold``, else
    ``"EXCLUDE"``. The verdict is the gate output the sweep
    runner consumes.

    Raises
    ------
    PosControlInvalid
        On ``n_seeds < 2`` (no sample variance), non-finite
        ``threshold``, or non-positive ``threshold``.
    """
    if n_seeds < 2:
        raise PosControlInvalid(f"n_seeds must be >= 2 (need ddof=1 std); got {n_seeds}")
    if not math.isfinite(threshold) or threshold <= 0.0:
        raise PosControlInvalid(f"threshold must be finite and > 0; got {threshold}")
    if not math.isfinite(lambda_) or lambda_ < 0.0:
        raise PosControlInvalid(f"lambda_ must be finite and >= 0; got {lambda_}")
    if N < 2:
        raise PosControlInvalid(f"N must be >= 2; got {N}")

    t0 = time.monotonic()
    evals_p: list[MetricEvaluation] = []
    evals_n: list[MetricEvaluation] = []
    censored_count = 0
    for i in range(n_seeds):
        seed = rng_seed_base + i
        ep, en = _evaluate_pair(
            substrate=substrate,
            metric=metric,
            N=N,
            lambda_=lambda_,
            seed=seed,
            steps_per_quarter=steps_per_quarter,
            omega_gamma=omega_gamma,
        )
        evals_p.append(ep)
        evals_n.append(en)
        censored_count += int(ep.is_censored) + int(en.is_censored)

    diffs: NDArray[np.float64] = np.array(
        [_per_seed_signal(p, n)[0] for p, n in zip(evals_p, evals_n)],
        dtype=np.float64,
    )
    raw_mean = float(diffs.mean())
    # Sample std with ddof=1 — variance over the per-seed signal
    # population. n_seeds >= 2 enforced above.
    signal_std = float(np.std(diffs, ddof=1))

    any_censored = censored_count > 0
    if any_censored:
        # Right-censoring honest aggregation: KM RMST over the
        # pre-event window. The window length in step units is the
        # horizon used for the survival integral. Both cohorts
        # share the same horizon by construction (same metric).
        spq = steps_per_quarter
        horizon = float((EVENT_QUARTER - PRE_EVENT_START_QUARTER) * spq)
        signal_mean_value = _cohort_signal_mean(metric, evals_p, evals_n, horizon=horizon)
    else:
        signal_mean_value = raw_mean

    se = signal_std / math.sqrt(float(n_seeds))
    if se <= 0.0 or not math.isfinite(se):
        # Degenerate variance — every seed produced the same diff.
        # If the magnitude is nonzero we treat it as +inf (infinite
        # SNR); otherwise zero (no detectable signal).
        ratio = math.inf if abs(signal_mean_value) > 0.0 else 0.0
    else:
        ratio = abs(signal_mean_value) / se

    verdict = "PASS" if ratio > threshold else "EXCLUDE"
    total_evals = 2 * n_seeds
    censoring_fraction = float(censored_count) / float(total_evals)
    wall = time.monotonic() - t0

    payload: dict[str, Any] = {
        "substrate_id": substrate.id,
        "metric_id": metric.id,
        "N": N,
        "lambda_": lambda_,
        "n_seeds": n_seeds,
        "signal_mean": signal_mean_value,
        "signal_std": signal_std,
        "signal_ci_ratio": ratio,
        "threshold": threshold,
        "verdict": verdict,
        "censoring_fraction": censoring_fraction,
        "rng_seed_base": rng_seed_base,
        "steps_per_quarter": steps_per_quarter,
        "omega_gamma": omega_gamma,
    }
    # Per-cell sha uses the validator's exact canonical form so
    # downstream tooling can recompute it independently. In the
    # degenerate-variance branch ``ratio`` is ``math.inf``;
    # canonical_preflight_json substitutes a stable string sentinel
    # so the sha is well-defined.
    sha = _capsule_sha256(payload)
    return PosControlCellResult(
        substrate_id=substrate.id,
        metric_id=metric.id,
        N=N,
        lambda_=lambda_,
        n_seeds=n_seeds,
        signal_mean=signal_mean_value,
        signal_std=signal_std,
        signal_ci_ratio=ratio,
        threshold=threshold,
        verdict=verdict,
        censoring_fraction=censoring_fraction,
        wallclock_seconds=wall,
        sha256=sha,
    )


# ---------------------------------------------------------------------------
# Full grid
# ---------------------------------------------------------------------------


def _result_to_dict(r: PosControlCellResult) -> dict[str, Any]:
    return {
        "substrate_id": r.substrate_id,
        "metric_id": r.metric_id,
        "N": r.N,
        "lambda_": r.lambda_,
        "n_seeds": r.n_seeds,
        "signal_mean": r.signal_mean,
        "signal_std": r.signal_std,
        "signal_ci_ratio": r.signal_ci_ratio,
        "threshold": r.threshold,
        "verdict": r.verdict,
        "censoring_fraction": r.censoring_fraction,
        "wallclock_seconds": r.wallclock_seconds,
        "sha256": r.sha256,
    }


def run_pos_control_all(
    substrates: tuple[Substrate, ...] = ALL_SUBSTRATES,
    metrics: tuple[Metric, ...] = ALL_METRICS,
    *,
    N: int = DEFAULT_POS_N,
    lambda_: float = DEFAULT_POS_LAMBDA,
    n_seeds: int = DEFAULT_POS_N_SEEDS,
    rng_seed_base: int = DEFAULT_POS_RNG_SEED_BASE,
    threshold: float = DEFAULT_POS_THRESHOLD,
    steps_per_quarter: int = DEFAULT_STEPS_PER_QUARTER,
    omega_gamma: float = DEFAULT_OMEGA_GAMMA,
    output_path: Path | None = None,
) -> PosControlVerdict:
    """Run the positive-control gate over the full substrate × metric grid.

    Writes an atomic JSON capsule when ``output_path`` is given;
    returns the verdict regardless. The capsule format matches
    :mod:`d002c_crn_validator`'s discipline (tmp + fsync +
    os.replace, sha256 over canonical-JSON payload).

    The verdict carries the load-bearing ``excluded_combos`` list:
    each ``(substrate_id, metric_id)`` pair whose cell failed the
    gate is reported here. The sweep runner consumes this list
    verbatim — there is no silent rescue.
    """
    if not substrates:
        raise PosControlInvalid("substrates must be non-empty")
    if not metrics:
        raise PosControlInvalid("metrics must be non-empty")

    t0 = time.monotonic()
    results: list[PosControlCellResult] = []
    for s in substrates:
        for m in metrics:
            results.append(
                run_pos_control_cell(
                    s,
                    m,
                    N=N,
                    lambda_=lambda_,
                    n_seeds=n_seeds,
                    rng_seed_base=rng_seed_base,
                    threshold=threshold,
                    steps_per_quarter=steps_per_quarter,
                    omega_gamma=omega_gamma,
                )
            )
    wall = time.monotonic() - t0

    n_pass = sum(1 for r in results if r.verdict == "PASS")
    n_exclude = len(results) - n_pass
    excluded_combos: tuple[tuple[str, str], ...] = tuple(
        (r.substrate_id, r.metric_id) for r in results if r.verdict == "EXCLUDE"
    )
    all_pass = n_exclude == 0

    generated_at = _now_iso()

    # Build the FULL capsule body (every field except ``sha256``)
    # FIRST, then sha it via the validator's canonical form. This
    # is what makes the preflight round-trip succeed: the validator
    # recomputes sha over capsule_without_sha and refuses launch on
    # any drift.
    capsule_without_sha: dict[str, Any] = {
        "kind": "d002c_pos_control_capsule_v1",
        "all_pass": all_pass,
        "n_pass": n_pass,
        "n_exclude": n_exclude,
        "excluded_combos": [list(c) for c in excluded_combos],
        "n_seeds": n_seeds,
        "N": N,
        "lambda_": lambda_,
        "threshold": threshold,
        "steps_per_quarter": steps_per_quarter,
        "omega_gamma": omega_gamma,
        "rng_seed_base": rng_seed_base,
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

    return PosControlVerdict(
        all_pass=all_pass,
        n_pass=n_pass,
        n_exclude=n_exclude,
        excluded_combos=excluded_combos,
        results=tuple(results),
        sha256=sha,
        generated_at=generated_at,
        wallclock_seconds=wall,
    )


__all__ = [
    "DEFAULT_POS_N",
    "DEFAULT_POS_LAMBDA",
    "DEFAULT_POS_N_SEEDS",
    "DEFAULT_POS_THRESHOLD",
    "DEFAULT_POS_RNG_SEED_BASE",
    "PosControlInvalid",
    "PosControlCellResult",
    "PosControlVerdict",
    "run_pos_control_cell",
    "run_pos_control_all",
]
