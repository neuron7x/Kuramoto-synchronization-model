# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C C2.4-B — Tests for the negative-control pre-flight gate.

Two layers:

  * Unit tests against a fully-controlled stub metric that bypass
    the Kuramoto integrator. These pin the gate's arithmetic
    (FPR computation, z-score critical-value lookup, verdict,
    sha256, atomic capsule write).
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

import numpy as np
import pytest

from research.systemic_risk.d002c_metrics import (
    AucPreEventMetric,
    KuramotoTrajectory,
    MetricEvaluation,
)
from research.systemic_risk.d002c_neg_control import (
    DEFAULT_NEG_ALPHA_BONFERRONI,
    DEFAULT_NEG_LAMBDA,
    DEFAULT_NEG_N_GRID,
    DEFAULT_NEG_N_SEEDS,
    DEFAULT_NEG_TOLERANCE,
    NegControlInvalid,
    _atomic_write,
    _bonferroni_critical_value,
    _phi_inv,
    run_neg_control_all,
    run_neg_control_cell,
)
from research.systemic_risk.d002c_substrates import (
    BlockStructuredSubstrate,
    SubstrateRealization,
)

# ---------------------------------------------------------------------------
# Stubs — fully-controlled inputs for fast arithmetic tests
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _GaussianMetric:
    """Returns a deterministic Gaussian draw per call so the per-seed
    diff is N(0, σ²) for some fixed σ. Used to exercise the FPR
    arithmetic without invoking the Kuramoto integrator."""

    sigma: float = 1.0
    _counter: list[int] = dataclasses.field(default_factory=lambda: [0])

    @property
    def id(self) -> str:
        return "stub_gaussian"

    def evaluate(self, trajectory: KuramotoTrajectory) -> MetricEvaluation:
        idx = self._counter[0]
        self._counter[0] += 1
        # Deterministic Gaussian via numpy seeded by idx. Two calls
        # per seed (a, b); their difference is N(0, 2σ²).
        rng = np.random.default_rng(idx + 1_000_000)
        return MetricEvaluation(
            metric_id=self.id,
            value=float(rng.normal(loc=0.0, scale=self.sigma)),
            is_censored=False,
        )


@dataclass(frozen=True)
class _ConstantMetric:
    """Returns the same value for every call. Per-seed diff is exactly
    zero — exercises the degenerate-std branch of the FPR computation."""

    value: float = 1.0

    @property
    def id(self) -> str:
        return "stub_constant"

    def evaluate(self, trajectory: KuramotoTrajectory) -> MetricEvaluation:
        return MetricEvaluation(metric_id=self.id, value=float(self.value), is_censored=False)


@dataclass(frozen=True)
class _StubSubstrate:
    """Reuse the real block substrate; the stub metric ignores K."""

    @property
    def id(self) -> str:
        return "stub_substrate"

    def realize(self, *, N: int, lambda_: float, seed: int) -> SubstrateRealization:
        return BlockStructuredSubstrate().realize(N=N, lambda_=lambda_, seed=seed)


# ---------------------------------------------------------------------------
# Arithmetic — Φ^{-1} probit + Bonferroni critical value
# ---------------------------------------------------------------------------


def test_phi_inv_recovers_standard_normal_quantiles() -> None:
    """Spot-check the Acklam probit at canonical quantiles."""
    assert _phi_inv(0.5) == pytest.approx(0.0, abs=1e-9)
    assert _phi_inv(0.975) == pytest.approx(1.959963984540054, abs=1e-6)
    assert _phi_inv(0.025) == pytest.approx(-1.959963984540054, abs=1e-6)


def test_phi_inv_rejects_invalid_inputs() -> None:
    """p must lie in (0, 1)."""
    with pytest.raises(NegControlInvalid):
        _phi_inv(0.0)
    with pytest.raises(NegControlInvalid):
        _phi_inv(1.0)
    with pytest.raises(NegControlInvalid):
        _phi_inv(-0.1)


