#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002H canonical sweep -- ricci_flow grid execution.

Executes the full canonical sweep on the 18-cell grid pinned in
``docs/governance/D002H_PREREGISTRATION.yaml`` (substrate=[ricci_flow],
N=[50, 100, 200], lambda in {0.0, 0.05, 0.10, 0.20, 0.40, 1.0},
n_seeds=20, n_bootstrap=16), with null mechanisms M1_INDEPENDENT_SEED
and M3_TOPOLOGY_CONDITIONED.

Acceptance (4-term conjunction per
``docs/governance/D002H_R2B_INAPPLICABILITY_NOTE.md``):
    R1 (signal vs CI) AND R2 (FPR at lambda=0 under M1)
    AND R3 (direction stability) AND NULL_AUDIT

R2-B (FPR under M6 placebo) is STRUCTURALLY INAPPLICABLE under D-002H
scope because M6 is not in ``null_mechanisms_allowed`` -- see
``D002H_R2B_INAPPLICABILITY_NOTE.md``.

Anti-overclaim guards (from ``D002G_ACCEPTANCE_RULES.md`` Section 3):
MARGINAL_PASS, SINGLE_PATH_PASS, NULL_AUDIT_FAIL.

This script:
  1. Verifies governance-doc anchor sha256 (D-002G acceptance, D-002H
     prereg, D-002C ledger, R2-B note) byte-exact at the merged anchor
     ee12a9e6a08e5916109c99eec84796d1e1375cd0.
  2. Iterates the 18-cell ricci_flow grid across 3 inherited metrics
     (tau_onset, sync_auc, phase_lag). Per (cell, metric):
        - precursor cohort:   20 seeds in [42, 62) -- substrate.realize
          + simulate_kuramoto on K_precursor.
        - M1 null cohort:     20 seeds in [42+10000, 62+10000) --
          realize_null(strategy=M1_INDEPENDENT_SEED) + simulate_kuramoto
          on K_baseline (independent-seed null).
        - M3 null cohort:     realize_null(strategy=M3_TOPOLOGY_CONDITIONED,
          null_seed=12345 fixed) + simulate_kuramoto. M3 requires
          lambda > 0; at lambda=0 M3 is N/A by mechanism contract.
        - signal_diff_M1 / signal_diff_M3 = precursor_value - null_value
          (paired by seed for M1 by construction; M3 fixed null_seed).
        - BCa bootstrap CI (n_bootstrap=16, alpha=0.05, seed derived
          from rng_seed_base XOR 0x9E3779B9) on per-seed signal_diff.
        - R1, R3 evaluated per (cell, metric, null_mechanism).
  3. R2 (FPR under M1): fraction of lambda=0 cells (within same
     substrate/metric/N) whose signal_over_ci > 1.0. Bonferroni-
     corrected per-cell alpha = 0.05 / 216 = 2.315e-4 (denominator
     inherited verbatim from D-002G per acceptance rules Section 5).
  4. Post-sweep null audit via run_null_audit_all on the M1 sweep
     capsule (n_shuffles=100, rng_seed=42, p_threshold=0.05). Every
     cell must report PASS.
  5. Cell verdict: PASS iff (R1 AND R2 AND R3 AND NULL_AUDIT) for ANY
     metric within the cell. Aggregate verdict per anti-overclaim
     guards.

Output:
  artifacts/d002h/canonical/results/<RUN_ID>/
    sweep_capsule_v1.json
    null_audit_capsule.json
    verdict.json
  artifacts/d002h/canonical/d002h_canonical_run_verdict.json (top-level)

NON-NEGOTIABLES:
  * Deterministic + reproducible (base_seed=42, null_seed_M3=12345,
    null_seed_offset_M1=10000, M3_PLACEBO_SALT=523 -- all pinned in
    D-002H prereg).
  * NO source code edit. NO mechanism/substrate code change. NO
    acceptance-rule change. NO ledger touch.
  * NO forced PASS. Truthful FAIL is preserved as negative artifact.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

# Resolve repo root via env or cwd, then append to sys.path.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# psutil is optional -- only used for RSS reporting.
try:
    import psutil  # type: ignore[import-untyped]

    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False

from research.systemic_risk.d002c_kuramoto import (  # noqa: E402
    DEFAULT_OMEGA_GAMMA,
    DEFAULT_STEPS_PER_QUARTER,
    simulate_kuramoto,
)
from research.systemic_risk.d002c_metrics import METRIC_BY_ID  # noqa: E402
from research.systemic_risk.d002c_null_audit import (  # noqa: E402
    NullAuditInputCell,
    run_null_audit_all,
)
from research.systemic_risk.d002c_substrates import (  # noqa: E402
    SUBSTRATE_BY_ID,
)
from research.systemic_risk.d002c_sweep_runner import (  # noqa: E402
    bca_bootstrap_ci,
)
from research.systemic_risk.d002g_null_mechanisms import (  # noqa: E402
    BitIdenticalNullError,
    D002GNullInvalid,
    M3NotEligibleError,
    realize_null,
)

# ---------------------------------------------------------------------------
# Locked constants -- mirror D-002H prereg verbatim.
# ---------------------------------------------------------------------------
RUN_ID: Final[str] = "d002h_ricci_flow_canonical_v1_2026-05-14"
SCHEMA_VERSION: Final[str] = "D002H-CANONICAL-RUN-VERDICT-v1"
STUDY_ID: Final[str] = "D-002H"

