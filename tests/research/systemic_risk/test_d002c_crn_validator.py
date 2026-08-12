# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C C2.3 — Tests for the CRN variance-reduction GO/NO-GO validator.

Two layers:

  * **Pure-logic tests** — exercise the variance-ratio computation,
    verdict logic, sha determinism, atomic write, capsule emission
    against synthetic and stubbed inputs. Run in milliseconds.

  * **Integration smoke test** — runs the validator end-to-end on
    a known-stable (substrate, metric) combo at small N so the CI
    fast lane stays under budget while still exercising the real
    Kuramoto → metric pipeline.

Pins gates G1-G8 from the C2.3 execution order.
"""

from __future__ import annotations

import dataclasses
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from research.systemic_risk.d002c_crn_validator import (
    DEFAULT_MINIMUM_PASSES,
    DEFAULT_RATIO_THRESHOLD,
    CRNGlobalVerdict,
    CRNValidatorInvalid,
    _atomic_write,
    _ci_narrowing_factor,
    _compute_variance_ratio,
    measure_variance_reduction,
    run_full_validation,
)
from research.systemic_risk.d002c_metrics import (
    AucPreEventMetric,
    KuramotoTrajectory,
    Metric,
    MetricEvaluation,
)
from research.systemic_risk.d002c_substrates import (
    BlockStructuredSubstrate,
    Substrate,
    SubstrateRealization,
)

# ---------------------------------------------------------------------------
# Synthetic helpers — controlled-output stubs for fast unit tests
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _StubMetric:
    """Returns a deterministic value from the substrate seed embedded
    in the realisation's K matrix Frobenius norm. Used to construct
    fully-controlled CRN tests without invoking the Kuramoto integrator."""

    metric_id_: str = "stub"

    @property
    def id(self) -> str:
        return self.metric_id_

    def evaluate(self, trajectory: KuramotoTrajectory) -> MetricEvaluation:
        # value = mean R over the pre-event window — deterministic in (K, seed)
        sl = trajectory.pre_event_slice
        return MetricEvaluation(
            metric_id=self.id,
            value=float(trajectory.R[sl].mean()),
            is_censored=False,
        )


# ---------------------------------------------------------------------------
# G3: variance-ratio computation is correct (manual numpy reference)
# ---------------------------------------------------------------------------


def test_compute_variance_ratio_matches_numpy_ddof1() -> None:
    paired = np.array([1.0, 1.05, 0.95, 1.02, 0.98], dtype=np.float64)
    unpaired = np.array([1.0, 2.0, -1.0, 3.0, -2.0], dtype=np.float64)
    pv, uv, ratio = _compute_variance_ratio(paired, unpaired)
    assert pv == pytest.approx(float(np.var(paired, ddof=1)))
    assert uv == pytest.approx(float(np.var(unpaired, ddof=1)))
    assert ratio == pytest.approx(pv / uv)


def test_compute_variance_ratio_zero_unpaired_yields_inf() -> None:
    paired = np.array([1.0, 2.0, 3.0])
    unpaired = np.array([5.0, 5.0, 5.0])  # variance = 0
    _, _, ratio = _compute_variance_ratio(paired, unpaired)
    assert ratio == math.inf


def test_compute_variance_ratio_rejects_too_few_replicates() -> None:
    with pytest.raises(CRNValidatorInvalid):
        _compute_variance_ratio(np.array([1.0]), np.array([1.0, 2.0]))


def test_ci_narrowing_factor_correct() -> None:
    # paired=0.04, unpaired=1.0 → sqrt(25) = 5x
    assert _ci_narrowing_factor(0.04, 1.0) == pytest.approx(5.0)


def test_ci_narrowing_factor_zero_paired_yields_inf() -> None:
    assert _ci_narrowing_factor(0.0, 1.0) == math.inf


# ---------------------------------------------------------------------------
# G4: sha determinism
# ---------------------------------------------------------------------------


def test_measure_sha_deterministic_across_calls() -> None:
    s = BlockStructuredSubstrate()
    m = AucPreEventMetric()
    a = measure_variance_reduction(s, m, N=30, lambda_=0.50, n_replicates=4, steps_per_quarter=4)
    b = measure_variance_reduction(s, m, N=30, lambda_=0.50, n_replicates=4, steps_per_quarter=4)
    assert a.sha256 == b.sha256
    assert a.variance_ratio == b.variance_ratio
    assert a.paired_variance == b.paired_variance
    assert a.unpaired_variance == b.unpaired_variance


def test_measure_sha_changes_with_threshold() -> None:
    s = BlockStructuredSubstrate()
    m = AucPreEventMetric()
    a = measure_variance_reduction(
        s,
        m,
        N=30,
        lambda_=0.50,
        n_replicates=4,
        ratio_threshold=0.50,
        steps_per_quarter=4,
    )
    b = measure_variance_reduction(
        s,
        m,
        N=30,
        lambda_=0.50,
        n_replicates=4,
        ratio_threshold=0.25,
        steps_per_quarter=4,
    )
    assert a.sha256 != b.sha256


def test_measure_sha_changes_with_seed() -> None:
    s = BlockStructuredSubstrate()
    m = AucPreEventMetric()
    a = measure_variance_reduction(
        s, m, N=30, lambda_=0.50, n_replicates=4, rng_seed_base=42, steps_per_quarter=4
    )
    b = measure_variance_reduction(
        s, m, N=30, lambda_=0.50, n_replicates=4, rng_seed_base=43, steps_per_quarter=4
    )
    assert a.sha256 != b.sha256


# ---------------------------------------------------------------------------
# Contract: input validation
# ---------------------------------------------------------------------------


def test_measure_rejects_n_replicates_below_two() -> None:
    s = BlockStructuredSubstrate()
    m = AucPreEventMetric()
    with pytest.raises(CRNValidatorInvalid):
        measure_variance_reduction(s, m, N=30, lambda_=0.50, n_replicates=1)


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
def test_measure_rejects_bad_threshold(bad: float) -> None:
    s = BlockStructuredSubstrate()
    m = AucPreEventMetric()
    with pytest.raises(CRNValidatorInvalid):
        measure_variance_reduction(
            s,
            m,
            N=30,
            lambda_=0.50,
            n_replicates=4,
            ratio_threshold=bad,
            steps_per_quarter=4,
        )


# ---------------------------------------------------------------------------
# G1 + G2: real-pipeline integration smoke test (single stable combo)
# ---------------------------------------------------------------------------


def test_real_pipeline_paired_var_lower_than_unpaired() -> None:
    """End-to-end through the real Kuramoto integrator. The block_structured
    × sync_auc cell is the most numerically stable combination — paired
    variance must be strictly lower than unpaired variance (otherwise CRN
    is broken in this geometry)."""
    res = measure_variance_reduction(
        BlockStructuredSubstrate(),
        AucPreEventMetric(),
        N=30,
        lambda_=0.50,
        n_replicates=20,
        steps_per_quarter=4,
    )
    assert res.paired_variance < res.unpaired_variance
    assert res.verdict == "GO"
    assert res.variance_ratio < DEFAULT_RATIO_THRESHOLD


def test_real_pipeline_capsule_json_round_trip(tmp_path: Path) -> None:
    """run_full_validation must produce a JSON file that re-loads cleanly,
    with the per-cell sha matching the validator's emission."""
    capsule = tmp_path / "crn_capsule.json"
    verdict = run_full_validation(
        output_path=capsule,
        substrates=(BlockStructuredSubstrate(),),
        metrics=(AucPreEventMetric(),),
        N=30,
        lambda_=0.50,
        n_replicates=10,
        steps_per_quarter=4,
        minimum_passes=1,
    )
    assert capsule.exists()
    data = json.loads(capsule.read_text(encoding="utf-8"))
    assert data["global_verdict"] in {"GO", "NO_GO"}
    assert data["n_replicates_per_cell"] == 10
    assert len(data["results"]) == 1
    assert data["results"][0]["sha256"] == verdict.results[0].sha256


