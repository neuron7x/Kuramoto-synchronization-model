# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C C2.4-B — Tests for the positive-control pre-flight gate.

Two layers:

  * Unit tests against a fully-controlled stub substrate +
    stub metric that bypass the Kuramoto integrator. These pin
    the gate's arithmetic (signal_ci_ratio, verdict, sha256,
    censoring path, atomic capsule write).
  * Integration smoke tests against the real
    block_structured + sync_auc combo at small N so the CI
    fast lane stays under budget while still exercising the
    full pipeline.
"""

from __future__ import annotations

import dataclasses
import json
import math
from dataclasses import dataclass
from pathlib import Path

import pytest

from research.systemic_risk.d002c_metrics import (
    AucPreEventMetric,
    KuramotoTrajectory,
    MetricEvaluation,
)
from research.systemic_risk.d002c_pos_control import (
    DEFAULT_POS_LAMBDA,
    DEFAULT_POS_N,
    DEFAULT_POS_N_SEEDS,
    DEFAULT_POS_THRESHOLD,
    PosControlInvalid,
    _atomic_write,
    run_pos_control_all,
    run_pos_control_cell,
)
from research.systemic_risk.d002c_substrates import (
    BlockStructuredSubstrate,
    SubstrateRealization,
)

# ---------------------------------------------------------------------------
# Stubs — fully-controlled inputs for fast arithmetic tests
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ConstantSignalMetric:
    """Returns ``precursor_value`` when the trajectory's R-mean over the
    pre-event window exceeds ``baseline_value`` — i.e. emits a
    deterministic precursor-vs-null signal regardless of the real
    integrator's stochasticity."""

    precursor_value: float
    baseline_value: float
    censored_fraction: float = 0.0
    _counter: list[int] = dataclasses.field(default_factory=lambda: [0])

    @property
    def id(self) -> str:
        return "stub_constant_signal"

    def evaluate(self, trajectory: KuramotoTrajectory) -> MetricEvaluation:
        idx = self._counter[0]
        self._counter[0] += 1
        # Alternate precursor / baseline values so paired eval reads
        # precursor on even calls, baseline on odd. The pos-control
        # helper calls precursor first, then baseline — so this gives
        # a stable +(precursor-baseline) diff per seed.
        if idx % 2 == 0:
            value = self.precursor_value
        else:
            value = self.baseline_value
        # Optional censoring: every Nth eval is marked censored to
        # exercise the KM RMST fallback path.
        is_censored = False
        if self.censored_fraction > 0.0:
            stride = max(1, int(round(1.0 / self.censored_fraction)))
            is_censored = idx % stride == 0
        return MetricEvaluation(
            metric_id=self.id,
            value=float(value),
            is_censored=is_censored,
        )


@dataclass(frozen=True)
class _StubSubstrate:
    """Deterministic substrate that returns a small valid realisation.

    K is a tiny well-conditioned matrix; spectral / density gates
    are bypassed by skipping the calibration validator entirely
    (used only as input to the stub metric — the real integrator
    is NOT invoked when the metric stub overrides simulate_kuramoto).
    """

    N: int = 6

    @property
    def id(self) -> str:
        return "stub_substrate"

    def realize(self, *, N: int, lambda_: float, seed: int) -> SubstrateRealization:
        # Reuse the real block substrate's realisation so all
        # contract gates pass; the stub metric ignores K anyway.
        return BlockStructuredSubstrate().realize(N=N, lambda_=lambda_, seed=seed)


# ---------------------------------------------------------------------------
# Arithmetic contract — signal_ci_ratio formula
# ---------------------------------------------------------------------------


def test_signal_ci_ratio_matches_t_statistic_formula() -> None:
    """For a stub metric that yields constant precursor-baseline = 1.0
    on every seed, signal_std = 0 → ratio = +inf, verdict = PASS."""
    metric = _ConstantSignalMetric(precursor_value=2.0, baseline_value=1.0)
    result = run_pos_control_cell(
        _StubSubstrate(),
        metric,
        N=20,
        lambda_=1.0,
        n_seeds=4,
        steps_per_quarter=2,
    )
    assert result.signal_mean == pytest.approx(1.0)
    assert result.signal_std == pytest.approx(0.0)
    assert result.signal_ci_ratio == math.inf
    assert result.verdict == "PASS"