ANCHOR_MAIN_SHA: Final[str] = "ee12a9e6a08e5916109c99eec84796d1e1375cd0"
D002C_LEDGER_SHA_AT_RUN: Final[str] = (
    "f96ba9b5a2057d2e0bff84afc28578ab316cff73f6dc6673fb0d6d543b8bd6dd"
)
D002G_ACCEPTANCE_SHA: Final[str] = (
    "875b1e3eb031b8e5333dc8b455454f0a30419ead1ebe787aa01d5882e7d6ad31"
)
D002H_PREREG_SHA: Final[str] = "44b18b5a40ce9d188a9c3bd49339621f81a65a15f97a683247902450dd54acec"

SUBSTRATE_ID: Final[str] = "ricci_flow"
N_GRID: Final[tuple[int, ...]] = (50, 100, 200)
LAMBDA_GRID: Final[tuple[float, ...]] = (0.0, 0.05, 0.10, 0.20, 0.40, 1.0)
METRIC_IDS: Final[tuple[str, ...]] = ("tau_onset", "sync_auc", "phase_lag")
N_SEEDS: Final[int] = 20
N_BOOTSTRAP: Final[int] = 16
BASE_SEED: Final[int] = 42
NULL_SEED_OFFSET_M1: Final[int] = 10000
NULL_SEED_M3: Final[int] = 12345
CI_ALPHA: Final[float] = 0.05
DIRECTION_MIN_FRACTION: Final[float] = 0.80
SIGNAL_CI_RATIO_MIN: Final[float] = 1.0
BONFERRONI_N_CELLS: Final[int] = 216  # inherited verbatim from D-002G
EFFECTIVE_ALPHA_PER_CELL: Final[float] = 0.05 / float(BONFERRONI_N_CELLS)
MARGIN_RELATIVE: Final[float] = 0.05

# Null audit configuration (per D002G_ACCEPTANCE_RULES.md Section 2 NULL_AUDIT).
NULL_AUDIT_N_SHUFFLES: Final[int] = 100
NULL_AUDIT_RNG_SEED: Final[int] = 42
NULL_AUDIT_P_THRESHOLD: Final[float] = 0.05

# Tier strings -- locked enum.
TIER_PASS: Final[str] = "SYNTHETIC_GATE6_CERTIFIED_D002H_REDESIGN"
TIER_MARGINAL: Final[str] = "MARGINAL_PASS_SYNTHETIC_D002H"
TIER_FAIL: Final[str] = "D002H_REDESIGN_INSUFFICIENT_AT_TESTED_BUDGET"
TIER_REFUSED: Final[str] = "REFUSED_NULL_AUDIT_FAIL_D002H"
LOCKED_TIER_ENUM: Final[frozenset[str]] = frozenset(
    {TIER_PASS, TIER_MARGINAL, TIER_FAIL, TIER_REFUSED}
)

ARTIFACT_DIR: Final[Path] = _REPO_ROOT / "artifacts" / "d002h" / "canonical" / "results" / RUN_ID
TOP_VERDICT_PATH: Final[Path] = (
    _REPO_ROOT / "artifacts" / "d002h" / "canonical" / "d002h_canonical_run_verdict.json"
)


# ---------------------------------------------------------------------------
# Sha verification + JSON helpers.
# ---------------------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    with path.open("rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256_canonical(obj: Any) -> str:
    return hashlib.sha256(_canonical_json(obj).encode("utf-8")).hexdigest()


def _finite_or_str(x: float) -> Any:
    f = float(x)
    if math.isnan(f):
        return "NaN"
    if math.isinf(f):
        return "Infinity" if f > 0 else "-Infinity"
    return f


def _verify_anchors(repo_root: Path) -> dict[str, str]:
    """Verify governance docs byte-exact at the merged anchor.

    Refuses launch on any drift -- the D-002H verdict computation depends
    on the locked acceptance contract being byte-exact.
    """
    files = {
        "D002G_ACCEPTANCE_RULES.md": D002G_ACCEPTANCE_SHA,
        "D002H_PREREGISTRATION.yaml": D002H_PREREG_SHA,
        "D002C_CLAIM_LEDGER.yaml": D002C_LEDGER_SHA_AT_RUN,
    }
    observed: dict[str, str] = {}
    drift: list[str] = []
    for fname, expected in files.items():
        p = repo_root / "docs" / "governance" / fname
        actual = _sha256_file(p)
        observed[fname] = actual
        if actual != expected:
            drift.append(f"{fname}: expected {expected}, got {actual}")
    if drift:
        raise RuntimeError(
            "anchor sha drift -- canonical run refuses launch:\n  " + "\n  ".join(drift)
        )
    return observed


# ---------------------------------------------------------------------------
# Direction stability.
# ---------------------------------------------------------------------------


def _direction_stability_fraction(diffs: NDArray[np.float64]) -> tuple[float, str]:
    """Fraction of seeds whose sign matches the majority sign.

    Returns (fraction, direction) where direction is "up" / "down" / "none".
    Zeros do not contribute to either tally.
    """
    n = int(diffs.size)
    if n == 0:
        return 0.0, "none"
    up = int(np.sum(diffs > 0.0))
    down = int(np.sum(diffs < 0.0))
    if up == 0 and down == 0:
        return 0.0, "none"
    if up >= down:
        return up / float(n), "up"
    return down / float(n), "down"


