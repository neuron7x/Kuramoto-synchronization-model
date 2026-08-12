# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C C2.4 — Mini-grid smoke test for the Signal Amplification Sweep.

Mission
=======
Pre-flight check that exercises every (substrate × metric) combo on a
small N/λ grid end-to-end and must complete under a hard wallclock
budget. If the smoke run fails, the 200+-hour sweep is doomed for
trivial-bug reasons — wrong shapes, an integrator import bug, a metric
that raises on a small N — and we want to know in 60s, not 8 days.

Grid
====
N ∈ DEFAULT_SMOKE_N_GRID = (50, 100)
λ ∈ DEFAULT_SMOKE_LAMBDA_GRID = (0.0, 0.5)
substrates × metrics = 9 (3 × 3)

Total cells: 2 × 2 × 9 = 36. ``n_seeds`` = 5 paired runs per cell.

Budget
======
60s on a developer laptop (Ryzen / M-series). The spec says 30 minutes;
we are aggressive on purpose: a smoke that takes 8 minutes is too slow
to catch a bad PR before the reviewer's attention budget collapses.

Verdict
=======
PASS iff
  * every cell raised no exception
  * AND total wallclock ≤ ``max_wallclock_seconds``
Otherwise FAIL — with the offending cells (or the over-budget
total) recorded in the capsule.

Strict scope
============
Mini-grid execution + capsule emission ONLY. NO sweep launch. NO claim
layer. NO promotion of a PASS verdict into a tier — the sweep runner
(C2.4 session A) reads the capsule and refuses to launch if the smoke
test FAILED.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

from .d002c_kuramoto import (
    DEFAULT_OMEGA_GAMMA,
    simulate_kuramoto,
)
from .d002c_metrics import (
    ALL_METRICS,
    Metric,
)
from .d002c_preflight import canonical_preflight_json
from .d002c_substrates import (
    ALL_SUBSTRATES,
    Substrate,
)