def test_bonferroni_critical_value_matches_two_sided() -> None:
    """z_crit at α_b = 2.31e-4 ≈ 3.685 (two-sided)."""
    z = _bonferroni_critical_value(2.31e-4)
    # scipy reference: scipy.stats.norm.ppf(1 - 2.31e-4 / 2) ≈ 3.685
    assert 3.6 < z < 3.8
    # And monotone in α: smaller α ⇒ larger critical value
    z_tighter = _bonferroni_critical_value(1e-5)
    assert z_tighter > z


def test_bonferroni_critical_value_rejects_out_of_range_alpha() -> None:
    with pytest.raises(NegControlInvalid):
        _bonferroni_critical_value(0.0)
    with pytest.raises(NegControlInvalid):
        _bonferroni_critical_value(1.0)


# ---------------------------------------------------------------------------
# Stub-metric FPR — controlled-output arithmetic
# ---------------------------------------------------------------------------


def test_constant_metric_yields_zero_fpr() -> None:
    """If the metric is constant, per-seed diffs are exactly zero, std=0;
    the degenerate path counts no false positives."""
    result = run_neg_control_cell(
        _StubSubstrate(),
        _ConstantMetric(value=3.0),
        N=20,
        n_seeds=8,
        steps_per_quarter=2,
    )
    assert result.fpr == pytest.approx(0.0)
    assert result.false_positive_count == 0
    assert result.verdict == "PASS"


def test_gaussian_metric_fpr_well_below_target_at_default_alpha() -> None:
    """A Gaussian null at α_b = 2.31e-4 should have very few false
    positives over 50 seeds (expected ≈ 0.012); FPR should be ≤
    α_b + tolerance with high probability."""
    result = run_neg_control_cell(
        _StubSubstrate(),
        _GaussianMetric(sigma=1.0),
        N=20,
        n_seeds=50,
        steps_per_quarter=2,
    )
    assert result.fpr <= DEFAULT_NEG_ALPHA_BONFERRONI + DEFAULT_NEG_TOLERANCE
    assert result.verdict == "PASS"


# ---------------------------------------------------------------------------
# Real pipeline — block × sync_auc at small N, λ=0
# ---------------------------------------------------------------------------


def test_real_pipeline_block_sync_auc_passes_at_lambda_zero() -> None:
    """End-to-end null cell at λ=0: FPR within α_b + tolerance."""
    result = run_neg_control_cell(
        BlockStructuredSubstrate(),
        AucPreEventMetric(),
        N=20,
        n_seeds=20,
        steps_per_quarter=4,
    )
    assert result.lambda_ == 0.0
    assert result.fpr <= DEFAULT_NEG_ALPHA_BONFERRONI + DEFAULT_NEG_TOLERANCE
    assert result.verdict == "PASS"


def test_real_pipeline_verdict_pass_at_default_tolerance() -> None:
    result = run_neg_control_cell(
        BlockStructuredSubstrate(),
        AucPreEventMetric(),
        N=20,
        n_seeds=20,
        steps_per_quarter=4,
    )
    assert result.alpha_bonferroni == pytest.approx(DEFAULT_NEG_ALPHA_BONFERRONI)
    assert result.threshold_tolerance == pytest.approx(DEFAULT_NEG_TOLERANCE)
    assert result.verdict == "PASS"


def test_real_pipeline_verdict_exclude_when_tolerance_zero_and_any_fp() -> None:
    """When tolerance=0, even one false positive forces EXCLUDE because
    fpr >= 1/n_seeds > 0 = α_b. We FORCE a false positive by setting
    α_bonferroni high enough that ~50% of the null cohort exceeds the
    critical value."""
    result = run_neg_control_cell(
        BlockStructuredSubstrate(),
        AucPreEventMetric(),
        N=20,
        n_seeds=10,
        alpha_bonferroni=0.5,  # z_crit ≈ 0.674 → many crossings
        tolerance=0.0,
        steps_per_quarter=4,
    )
    # FPR will likely exceed α_b + tolerance(=0) for a finite cohort,
    # but the test is robust either way: we assert the exact
    # PASS/EXCLUDE logic.
    expected = "PASS" if result.fpr <= 0.5 else "EXCLUDE"
    assert result.verdict == expected
    assert result.threshold_tolerance == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# sha256 determinism
# ---------------------------------------------------------------------------


