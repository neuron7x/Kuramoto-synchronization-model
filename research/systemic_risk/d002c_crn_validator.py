# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C — Common-Random-Numbers variance-reduction GO/NO-GO validator.

Mission
=======
Empirically prove that CRN reduces variance of the signal estimator
in the D-002C Signal Amplification Sweep — *before* the 200+-hour
sweep launches. If CRN doesn't help in this problem geometry, the
acceptance criterion ``|signal| / CI > 1`` is operationally
unreachable at N ≤ 200, and the sweep is doomed by construction.

The validator runs all nine (substrate × metric) combinations at
the locked sweep grid centre (default N=200, λ=0.50) over a
configurable number of replicates and reports:

  variance_ratio = V(signal_paired) / V(signal_unpaired)

Per-cell verdict ``GO`` iff ``ratio ≤ ratio_threshold`` (default
0.50, i.e. CRN reduces variance by ≥2×). Global verdict ``GO``
iff at least ``minimum_passes`` (default 6) of 9 cells report
``GO``.

CRN protocol
============
For each replicate ``i`` with seed ``s = base + i``:

  * **Paired (CRN)** — realise the substrate once at seed ``s``
    (drives Erdős-Rényi topology for the Ricci substrate; the
    block / temporal substrates are deterministic in ``N``).
    Integrate two Kuramoto trajectories using the SAME seed (so
    ``ω``, ``θ(0)``, and integrator stream are identical) on
    ``K_baseline`` and ``K_precursor``. Difference of metrics =
    paired signal sample. The shared noise cancels in the
    subtraction.

  * **Unpaired (independent)** — realise the substrate twice
    at different seeds, integrate two Kuramoto trajectories with
    different seeds, take the metric difference. Noise terms
    are uncorrelated.

The variance ratio is computed with ``ddof=1`` (sample variance,
unbiased) on the two sample populations.

Output capsule
==============
:func:`run_full_validation` writes an atomic JSON capsule
containing every per-cell result, the global verdict, and the
canonical sha256 over the result payload — content-addressed so
a reviewer can verify integrity without re-running.