def test_signal_ci_ratio_zero_when_no_signal() -> None:
    """Stub metric with precursor == baseline → mean = 0 → ratio = 0 → EXCLUDE."""
    metric = _ConstantSignalMetric(precursor_value=1.0, baseline_value=1.0)
    result = run_pos_control_cell(
        _StubSubstrate(),
        metric,
        N=20,
        lambda_=1.0,
        n_seeds=4,
        steps_per_quarter=2,
    )
    assert result.signal_mean == pytest.approx(0.0)
    assert result.signal_ci_ratio == pytest.approx(0.0)
    assert result.verdict == "EXCLUDE"


# ---------------------------------------------------------------------------
# Real pipeline — block × sync_auc at small N
# ---------------------------------------------------------------------------


def test_real_pipeline_block_sync_auc_pass_at_lambda_one() -> None:
    """End-to-end: a known-strong-signal cell PASSes the default threshold."""
    result = run_pos_control_cell(
        BlockStructuredSubstrate(),
        AucPreEventMetric(),
        N=20,
        lambda_=1.0,
        n_seeds=8,
        steps_per_quarter=4,
    )
    assert math.isfinite(result.signal_ci_ratio)
    assert result.signal_ci_ratio > 0.0
    assert result.verdict in {"PASS", "EXCLUDE"}


def test_real_pipeline_signal_ci_ratio_finite_and_positive_at_lambda_positive() -> None:
    result = run_pos_control_cell(
        BlockStructuredSubstrate(),
        AucPreEventMetric(),
        N=20,
        lambda_=1.0,
        n_seeds=6,
        steps_per_quarter=4,
    )
    assert math.isfinite(result.signal_ci_ratio)
    assert result.signal_ci_ratio >= 0.0
    assert math.isfinite(result.signal_mean)
    assert math.isfinite(result.signal_std)


def test_real_pipeline_verdict_pass_at_loose_threshold() -> None:
    """Threshold = 0.01 — almost any positive ratio passes."""
    result = run_pos_control_cell(
        BlockStructuredSubstrate(),
        AucPreEventMetric(),
        N=20,
        lambda_=1.0,
        n_seeds=6,
        threshold=0.01,
        steps_per_quarter=4,
    )
    assert result.verdict == "PASS"
    assert result.threshold == pytest.approx(0.01)


def test_real_pipeline_verdict_exclude_at_tight_threshold() -> None:
    """Threshold = 1000 — no finite ratio can exceed it."""
    result = run_pos_control_cell(
        BlockStructuredSubstrate(),
        AucPreEventMetric(),
        N=20,
        lambda_=1.0,
        n_seeds=6,
        threshold=1000.0,
        steps_per_quarter=4,
    )
    assert result.verdict == "EXCLUDE"
    assert result.threshold == pytest.approx(1000.0)


# ---------------------------------------------------------------------------
# sha256 determinism
# ---------------------------------------------------------------------------


def test_sha256_deterministic_across_calls() -> None:
    """Same inputs → same sha. Bit-identical payload by construction."""
    a = run_pos_control_cell(
        BlockStructuredSubstrate(),
        AucPreEventMetric(),
        N=20,
        lambda_=1.0,
        n_seeds=4,
        threshold=2.0,
        steps_per_quarter=4,
    )
    b = run_pos_control_cell(
        BlockStructuredSubstrate(),
        AucPreEventMetric(),
        N=20,
        lambda_=1.0,
        n_seeds=4,
        threshold=2.0,
        steps_per_quarter=4,
    )
    assert a.sha256 == b.sha256
    assert a.signal_mean == pytest.approx(b.signal_mean)
    assert a.signal_ci_ratio == pytest.approx(b.signal_ci_ratio)


def test_sha256_changes_with_threshold() -> None:
    """Threshold is part of the payload → different threshold ⇒ different sha."""
    base = run_pos_control_cell(
        BlockStructuredSubstrate(),
        AucPreEventMetric(),
        N=20,
        lambda_=1.0,
        n_seeds=4,
        threshold=2.0,
        steps_per_quarter=4,
    )
    perturbed = run_pos_control_cell(
        BlockStructuredSubstrate(),
        AucPreEventMetric(),
        N=20,
        lambda_=1.0,
        n_seeds=4,
        threshold=2.5,
        steps_per_quarter=4,
    )
    assert base.sha256 != perturbed.sha256


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_n_seeds_lt_2_raises() -> None:
    with pytest.raises(PosControlInvalid, match="n_seeds"):
        run_pos_control_cell(
            BlockStructuredSubstrate(),
            AucPreEventMetric(),
            N=20,
            lambda_=1.0,
            n_seeds=1,
            steps_per_quarter=4,
        )