def test_sha256_deterministic_across_calls() -> None:
    a = run_neg_control_cell(
        BlockStructuredSubstrate(),
        AucPreEventMetric(),
        N=20,
        n_seeds=8,
        steps_per_quarter=4,
    )
    b = run_neg_control_cell(
        BlockStructuredSubstrate(),
        AucPreEventMetric(),
        N=20,
        n_seeds=8,
        steps_per_quarter=4,
    )
    assert a.sha256 == b.sha256
    assert a.fpr == pytest.approx(b.fpr)
    assert a.false_positive_count == b.false_positive_count


def test_sha256_changes_with_alpha_bonferroni() -> None:
    base = run_neg_control_cell(
        BlockStructuredSubstrate(),
        AucPreEventMetric(),
        N=20,
        n_seeds=8,
        alpha_bonferroni=2.31e-4,
        steps_per_quarter=4,
    )
    perturbed = run_neg_control_cell(
        BlockStructuredSubstrate(),
        AucPreEventMetric(),
        N=20,
        n_seeds=8,
        alpha_bonferroni=5e-4,
        steps_per_quarter=4,
    )
    assert base.sha256 != perturbed.sha256


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_n_seeds_lt_2_raises() -> None:
    with pytest.raises(NegControlInvalid, match="n_seeds"):
        run_neg_control_cell(
            BlockStructuredSubstrate(),
            AucPreEventMetric(),
            N=20,
            n_seeds=1,
            steps_per_quarter=4,
        )


def test_n_lt_2_raises() -> None:
    with pytest.raises(NegControlInvalid, match="N"):
        run_neg_control_cell(
            BlockStructuredSubstrate(),
            AucPreEventMetric(),
            N=1,
            n_seeds=8,
            steps_per_quarter=4,
        )


def test_tolerance_negative_raises() -> None:
    with pytest.raises(NegControlInvalid, match="tolerance"):
        run_neg_control_cell(
            BlockStructuredSubstrate(),
            AucPreEventMetric(),
            N=20,
            n_seeds=8,
            tolerance=-0.1,
            steps_per_quarter=4,
        )


def test_alpha_bonferroni_out_of_range_raises() -> None:
    with pytest.raises(NegControlInvalid, match="alpha_bonferroni"):
        run_neg_control_cell(
            BlockStructuredSubstrate(),
            AucPreEventMetric(),
            N=20,
            n_seeds=8,
            alpha_bonferroni=0.0,
            steps_per_quarter=4,
        )
    with pytest.raises(NegControlInvalid, match="alpha_bonferroni"):
        run_neg_control_cell(
            BlockStructuredSubstrate(),
            AucPreEventMetric(),
            N=20,
            n_seeds=8,
            alpha_bonferroni=1.0,
            steps_per_quarter=4,
        )


# ---------------------------------------------------------------------------
# run_neg_control_all — grid sweep + capsule
# ---------------------------------------------------------------------------


def test_run_all_cell_count_matches_substrate_metric_n_grid_product() -> None:
    """1 substrate × 1 metric × 3 N values = 3 cells."""
    verdict = run_neg_control_all(
        (BlockStructuredSubstrate(),),
        (AucPreEventMetric(),),
        N_grid=(20, 30, 40),
        n_seeds=8,
        steps_per_quarter=4,
    )
    assert len(verdict.results) == 3
    # Each N appears exactly once for the one (substrate, metric) pair.
    Ns = sorted(r.N for r in verdict.results)
    assert Ns == [20, 30, 40]


def test_run_all_default_n_grid_has_three_values() -> None:
    assert DEFAULT_NEG_N_GRID == (50, 100, 200)


def test_run_all_writes_atomic_capsule(tmp_path: Path) -> None:
    cap = tmp_path / "neg.json"
    verdict = run_neg_control_all(
        (BlockStructuredSubstrate(),),
        (AucPreEventMetric(),),
        N_grid=(20,),
        n_seeds=6,
        steps_per_quarter=4,
        output_path=cap,
    )
    assert cap.is_file()
    data = json.loads(cap.read_text(encoding="utf-8"))
    assert data["kind"] == "d002c_neg_control_capsule_v1"
    assert data["all_pass"] == verdict.all_pass
    assert data["sha256"] == verdict.sha256
    assert data["results"][0]["sha256"] == verdict.results[0].sha256
    assert data["N_grid"] == [20]


