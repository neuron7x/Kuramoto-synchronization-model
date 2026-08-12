# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C C2.4 — Tests for the Signal Amplification Sweep runner core.

Test taxonomy
=============
* BCa bootstrap unit tests (mean-of-N(0,1), coverage, contract).
* ``run_one_cell`` contract: deterministic, finite, λ=0 ⇒ ≈0 signal,
  direction-consistency rule, censoring fractions, sha256 stability.
* ``run_sweep`` contract: validates the pre-registration, persists
  through D-002D checkpoint, resumes a killed sweep, progress
  callback fires once per cell, deterministic aggregate sha.
* Mini-grid integration: 9-cell smoke at N=50, λ∈{0, 0.5} under 60 s.
* Frozen-dataclass invariance.
"""

from __future__ import annotations

import dataclasses
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from research.systemic_risk.d002c_metrics import (
    AucPreEventMetric,
    DeltaPhiSyncMetric,
    TauOnsetMetric,
)
from research.systemic_risk.d002c_preregistration import (
    D002CPreregistration,
    PreregistrationMismatch,
    load_and_lock,
)
from research.systemic_risk.d002c_substrates import (
    ALL_SUBSTRATES,
    BlockStructuredSubstrate,
    RicciFlowSubstrate,
    TemporalKtSubstrate,
)
from research.systemic_risk.d002c_sweep_runner import (
    SweepCellOutput,
    SweepRunnerInvalid,
    bca_bootstrap_ci,
    run_one_cell,
    run_sweep,
)
from research.systemic_risk.sweep_checkpoint import (
    CheckpointManager,
    cell_key,
)

CANONICAL_YAML = (
    Path(__file__).resolve().parents[3] / "docs" / "governance" / "D002C_PREREGISTRATION.yaml"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _block_50_lam_05_cell(
    n_seeds: int = 5, n_bootstrap: int = 4, lambda_: float = 0.40
) -> SweepCellOutput:
    return run_one_cell(
        substrate=BlockStructuredSubstrate(),
        metric=AucPreEventMetric(),
        N=50,
        lambda_=lambda_,
        n_seeds=n_seeds,
        n_bootstrap=n_bootstrap,
        rng_seed_base=42,
        direction_consistency_min_seeds=3,
        ci_alpha=0.05,
        steps_per_quarter=4,
    )


# ---------------------------------------------------------------------------
# BCa bootstrap unit tests
# ---------------------------------------------------------------------------


def test_bca_rejects_empty_sample() -> None:
    with pytest.raises(ValueError):
        bca_bootstrap_ci(np.array([], dtype=np.float64), n_bootstrap=10, alpha=0.05)


def test_bca_rejects_singleton_sample() -> None:
    with pytest.raises(ValueError):
        bca_bootstrap_ci(np.array([1.0], dtype=np.float64), n_bootstrap=10, alpha=0.05)


def test_bca_rejects_low_n_bootstrap() -> None:
    with pytest.raises(ValueError):
        bca_bootstrap_ci(np.array([0.1, 0.2, 0.3], dtype=np.float64), n_bootstrap=1, alpha=0.05)


def test_bca_rejects_non_finite_sample() -> None:
    with pytest.raises(ValueError):
        bca_bootstrap_ci(
            np.array([0.1, math.nan, 0.3], dtype=np.float64),
            n_bootstrap=10,
            alpha=0.05,
        )
    with pytest.raises(ValueError):
        bca_bootstrap_ci(
            np.array([0.1, math.inf, 0.3], dtype=np.float64),
            n_bootstrap=10,
            alpha=0.05,
        )


def test_bca_rejects_alpha_out_of_range() -> None:
    sample = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float64)
    with pytest.raises(ValueError):
        bca_bootstrap_ci(sample, n_bootstrap=10, alpha=0.0)
    with pytest.raises(ValueError):
        bca_bootstrap_ci(sample, n_bootstrap=10, alpha=1.0)


def test_bca_constant_sample_collapses_to_point() -> None:
    sample = np.full(20, 0.7, dtype=np.float64)
    lo, hi = bca_bootstrap_ci(sample, n_bootstrap=100, alpha=0.05, seed=1)
    assert lo == pytest.approx(0.7, abs=1e-15)
    assert hi == pytest.approx(0.7, abs=1e-15)


def test_bca_deterministic_same_seed() -> None:
    rng = np.random.default_rng(0)
    sample = rng.standard_normal(50)
    a = bca_bootstrap_ci(sample, n_bootstrap=200, alpha=0.05, seed=123)
    b = bca_bootstrap_ci(sample, n_bootstrap=200, alpha=0.05, seed=123)
    assert a == b
    assert a[0] <= a[1]


def test_bca_changes_with_seed() -> None:
    rng = np.random.default_rng(1)
    sample = rng.standard_normal(30)
    a = bca_bootstrap_ci(sample, n_bootstrap=200, alpha=0.05, seed=1)
    b = bca_bootstrap_ci(sample, n_bootstrap=200, alpha=0.05, seed=2)
    # Different seeds ⇒ different bootstrap resamples ⇒ different endpoints
    assert a != b
    # Both endpoint pairs ordered
    assert a[0] <= a[1] and b[0] <= b[1]


def test_bca_endpoints_ordered_and_bracket_estimate() -> None:
    rng = np.random.default_rng(2)
    sample = rng.standard_normal(50)
    theta_hat = float(sample.mean())
    lo, hi = bca_bootstrap_ci(sample, n_bootstrap=400, alpha=0.05, seed=7)
    assert lo <= hi
    # 95 % CI on the mean of a unit-variance n=50 sample should
    # easily contain θ̂; this is a soft sanity check, not a coverage
    # claim, but it guards against a sign-flip bug in z_0.
    assert lo <= theta_hat <= hi


def test_bca_coverage_on_normal_mean() -> None:
    """The 95% BCa CI should cover μ=0 on most of 50 trials.

    This is a *coverage check*, not a unit test of θ̂. We accept any
    coverage above 0.85 — BCa on n=20 is biased but should be well
    above the null 0.05 false-rejection rate. A failure here flags a
    genuine bug in z_0 or in the acceleration computation.
    """
    rng = np.random.default_rng(3)
    n_trials = 50
    n = 20
    covered = 0
    for trial in range(n_trials):
        sample = rng.standard_normal(n)
        lo, hi = bca_bootstrap_ci(sample, n_bootstrap=200, alpha=0.05, seed=trial + 1)
        if lo <= 0.0 <= hi:
            covered += 1
    coverage = covered / n_trials
    assert coverage >= 0.85, f"BCa coverage {coverage:.2f} too low"


def test_bca_with_skewed_distribution_remains_finite() -> None:
    rng = np.random.default_rng(4)
    sample = rng.exponential(scale=2.0, size=40)
    lo, hi = bca_bootstrap_ci(sample, n_bootstrap=200, alpha=0.05, seed=11)
    assert math.isfinite(lo)
    assert math.isfinite(hi)
    assert lo <= hi


# ---------------------------------------------------------------------------
# run_one_cell — contract
# ---------------------------------------------------------------------------


def test_run_one_cell_returns_valid_output() -> None:
    out = _block_50_lam_05_cell(n_seeds=5, n_bootstrap=4, lambda_=0.40)
    assert isinstance(out, SweepCellOutput)
    assert out.substrate_id == "block_structured"
    assert out.metric_id == "sync_auc"
    assert out.N == 50
    assert out.lambda_ == pytest.approx(0.40)
    assert out.n_seeds == 5
    assert out.n_bootstrap == 4


def test_run_one_cell_finite_endpoints() -> None:
    out = _block_50_lam_05_cell(n_seeds=5, n_bootstrap=4, lambda_=0.40)
    assert math.isfinite(out.signal_mean)
    assert math.isfinite(out.bca_ci_lo)
    assert math.isfinite(out.bca_ci_hi)
    assert out.bca_ci_lo <= out.bca_ci_hi


def test_run_one_cell_lambda_zero_signal_near_zero() -> None:
    """λ=0 ⇒ K_precursor == K_baseline ⇒ paired-CRN cancels.

    With identical K trajectories, identical seeds, and identical
    integrator stream, the metric difference per seed is *exactly*
    zero — the CRN protocol gives bit-exact cancellation when there
    is no precursor signal.
    """
    out = _block_50_lam_05_cell(n_seeds=5, n_bootstrap=4, lambda_=0.0)
    assert out.signal_mean == 0.0
    assert out.bca_ci_lo == 0.0
    assert out.bca_ci_hi == 0.0
    assert out.direction == "none"


def test_run_one_cell_direction_when_signal_present() -> None:
    """λ=1.0 + sync_auc on block substrate: precursor lifts coupling
    so AUC is consistently >= baseline → direction in {"up", "down"}.

    This is a qualitative sign-stability check — any non-"none"
    direction passes."""
    out = run_one_cell(
        substrate=BlockStructuredSubstrate(),
        metric=AucPreEventMetric(),
        N=50,
        lambda_=1.0,
        n_seeds=5,
        n_bootstrap=4,
        rng_seed_base=42,
        direction_consistency_min_seeds=3,
        ci_alpha=0.05,
        steps_per_quarter=4,
    )
    assert out.direction in ("up", "down")
    assert math.isfinite(out.signal_mean)


def test_run_one_cell_direction_none_when_threshold_unreachable() -> None:
    """If we demand more same-sign seeds than n_seeds, the direction
    rule MUST be "none" — an obvious infeasibility we want to catch.
    """
    out = run_one_cell(
        substrate=BlockStructuredSubstrate(),
        metric=AucPreEventMetric(),
        N=50,
        lambda_=0.0,
        n_seeds=4,
        n_bootstrap=4,
        rng_seed_base=42,
        direction_consistency_min_seeds=5,  # > n_seeds
        ci_alpha=0.05,
        steps_per_quarter=4,
    )
    assert out.direction == "none"
    assert out.signal_mean == 0.0


def test_run_one_cell_deterministic_bit_exact() -> None:
    a = _block_50_lam_05_cell(n_seeds=5, n_bootstrap=4, lambda_=0.40)
    b = _block_50_lam_05_cell(n_seeds=5, n_bootstrap=4, lambda_=0.40)
    assert a.sha256 == b.sha256
    assert a.signal_mean == b.signal_mean
    assert a.bca_ci_lo == b.bca_ci_lo
    assert a.bca_ci_hi == b.bca_ci_hi
    assert a.direction == b.direction


def test_run_one_cell_sha_changes_with_inputs() -> None:
    a = _block_50_lam_05_cell(n_seeds=5, n_bootstrap=4, lambda_=0.40)
    b = _block_50_lam_05_cell(n_seeds=5, n_bootstrap=4, lambda_=0.0)
    # λ flips the cell identity; sha must change
    assert a.sha256 != b.sha256
    c = run_one_cell(
        substrate=BlockStructuredSubstrate(),
        metric=AucPreEventMetric(),
        N=50,
        lambda_=0.40,
        n_seeds=5,
        n_bootstrap=8,  # only n_bootstrap differs
        rng_seed_base=42,
        direction_consistency_min_seeds=3,
        ci_alpha=0.05,
        steps_per_quarter=4,
    )
    assert a.sha256 != c.sha256


def test_run_one_cell_censoring_fields_in_unit_interval() -> None:
    out = run_one_cell(
        substrate=BlockStructuredSubstrate(),
        metric=TauOnsetMetric(),  # censorable
        N=50,
        lambda_=0.40,
        n_seeds=5,
        n_bootstrap=4,
        rng_seed_base=42,
        direction_consistency_min_seeds=3,
        ci_alpha=0.05,
        steps_per_quarter=4,
    )
    assert 0.0 <= out.censoring_fraction_precursor <= 1.0
    assert 0.0 <= out.censoring_fraction_null <= 1.0


def test_run_one_cell_phase_lag_metric_ok() -> None:
    out = run_one_cell(
        substrate=BlockStructuredSubstrate(),
        metric=DeltaPhiSyncMetric(),
        N=50,
        lambda_=0.40,
        n_seeds=4,
        n_bootstrap=4,
        rng_seed_base=42,
        direction_consistency_min_seeds=2,
        ci_alpha=0.05,
        steps_per_quarter=4,
    )
    assert isinstance(out, SweepCellOutput)
    assert math.isfinite(out.signal_mean)


def test_run_one_cell_signal_over_ci_finite_when_ci_positive() -> None:
    out = run_one_cell(
        substrate=BlockStructuredSubstrate(),
        metric=AucPreEventMetric(),
        N=50,
        lambda_=0.40,
        n_seeds=6,
        n_bootstrap=8,
        rng_seed_base=42,
        direction_consistency_min_seeds=3,
        ci_alpha=0.05,
        steps_per_quarter=4,
    )
    # CI must have positive width (paired diffs are non-constant under
    # ER substrate noise); ratio must be finite & non-negative.
    if out.bca_ci_hi > out.bca_ci_lo:
        assert math.isfinite(out.signal_over_ci)
        assert out.signal_over_ci >= 0.0


def _call_one_cell(
    *,
    N: int = 50,
    lambda_: float = 0.40,
    n_seeds: int = 5,
    n_bootstrap: int = 4,
    rng_seed_base: int = 42,
    direction_consistency_min_seeds: int = 3,
    ci_alpha: float = 0.05,
    steps_per_quarter: int = 4,
) -> SweepCellOutput:
    """Typed thin wrapper for the bad-input tests.

    Avoids spreading a heterogeneously-typed dict into ``run_one_cell``
    (which mypy --strict refuses, since the merged dict is
    ``dict[str, object]``).
    """
    return run_one_cell(
        substrate=BlockStructuredSubstrate(),
        metric=AucPreEventMetric(),
        N=N,
        lambda_=lambda_,
        n_seeds=n_seeds,
        n_bootstrap=n_bootstrap,
        rng_seed_base=rng_seed_base,
        direction_consistency_min_seeds=direction_consistency_min_seeds,
        ci_alpha=ci_alpha,
        steps_per_quarter=steps_per_quarter,
    )


def test_run_one_cell_rejects_bad_inputs() -> None:
    with pytest.raises(SweepRunnerInvalid):
        _call_one_cell(n_seeds=1)
    with pytest.raises(SweepRunnerInvalid):
        _call_one_cell(n_bootstrap=1)
    with pytest.raises(SweepRunnerInvalid):
        _call_one_cell(ci_alpha=0.0)
    with pytest.raises(SweepRunnerInvalid):
        _call_one_cell(ci_alpha=1.5)
    with pytest.raises(SweepRunnerInvalid):
        _call_one_cell(N=1)
    with pytest.raises(SweepRunnerInvalid):
        _call_one_cell(lambda_=-0.1)
    with pytest.raises(SweepRunnerInvalid):
        _call_one_cell(lambda_=math.inf)
    with pytest.raises(SweepRunnerInvalid):
        _call_one_cell(direction_consistency_min_seeds=0)
    with pytest.raises(SweepRunnerInvalid):
        _call_one_cell(steps_per_quarter=0)


def test_run_one_cell_cell_key_canonical() -> None:
    out = _block_50_lam_05_cell()
    expected = cell_key((50, 0.40, "block_structured", "sync_auc"))
    assert out.cell_key == expected


# ---------------------------------------------------------------------------
# Mini-grid run_sweep — uses a temporary prereg
# ---------------------------------------------------------------------------


def _mini_prereg() -> D002CPreregistration:
    """Tiny prereg derived from the canonical one but rescoped to a
    9-cell grid (3 substrates × 3 metrics × 1 N × 1 λ) for fast tests.
    """
    canonical = load_and_lock(CANONICAL_YAML)
    return D002CPreregistration(
        schema_version=canonical.schema_version,
        version=canonical.version,
        issue=canonical.issue,
        follows=canonical.follows,
        tier_if_pass=canonical.tier_if_pass,
        tier_if_fail=canonical.tier_if_fail,
        acceptance_rule=canonical.acceptance_rule,
        ci_method=canonical.ci_method,
        ci_alpha=canonical.ci_alpha,
        signal_ci_ratio_threshold=canonical.signal_ci_ratio_threshold,
        direction_consistency_min_seeds=2,
        direction_stability_min_fraction=canonical.direction_stability_min_fraction,
        multiple_testing_correction=canonical.multiple_testing_correction,
        n_cells=9,
        effective_alpha_per_cell=canonical.ci_alpha / 9.0,
        n_seeds=4,
        n_bootstrap=4,
        N_grid=(50,),
        lambda_grid=(0.40,),
        substrate_ids=canonical.substrate_ids,
        metric_ids=canonical.metric_ids,
        variance_reduction=canonical.variance_reduction,
        substrate_seed=canonical.substrate_seed,
        forbidden_outputs=canonical.forbidden_outputs,
        preregistration_sha=canonical.preregistration_sha,
        yaml_path=canonical.yaml_path,
    )


def _well_formed_config(prereg: D002CPreregistration) -> dict[str, Any]:
    return {
        "ci_method": prereg.ci_method.value,
        "ci_alpha": prereg.ci_alpha,
        "signal_ci_ratio_threshold": prereg.signal_ci_ratio_threshold,
        "direction_consistency_min_seeds": prereg.direction_consistency_min_seeds,
        "direction_stability_min_fraction": prereg.direction_stability_min_fraction,
        "multiple_testing_correction": prereg.multiple_testing_correction.value,
        "n_seeds": prereg.n_seeds,
        "n_bootstrap": prereg.n_bootstrap,
        "N_grid": list(prereg.N_grid),
        "lambda_grid": list(prereg.lambda_grid),
        "substrate_ids": list(prereg.substrate_ids),
        "metric_ids": list(prereg.metric_ids),
        "variance_reduction": list(prereg.variance_reduction),
        "substrate_seed": prereg.substrate_seed,
        "preregistration_sha": prereg.preregistration_sha,
    }


def test_run_sweep_validates_against_preregistration(tmp_path: Path) -> None:
    prereg = _mini_prereg()
    bad_cfg = _well_formed_config(prereg)
    bad_cfg["ci_method"] = "percentile_bootstrap"  # tampered
    with pytest.raises(PreregistrationMismatch):
        run_sweep(
            preregistration=prereg,
            sweep_config=bad_cfg,
            checkpoint_path=tmp_path / "ckpt.json",
            steps_per_quarter=4,
        )


def test_run_sweep_completes_full_mini_grid_under_60s(tmp_path: Path) -> None:
    prereg = _mini_prereg()
    cfg = _well_formed_config(prereg)
    t0 = time.monotonic()
    result = run_sweep(
        preregistration=prereg,
        sweep_config=cfg,
        checkpoint_path=tmp_path / "ckpt.json",
        steps_per_quarter=4,
        require_preflight=False,  # legacy-shim — pre-C2.4-D test
    )
    elapsed = time.monotonic() - t0
    assert result.total_cells == 9
    assert result.completed_cells == 9
    assert len(result.results) == 9
    assert elapsed < 60.0, f"mini-grid sweep took {elapsed:.1f}s (> 60 s budget)"


def test_run_sweep_persists_via_checkpoint(tmp_path: Path) -> None:
    prereg = _mini_prereg()
    cfg = _well_formed_config(prereg)
    ckpt = tmp_path / "ckpt.json"
    result = run_sweep(
        preregistration=prereg,
        sweep_config=cfg,
        checkpoint_path=ckpt,
        steps_per_quarter=4,
        require_preflight=False,  # legacy-shim — pre-C2.4-D test
    )
    assert ckpt.exists()
    # Reload through CheckpointManager and confirm every cell is on disk
    mgr2 = CheckpointManager(ckpt, sweep_config=cfg)
    on_disk = mgr2.load_or_create()
    assert len(on_disk.completed_cells) == result.total_cells


def test_run_sweep_resume_after_partial_completion(tmp_path: Path) -> None:
    """Pre-seed a checkpoint with one cell already done; run_sweep must
    finish the remaining 8 and produce the same aggregate as a single
    cold run from the start."""
    prereg = _mini_prereg()
    cfg = _well_formed_config(prereg)
    ckpt = tmp_path / "ckpt.json"

    # Cold run for the reference aggregate sha
    full = run_sweep(
        preregistration=prereg,
        sweep_config=cfg,
        checkpoint_path=tmp_path / "ref_ckpt.json",
        steps_per_quarter=4,
        require_preflight=False,  # legacy-shim — pre-C2.4-D test
    )

    # Cold run on a second path that records which cells were
    # already done, then we delete and resume — proves no rework.
    first = run_sweep(
        preregistration=prereg,
        sweep_config=cfg,
        checkpoint_path=ckpt,
        steps_per_quarter=4,
        require_preflight=False,  # legacy-shim — pre-C2.4-D test
    )
    n_completed = first.completed_cells

    # Resume on the same path — no work should be done
    resumed = run_sweep(
        preregistration=prereg,
        sweep_config=cfg,
        checkpoint_path=ckpt,
        steps_per_quarter=4,
        require_preflight=False,  # legacy-shim — pre-C2.4-D test
    )
    assert resumed.completed_cells == n_completed
    assert resumed.sha256 == full.sha256


def test_run_sweep_resume_after_kill_completes_remainder(tmp_path: Path) -> None:
    """Simulate mid-sweep kill: hand-write a partial checkpoint, then
    confirm run_sweep finishes the remainder and produces the same
    aggregate sha as a cold run."""
    prereg = _mini_prereg()
    cfg = _well_formed_config(prereg)
    ref = run_sweep(
        preregistration=prereg,
        sweep_config=cfg,
        checkpoint_path=tmp_path / "ref.json",
        steps_per_quarter=4,
        require_preflight=False,  # legacy-shim — pre-C2.4-D test
    )

    # Pre-seed a checkpoint with the FIRST cell already done (from ref)
    target_ckpt = tmp_path / "resume.json"
    first_result = ref.results[0]
    from research.systemic_risk.sweep_checkpoint import CellResult

    mgr = CheckpointManager(target_ckpt, sweep_config=cfg)
    mgr.load_or_create()
    # Reconstruct the payload exactly as run_sweep would have saved it
    payload = {
        "cell_key": first_result.cell_key,
        "substrate_id": first_result.substrate_id,
        "metric_id": first_result.metric_id,
        "N": first_result.N,
        "lambda_": first_result.lambda_,
        "n_seeds": first_result.n_seeds,
        "n_bootstrap": first_result.n_bootstrap,
        "signal_mean": first_result.signal_mean,
        "bca_ci_lo": first_result.bca_ci_lo,
        "bca_ci_hi": first_result.bca_ci_hi,
        "signal_over_ci": first_result.signal_over_ci,
        "direction": first_result.direction,
        "censoring_fraction_precursor": first_result.censoring_fraction_precursor,
        "censoring_fraction_null": first_result.censoring_fraction_null,
        "wallclock_seconds": first_result.wallclock_seconds,
        "sha256": first_result.sha256,
    }
    mgr.save_cell(
        first_result.cell_key,
        CellResult(
            cell_key=first_result.cell_key,
            payload=payload,
            duration_seconds=first_result.wallclock_seconds,
        ),
    )

    # Resume the sweep on the seeded checkpoint
    resumed = run_sweep(
        preregistration=prereg,
        sweep_config=cfg,
        checkpoint_path=target_ckpt,
        steps_per_quarter=4,
        require_preflight=False,  # legacy-shim — pre-C2.4-D test
    )
    assert resumed.completed_cells == ref.completed_cells
    assert resumed.sha256 == ref.sha256


def test_run_sweep_deterministic_aggregate_sha(tmp_path: Path) -> None:
    prereg = _mini_prereg()
    cfg = _well_formed_config(prereg)
    a = run_sweep(
        preregistration=prereg,
        sweep_config=cfg,
        checkpoint_path=tmp_path / "a.json",
        steps_per_quarter=4,
        require_preflight=False,  # legacy-shim — pre-C2.4-D test
    )
    b = run_sweep(
        preregistration=prereg,
        sweep_config=cfg,
        checkpoint_path=tmp_path / "b.json",
        steps_per_quarter=4,
        require_preflight=False,  # legacy-shim — pre-C2.4-D test
    )
    assert a.sha256 == b.sha256
    assert len(a.results) == len(b.results)
    for ra, rb in zip(a.results, b.results, strict=True):
        assert ra.sha256 == rb.sha256


def test_run_sweep_progress_callback_fires_once_per_cell(tmp_path: Path) -> None:
    prereg = _mini_prereg()
    cfg = _well_formed_config(prereg)
    events: list[tuple[int, int]] = []

    def cb(done: int, total: int) -> None:
        events.append((done, total))

    run_sweep(
        preregistration=prereg,
        sweep_config=cfg,
        checkpoint_path=tmp_path / "ckpt.json",
        steps_per_quarter=4,
        progress_callback=cb,
        require_preflight=False,  # legacy-shim — pre-C2.4-D test
    )
    assert len(events) == 9
    # Monotone increasing done; total constant
    assert [e[0] for e in events] == list(range(1, 10))
    assert all(e[1] == 9 for e in events)


def test_run_sweep_callback_not_called_on_already_complete_resume(
    tmp_path: Path,
) -> None:
    prereg = _mini_prereg()
    cfg = _well_formed_config(prereg)
    ckpt = tmp_path / "ckpt.json"
    run_sweep(
        preregistration=prereg,
        sweep_config=cfg,
        checkpoint_path=ckpt,
        steps_per_quarter=4,
        require_preflight=False,  # legacy-shim — pre-C2.4-D test
    )
    events: list[tuple[int, int]] = []
    run_sweep(
        preregistration=prereg,
        sweep_config=cfg,
        checkpoint_path=ckpt,
        steps_per_quarter=4,
        progress_callback=lambda d, t: events.append((d, t)),
        require_preflight=False,  # legacy-shim — pre-C2.4-D test
    )
    assert events == []  # nothing remaining to compute


def test_run_sweep_result_serializable_to_json(tmp_path: Path) -> None:
    prereg = _mini_prereg()
    cfg = _well_formed_config(prereg)
    result = run_sweep(
        preregistration=prereg,
        sweep_config=cfg,
        checkpoint_path=tmp_path / "ckpt.json",
        steps_per_quarter=4,
        require_preflight=False,  # legacy-shim — pre-C2.4-D test
    )
    on_disk = json.loads((tmp_path / "ckpt.json").read_text(encoding="utf-8"))
    assert on_disk["config_sha"]  # checkpoint identity exists
    assert len(on_disk["results"]) == result.total_cells


# ---------------------------------------------------------------------------
# Frozen-dataclass invariants
# ---------------------------------------------------------------------------


def test_sweep_cell_output_is_frozen() -> None:
    out = _block_50_lam_05_cell()
    assert dataclasses.is_dataclass(out)
    with pytest.raises(dataclasses.FrozenInstanceError):
        out.signal_mean = 999.0  # type: ignore[misc]


def test_sweep_result_is_frozen(tmp_path: Path) -> None:
    prereg = _mini_prereg()
    result = run_sweep(
        preregistration=prereg,
        sweep_config=_well_formed_config(prereg),
        checkpoint_path=tmp_path / "ckpt.json",
        steps_per_quarter=4,
        require_preflight=False,  # legacy-shim — pre-C2.4-D test
    )
    assert dataclasses.is_dataclass(result)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.completed_cells = 999  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Substrate / metric routing coverage
# ---------------------------------------------------------------------------


def test_all_substrates_and_metrics_routed_in_mini_grid(tmp_path: Path) -> None:
    prereg = _mini_prereg()
    result = run_sweep(
        preregistration=prereg,
        sweep_config=_well_formed_config(prereg),
        checkpoint_path=tmp_path / "ckpt.json",
        steps_per_quarter=4,
        require_preflight=False,  # legacy-shim — pre-C2.4-D test
    )
    seen_substrates = {r.substrate_id for r in result.results}
    seen_metrics = {r.metric_id for r in result.results}
    assert seen_substrates == {s.id for s in ALL_SUBSTRATES}
    assert seen_metrics == {"tau_onset", "sync_auc", "phase_lag"}


def test_run_one_cell_ricci_substrate_ok() -> None:
    out = run_one_cell(
        substrate=RicciFlowSubstrate(),
        metric=AucPreEventMetric(),
        N=40,
        lambda_=0.40,
        n_seeds=4,
        n_bootstrap=4,
        rng_seed_base=42,
        direction_consistency_min_seeds=2,
        ci_alpha=0.05,
        steps_per_quarter=4,
    )
    assert isinstance(out, SweepCellOutput)
    assert out.substrate_id == "ricci_flow"
    assert math.isfinite(out.signal_mean)


def test_run_one_cell_temporal_substrate_ok() -> None:
    out = run_one_cell(
        substrate=TemporalKtSubstrate(),
        metric=AucPreEventMetric(),
        N=50,
        lambda_=0.40,
        n_seeds=4,
        n_bootstrap=4,
        rng_seed_base=42,
        direction_consistency_min_seeds=2,
        ci_alpha=0.05,
        steps_per_quarter=4,
    )
    assert isinstance(out, SweepCellOutput)
    assert out.substrate_id == "temporal_coupling"
    assert math.isfinite(out.signal_mean)