# ---------------------------------------------------------------------------
# Per-cell evaluation: one (substrate, metric, N, lambda) under both
# M1 and M3 null mechanisms.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CellEvaluation:
    cell_key: str  # canonical "[N=...,lambda=...,sub=...,metric=...]"
    substrate_id: str
    metric_id: str
    N: int
    lambda_value: float
    null_mechanism: str  # "M1_INDEPENDENT_SEED" or "M3_TOPOLOGY_CONDITIONED"
    n_seeds: int
    n_bootstrap: int
    seed_ids: tuple[int, ...]
    precursor_values: tuple[float, ...]
    null_values: tuple[float, ...]
    signal_diffs: tuple[float, ...]
    signal_mean: float
    bca_ci_lo: float
    bca_ci_hi: float
    signal_over_ci: float
    direction: str
    direction_stability: float
    wallclock_seconds: float
    status: str  # "OK" / "INELIGIBLE_<reason>" / "ERROR_<reason>"
    error_msg: str = ""


def _build_cell_key(*, N: int, lambda_value: float, substrate_id: str, metric_id: str) -> str:
    return f"[N={int(N)},lambda={float(lambda_value)},sub={substrate_id},metric={metric_id}]"


def _evaluate_cell_one_mechanism(
    *,
    substrate_id: str,
    metric_id: str,
    N: int,
    lambda_value: float,
    null_mechanism: str,
) -> CellEvaluation:
    """Evaluate one cell under one null mechanism.

    The mechanism choice determines how the null K_baseline is drawn:
      * M1: per-seed independent (base_seed + 10000 + i for each seed i)
      * M3: topology-conditioned, fixed null_seed=12345
    """
    cell_key = _build_cell_key(
        N=N,
        lambda_value=lambda_value,
        substrate_id=substrate_id,
        metric_id=metric_id,
    )
    substrate = SUBSTRATE_BY_ID[substrate_id]
    metric = METRIC_BY_ID[metric_id]
    t0 = time.monotonic()

    # M3 is INAPPLICABLE at lambda=0 by mechanism contract.
    if null_mechanism == "M3_TOPOLOGY_CONDITIONED" and lambda_value <= 0.0:
        wall = time.monotonic() - t0
        return CellEvaluation(
            cell_key=cell_key,
            substrate_id=substrate_id,
            metric_id=metric_id,
            N=int(N),
            lambda_value=float(lambda_value),
            null_mechanism=null_mechanism,
            n_seeds=0,
            n_bootstrap=N_BOOTSTRAP,
            seed_ids=(),
            precursor_values=(),
            null_values=(),
            signal_diffs=(),
            signal_mean=0.0,
            bca_ci_lo=0.0,
            bca_ci_hi=0.0,
            signal_over_ci=0.0,
            direction="none",
            direction_stability=0.0,
            wallclock_seconds=wall,
            status="INELIGIBLE_M3_LAMBDA_ZERO",
        )

    precursor_values_list: list[float] = []
    null_values_list: list[float] = []
    seed_ids_list: list[int] = []

    for i in range(N_SEEDS):
        base_seed_i = BASE_SEED + i
        seed_ids_list.append(int(base_seed_i))

        # Precursor cohort: substrate.realize at base_seed_i.
        try:
            precursor_real = substrate.realize(
                N=int(N), lambda_=float(lambda_value), seed=int(base_seed_i)
            )
        except Exception as exc:
            wall = time.monotonic() - t0
            return CellEvaluation(
                cell_key=cell_key,
                substrate_id=substrate_id,
                metric_id=metric_id,
                N=int(N),
                lambda_value=float(lambda_value),
                null_mechanism=null_mechanism,
                n_seeds=int(i),
                n_bootstrap=N_BOOTSTRAP,
                seed_ids=tuple(seed_ids_list),
                precursor_values=tuple(precursor_values_list),
                null_values=tuple(null_values_list),
                signal_diffs=(),
                signal_mean=0.0,
                bca_ci_lo=0.0,
                bca_ci_hi=0.0,
                signal_over_ci=0.0,
                direction="none",
                direction_stability=0.0,
                wallclock_seconds=wall,
                status="ERROR_PRECURSOR_REALIZE",
                error_msg=f"{type(exc).__name__}: {exc}",
            )

        traj_p = simulate_kuramoto(
            precursor_real.K_precursor,
            seed=int(base_seed_i),
            steps_per_quarter=DEFAULT_STEPS_PER_QUARTER,
            omega_gamma=DEFAULT_OMEGA_GAMMA,
        )
        eval_p = metric.evaluate(traj_p)
        precursor_values_list.append(float(eval_p.value))

        # Null cohort -- mechanism-dependent.
        try:
            if null_mechanism == "M1_INDEPENDENT_SEED":
                # Per-seed independent null: base_seed_i + NULL_SEED_OFFSET.
                null_real = realize_null(
                    substrate,
                    strategy="M1_INDEPENDENT_SEED",
                    base_seed=int(base_seed_i),
                    N=int(N),
                    lambda_value=float(lambda_value),
                )
                K_null = null_real.K_baseline
                null_kuramoto_seed = int(base_seed_i) + NULL_SEED_OFFSET_M1
            elif null_mechanism == "M3_TOPOLOGY_CONDITIONED":
                # Fixed null_seed across all seeds (per D-002H prereg).
                null_real = realize_null(
                    substrate,
                    strategy="M3_TOPOLOGY_CONDITIONED",
                    base_seed=int(base_seed_i),
                    N=int(N),
                    lambda_value=float(lambda_value),
                    null_seed=int(NULL_SEED_M3),
                )
                K_null = null_real.K_baseline
                # M3 uses the fixed null seed for its own RNG; but the
                # Kuramoto integration on K_null is paired by the
                # precursor seed to keep omega + theta(0) shared.
                null_kuramoto_seed = int(base_seed_i)
            else:
                raise ValueError(f"unknown null_mechanism: {null_mechanism!r}")
        except BitIdenticalNullError as exc:
            wall = time.monotonic() - t0
            return CellEvaluation(
                cell_key=cell_key,
                substrate_id=substrate_id,
                metric_id=metric_id,
                N=int(N),
                lambda_value=float(lambda_value),
                null_mechanism=null_mechanism,
                n_seeds=int(i),
                n_bootstrap=N_BOOTSTRAP,
                seed_ids=tuple(seed_ids_list),
                precursor_values=tuple(precursor_values_list),
                null_values=tuple(null_values_list),
                signal_diffs=(),
                signal_mean=0.0,
                bca_ci_lo=0.0,
                bca_ci_hi=0.0,
                signal_over_ci=0.0,
                direction="none",
                direction_stability=0.0,
                wallclock_seconds=wall,
                status="INELIGIBLE_M1_BIT_IDENTICAL",
                error_msg=str(exc),
            )
        except M3NotEligibleError as exc:
            wall = time.monotonic() - t0
            return CellEvaluation(
                cell_key=cell_key,
                substrate_id=substrate_id,
                metric_id=metric_id,
                N=int(N),
                lambda_value=float(lambda_value),
                null_mechanism=null_mechanism,
                n_seeds=int(i),
                n_bootstrap=N_BOOTSTRAP,
                seed_ids=tuple(seed_ids_list),
                precursor_values=tuple(precursor_values_list),
                null_values=tuple(null_values_list),
                signal_diffs=(),
                signal_mean=0.0,
                bca_ci_lo=0.0,
                bca_ci_hi=0.0,
                signal_over_ci=0.0,
                direction="none",
                direction_stability=0.0,
                wallclock_seconds=wall,
                status="INELIGIBLE_M3",
                error_msg=str(exc),
            )
        except D002GNullInvalid as exc:
            wall = time.monotonic() - t0
            return CellEvaluation(
                cell_key=cell_key,
                substrate_id=substrate_id,
                metric_id=metric_id,
                N=int(N),
                lambda_value=float(lambda_value),
                null_mechanism=null_mechanism,
                n_seeds=int(i),
                n_bootstrap=N_BOOTSTRAP,
                seed_ids=tuple(seed_ids_list),
                precursor_values=tuple(precursor_values_list),
                null_values=tuple(null_values_list),
                signal_diffs=(),
                signal_mean=0.0,
                bca_ci_lo=0.0,
                bca_ci_hi=0.0,
                signal_over_ci=0.0,
                direction="none",
                direction_stability=0.0,
                wallclock_seconds=wall,
                status="INELIGIBLE_NULL_CONTRACT",
                error_msg=str(exc),
            )

        # The null cohort K is a single time slice (T, N, N); we need
        # the (T,N,N) trajectory shape for simulate_kuramoto, which is
        # what _baseline_slice already extracted via NullRealization. The
        # null realisation gives the K trajectory shape needed.
        if K_null.ndim == 2:
            # _baseline_slice returns the t=0 slice; the integrator needs
            # a (T, N, N) trajectory. The standard contract is to broadcast
            # the constant baseline across all time steps -- but the M1
            # null contract says use precursor_real's K_baseline TIME
            # structure (no precursor injection). We mirror that by
            # building a (T, N, N) trajectory tiling K_null at every t.
            T_steps = precursor_real.K_baseline.shape[0]
            K_null_traj = np.broadcast_to(
                K_null[None, :, :], (T_steps, K_null.shape[0], K_null.shape[1])
            ).copy()
        else:
            K_null_traj = K_null

        traj_n = simulate_kuramoto(
            K_null_traj,
            seed=int(null_kuramoto_seed),
            steps_per_quarter=DEFAULT_STEPS_PER_QUARTER,
            omega_gamma=DEFAULT_OMEGA_GAMMA,
        )
        eval_n = metric.evaluate(traj_n)
        null_values_list.append(float(eval_n.value))

    # Compute signal diffs + statistics.
    precursor_arr = np.asarray(precursor_values_list, dtype=np.float64)
    null_arr = np.asarray(null_values_list, dtype=np.float64)
    diffs = precursor_arr - null_arr
    signal_mean = float(diffs.mean())

    bca_seed = int(BASE_SEED) ^ 0x9E37_79B9
    ci_lo, ci_hi = bca_bootstrap_ci(diffs, int(N_BOOTSTRAP), float(CI_ALPHA), seed=int(bca_seed))
    half_width = 0.5 * (float(ci_hi) - float(ci_lo))
    if half_width > 0.0:
        signal_over_ci = abs(signal_mean) / half_width
    elif signal_mean == 0.0:
        signal_over_ci = 0.0
    else:
        signal_over_ci = math.inf

    stability_fraction, direction = _direction_stability_fraction(diffs)

    wall = time.monotonic() - t0
    return CellEvaluation(
        cell_key=cell_key,
        substrate_id=substrate_id,
        metric_id=metric_id,
        N=int(N),
        lambda_value=float(lambda_value),
        null_mechanism=null_mechanism,
        n_seeds=int(N_SEEDS),
        n_bootstrap=int(N_BOOTSTRAP),
        seed_ids=tuple(seed_ids_list),
        precursor_values=tuple(precursor_values_list),
        null_values=tuple(null_values_list),
        signal_diffs=tuple(float(x) for x in diffs.tolist()),
        signal_mean=float(signal_mean),
        bca_ci_lo=float(ci_lo),
        bca_ci_hi=float(ci_hi),
        signal_over_ci=float(signal_over_ci),
        direction=direction,
        direction_stability=float(stability_fraction),
        wallclock_seconds=float(wall),
        status="OK",
    )