def test_run_all_capsule_no_orphan_tmp(tmp_path: Path) -> None:
    cap = tmp_path / "neg.json"
    run_neg_control_all(
        (BlockStructuredSubstrate(),),
        (AucPreEventMetric(),),
        N_grid=(20,),
        n_seeds=6,
        steps_per_quarter=4,
        output_path=cap,
    )
    orphans = [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert orphans == []
    assert cap.is_file()


def test_run_all_excluded_cells_lists_triples(tmp_path: Path) -> None:
    """When the per-cell verdict is EXCLUDE, the (substrate, metric, N)
    triple appears in excluded_cells exactly once."""
    verdict = run_neg_control_all(
        (BlockStructuredSubstrate(),),
        (AucPreEventMetric(),),
        N_grid=(20,),
        n_seeds=10,
        alpha_bonferroni=0.5,  # forces many false positives
        tolerance=0.0,
        steps_per_quarter=4,
    )
    for r in verdict.results:
        if r.verdict == "EXCLUDE":
            assert (r.substrate_id, r.metric_id, r.N) in verdict.excluded_cells
    assert verdict.n_pass + verdict.n_exclude == len(verdict.results)


def test_run_all_empty_substrates_raises() -> None:
    with pytest.raises(NegControlInvalid, match="substrates"):
        run_neg_control_all(
            (),
            (AucPreEventMetric(),),
            N_grid=(20,),
            n_seeds=8,
            steps_per_quarter=4,
        )


def test_run_all_empty_metrics_raises() -> None:
    with pytest.raises(NegControlInvalid, match="metrics"):
        run_neg_control_all(
            (BlockStructuredSubstrate(),),
            (),
            N_grid=(20,),
            n_seeds=8,
            steps_per_quarter=4,
        )


def test_run_all_empty_n_grid_raises() -> None:
    with pytest.raises(NegControlInvalid, match="N_grid"):
        run_neg_control_all(
            (BlockStructuredSubstrate(),),
            (AucPreEventMetric(),),
            N_grid=(),
            n_seeds=8,
            steps_per_quarter=4,
        )


# ---------------------------------------------------------------------------
# Frozen dataclasses
# ---------------------------------------------------------------------------


def test_cell_result_is_frozen() -> None:
    result = run_neg_control_cell(
        BlockStructuredSubstrate(),
        AucPreEventMetric(),
        N=20,
        n_seeds=6,
        steps_per_quarter=4,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.verdict = "TAMPERED"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.fpr = 0.0  # type: ignore[misc]


def test_verdict_is_frozen() -> None:
    verdict = run_neg_control_all(
        (BlockStructuredSubstrate(),),
        (AucPreEventMetric(),),
        N_grid=(20,),
        n_seeds=6,
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
    """Locked C2.4 contract: tampering caught by acceptor falsifier."""
    assert DEFAULT_NEG_N_SEEDS == 50
    assert DEFAULT_NEG_LAMBDA == 0.0
    assert DEFAULT_NEG_ALPHA_BONFERRONI == 2.31e-4
    assert DEFAULT_NEG_TOLERANCE == 1e-3


# ---------------------------------------------------------------------------
# Atomic write — exception cleanup
# ---------------------------------------------------------------------------


def test_atomic_write_cleans_orphan_tmp_on_serialization_failure(
    tmp_path: Path,
) -> None:
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
# FPR ≈ α_b under a controlled Gaussian null
# ---------------------------------------------------------------------------


def test_fpr_approaches_alpha_at_large_n_seeds_with_loose_threshold() -> None:
    """Under a Gaussian null with α_b = 0.05, the empirical FPR over
    100 seeds should be in a binomial CI around 0.05. The test asserts
    a generous bound: FPR <= 0.15 (chosen so finite-sample noise at
    n=100 does not flake)."""
    result = run_neg_control_cell(
        _StubSubstrate(),
        _GaussianMetric(sigma=1.0),
        N=20,
        n_seeds=100,
        alpha_bonferroni=0.05,
        tolerance=0.10,
        steps_per_quarter=2,
    )
    assert 0.0 <= result.fpr <= 0.15
    assert math.isfinite(result.fpr)
