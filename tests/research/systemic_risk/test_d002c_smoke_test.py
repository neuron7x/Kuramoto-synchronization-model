# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C C2.4 — Tests for the mini-grid smoke pre-flight.

Pins the load-bearing contract:

  * tiny grid completes end-to-end and PASSes
  * impossibly tight budget FAILs with verdict captured
  * raising cells are recorded with error text, not propagated
  * atomic capsule is JSON-parseable and leaves no orphan .tmp
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from research.systemic_risk.d002c_metrics import (
    AucPreEventMetric,
    KuramotoTrajectory,
    Metric,
    MetricEvaluation,
)
from research.systemic_risk.d002c_smoke_test import (
    DEFAULT_SMOKE_LAMBDA_GRID,
    DEFAULT_SMOKE_MAX_WALLCLOCK_SEC,
    DEFAULT_SMOKE_N_GRID,
    DEFAULT_SMOKE_N_SEEDS,
    DEFAULT_SMOKE_RNG_SEED_BASE,
    DEFAULT_SMOKE_STEPS_PER_QUARTER,
    SmokeTestInvalid,
    SmokeTestResult,
    _atomic_write,
    _run_cell,
    run_smoke_test,
)
from research.systemic_risk.d002c_substrates import (
    BlockStructuredSubstrate,
    SubstrateRealization,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_default_constants_have_locked_values() -> None:
    """Locked defaults — drift here breaks the sweep gate's pre-flight."""
    assert DEFAULT_SMOKE_N_GRID == (50, 100)
    assert DEFAULT_SMOKE_LAMBDA_GRID == (0.0, 0.5)
    assert DEFAULT_SMOKE_N_SEEDS == 5
    assert DEFAULT_SMOKE_MAX_WALLCLOCK_SEC == 60.0
    assert DEFAULT_SMOKE_STEPS_PER_QUARTER == 6
    assert DEFAULT_SMOKE_RNG_SEED_BASE == 42


def test_smoke_test_result_is_frozen() -> None:
    """Frozen-dataclass contract — mutating must raise."""
    res = run_smoke_test(
        substrates=(BlockStructuredSubstrate(),),
        metrics=(AucPreEventMetric(),),
        N_grid=(20,),
        lambda_grid=(0.0,),
        n_seeds=2,
        steps_per_quarter=3,
        max_wallclock_seconds=120.0,
    )
    assert isinstance(res, SmokeTestResult)
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.verdict = "MUTATED"  # type: ignore[misc]


def test_smoke_cell_result_is_frozen() -> None:
    """Per-cell record is also frozen."""
    res = run_smoke_test(
        substrates=(BlockStructuredSubstrate(),),
        metrics=(AucPreEventMetric(),),
        N_grid=(20,),
        lambda_grid=(0.0,),
        n_seeds=2,
        steps_per_quarter=3,
        max_wallclock_seconds=120.0,
    )
    assert len(res.cells) >= 1
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.cells[0].ok = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_tiny_grid_returns_pass_with_all_cells_ok() -> None:
    """1×1×1 grid on a stable (substrate, metric) ⇒ PASS, n_failed=0."""
    res = run_smoke_test(
        substrates=(BlockStructuredSubstrate(),),
        metrics=(AucPreEventMetric(),),
        N_grid=(20,),
        lambda_grid=(0.0,),
        n_seeds=2,
        steps_per_quarter=3,
        max_wallclock_seconds=120.0,
    )
    assert res.verdict == "PASS"
    assert res.n_cells_total == 1
    assert res.n_cells_failed == 0
    assert res.cells[0].ok is True
    assert res.cells[0].error == ""


def test_tiny_grid_runs_all_9_combos() -> None:
    """Full registry on a single (N, λ) point ⇒ 9 cells (3×3)."""
    res = run_smoke_test(
        N_grid=(20,),
        lambda_grid=(0.0,),
        n_seeds=2,
        steps_per_quarter=3,
        max_wallclock_seconds=180.0,
    )
    # 3 substrates × 3 metrics × 1 N × 1 λ
    assert res.n_cells_total == 9
    assert res.verdict == "PASS"
    assert res.n_cells_failed == 0


def test_cells_carry_substrate_metric_grid_metadata() -> None:
    """Every cell records its (substrate, metric, N, λ) coordinates."""
    res = run_smoke_test(
        substrates=(BlockStructuredSubstrate(),),
        metrics=(AucPreEventMetric(),),
        N_grid=(20, 25),
        lambda_grid=(0.0, 0.5),
        n_seeds=2,
        steps_per_quarter=3,
        max_wallclock_seconds=120.0,
    )
    assert res.n_cells_total == 4
    seen = {(c.N, c.lambda_) for c in res.cells}
    assert seen == {(20, 0.0), (20, 0.5), (25, 0.0), (25, 0.5)}
    assert all(c.substrate_id == "block_structured" for c in res.cells)
    assert all(c.metric_id == "sync_auc" for c in res.cells)


# ---------------------------------------------------------------------------
# Budget enforcement
# ---------------------------------------------------------------------------


def test_impossibly_tight_budget_yields_fail() -> None:
    """``max_wallclock_seconds=0.001`` is impossible to meet ⇒ FAIL."""
    res = run_smoke_test(
        substrates=(BlockStructuredSubstrate(),),
        metrics=(AucPreEventMetric(),),
        N_grid=(20,),
        lambda_grid=(0.0,),
        n_seeds=2,
        steps_per_quarter=3,
        max_wallclock_seconds=0.001,
    )
    assert res.verdict == "FAIL"
    assert res.total_wallclock_seconds > 0.001
    # Cells themselves may have succeeded — only the budget gate fired.
    assert res.n_cells_failed == 0
    assert res.n_cells_ok == res.n_cells_total


# ---------------------------------------------------------------------------
# Failure isolation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _RaisingMetric:
    """Synthetic metric that always raises — used to verify per-cell
    isolation. Without isolation, ONE bad cell would crash the smoke
    test and we'd never get to see the rest."""

    metric_id_: str = "raises_always"

    @property
    def id(self) -> str:
        return self.metric_id_

    def evaluate(self, trajectory: KuramotoTrajectory) -> MetricEvaluation:
        raise RuntimeError("synthetic explosion for smoke-isolation test")


def test_raising_cell_records_error_does_not_short_circuit() -> None:
    """A cell whose metric raises must:
    * record ok=False + non-empty error text
    * NOT prevent the surrounding cells from running
    """
    raising: Metric = _RaisingMetric()
    res = run_smoke_test(
        substrates=(BlockStructuredSubstrate(),),
        metrics=(raising, AucPreEventMetric()),
        N_grid=(20,),
        lambda_grid=(0.0,),
        n_seeds=2,
        steps_per_quarter=3,
        max_wallclock_seconds=120.0,
    )
    assert res.n_cells_total == 2
    assert res.n_cells_failed == 1
    assert res.n_cells_ok == 1
    assert res.verdict == "FAIL"
    raising_cell = next(c for c in res.cells if c.metric_id == "raises_always")
    ok_cell = next(c for c in res.cells if c.metric_id == "sync_auc")
    assert raising_cell.ok is False
    assert "synthetic explosion" in raising_cell.error
    assert ok_cell.ok is True
    assert ok_cell.error == ""


def test_run_cell_returns_failure_record_not_exception() -> None:
    """Direct probe: _run_cell on a raising metric returns a Result with
    ok=False — never propagates the exception."""
    raising: Metric = _RaisingMetric()
    cell = _run_cell(
        BlockStructuredSubstrate(),
        raising,
        N=20,
        lambda_=0.0,
        n_seeds=2,
        rng_seed_base=42,
        steps_per_quarter=3,
        omega_gamma=0.5,
    )
    assert cell.ok is False
    assert cell.error != ""
    assert cell.substrate_id == "block_structured"
    assert cell.metric_id == "raises_always"


# ---------------------------------------------------------------------------
# Determinism / sha
# ---------------------------------------------------------------------------


def test_sha256_round_trips_with_preflight_canonical_form(tmp_path: Path) -> None:
    """Round-trip contract: the writer's sha MUST equal the preflight
    validator's recompute over (capsule - sha256). This is the contract
    that C2.4-D enforces — any drift triggers ``capsule_sha256_mismatch``.

    Wallclock fields are now part of the full-capsule body (so the
    validator can recompute over the on-disk JSON without rebuilding a
    surrogate dict). Two separate runs therefore produce DIFFERENT
    shas, but each run's sha MUST round-trip cleanly.
    """
    import hashlib

    from research.systemic_risk.d002c_preflight import canonical_preflight_json

    out = tmp_path / "smoke.json"
    res = run_smoke_test(
        substrates=(BlockStructuredSubstrate(),),
        metrics=(AucPreEventMetric(),),
        N_grid=(20,),
        lambda_grid=(0.0, 0.5),
        n_seeds=2,
        steps_per_quarter=3,
        max_wallclock_seconds=120.0,
        output_path=out,
    )
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    body = {k: v for k, v in on_disk.items() if k != "sha256"}
    recomputed = hashlib.sha256(canonical_preflight_json(body).encode("utf-8")).hexdigest()
    assert on_disk["sha256"] == recomputed
    assert res.sha256 == recomputed


def test_sha256_changes_with_grid() -> None:
    """sha must distinguish configurations — different N_grid ⇒ different
    sha even with everything else equal."""
    a = run_smoke_test(
        substrates=(BlockStructuredSubstrate(),),
        metrics=(AucPreEventMetric(),),
        N_grid=(20,),
        lambda_grid=(0.0,),
        n_seeds=2,
        steps_per_quarter=3,
        max_wallclock_seconds=120.0,
    )
    b = run_smoke_test(
        substrates=(BlockStructuredSubstrate(),),
        metrics=(AucPreEventMetric(),),
        N_grid=(25,),
        lambda_grid=(0.0,),
        n_seeds=2,
        steps_per_quarter=3,
        max_wallclock_seconds=120.0,
    )
    assert a.sha256 != b.sha256


# ---------------------------------------------------------------------------
# Input validation / fail-closed
# ---------------------------------------------------------------------------


def test_empty_substrates_raises() -> None:
    with pytest.raises(SmokeTestInvalid):
        run_smoke_test(
            substrates=(),
            metrics=(AucPreEventMetric(),),
            N_grid=(20,),
            lambda_grid=(0.0,),
        )


def test_empty_metrics_raises() -> None:
    with pytest.raises(SmokeTestInvalid):
        run_smoke_test(
            substrates=(BlockStructuredSubstrate(),),
            metrics=(),
            N_grid=(20,),
            lambda_grid=(0.0,),
        )


def test_empty_N_grid_raises() -> None:
    with pytest.raises(SmokeTestInvalid):
        run_smoke_test(
            substrates=(BlockStructuredSubstrate(),),
            metrics=(AucPreEventMetric(),),
            N_grid=(),
            lambda_grid=(0.0,),
        )


def test_empty_lambda_grid_raises() -> None:
    with pytest.raises(SmokeTestInvalid):
        run_smoke_test(
            substrates=(BlockStructuredSubstrate(),),
            metrics=(AucPreEventMetric(),),
            N_grid=(20,),
            lambda_grid=(),
        )


def test_bad_budget_raises() -> None:
    with pytest.raises(SmokeTestInvalid):
        run_smoke_test(
            substrates=(BlockStructuredSubstrate(),),
            metrics=(AucPreEventMetric(),),
            N_grid=(20,),
            lambda_grid=(0.0,),
            max_wallclock_seconds=-1.0,
        )
    with pytest.raises(SmokeTestInvalid):
        run_smoke_test(
            substrates=(BlockStructuredSubstrate(),),
            metrics=(AucPreEventMetric(),),
            N_grid=(20,),
            lambda_grid=(0.0,),
            max_wallclock_seconds=float("inf"),
        )


def test_bad_n_seeds_raises() -> None:
    with pytest.raises(SmokeTestInvalid):
        run_smoke_test(
            substrates=(BlockStructuredSubstrate(),),
            metrics=(AucPreEventMetric(),),
            N_grid=(20,),
            lambda_grid=(0.0,),
            n_seeds=0,
        )


# ---------------------------------------------------------------------------
# Atomic capsule
# ---------------------------------------------------------------------------


def test_atomic_capsule_round_trips(tmp_path: Path) -> None:
    """End-to-end: run a tiny smoke, persist, parse, check sha matches."""
    out = tmp_path / "smoke_capsule.json"
    res = run_smoke_test(
        substrates=(BlockStructuredSubstrate(),),
        metrics=(AucPreEventMetric(),),
        N_grid=(20,),
        lambda_grid=(0.0,),
        n_seeds=2,
        steps_per_quarter=3,
        max_wallclock_seconds=120.0,
        output_path=out,
    )
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["verdict"] == "PASS"
    assert data["sha256"] == res.sha256
    assert data["n_cells_total"] == res.n_cells_total
    # No orphan .tmp left behind
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []


def test_atomic_write_no_orphan_tmp_on_success(tmp_path: Path) -> None:
    """Direct probe of the atomic helper — successful path leaves only
    the final file, no .tmp residue."""
    target = tmp_path / "x.json"
    _atomic_write(target, {"a": 1, "b": "two"})
    assert target.exists()
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []


def test_atomic_write_no_orphan_tmp_on_exception(tmp_path: Path) -> None:
    """Atomic helper must clean .tmp even when serialisation fails."""
    target = tmp_path / "x.json"

    class Unserialisable:
        pass

    payload: dict[str, object] = {"bad": Unserialisable()}
    with pytest.raises(TypeError):
        _atomic_write(target, payload)
    assert not target.exists()
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []


# ---------------------------------------------------------------------------
# Cell stats sanity
# ---------------------------------------------------------------------------


def test_signal_std_zero_for_single_seed() -> None:
    """With ``n_seeds=1`` ddof=1 std is undefined; the cell should return
    0.0 by contract (not NaN)."""
    res = run_smoke_test(
        substrates=(BlockStructuredSubstrate(),),
        metrics=(AucPreEventMetric(),),
        N_grid=(20,),
        lambda_grid=(0.0,),
        n_seeds=1,
        steps_per_quarter=3,
        max_wallclock_seconds=120.0,
    )
    assert res.cells[0].ok is True
    assert res.cells[0].signal_std == 0.0


def test_lambda_zero_implies_signal_near_zero() -> None:
    """At λ=0 K_precursor == K_baseline, so the paired metric difference
    must be exactly zero across seeds — null run sanity."""
    res = run_smoke_test(
        substrates=(BlockStructuredSubstrate(),),
        metrics=(AucPreEventMetric(),),
        N_grid=(20,),
        lambda_grid=(0.0,),
        n_seeds=3,
        steps_per_quarter=3,
        max_wallclock_seconds=120.0,
    )
    cell = res.cells[0]
    assert cell.ok is True
    assert cell.signal_mean == 0.0
    assert cell.signal_std == 0.0


def test_default_smoke_realization_is_paired(tmp_path: Path) -> None:
    """Defensive sanity: the SubstrateRealization the smoke test exercises
    is the canonical paired (baseline, precursor) pair, not a sliced view."""
    block = BlockStructuredSubstrate()
    real = block.realize(N=20, lambda_=0.5, seed=42)
    assert isinstance(real, SubstrateRealization)
    assert real.K_baseline.shape == real.K_precursor.shape
    assert real.precursor_frobenius_delta > 0.0