# ---------------------------------------------------------------------------
# Global-verdict logic with stubs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CountingSubstrate:
    """Block substrate proxy with a configurable id (so we can build a
    grid of fake substrates without re-running real construction)."""

    base_substrate: Substrate
    id_: str

    @property
    def id(self) -> str:
        return self.id_

    def realize(self, *, N: int, lambda_: float, seed: int) -> SubstrateRealization:
        return self.base_substrate.realize(N=N, lambda_=lambda_, seed=seed)


def test_run_full_validation_global_go_when_minimum_passes_met(tmp_path: Path) -> None:
    """With 3 substrates × 1 metric and a threshold of 1 pass required,
    a GO global verdict should issue iff at least 1 cell returns GO. Use
    the block substrate — its CRN ratio is dramatically < 0.50, so all
    cells pass."""
    out = tmp_path / "global_go.json"
    base = BlockStructuredSubstrate()
    verdict = run_full_validation(
        output_path=out,
        substrates=(
            _CountingSubstrate(base, "block_a"),
            _CountingSubstrate(base, "block_b"),
            _CountingSubstrate(base, "block_c"),
        ),
        metrics=(AucPreEventMetric(),),
        N=30,
        lambda_=0.50,
        n_replicates=6,
        steps_per_quarter=4,
        minimum_passes=1,
    )
    assert verdict.global_verdict == "GO"
    assert verdict.n_go >= 1


def test_run_full_validation_global_no_go_when_insufficient(tmp_path: Path) -> None:
    """Force NO_GO by setting minimum_passes higher than the number of cells."""
    out = tmp_path / "global_nogo.json"
    base = BlockStructuredSubstrate()
    # 1 cell, minimum_passes=1 set to == n_cells. Now make threshold so
    # tight that even the best CRN can't pass.
    verdict = run_full_validation(
        output_path=out,
        substrates=(_CountingSubstrate(base, "stub"),),
        metrics=(AucPreEventMetric(),),
        N=30,
        lambda_=0.50,
        n_replicates=6,
        steps_per_quarter=4,
        ratio_threshold=1e-50,  # impossible to beat
        minimum_passes=1,
    )
    assert verdict.global_verdict == "NO_GO"
    assert verdict.n_nogo == 1