# ---------------------------------------------------------------------------
# Per-cell verdict (4-term conjunction).
# ---------------------------------------------------------------------------


def _is_marginal(measured: float, threshold: float) -> bool:
    if not math.isfinite(measured) or not math.isfinite(threshold):
        return False
    if threshold == 0.0:
        return abs(measured) <= MARGIN_RELATIVE
    return abs(measured - threshold) / abs(threshold) <= MARGIN_RELATIVE


@dataclass
class RuleResult:
    rule_id: str
    measured: float
    threshold: float
    passed: bool
    marginal: bool


def _eval_R1(cell: CellEvaluation) -> RuleResult:
    measured = float(cell.signal_over_ci) if math.isfinite(cell.signal_over_ci) else 0.0
    passed = measured > SIGNAL_CI_RATIO_MIN and cell.status == "OK"
    marginal = passed and _is_marginal(measured, SIGNAL_CI_RATIO_MIN)
    return RuleResult("R1", measured, SIGNAL_CI_RATIO_MIN, passed, marginal)


def _eval_R2(
    candidate: CellEvaluation,
    all_M1_evals: list[CellEvaluation],
) -> RuleResult:
    """FPR(lambda=0, M1 null) <= 0.05/216 across cells at same (sub, metric, N)."""
    null_cells = [
        c
        for c in all_M1_evals
        if c.substrate_id == candidate.substrate_id
        and c.metric_id == candidate.metric_id
        and c.N == candidate.N
        and c.lambda_value == 0.0
        and c.status == "OK"
    ]
    if not null_cells:
        # No usable null cell -- fail-closed.
        return RuleResult("R2", 1.0, EFFECTIVE_ALPHA_PER_CELL, False, False)
    n_total = len(null_cells)
    n_fp = sum(
        1
        for c in null_cells
        if math.isfinite(c.signal_over_ci) and c.signal_over_ci > SIGNAL_CI_RATIO_MIN
    )
    fpr = n_fp / float(n_total)
    passed = fpr <= EFFECTIVE_ALPHA_PER_CELL
    marginal = passed and _is_marginal(fpr, EFFECTIVE_ALPHA_PER_CELL)
    return RuleResult("R2", fpr, EFFECTIVE_ALPHA_PER_CELL, passed, marginal)