def _capsule_sha256(payload: dict[str, Any]) -> str:
    """SHA-256 over the validator's exact canonical form.

    The pre-flight validator (:mod:`d002c_preflight`) recomputes
    a capsule's sha by re-encoding the capsule body (minus the
    ``sha256`` field) via :func:`canonical_preflight_json`. To
    survive validator round-trip, the smoke-test writer MUST use
    the SAME function — anything else (bare ``json.dumps``, a
    smaller surrogate dict, untouched non-finite floats) drifts
    and the validator refuses launch with
    ``capsule_sha256_mismatch``.
    """
    return hashlib.sha256(canonical_preflight_json(payload).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Locked defaults
# ---------------------------------------------------------------------------
DEFAULT_SMOKE_N_GRID: Final[tuple[int, ...]] = (50, 100)
DEFAULT_SMOKE_LAMBDA_GRID: Final[tuple[float, ...]] = (0.0, 0.5)
DEFAULT_SMOKE_N_SEEDS: Final[int] = 5
DEFAULT_SMOKE_MAX_WALLCLOCK_SEC: Final[float] = 60.0
DEFAULT_SMOKE_STEPS_PER_QUARTER: Final[int] = 6
DEFAULT_SMOKE_RNG_SEED_BASE: Final[int] = 42


class SmokeTestInvalid(RuntimeError):
    """Malformed smoke-test request (empty grid, bad budget, ...)."""


@dataclass(frozen=True)
class SmokeCellResult:
    """One (substrate, metric, N, λ) cell.

    ``ok`` is the load-bearing flag — if False, ``error`` carries the
    exception's repr so the reviewer can localise the failure without
    re-running.
    """

    substrate_id: str
    metric_id: str
    N: int
    lambda_: float
    n_seeds: int
    signal_mean: float
    signal_std: float
    censoring_fraction: float
    wallclock_seconds: float
    ok: bool
    error: str


@dataclass(frozen=True)
class SmokeTestResult:
    """Aggregate of all cells + global verdict."""

    grid_N: tuple[int, ...]
    grid_lambda: tuple[float, ...]
    n_seeds: int
    n_cells_total: int
    n_cells_ok: int
    n_cells_failed: int
    cells: tuple[SmokeCellResult, ...]
    total_wallclock_seconds: float
    verdict: str  # "PASS" | "FAIL"
    sha256: str
    generated_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    """tmp + fsync + os.replace. Cleanup on exception, never mask original."""
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


# ---------------------------------------------------------------------------
# Per-cell runner
# ---------------------------------------------------------------------------


def _run_cell(
    substrate: Substrate,
    metric: Metric,
    *,
    N: int,
    lambda_: float,
    n_seeds: int,
    rng_seed_base: int,
    steps_per_quarter: int,
    omega_gamma: float,
) -> SmokeCellResult:
    """Run ``n_seeds`` CRN-paired (precursor − null) draws for one cell.

    Returns a SmokeCellResult with ``ok=True`` on success or
    ``ok=False`` + the exception's traceback summary on failure.
    Never raises — the smoke test must continue past per-cell errors
    so we get the full diagnostic picture in a single run.
    """
    t0 = time.monotonic()
    try:
        diffs: list[float] = []
        censored_count = 0
        total_evals = 0
        for i in range(n_seeds):
            seed = rng_seed_base + i
            real = substrate.realize(N=N, lambda_=lambda_, seed=seed)
            # CRN-paired: same integrator seed for precursor + null
            traj_pre = simulate_kuramoto(
                real.K_precursor,
                seed=seed,
                steps_per_quarter=steps_per_quarter,
                omega_gamma=omega_gamma,
            )
            traj_null = simulate_kuramoto(
                real.K_baseline,
                seed=seed,
                steps_per_quarter=steps_per_quarter,
                omega_gamma=omega_gamma,
            )
            eval_pre = metric.evaluate(traj_pre)
            eval_null = metric.evaluate(traj_null)
            diffs.append(float(eval_pre.value - eval_null.value))
            total_evals += 2
            if eval_pre.is_censored:
                censored_count += 1
            if eval_null.is_censored:
                censored_count += 1
        diffs_arr: NDArray[np.float64] = np.asarray(diffs, dtype=np.float64)
        sig_mean = float(diffs_arr.mean())
        sig_std = float(diffs_arr.std(ddof=1)) if diffs_arr.size > 1 else 0.0
        cens_frac = float(censored_count) / float(max(total_evals, 1))
        wall = time.monotonic() - t0
        return SmokeCellResult(
            substrate_id=substrate.id,
            metric_id=metric.id,
            N=N,
            lambda_=lambda_,
            n_seeds=n_seeds,
            signal_mean=sig_mean,
            signal_std=sig_std,
            censoring_fraction=cens_frac,
            wallclock_seconds=wall,
            ok=True,
            error="",
        )
    except Exception as exc:
        wall = time.monotonic() - t0
        # Compact traceback summary so the capsule remains diff-friendly
        tb = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        return SmokeCellResult(
            substrate_id=substrate.id,
            metric_id=metric.id,
            N=N,
            lambda_=lambda_,
            n_seeds=n_seeds,
            signal_mean=math.nan,
            signal_std=math.nan,
            censoring_fraction=math.nan,
            wallclock_seconds=wall,
            ok=False,
            error=tb,
        )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def _cell_to_dict(c: SmokeCellResult) -> dict[str, Any]:
    return {
        "substrate_id": c.substrate_id,
        "metric_id": c.metric_id,
        "N": c.N,
        "lambda_": c.lambda_,
        "n_seeds": c.n_seeds,
        "signal_mean": _finite_or_none(c.signal_mean),
        "signal_std": _finite_or_none(c.signal_std),
        "censoring_fraction": _finite_or_none(c.censoring_fraction),
        "wallclock_seconds": c.wallclock_seconds,
        "ok": c.ok,
        "error": c.error,
    }


def _finite_or_none(x: float) -> float | None:
    """JSON cannot serialise NaN under strict=False with sort_keys; use None.

    We KEEP the dataclass-level NaN (load-bearing for downstream consumers
    that want a single-typed numeric column), but downgrade to None at the
    JSON boundary.
    """
    return float(x) if math.isfinite(x) else None


def run_smoke_test(
    substrates: tuple[Substrate, ...] = ALL_SUBSTRATES,
    metrics: tuple[Metric, ...] = ALL_METRICS,
    *,
    N_grid: tuple[int, ...] = DEFAULT_SMOKE_N_GRID,
    lambda_grid: tuple[float, ...] = DEFAULT_SMOKE_LAMBDA_GRID,
    n_seeds: int = DEFAULT_SMOKE_N_SEEDS,
    rng_seed_base: int = DEFAULT_SMOKE_RNG_SEED_BASE,
    steps_per_quarter: int = DEFAULT_SMOKE_STEPS_PER_QUARTER,
    omega_gamma: float = DEFAULT_OMEGA_GAMMA,
    max_wallclock_seconds: float = DEFAULT_SMOKE_MAX_WALLCLOCK_SEC,
    output_path: Path | None = None,
) -> SmokeTestResult:
    """Run the full mini-grid and emit a smoke capsule.

    Failed cells DO NOT short-circuit the run: the smoke test exists to
    report every issue in a single pass so the reviewer doesn't have to
    bisect cell-by-cell.

    Parameters
    ----------
    substrates, metrics
        Iterables to product into a grid. Default = the locked
        9-cell registry.
    N_grid, lambda_grid
        Grid points. Default = the locked smoke grid.
    n_seeds
        CRN-paired seeds per cell. Default 5 — enough for a sample
        std without bloating the wallclock.
    rng_seed_base
        Replicate ``i`` uses ``rng_seed_base + i`` for substrate +
        integrator (bit-exact CRN, mirrors C2.3).
    steps_per_quarter
        Smaller than ``DEFAULT_STEPS_PER_QUARTER`` (10) for speed.
        Default 6 — empirically the smallest value that keeps Heun
        stable on these substrates at smoke-grid N.
    max_wallclock_seconds
        Hard ceiling. Smoke PASSes iff every cell OK AND total
        wallclock ≤ this. Default 60s.
    output_path
        Optional. If set, an atomic JSON capsule is written.

    Returns
    -------
    SmokeTestResult
        Aggregate dataclass with sha256 over canonical-JSON of
        load-bearing fields.

    Raises
    ------
    SmokeTestInvalid
        Empty substrates / metrics / N / λ grids, n_seeds < 1,
        non-finite budget, etc.
    """
    if not substrates:
        raise SmokeTestInvalid("empty substrates tuple")
    if not metrics:
        raise SmokeTestInvalid("empty metrics tuple")
    if not N_grid:
        raise SmokeTestInvalid("empty N_grid")
    if not lambda_grid:
        raise SmokeTestInvalid("empty lambda_grid")
    if n_seeds < 1:
        raise SmokeTestInvalid(f"n_seeds must be >= 1; got {n_seeds}")
    if not math.isfinite(max_wallclock_seconds) or max_wallclock_seconds <= 0.0:
        raise SmokeTestInvalid(
            f"max_wallclock_seconds must be finite and > 0; got {max_wallclock_seconds}"
        )

    t0 = time.monotonic()
    cells: list[SmokeCellResult] = []
    for N in N_grid:
        for lam in lambda_grid:
            for s in substrates:
                for m in metrics:
                    cells.append(
                        _run_cell(
                            s,
                            m,
                            N=int(N),
                            lambda_=float(lam),
                            n_seeds=n_seeds,
                            rng_seed_base=rng_seed_base,
                            steps_per_quarter=steps_per_quarter,
                            omega_gamma=omega_gamma,
                        )
                    )
    total_wall = time.monotonic() - t0

    n_ok = sum(1 for c in cells if c.ok)
    n_failed = len(cells) - n_ok
    over_budget = total_wall > max_wallclock_seconds
    verdict = "PASS" if (n_failed == 0 and not over_budget) else "FAIL"

    generated_at = _now_iso()

    # Build the FULL capsule body (every field except ``sha256``)
    # FIRST, then sha it via the validator's canonical form so the
    # preflight round-trip succeeds. The previous implementation
    # hashed a smaller payload dict; that drifted from the
    # validator's recompute and triggered ``capsule_sha256_mismatch``
    # refusal at launch time.
    capsule_without_sha: dict[str, Any] = {
        "verdict": verdict,
        "grid_N": list(N_grid),
        "grid_lambda": list(lambda_grid),
        "n_seeds": n_seeds,
        "n_cells_total": len(cells),
        "n_cells_ok": n_ok,
        "n_cells_failed": n_failed,
        "total_wallclock_seconds": total_wall,
        "max_wallclock_seconds": max_wallclock_seconds,
        "over_budget": over_budget,
        "steps_per_quarter": steps_per_quarter,
        "omega_gamma": omega_gamma,
        "rng_seed_base": rng_seed_base,
        "cells": [_cell_to_dict(c) for c in cells],
        "generated_at": generated_at,
    }
    sha = _capsule_sha256(capsule_without_sha)

    result = SmokeTestResult(
        grid_N=tuple(int(x) for x in N_grid),
        grid_lambda=tuple(float(x) for x in lambda_grid),
        n_seeds=n_seeds,
        n_cells_total=len(cells),
        n_cells_ok=n_ok,
        n_cells_failed=n_failed,
        cells=tuple(cells),
        total_wallclock_seconds=total_wall,
        verdict=verdict,
        sha256=sha,
        generated_at=generated_at,
    )

    if output_path is not None:
        capsule = {**capsule_without_sha, "sha256": sha}
        _atomic_write(Path(output_path), capsule)

    return result


__all__ = [
    "DEFAULT_SMOKE_N_GRID",
    "DEFAULT_SMOKE_LAMBDA_GRID",
    "DEFAULT_SMOKE_N_SEEDS",
    "DEFAULT_SMOKE_MAX_WALLCLOCK_SEC",
    "DEFAULT_SMOKE_STEPS_PER_QUARTER",
    "DEFAULT_SMOKE_RNG_SEED_BASE",
    "SmokeTestInvalid",
    "SmokeCellResult",
    "SmokeTestResult",
    "run_smoke_test",
]