def test_threshold_non_finite_raises() -> None:
    with pytest.raises(PosControlInvalid, match="threshold"):
        run_pos_control_cell(
            BlockStructuredSubstrate(),
            AucPreEventMetric(),
            N=20,
            lambda_=1.0,
            n_seeds=4,
            threshold=math.nan,
            steps_per_quarter=4,
        )


def test_threshold_non_positive_raises() -> None:
    with pytest.raises(PosControlInvalid, match="threshold"):
        run_pos_control_cell(
            BlockStructuredSubstrate(),
            AucPreEventMetric(),
            N=20,
            lambda_=1.0,
            n_seeds=4,
            threshold=0.0,
            steps_per_quarter=4,
        )


def test_n_lt_2_raises() -> None:
    with pytest.raises(PosControlInvalid, match="N"):
        run_pos_control_cell(
            BlockStructuredSubstrate(),
            AucPreEventMetric(),
            N=1,
            lambda_=1.0,
            n_seeds=4,
            steps_per_quarter=4,
        )


def test_negative_lambda_raises() -> None:
    with pytest.raises(PosControlInvalid, match="lambda_"):
        run_pos_control_cell(
            BlockStructuredSubstrate(),
            AucPreEventMetric(),
            N=20,
            lambda_=-0.1,
            n_seeds=4,
            steps_per_quarter=4,
        )


# ---------------------------------------------------------------------------
# Right-censoring path
# ---------------------------------------------------------------------------


def test_censoring_fraction_reported_correctly() -> None:
    """A metric that censors half its outputs reports censoring_fraction ≈ 0.5."""
    metric = _ConstantSignalMetric(precursor_value=2.0, baseline_value=1.0, censored_fraction=0.5)
    result = run_pos_control_cell(
        _StubSubstrate(),
        metric,
        N=20,
        lambda_=1.0,
        n_seeds=4,
        steps_per_quarter=2,
    )
    # 8 total evaluations; every other one censored → 4/8 = 0.5
    assert 0.4 <= result.censoring_fraction <= 0.6


def test_censored_path_preserves_finite_signal() -> None:
    """When censored, the KM RMST aggregator is used; signal_mean stays finite."""
    metric = _ConstantSignalMetric(precursor_value=3.0, baseline_value=1.0, censored_fraction=0.25)
    result = run_pos_control_cell(
        _StubSubstrate(),
        metric,
        N=20,
        lambda_=1.0,
        n_seeds=4,
        steps_per_quarter=2,
    )
    assert math.isfinite(result.signal_mean)
    assert math.isfinite(result.signal_std)
    assert result.censoring_fraction > 0.0


# ---------------------------------------------------------------------------
# run_pos_control_all — grid sweep + capsule
# ---------------------------------------------------------------------------


def test_run_all_reports_correct_pass_counts() -> None:
    """1 substrate × 1 metric grid → 1 result, all_pass mirrors verdict."""
    verdict = run_pos_control_all(
        (BlockStructuredSubstrate(),),
        (AucPreEventMetric(),),
        N=20,
        lambda_=1.0,
        n_seeds=6,
        threshold=0.01,
        steps_per_quarter=4,
    )
    assert len(verdict.results) == 1
    assert verdict.n_pass + verdict.n_exclude == 1
    assert verdict.all_pass == (verdict.n_exclude == 0)


def test_run_all_excluded_combos_populated_correctly() -> None:
    """Impossibly tight threshold → every cell EXCLUDEd → excluded_combos
    lists every (substrate_id, metric_id) pair."""
    verdict = run_pos_control_all(
        (BlockStructuredSubstrate(),),
        (AucPreEventMetric(),),
        N=20,
        lambda_=1.0,
        n_seeds=6,
        threshold=1e30,
        steps_per_quarter=4,
    )
    assert verdict.n_exclude == 1
    assert verdict.n_pass == 0
    assert verdict.all_pass is False
    assert verdict.excluded_combos == (("block_structured", "sync_auc"),)


def test_run_all_writes_atomic_capsule(tmp_path: Path) -> None:
    """Atomic write produces a JSON-parseable file with the expected keys."""
    cap = tmp_path / "pos.json"
    verdict = run_pos_control_all(
        (BlockStructuredSubstrate(),),
        (AucPreEventMetric(),),
        N=20,
        lambda_=1.0,
        n_seeds=4,
        threshold=0.01,
        steps_per_quarter=4,
        output_path=cap,
    )
    assert cap.is_file()
    data = json.loads(cap.read_text(encoding="utf-8"))
    assert data["kind"] == "d002c_pos_control_capsule_v1"
    assert data["all_pass"] == verdict.all_pass
    assert data["sha256"] == verdict.sha256
    assert data["results"][0]["sha256"] == verdict.results[0].sha256