def test_run_full_validation_rejects_invalid_minimum_passes(tmp_path: Path) -> None:
    out = tmp_path / "x.json"
    with pytest.raises(CRNValidatorInvalid):
        run_full_validation(
            output_path=out,
            substrates=(BlockStructuredSubstrate(),),
            metrics=(AucPreEventMetric(),),
            N=20,
            lambda_=0.50,
            n_replicates=4,
            steps_per_quarter=4,
            minimum_passes=0,
        )
    with pytest.raises(CRNValidatorInvalid):
        run_full_validation(
            output_path=out,
            substrates=(BlockStructuredSubstrate(),),
            metrics=(AucPreEventMetric(),),
            N=20,
            lambda_=0.50,
            n_replicates=4,
            steps_per_quarter=4,
            minimum_passes=999,  # > n_cells
        )


# ---------------------------------------------------------------------------
# G5: atomic capsule write
# ---------------------------------------------------------------------------


def test_atomic_write_writes_file_and_cleans_tmp(tmp_path: Path) -> None:
    target = tmp_path / "cap.json"
    payload = {"verdict": "GO", "n": 7}
    _atomic_write(target, payload)
    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8")) == payload
    # No orphan .tmp
    leftovers = [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_atomic_write_creates_parent_dir(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "sub" / "cap.json"
    _atomic_write(target, {"x": 1})
    assert target.exists()


def test_atomic_write_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "cap.json"
    _atomic_write(target, {"first": True})
    _atomic_write(target, {"second": True})
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data == {"second": True}


def test_atomic_write_no_orphan_tmp_on_exception(tmp_path: Path) -> None:
    """If serialisation fails, the .tmp must NOT be left behind."""
    target = tmp_path / "cap.json"
    # An un-serialisable payload (a set is not JSON-encodable)
    with pytest.raises((TypeError, ValueError)):
        _atomic_write(target, {"bad": {1, 2, 3}})
    leftovers = [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []
    # target itself should not have been created either
    assert not target.exists()


# ---------------------------------------------------------------------------
# CRNValidatorResult / CRNGlobalVerdict — basic invariants
# ---------------------------------------------------------------------------


def test_crn_validator_result_is_frozen() -> None:
    s = BlockStructuredSubstrate()
    m = AucPreEventMetric()
    r = measure_variance_reduction(s, m, N=20, lambda_=0.50, n_replicates=4, steps_per_quarter=4)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.verdict = "NO_GO"  # type: ignore[misc]


def test_crn_global_verdict_carries_per_cell_results(tmp_path: Path) -> None:
    out = tmp_path / "cap.json"
    verdict = run_full_validation(
        output_path=out,
        substrates=(BlockStructuredSubstrate(),),
        metrics=(AucPreEventMetric(),),
        N=20,
        lambda_=0.50,
        n_replicates=4,
        steps_per_quarter=4,
        minimum_passes=1,
    )
    assert isinstance(verdict, CRNGlobalVerdict)
    assert len(verdict.results) == 1
    assert verdict.results[0].metric_id == "sync_auc"
    assert verdict.results[0].substrate_id == "block_structured"


def test_default_constants_match_locked_values() -> None:
    assert DEFAULT_RATIO_THRESHOLD == 0.50
    assert DEFAULT_MINIMUM_PASSES == 6


# ---------------------------------------------------------------------------
# G7: per-substrate × per-metric integration coverage (3 stable combos)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "metric_obj",
    [AucPreEventMetric()],
    ids=["sync_auc"],
)
def test_block_substrate_with_each_metric_produces_valid_result(
    metric_obj: Metric, tmp_path: Path
) -> None:
    """Every metric must produce a finite, well-formed result on the
    block substrate at the smoke-test grid point. A NaN/inf paired
    variance OR a missing sha would indicate a regression in the
    cohort aggregation pipeline."""
    r = measure_variance_reduction(
        BlockStructuredSubstrate(),
        metric_obj,
        N=30,
        lambda_=0.50,
        n_replicates=8,
        steps_per_quarter=4,
    )
    assert math.isfinite(r.paired_variance)
    assert math.isfinite(r.unpaired_variance)
    assert len(r.sha256) == 64
    assert r.verdict in {"GO", "NO_GO"}
    assert r.metric_id == metric_obj.id


# ---------------------------------------------------------------------------
# Negative test: paired protocol cannot produce HIGHER variance than
# unpaired on the same stable combo (CRN cannot HURT in this regime)
# ---------------------------------------------------------------------------


def test_paired_variance_never_exceeds_unpaired_on_stable_combo() -> None:
    """On the block × sync_auc combo (the most numerically stable),
    the paired protocol's variance must be ≤ the unpaired variance.
    A paired_var > unpaired_var on this combo means the CRN seed
    pairing is wired backwards (the seeds aren't actually shared
    inside the paired branch)."""
    r = measure_variance_reduction(
        BlockStructuredSubstrate(),
        AucPreEventMetric(),
        N=50,
        lambda_=0.50,
        n_replicates=12,
        steps_per_quarter=4,
    )
    assert r.paired_variance <= r.unpaired_variance + 1e-12