Atomic write: tmp + ``os.replace`` (mirrors D-002D's discipline)
plus ``fsync`` before rename so the capsule survives power loss.

Strict scope
============
Variance measurement + capsule emission ONLY. NO sweep launch.
NO claim layer. NO promotion of a GO verdict into a tier — the
sweep runner (C2.4) reads the capsule and refuses to launch if
the global verdict is NO_GO.
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
# Locked defaults — match the D-002C pre-registration grid centre.
# ---------------------------------------------------------------------------
DEFAULT_N: Final[int] = 200
DEFAULT_LAMBDA: Final[float] = 0.50
DEFAULT_N_REPLICATES: Final[int] = 100
DEFAULT_RNG_SEED_BASE: Final[int] = 42
DEFAULT_RATIO_THRESHOLD: Final[float] = 0.50
DEFAULT_MINIMUM_PASSES: Final[int] = 6  # of 9 (substrate × metric) cells
DEFAULT_UNPAIRED_SEED_STRIDE: Final[int] = 1_000_003  # large prime, no overlap


class CRNValidatorInvalid(RuntimeError):
    """Bad input to the validator (invalid grid point, empty cohort, etc.)."""


@dataclass(frozen=True)
class CRNValidatorResult:
    """Per-cell result. ``variance_ratio`` is the load-bearing field."""

    substrate_id: str
    metric_id: str
    N: int
    lambda_: float
    n_replicates: int
    paired_variance: float
    unpaired_variance: float
    variance_ratio: float
    ci_narrowing_factor: float
    paired_mean: float
    unpaired_mean: float
    verdict: str  # "GO" | "NO_GO"
    ratio_threshold: float
    sha256: str
    generated_at: str


@dataclass(frozen=True)
class CRNGlobalVerdict:
    """Aggregate over all (substrate × metric) cells."""

    global_verdict: str  # "GO" | "NO_GO"
    n_go: int
    n_nogo: int
    minimum_passes: int
    ratio_threshold: float
    results: tuple[CRNValidatorResult, ...]
    sha256: str
    generated_at: str
    wallclock_seconds: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _canonical_json(payload: dict[str, Any]) -> str:
    """Canonical JSON: sorted keys, separators (',',':'), no whitespace."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _compute_variance_ratio(
    paired: NDArray[np.float64],
    unpaired: NDArray[np.float64],
) -> tuple[float, float, float]:
    """Return (paired_var, unpaired_var, ratio).

    Ratio = paired / unpaired; +inf when unpaired variance is exactly zero
    (signals a degenerate metric — typically all realisations identical).
    """
    if paired.size < 2 or unpaired.size < 2:
        raise CRNValidatorInvalid(
            f"need >= 2 replicates for ddof=1 variance; got "
            f"paired={paired.size}, unpaired={unpaired.size}"
        )
    pv = float(np.var(paired, ddof=1))
    uv = float(np.var(unpaired, ddof=1))
    if uv <= 0.0:
        ratio = math.inf
    else:
        ratio = pv / uv
    return pv, uv, ratio


def _ci_narrowing_factor(pv: float, uv: float) -> float:
    """sqrt(unpaired / paired). Indicates how much narrower the CI on the
    signal estimate becomes under CRN."""
    if pv <= 0.0:
        return math.inf  # perfect cancellation — CI collapses to a point
    return float(math.sqrt(uv / pv))


def _evaluate_one(
    *,
    substrate: Substrate,
    metric: Metric,
    N: int,
    lambda_: float,
    substrate_seed: int,
    integrator_seed: int,
    use_precursor: bool,
    steps_per_quarter: int,
    omega_gamma: float,
) -> float:
    """Single end-to-end evaluation: substrate → integrator → metric.

    Decoupling ``substrate_seed`` from ``integrator_seed`` lets the
    caller compose paired / unpaired CRN protocols exactly:

      * paired   — substrate_seed == integrator_seed for both runs
      * unpaired — substrate_seed and integrator_seed differ
                   across the two runs

    For substrates whose realisation is deterministic in (N, λ)
    (block_structured, temporal_coupling) ``substrate_seed`` is
    irrelevant; for the Ricci substrate it drives the ER topology.
    """
    r = substrate.realize(N=N, lambda_=lambda_, seed=substrate_seed)
    K = r.K_precursor if use_precursor else r.K_baseline
    traj = simulate_kuramoto(
        K,
        seed=integrator_seed,
        steps_per_quarter=steps_per_quarter,
        omega_gamma=omega_gamma,
    )
    return float(metric.evaluate(traj).value)


def measure_variance_reduction(
    substrate: Substrate,
    metric: Metric,
    *,
    N: int = DEFAULT_N,
    lambda_: float = DEFAULT_LAMBDA,
    n_replicates: int = DEFAULT_N_REPLICATES,
    rng_seed_base: int = DEFAULT_RNG_SEED_BASE,
    ratio_threshold: float = DEFAULT_RATIO_THRESHOLD,
    steps_per_quarter: int = DEFAULT_STEPS_PER_QUARTER,
    omega_gamma: float = DEFAULT_OMEGA_GAMMA,
    unpaired_seed_stride: int = DEFAULT_UNPAIRED_SEED_STRIDE,
) -> CRNValidatorResult:
    """Run paired + unpaired evaluations and report variance ratio + verdict.

    Parameters
    ----------
    substrate, metric
        The (substrate, metric) cell to evaluate.
    N, lambda_
        Grid point at which to measure CRN effectiveness. Defaults to
        the pre-registration grid centre.
    n_replicates
        Number of paired AND unpaired replicates (total integrations
        ≈ ``4 · n_replicates``).
    rng_seed_base
        Base seed; replicate ``i`` uses ``rng_seed_base + i``.
    ratio_threshold
        Per-cell GO threshold. Default 0.50 (≥2× variance reduction).
    steps_per_quarter, omega_gamma
        Integrator hyperparameters.
    unpaired_seed_stride
        Offset added to seeds in the unpaired protocol so the two
        substrate realisations and the two integrator streams are
        independent. Default is a large prime (1_000_003) so no
        accidental collision with the paired replicate index.

    Returns
    -------
    CRNValidatorResult
        With sha256 computed over the canonical-JSON of the load-bearing
        fields. Same inputs → same sha (verified in the test suite).
    """
    if n_replicates < 2:
        raise CRNValidatorInvalid(f"n_replicates must be >= 2; got {n_replicates}")
    if not math.isfinite(ratio_threshold) or ratio_threshold <= 0.0:
        raise CRNValidatorInvalid(f"ratio_threshold must be finite and > 0; got {ratio_threshold}")

    paired = np.empty(n_replicates, dtype=np.float64)
    unpaired = np.empty(n_replicates, dtype=np.float64)

    for i in range(n_replicates):
        seed_a = rng_seed_base + i
        seed_b = rng_seed_base + i + unpaired_seed_stride

        # ---- Paired (CRN): same seed for both runs in this pair ----
        m_pre_p = _evaluate_one(
            substrate=substrate,
            metric=metric,
            N=N,
            lambda_=lambda_,
            substrate_seed=seed_a,
            integrator_seed=seed_a,
            use_precursor=True,
            steps_per_quarter=steps_per_quarter,
            omega_gamma=omega_gamma,
        )
        m_null_p = _evaluate_one(
            substrate=substrate,
            metric=metric,
            N=N,
            lambda_=lambda_,
            substrate_seed=seed_a,
            integrator_seed=seed_a,
            use_precursor=False,
            steps_per_quarter=steps_per_quarter,
            omega_gamma=omega_gamma,
        )
        paired[i] = m_pre_p - m_null_p

        # ---- Unpaired: substrate and integrator seeds differ between runs
        m_pre_u = _evaluate_one(
            substrate=substrate,
            metric=metric,
            N=N,
            lambda_=lambda_,
            substrate_seed=seed_a,
            integrator_seed=seed_a,
            use_precursor=True,
            steps_per_quarter=steps_per_quarter,
            omega_gamma=omega_gamma,
        )
        m_null_u = _evaluate_one(
            substrate=substrate,
            metric=metric,
            N=N,
            lambda_=lambda_,
            substrate_seed=seed_b,
            integrator_seed=seed_b,
            use_precursor=False,
            steps_per_quarter=steps_per_quarter,
            omega_gamma=omega_gamma,
        )
        unpaired[i] = m_pre_u - m_null_u

    pv, uv, ratio = _compute_variance_ratio(paired, unpaired)
    verdict = "GO" if ratio <= ratio_threshold else "NO_GO"
    payload: dict[str, Any] = {
        "substrate_id": substrate.id,
        "metric_id": metric.id,
        "N": N,
        "lambda_": lambda_,
        "n_replicates": n_replicates,
        "paired_variance": pv,
        "unpaired_variance": uv,
        "variance_ratio": ratio,
        "paired_mean": float(paired.mean()),
        "unpaired_mean": float(unpaired.mean()),
        "ratio_threshold": ratio_threshold,
        "verdict": verdict,
        "rng_seed_base": rng_seed_base,
        "steps_per_quarter": steps_per_quarter,
        "omega_gamma": omega_gamma,
        "unpaired_seed_stride": unpaired_seed_stride,
    }
    sha = _sha256(payload)
    return CRNValidatorResult(
        substrate_id=substrate.id,
        metric_id=metric.id,
        N=N,
        lambda_=lambda_,
        n_replicates=n_replicates,
        paired_variance=pv,
        unpaired_variance=uv,
        variance_ratio=ratio,
        ci_narrowing_factor=_ci_narrowing_factor(pv, uv),
        paired_mean=float(paired.mean()),
        unpaired_mean=float(unpaired.mean()),
        verdict=verdict,
        ratio_threshold=ratio_threshold,
        sha256=sha,
        generated_at=_now_iso(),
    )


# ---------------------------------------------------------------------------
# Atomic capsule writer
# ---------------------------------------------------------------------------


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    """tmp + fsync + os.replace. Matches D-002D's discipline."""
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
        # Best-effort cleanup; never mask the original exception.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _result_to_dict(r: CRNValidatorResult) -> dict[str, Any]:
    return {
        "substrate_id": r.substrate_id,
        "metric_id": r.metric_id,
        "N": r.N,
        "lambda_": r.lambda_,
        "n_replicates": r.n_replicates,
        "paired_variance": r.paired_variance,
        "unpaired_variance": r.unpaired_variance,
        "variance_ratio": r.variance_ratio,
        "ci_narrowing_factor": r.ci_narrowing_factor,
        "paired_mean": r.paired_mean,
        "unpaired_mean": r.unpaired_mean,
        "verdict": r.verdict,
        "ratio_threshold": r.ratio_threshold,
        "sha256": r.sha256,
        "generated_at": r.generated_at,
    }


def run_full_validation(
    *,
    output_path: Path,
    substrates: tuple[Substrate, ...] = ALL_SUBSTRATES,
    metrics: tuple[Metric, ...] = ALL_METRICS,
    N: int = DEFAULT_N,
    lambda_: float = DEFAULT_LAMBDA,
    n_replicates: int = DEFAULT_N_REPLICATES,
    rng_seed_base: int = DEFAULT_RNG_SEED_BASE,
    ratio_threshold: float = DEFAULT_RATIO_THRESHOLD,
    minimum_passes: int = DEFAULT_MINIMUM_PASSES,
    steps_per_quarter: int = DEFAULT_STEPS_PER_QUARTER,
    omega_gamma: float = DEFAULT_OMEGA_GAMMA,
) -> CRNGlobalVerdict:
    """Run the full (substrate × metric) grid and emit the capsule.

    Returns
    -------
    CRNGlobalVerdict
        Global verdict is ``"GO"`` iff at least ``minimum_passes``
        cells (default 6 of 9) report ``"GO"``. The capsule on disk
        carries every per-cell result + the global verdict + a
        canonical sha256 over the result payload.
    """
    if minimum_passes < 1 or minimum_passes > len(substrates) * len(metrics):
        raise CRNValidatorInvalid(
            f"minimum_passes={minimum_passes} outside [1, {len(substrates) * len(metrics)}]"
        )

    t0 = time.monotonic()
    results: list[CRNValidatorResult] = []
    for s in substrates:
        for m in metrics:
            res = measure_variance_reduction(
                s,
                m,
                N=N,
                lambda_=lambda_,
                n_replicates=n_replicates,
                rng_seed_base=rng_seed_base,
                ratio_threshold=ratio_threshold,
                steps_per_quarter=steps_per_quarter,
                omega_gamma=omega_gamma,
            )
            results.append(res)
    wall = time.monotonic() - t0

    n_go = sum(1 for r in results if r.verdict == "GO")
    n_nogo = len(results) - n_go
    global_verdict = "GO" if n_go >= minimum_passes else "NO_GO"

    # Canonical sha over the ordered list of per-cell shas
    aggregate = {
        "per_cell_shas": [r.sha256 for r in results],
        "n_go": n_go,
        "n_nogo": n_nogo,
        "minimum_passes": minimum_passes,
        "ratio_threshold": ratio_threshold,
    }
    sha = _sha256(aggregate)
    generated_at = _now_iso()

    capsule: dict[str, Any] = {
        "global_verdict": global_verdict,
        "n_go": n_go,
        "n_nogo": n_nogo,
        "minimum_passes": minimum_passes,
        "ratio_threshold": ratio_threshold,
        "n_replicates_per_cell": n_replicates,
        "N": N,
        "lambda_": lambda_,
        "steps_per_quarter": steps_per_quarter,
        "omega_gamma": omega_gamma,
        "rng_seed_base": rng_seed_base,
        "wallclock_seconds": wall,
        "results": [_result_to_dict(r) for r in results],
        "sha256": sha,
        "generated_at": generated_at,
        "substrate_ids": [s.id for s in substrates],
        "metric_ids": [m.id for m in metrics],
    }
    _atomic_write(Path(output_path), capsule)

    return CRNGlobalVerdict(
        global_verdict=global_verdict,
        n_go=n_go,
        n_nogo=n_nogo,
        minimum_passes=minimum_passes,
        ratio_threshold=ratio_threshold,
        results=tuple(results),
        sha256=sha,
        generated_at=generated_at,
        wallclock_seconds=wall,
    )


__all__ = [
    "DEFAULT_N",
    "DEFAULT_LAMBDA",
    "DEFAULT_N_REPLICATES",
    "DEFAULT_RNG_SEED_BASE",
    "DEFAULT_RATIO_THRESHOLD",
    "DEFAULT_MINIMUM_PASSES",
    "DEFAULT_UNPAIRED_SEED_STRIDE",
    "CRNValidatorInvalid",
    "CRNValidatorResult",
    "CRNGlobalVerdict",
    "measure_variance_reduction",
    "run_full_validation",
]