def _eval_R3(cell: CellEvaluation) -> RuleResult:
    measured = float(cell.direction_stability)
    passed = (
        cell.status == "OK"
        and cell.direction in {"up", "down"}
        and measured >= DIRECTION_MIN_FRACTION
    )
    marginal = passed and _is_marginal(measured, DIRECTION_MIN_FRACTION)
    return RuleResult("R3", measured, DIRECTION_MIN_FRACTION, passed, marginal)


# ---------------------------------------------------------------------------
# Top-level sweep driver.
# ---------------------------------------------------------------------------


def _process_size(repo_root: Path) -> int:
    if not _PSUTIL_AVAILABLE:
        return 0
    try:
        proc = psutil.Process(os.getpid())
        return int(proc.memory_info().rss // (1024 * 1024))
    except Exception:
        return 0


def main() -> int:
    print(f"D-002H canonical sweep starting at {_now_iso()}", flush=True)
    print(f"  run_id={RUN_ID}", flush=True)
    print(f"  scope={SUBSTRATE_ID} only", flush=True)
    print(
        f"  grid: 3N x 6lambda x {len(METRIC_IDS)}metrics = "
        f"{3 * 6 * len(METRIC_IDS)} (cell, metric) combos x 2 nulls",
        flush=True,
    )

    repo_root = _REPO_ROOT
    print(f"  repo_root={repo_root}", flush=True)

    print("Phase 0 -- anchor sha verification...", flush=True)
    observed_anchors = _verify_anchors(repo_root)
    for fname, sha in observed_anchors.items():
        print(f"  {fname}: {sha[:16]}... OK", flush=True)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    t_sweep_start = time.monotonic()

    # ---- Phase 2: sweep all (cell, metric) under M1 and M3 nulls ----
    all_M1: list[CellEvaluation] = []
    all_M3: list[CellEvaluation] = []
    total_evals = 3 * 6 * len(METRIC_IDS) * 2
    done_evals = 0
    print(f"Phase 2 -- executing sweep ({total_evals} evaluations)...", flush=True)
    for N in N_GRID:
        for lambda_value in LAMBDA_GRID:
            for metric_id in METRIC_IDS:
                for null_mechanism in ("M1_INDEPENDENT_SEED", "M3_TOPOLOGY_CONDITIONED"):
                    t_eval_start = time.monotonic()
                    cell_eval = _evaluate_cell_one_mechanism(
                        substrate_id=SUBSTRATE_ID,
                        metric_id=metric_id,
                        N=N,
                        lambda_value=lambda_value,
                        null_mechanism=null_mechanism,
                    )
                    t_eval = time.monotonic() - t_eval_start
                    if null_mechanism == "M1_INDEPENDENT_SEED":
                        all_M1.append(cell_eval)
                    else:
                        all_M3.append(cell_eval)
                    done_evals += 1
                    rss_mb = _process_size(repo_root)
                    print(
                        f"  [{done_evals}/{total_evals}] N={N} lam={lambda_value:.2f} "
                        f"metric={metric_id} null={null_mechanism} "
                        f"status={cell_eval.status} wall={t_eval:.2f}s "
                        f"signal_over_ci={cell_eval.signal_over_ci:.3f} "
                        f"dir={cell_eval.direction} rss_MB={rss_mb}",
                        flush=True,
                    )

    sweep_wallclock = time.monotonic() - t_sweep_start
    print(f"Phase 2 complete -- wallclock {sweep_wallclock:.1f}s", flush=True)

    # ---- Phase 3a: persist sweep capsule v1 ----
    sweep_capsule_path = ARTIFACT_DIR / "sweep_capsule_v1.json"
    capsule_body = {
        "schema_version": "D002H-CANONICAL-SWEEP-CAPSULE-v1",
        "run_id": RUN_ID,
        "study_id": STUDY_ID,
        "anchor_main_sha": ANCHOR_MAIN_SHA,
        "scope": "ricci_flow substrate only",
        "executed_at": _now_iso(),
        "anchors_observed": observed_anchors,
        "grid": {
            "substrates": [SUBSTRATE_ID],
            "N": list(N_GRID),
            "lambda_values": list(LAMBDA_GRID),
            "metrics": list(METRIC_IDS),
            "n_seeds": int(N_SEEDS),
            "n_bootstrap": int(N_BOOTSTRAP),
            "total_cells_canonical": 18,
        },
        "reproducibility": {
            "base_seed": int(BASE_SEED),
            "null_seed_offset_M1": int(NULL_SEED_OFFSET_M1),
            "null_seed_M3": int(NULL_SEED_M3),
        },
        "null_mechanisms": ["M1_INDEPENDENT_SEED", "M3_TOPOLOGY_CONDITIONED"],
        "sweep_wallclock_seconds": float(sweep_wallclock),
        "evaluations_M1": [_cell_eval_to_dict(c) for c in all_M1],
        "evaluations_M3": [_cell_eval_to_dict(c) for c in all_M3],
    }
    sweep_capsule_path.write_text(_canonical_json(capsule_body), encoding="utf-8")
    print(f"sweep capsule written: {sweep_capsule_path}", flush=True)

    # ---- Phase 3b: post-sweep null audit on M1 cohort ----
    print("Phase 3 -- post-sweep null audit (M1 cohort)...", flush=True)
    null_audit_capsule_path = ARTIFACT_DIR / "null_audit_capsule.json"
    null_audit_inputs: list[NullAuditInputCell] = []
    for cell_eval in all_M1:
        if cell_eval.status != "OK":
            continue
        if len(cell_eval.precursor_values) < 2 or len(cell_eval.null_values) < 2:
            continue
        null_audit_inputs.append(
            NullAuditInputCell(
                cell_key=cell_eval.cell_key,
                precursor_values=np.asarray(cell_eval.precursor_values, dtype=np.float64),
                null_values=np.asarray(cell_eval.null_values, dtype=np.float64),
            )
        )
    null_audit_result = run_null_audit_all(
        output_path=null_audit_capsule_path,
        sweep_results=tuple(null_audit_inputs),
        n_shuffles=NULL_AUDIT_N_SHUFFLES,
        rng_seed=NULL_AUDIT_RNG_SEED,
        p_value_threshold=NULL_AUDIT_P_THRESHOLD,
    )
    print(
        f"null audit: aggregate_verdict={null_audit_result.aggregate_verdict} "
        f"audited={null_audit_result.n_audited_cells} pass={null_audit_result.n_pass} "
        f"fail={null_audit_result.n_fail}",
        flush=True,
    )

    # Build per-cell-key null-audit verdict map.
    null_audit_per_cell: dict[str, str] = {}
    capsule_raw = json.loads(null_audit_capsule_path.read_text(encoding="utf-8"))
    for row in capsule_raw.get("results", []):
        null_audit_per_cell[str(row["cell_key"])] = str(row["verdict"])

    # ---- Phase 4: derive per-cell verdict (4-term conjunction) ----
    print("Phase 4 -- deriving verdict...", flush=True)
    per_cell_verdicts: list[dict[str, Any]] = []
    n_pass_cells = 0
    n_fail_cells = 0
    n_indeterminate_cells = 0
    cell_marginal_flags: list[bool] = []
    cell_passing_combos: set[tuple[str, str]] = set()  # (substrate, metric) tuples that pass

    for N in N_GRID:
        for lambda_value in LAMBDA_GRID:
            # A cell PASSES iff any metric within it satisfies R1 AND R2 AND R3 AND NULL_AUDIT
            # under the M1 null mechanism. M3 is reported for evidence but not the
            # verdict-conjunction (R2 is defined on M1 per D-002G acceptance Section 2).
            cell_passes = False
            cell_marginal = False
            metric_breakdown: list[dict[str, Any]] = []
            for metric_id in METRIC_IDS:
                m1 = next(
                    (
                        c
                        for c in all_M1
                        if c.metric_id == metric_id and c.N == N and c.lambda_value == lambda_value
                    ),
                    None,
                )
                m3 = next(
                    (
                        c
                        for c in all_M3
                        if c.metric_id == metric_id and c.N == N and c.lambda_value == lambda_value
                    ),
                    None,
                )
                if m1 is None:
                    continue
                # R1, R3 on M1 (the primary null cohort).
                r1 = _eval_R1(m1)
                r3 = _eval_R3(m1)
                # R2 only applicable at lambda > 0 (candidate is lambda > 0).
                if lambda_value > 0.0:
                    r2 = _eval_R2(m1, all_M1)
                else:
                    r2 = RuleResult("R2", 0.0, EFFECTIVE_ALPHA_PER_CELL, False, False)
                # NULL_AUDIT per the M1 cohort cell.
                null_audit_verdict_str = null_audit_per_cell.get(m1.cell_key, "MISSING")
                null_audit_passed = null_audit_verdict_str == "PASS"
                metric_passes = (
                    lambda_value > 0.0
                    and r1.passed
                    and r2.passed
                    and r3.passed
                    and null_audit_passed
                )
                metric_marginal = metric_passes and r1.marginal and r2.marginal and r3.marginal
                m3_summary: dict[str, Any] = {}
                if m3 is not None:
                    m3_summary = {
                        "status": m3.status,
                        "signal_mean": _finite_or_str(m3.signal_mean),
                        "bca_ci_lo": _finite_or_str(m3.bca_ci_lo),
                        "bca_ci_hi": _finite_or_str(m3.bca_ci_hi),
                        "signal_over_ci": _finite_or_str(m3.signal_over_ci),
                        "direction": m3.direction,
                        "direction_stability": _finite_or_str(m3.direction_stability),
                    }
                metric_breakdown.append(
                    {
                        "metric_id": metric_id,
                        "m1_status": m1.status,
                        "m1_signal_mean": _finite_or_str(m1.signal_mean),
                        "m1_bca_ci_lo": _finite_or_str(m1.bca_ci_lo),
                        "m1_bca_ci_hi": _finite_or_str(m1.bca_ci_hi),
                        "m1_signal_over_ci": _finite_or_str(m1.signal_over_ci),
                        "m1_direction": m1.direction,
                        "m1_direction_stability": _finite_or_str(m1.direction_stability),
                        "R1_passed": r1.passed,
                        "R1_marginal": r1.marginal,
                        "R2_passed": r2.passed,
                        "R2_measured_fpr": _finite_or_str(r2.measured),
                        "R2_threshold": _finite_or_str(r2.threshold),
                        "R3_passed": r3.passed,
                        "R3_marginal": r3.marginal,
                        "NULL_AUDIT_verdict": null_audit_verdict_str,
                        "metric_passes_conjunction": metric_passes,
                        "metric_marginal": metric_marginal,
                        "m3_evidence": m3_summary,
                    }
                )
                if metric_passes:
                    cell_passes = True
                    cell_passing_combos.add((SUBSTRATE_ID, metric_id))
                    if metric_marginal:
                        cell_marginal = True

            cell_key_canonical = f"[N={N},lambda={lambda_value},sub={SUBSTRATE_ID}]"
            if cell_passes:
                cell_verdict = "PASS"
                n_pass_cells += 1
            elif lambda_value <= 0.0:
                # lambda=0 cells are null cohort -- they cannot PASS (R2
                # is undefined at lambda=0 since there's no precursor),
                # so they are categorised as INDETERMINATE for the
                # verdict-conjunction (they STILL contribute to R2 FPR
                # estimation at lambda>0).
                cell_verdict = "INDETERMINATE_LAMBDA_ZERO_NULL_COHORT"
                n_indeterminate_cells += 1
            else:
                cell_verdict = "FAIL"
                n_fail_cells += 1
            cell_marginal_flags.append(cell_marginal)
            per_cell_verdicts.append(
                {
                    "cell_key": cell_key_canonical,
                    "N": int(N),
                    "lambda_value": float(lambda_value),
                    "substrate": SUBSTRATE_ID,
                    "verdict": cell_verdict,
                    "marginal": cell_marginal,
                    "metrics": metric_breakdown,
                }
            )

    # ---- Phase 4b: aggregate verdict + tier + anti-overclaim guards ----
    null_audit_fail = null_audit_result.aggregate_verdict != "PASS"
    marginal_pass = any(cell_marginal_flags) if n_pass_cells > 0 else False
    single_path_pass = len(cell_passing_combos) == 1 and n_pass_cells > 0

    if null_audit_fail:
        tier_string = TIER_REFUSED
        aggregate_verdict = "REFUSED"
    elif n_pass_cells == 0:
        tier_string = TIER_FAIL
        aggregate_verdict = "FAIL"
    elif marginal_pass:
        tier_string = TIER_MARGINAL
        aggregate_verdict = "MARGINAL_PASS"
    else:
        tier_string = TIER_PASS
        aggregate_verdict = "PASS"

    anti_overclaim_guards_triggered: list[str] = []
    if null_audit_fail:
        anti_overclaim_guards_triggered.append("NULL_AUDIT_FAIL")
    if marginal_pass:
        anti_overclaim_guards_triggered.append("MARGINAL_PASS")
    if single_path_pass:
        anti_overclaim_guards_triggered.append("SINGLE_PATH_PASS")

    # ---- Phase 4c: persist verdict capsule (per-RUN_ID) + top-level verdict ----
    verdict_per_run = {
        "schema_version": "D002H-CANONICAL-VERDICT-PER-RUN-v1",
        "run_id": RUN_ID,
        "study_id": STUDY_ID,
        "tier_string": tier_string,
        "aggregate_verdict": aggregate_verdict,
        "anti_overclaim_guards_triggered": anti_overclaim_guards_triggered,
        "per_cell_verdicts": per_cell_verdicts,
        "n_cells_total": 18,
        "n_cells_pass": int(n_pass_cells),
        "n_cells_fail": int(n_fail_cells),
        "n_cells_indeterminate": int(n_indeterminate_cells),
        "null_audit": {
            "aggregate_verdict": str(null_audit_result.aggregate_verdict),
            "n_audited_cells": int(null_audit_result.n_audited_cells),
            "n_pass": int(null_audit_result.n_pass),
            "n_fail": int(null_audit_result.n_fail),
            "capsule_sha256": str(null_audit_result.sha256),
        },
    }
    (ARTIFACT_DIR / "verdict.json").write_text(_canonical_json(verdict_per_run), encoding="utf-8")

    peak_rss_mb = _process_size(repo_root)

    top_verdict = {
        "schema_version": SCHEMA_VERSION,
        "study_id": STUDY_ID,
        "run_id": RUN_ID,
        "executed_at": _now_iso(),
        "anchor_main_sha": ANCHOR_MAIN_SHA,
        "scope": "ricci_flow substrate only",
        "grid": {
            "substrates": [SUBSTRATE_ID],
            "N": list(N_GRID),
            "lambda_values": list(LAMBDA_GRID),
            "metrics": list(METRIC_IDS),
            "n_seeds": int(N_SEEDS),
            "n_bootstrap": int(N_BOOTSTRAP),
            "total_cells_canonical": 18,
        },
        "reproducibility": {
            "base_seed": int(BASE_SEED),
            "null_seed_offset_M1": int(NULL_SEED_OFFSET_M1),
            "null_seed_M3": int(NULL_SEED_M3),
        },
        "acceptance_conjunction": (
            "R1 AND R2 AND R3 AND NULL_AUDIT "
            "(R2-B INAPPLICABLE per D002H_R2B_INAPPLICABILITY_NOTE.md)"
        ),
        "bonferroni_n_cells": int(BONFERRONI_N_CELLS),
        "effective_alpha_per_cell": float(EFFECTIVE_ALPHA_PER_CELL),
        "null_mechanisms_used": ["M1_INDEPENDENT_SEED", "M3_TOPOLOGY_CONDITIONED"],
        "n_cells_total": 18,
        "n_cells_pass": int(n_pass_cells),
        "n_cells_fail": int(n_fail_cells),
        "n_cells_indeterminate": int(n_indeterminate_cells),
        "anti_overclaim_guards": {
            "marginal_pass": bool(marginal_pass),
            "single_path_pass": bool(single_path_pass),
            "null_audit_fail": bool(null_audit_fail),
        },
        "anti_overclaim_guards_triggered": anti_overclaim_guards_triggered,
        "tier_string": tier_string,
        "aggregate_verdict": aggregate_verdict,
        "scope_note": (
            "Verdict scoped to ricci_flow substrate only per D-002H prereg. "
            "Does NOT generalise to block_structured or temporal_coupling "
            "(excluded by D-002G structural closure)."
        ),
        "d002c_ledger_touched": False,
        "d002c_ledger_sha_at_run": D002C_LEDGER_SHA_AT_RUN,
        "runtime_seconds_total": float(time.monotonic() - t_sweep_start),
        "peak_rss_MB": int(peak_rss_mb),
        "sweep_capsule_path": str(sweep_capsule_path.relative_to(repo_root)),
        "null_audit_capsule_path": str(null_audit_capsule_path.relative_to(repo_root)),
        "verdict_capsule_path": str((ARTIFACT_DIR / "verdict.json").relative_to(repo_root)),
    }
    TOP_VERDICT_PATH.write_text(_canonical_json(top_verdict), encoding="utf-8")
    print(f"top-level verdict written: {TOP_VERDICT_PATH}", flush=True)
    print(
        f"VERDICT: tier={tier_string} aggregate={aggregate_verdict} "
        f"cells_pass={n_pass_cells}/18 fail={n_fail_cells} "
        f"indeterminate={n_indeterminate_cells} "
        f"guards={anti_overclaim_guards_triggered}",
        flush=True,
    )
    return 0


def _cell_eval_to_dict(c: CellEvaluation) -> dict[str, Any]:
    return {
        "cell_key": c.cell_key,
        "substrate_id": c.substrate_id,
        "metric_id": c.metric_id,
        "N": int(c.N),
        "lambda_value": float(c.lambda_value),
        "null_mechanism": c.null_mechanism,
        "n_seeds": int(c.n_seeds),
        "n_bootstrap": int(c.n_bootstrap),
        "seed_ids": [int(s) for s in c.seed_ids],
        "precursor_values": [_finite_or_str(v) for v in c.precursor_values],
        "null_values": [_finite_or_str(v) for v in c.null_values],
        "signal_diffs": [_finite_or_str(v) for v in c.signal_diffs],
        "signal_mean": _finite_or_str(c.signal_mean),
        "bca_ci_lo": _finite_or_str(c.bca_ci_lo),
        "bca_ci_hi": _finite_or_str(c.bca_ci_hi),
        "signal_over_ci": _finite_or_str(c.signal_over_ci),
        "direction": c.direction,
        "direction_stability": _finite_or_str(c.direction_stability),
        "wallclock_seconds": float(c.wallclock_seconds),
        "status": c.status,
        "error_msg": c.error_msg,
    }


if __name__ == "__main__":
    raise SystemExit(main())
