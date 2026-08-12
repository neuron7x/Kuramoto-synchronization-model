# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""End-to-end gate-runner + decision-layer tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backtest.robustness_gates import DecisionLabel, evaluate_robustness_gates
from research.robustness.protocols.kuramoto_contract import KuramotoRobustnessContract
from research.robustness.protocols.kuramoto_gate_runner import run_kuramoto_gate_runner


@dataclass(frozen=True)
class _FakeCPCV:
    pbo_pass: bool
    psr_pass: bool
    annualised_sharpe: float
    n_folds: int
    loo_pbo_pass: bool = True


@dataclass(frozen=True)
class _FakeNull:
    all_families_pass: bool


@dataclass(frozen=True)
class _FakeJitter:
    evaluator_mode: str
    fraction_within_tol_pass: bool


@dataclass(frozen=True)
class _FakeEvidence:
    cpcv: _FakeCPCV
    null: _FakeNull
    jitter: _FakeJitter


class TestDecisionLayer:
    def _ev(
        self,
        *,
        pbo_pass: bool = True,
        psr_pass: bool = True,
        annualised_sharpe: float = 1.2,
        n_folds: int = 5,
        null_pass: bool = True,
        jitter_mode: str = "LIVE",
        jitter_pass: bool = True,
        loo_pbo_pass: bool = True,
    ) -> _FakeEvidence:
        return _FakeEvidence(
            cpcv=_FakeCPCV(
                pbo_pass=pbo_pass,
                psr_pass=psr_pass,
                annualised_sharpe=annualised_sharpe,
                n_folds=n_folds,
                loo_pbo_pass=loo_pbo_pass,
            ),
            null=_FakeNull(all_families_pass=null_pass),
            jitter=_FakeJitter(
                evaluator_mode=jitter_mode,
                fraction_within_tol_pass=jitter_pass,
            ),
        )

    def test_all_green_gives_pass(self) -> None:
        r = evaluate_robustness_gates(self._ev())
        assert r.label is DecisionLabel.PASS
        assert r.reasons == ()

    def test_pbo_red_gives_fail(self) -> None:
        r = evaluate_robustness_gates(self._ev(pbo_pass=False))
        assert r.label is DecisionLabel.FAIL
        assert any("PBO" in reason for reason in r.reasons)

    def test_psr_red_gives_fail(self) -> None:
        r = evaluate_robustness_gates(self._ev(psr_pass=False))
        assert r.label is DecisionLabel.FAIL
        assert any("PSR" in reason for reason in r.reasons)

    def test_null_red_gives_fail(self) -> None:
        r = evaluate_robustness_gates(self._ev(null_pass=False))
        assert r.label is DecisionLabel.FAIL

    def test_loo_pbo_red_gives_fail(self) -> None:
        r = evaluate_robustness_gates(self._ev(loo_pbo_pass=False))
        assert r.label is DecisionLabel.FAIL
        assert any("LOO" in reason for reason in r.reasons)

    def test_placeholder_jitter_with_require_live_demotes_to_insufficient(
        self,
    ) -> None:
        r = evaluate_robustness_gates(
            self._ev(jitter_mode="PLACEHOLDER_APPROXIMATION"),
            require_live_jitter=True,
        )
        assert r.label is DecisionLabel.INSUFFICIENT_EVIDENCE
        assert r.jitter_is_placeholder

    def test_placeholder_jitter_without_require_live_can_pass(self) -> None:
        r = evaluate_robustness_gates(
            self._ev(jitter_mode="PLACEHOLDER_APPROXIMATION"),
            require_live_jitter=False,
        )
        assert r.label is DecisionLabel.PASS
        assert r.jitter_is_placeholder

    def test_single_fold_gives_insufficient(self) -> None:
        r = evaluate_robustness_gates(self._ev(n_folds=1))
        assert r.label is DecisionLabel.INSUFFICIENT_EVIDENCE

    def test_live_jitter_failure_is_fail(self) -> None:
        r = evaluate_robustness_gates(self._ev(jitter_mode="LIVE", jitter_pass=False))
        assert r.label is DecisionLabel.FAIL


class TestGateRunnerEndToEnd:
    def test_pipeline_produces_all_three_suites(self) -> None:
        contract = KuramotoRobustnessContract.from_frozen_artifacts()
        evidence = run_kuramoto_gate_runner(
            contract,
            null_kwargs={"n_bootstrap": 32},
            jitter_kwargs={"n_candidates": 8},
        )
        assert evidence.cpcv.n_folds >= 2
        assert len(evidence.null.families) == 2
        assert evidence.jitter.evaluator_mode == "PLACEHOLDER_APPROXIMATION"

    def test_decision_matches_evidence(self) -> None:
        contract = KuramotoRobustnessContract.from_frozen_artifacts()
        evidence = run_kuramoto_gate_runner(
            contract,
            null_kwargs={"n_bootstrap": 32, "seed": 42},
            jitter_kwargs={"n_candidates": 8},
        )
        decision = evaluate_robustness_gates(evidence)
        # With only 32 bootstraps and proxy returns the null suite
        # almost certainly fails at the 5 % threshold, so the runner
        # must report a FAIL verdict on the frozen demo evidence.
        assert decision.label is DecisionLabel.FAIL
        assert not decision.null_pass
        assert any("null" in reason for reason in decision.reasons)


def test_cli_writes_expected_artifacts(tmp_path: Path) -> None:
    from scripts import run_kuramoto_robustness_v1 as cli  # noqa: PLC0415

    cwd_out = tmp_path / "robustness_v1"
    rc = cli.main(
        [
            "--n-bootstrap",
            "32",
            "--n-jitter-candidates",
            "8",
            "--out-dir",
            str(cwd_out),
        ]
    )
    assert rc in (0, 1)
    for name in (
        "verdict.json",
        "cpcv_summary.json",
        "null_summary.json",
        "jitter_summary.json",
        "ROBUSTNESS_RESULTS.md",
    ):
        assert (cwd_out / name).is_file()
