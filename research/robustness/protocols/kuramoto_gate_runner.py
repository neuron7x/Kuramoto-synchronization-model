# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Kuramoto robustness gate runner.

Loads the frozen contract, runs CPCV + null + jitter suites, and hands
the combined evidence to :func:`backtest.robustness_gates.evaluate_robustness_gates`
for a terminal decision label. The runner itself is pure orchestration
— no writes, no process-side effects.

Write-side emission (artifacts under
``results/cross_asset_kuramoto/robustness_v1/``) is handled by the CLI
entry point :mod:`scripts.run_kuramoto_robustness_v1`, so the runner
remains test-friendly.
"""

from __future__ import annotations

from dataclasses import dataclass

from .kuramoto_contract import KuramotoRobustnessContract
from .kuramoto_cpcv_suite import KuramotoCPCVResult, run_kuramoto_cpcv_suite
from .kuramoto_jitter_suite import KuramotoJitterSuiteResult, run_kuramoto_jitter_suite
from .kuramoto_null_suite import KuramotoNullSuiteResult, run_kuramoto_null_suite


@dataclass(frozen=True)
class KuramotoGateEvidence:
    """Aggregate of all suite outputs from one gate-runner invocation."""

    cpcv: KuramotoCPCVResult
    null: KuramotoNullSuiteResult
    jitter: KuramotoJitterSuiteResult


def run_kuramoto_gate_runner(
    contract: KuramotoRobustnessContract,
    *,
    cpcv_kwargs: dict[str, object] | None = None,
    null_kwargs: dict[str, object] | None = None,
    jitter_kwargs: dict[str, object] | None = None,
) -> KuramotoGateEvidence:
    """Orchestrate the three suites against the frozen contract.

    Each suite is invoked independently so a single-suite regression is
    isolated during debugging. The returned evidence bundle is an
    immutable view — callers route it to the decision layer separately.
    """
    cpcv = run_kuramoto_cpcv_suite(contract, **(cpcv_kwargs or {}))
    null = run_kuramoto_null_suite(contract, **(null_kwargs or {}))  # type: ignore[arg-type]
    jitter = run_kuramoto_jitter_suite(contract, **(jitter_kwargs or {}))  # type: ignore[arg-type]
    return KuramotoGateEvidence(cpcv=cpcv, null=null, jitter=jitter)