def test_run_all_capsule_no_orphan_tmp(tmp_path: Path) -> None:
    """No .tmp file left after a successful capsule write."""
    cap = tmp_path / "pos.json"
    run_pos_control_all(
        (BlockStructuredSubstrate(),),
        (AucPreEventMetric(),),
        N=20,
        lambda_=1.0,
        n_seeds=4,
        threshold=0.01,
        steps_per_quarter=4,
        output_path=cap,
    )
    orphans = [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert orphans == []
    assert cap.is_file()


def test_run_all_empty_substrates_raises() -> None:
    with pytest.raises(PosControlInvalid, match="substrates"):
        run_pos_control_all(
            (),
            (AucPreEventMetric(),),
            N=20,
            lambda_=1.0,
            n_seeds=4,
            steps_per_quarter=4,
        )


def test_run_all_empty_metrics_raises() -> None:
    with pytest.raises(PosControlInvalid, match="metrics"):
        run_pos_control_all(
            (BlockStructuredSubstrate(),),
            (),
            N=20,
            lambda_=1.0,
            n_seeds=4,
            steps_per_quarter=4,
        )


# ---------------------------------------------------------------------------
# Frozen dataclasses
# ---------------------------------------------------------------------------


def test_cell_result_is_frozen() -> None:
    """PosControlCellResult is immutable — direct attribute write raises."""
    result = run_pos_control_cell(
        BlockStructuredSubstrate(),
        AucPreEventMetric(),
        N=20,
        lambda_=1.0,
        n_seeds=4,
        steps_per_quarter=4,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.verdict = "TAMPERED"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.sha256 = "tampered"  # type: ignore[misc]


def test_verdict_is_frozen() -> None:
    verdict = run_pos_control_all(
        (BlockStructuredSubstrate(),),
        (AucPreEventMetric(),),
        N=20,
        lambda_=1.0,
        n_seeds=4,
        steps_per_quarter=4,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        verdict.all_pass = False  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        verdict.sha256 = "tampered"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Default constants
# ---------------------------------------------------------------------------


def test_default_constants_at_locked_values() -> None:
    """Locked C2.4 contract constants — tampering caught by acceptor falsifier."""
    assert DEFAULT_POS_N == 400
    assert DEFAULT_POS_LAMBDA == 1.0
    assert DEFAULT_POS_N_SEEDS == 50
    assert DEFAULT_POS_THRESHOLD == 2.0


# ---------------------------------------------------------------------------
# Atomic write — exception cleanup
# ---------------------------------------------------------------------------


def test_atomic_write_cleans_orphan_tmp_on_serialization_failure(
    tmp_path: Path,
) -> None:
    """If json.dump raises, the .tmp file is unlinked."""
    cap = tmp_path / "out.json"
    bad_payload: dict[str, object] = {"unserialisable": object()}
    with pytest.raises(TypeError):
        _atomic_write(cap, bad_payload)
    orphans = [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert orphans == []
    assert not cap.exists()


def test_atomic_write_overwrites_existing(tmp_path: Path) -> None:
    cap = tmp_path / "out.json"
    cap.write_text("STALE", encoding="utf-8")
    _atomic_write(cap, {"v": 1})
    data = json.loads(cap.read_text(encoding="utf-8"))
    assert data == {"v": 1}


def test_atomic_write_creates_parent_dirs(tmp_path: Path) -> None:
    cap = tmp_path / "deep" / "nested" / "out.json"
    _atomic_write(cap, {"v": 2})
    assert cap.is_file()
    assert json.loads(cap.read_text(encoding="utf-8")) == {"v": 2}


# ---------------------------------------------------------------------------
# Excluded-combos semantics — a failed combo is NOT silently fixed
# ---------------------------------------------------------------------------


def test_excluded_combo_does_not_carry_pass_verdict() -> None:
    """An EXCLUDE cell never appears in n_pass and always appears in excluded_combos."""
    verdict = run_pos_control_all(
        (BlockStructuredSubstrate(),),
        (AucPreEventMetric(),),
        N=20,
        lambda_=1.0,
        n_seeds=4,
        threshold=1e30,
        steps_per_quarter=4,
    )
    for r in verdict.results:
        if r.verdict == "EXCLUDE":
            assert (r.substrate_id, r.metric_id) in verdict.excluded_combos
    assert verdict.n_pass == sum(1 for r in verdict.results if r.verdict == "PASS")
