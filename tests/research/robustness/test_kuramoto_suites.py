# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the three Kuramoto-bound suites against frozen evidence."""

from __future__ import annotations

import pytest

from research.robustness.protocols.kuramoto_contract import KuramotoRobustnessContract
from research.robustness.protocols.kuramoto_cpcv_suite import (
    PBO_PASS_THRESHOLD,
    run_kuramoto_cpcv_suite,
)
from research.robustness.protocols.kuramoto_jitter_executor import EVALUATOR_MODE
from research.robustness.protocols.kuramoto_jitter_suite import run_kuramoto_jitter_suite
from research.robustness.protocols.kuramoto_null_suite import run_kuramoto_null_suite


@pytest.fixture(scope="module")
def contract() -> KuramotoRobustnessContract:
    return KuramotoRobustnessContract.from_frozen_artifacts()


class TestCPCVSuite:
    def test_pbo_in_unit_interval(self, contract: KuramotoRobustnessContract) -> None:
        r = run_kuramoto_cpcv_suite(contract)
        assert 0.0 <= r.pbo <= 1.0
        assert r.pbo_pass == (r.pbo < PBO_PASS_THRESHOLD)

    def test_fold_count_matches_frozen_bundle(self, contract: KuramotoRobustnessContract) -> None:
        r = run_kuramoto_cpcv_suite(contract)
        assert r.n_folds == len(contract.fold_metrics)
        assert r.n_bars == len(contract.equity_curve) - 1

    def test_loo_pbo_present_and_bounded(self, contract: KuramotoRobustnessContract) -> None:
        """When the LOO grid ships with the contract, the second PBO
        is computed on a (folds × LOO-perturbations) OOS matrix."""
        r = run_kuramoto_cpcv_suite(contract)
        assert contract.loo_grid is not None
        assert r.loo_pbo is not None
        assert 0.0 <= r.loo_pbo <= 1.0
        # 14 rows minus the baseline.
        assert r.loo_n_strategies == 13

    def test_loo_pbo_matches_hand_computed(self, contract: KuramotoRobustnessContract) -> None:
        """Regression-pin: on the frozen LOO grid Bailey PBO = 0.20.
        A drift here signals either the grid has been tampered with
        (will also trip the sha256 gate) or the PBO logic has regressed."""
        r = run_kuramoto_cpcv_suite(contract)
        assert r.loo_pbo is not None
        assert abs(r.loo_pbo - 0.20) < 1e-9

    def test_pbo_candidate_count_and_interpretation(
        self, contract: KuramotoRobustnessContract
    ) -> None:
        """Fold-mirror PBO must always be flagged tautological (n=2);
        LOO-grid PBO with n=13 must be flagged admissible."""
        r = run_kuramoto_cpcv_suite(contract)
        assert r.pbo_candidate_count == 2
        assert r.pbo_interpretation == "tautological"
        assert r.loo_n_strategies == 13
        assert r.loo_pbo_interpretation == "admissible"


class TestNullSuite:
    def test_two_families_returned_and_bounded(self, contract: KuramotoRobustnessContract) -> None:
        r = run_kuramoto_null_suite(contract, n_bootstrap=64)
        assert len(r.families) == 2
        names = {f.family for f in r.families}
        assert names == {"iid_bootstrap", "stationary_bootstrap"}
        for f in r.families:
            assert 0.0 < f.p_value <= 1.0
            assert f.n_bootstrap == 64

    def test_deterministic_seed(self, contract: KuramotoRobustnessContract) -> None:
        a = run_kuramoto_null_suite(contract, n_bootstrap=32, seed=7)
        b = run_kuramoto_null_suite(contract, n_bootstrap=32, seed=7)
        for fa, fb in zip(a.families, b.families, strict=True):
            assert fa.p_value == fb.p_value

    def test_invalid_bootstrap_raises(self, contract: KuramotoRobustnessContract) -> None:
        with pytest.raises(ValueError):
            run_kuramoto_null_suite(contract, n_bootstrap=0)


class TestJitterSuite:
    def test_executor_mode_is_placeholder(self, contract: KuramotoRobustnessContract) -> None:
        r = run_kuramoto_jitter_suite(contract, n_candidates=16)
        assert r.evaluator_mode == EVALUATOR_MODE == "PLACEHOLDER_APPROXIMATION"

    def test_anchor_sharpe_matches_risk_metrics(self, contract: KuramotoRobustnessContract) -> None:
        r = run_kuramoto_jitter_suite(contract, n_candidates=8)
        assert r.stability.anchor_sharpe == pytest.approx(
            float(contract.risk_metrics["sharpe"].iloc[0])
        )

    def test_forbidden_jitter_name_rejected(self, contract: KuramotoRobustnessContract) -> None:
        with pytest.raises(Exception, match="forbidden"):
            run_kuramoto_jitter_suite(
                contract,
                jitter_fractions={"seed_extra": 0.1, "cost_bps": 0.2},
                n_candidates=4,
            )

    def test_placeholder_quadratic_monotonicity(self, contract: KuramotoRobustnessContract) -> None:
        # Increasing candidate count should not produce a perturbed
        # Sharpe that exceeds the anchor by construction.
        r = run_kuramoto_jitter_suite(contract, n_candidates=64)
        assert max(r.stability.perturbed_sharpes) <= r.stability.anchor_sharpe

    def test_placeholder_forces_pass_false(self, contract: KuramotoRobustnessContract) -> None:
        """Task 2: placeholder evaluator MUST force fraction_within_tol_pass
        to False, regardless of the observed fraction. The decision layer
        carries evaluator_mode separately and uses it to route to
        INSUFFICIENT_EVIDENCE when require_live_jitter=True."""
        r = run_kuramoto_jitter_suite(contract, n_candidates=32)
        assert r.evaluator_mode == "PLACEHOLDER_APPROXIMATION"
        assert r.fraction_within_tol_pass is False
        # Sanity: the raw fraction is still reported honestly on stability.
        assert 0.0 <= r.stability.fraction_within_tol <= 1.0
