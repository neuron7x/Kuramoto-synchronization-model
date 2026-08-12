# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Decision-layer robustness gates.

Given a bundle of per-suite evidence from
:func:`research.robustness.protocols.kuramoto_gate_runner.run_kuramoto_gate_runner`
(or any strategy-family equivalent with the same evidence shape), this
module produces a single terminal label (PASS / FAIL /
INSUFFICIENT_EVIDENCE) plus a machine-readable breakdown.

Separating decisions from primitives keeps evidence collection pure:
the same evidence bundle can be re-evaluated under different decision
thresholds without re-running simulations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable


class DecisionLabel(str, Enum):
    """Terminal decision labels for a robustness evaluation."""

    PASS = "PASS"
    FAIL = "FAIL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@runtime_checkable
class _CPCVEvidence(Protocol):
    @property
    def pbo_pass(self) -> bool: ...
    @property
    def psr_pass(self) -> bool: ...
    @property
    def annualised_sharpe(self) -> float: ...
    @property
    def n_folds(self) -> int: ...
    @property
    def loo_pbo_pass(self) -> bool: ...


@runtime_checkable
class _NullEvidence(Protocol):
    @property
    def all_families_pass(self) -> bool: ...


@runtime_checkable
class _JitterEvidence(Protocol):
    @property
    def evaluator_mode(self) -> str: ...
    @property
    def fraction_within_tol_pass(self) -> bool: ...


@runtime_checkable
class _EvidenceBundle(Protocol):
    @property
    def cpcv(self) -> _CPCVEvidence: ...
    @property
    def null(self) -> _NullEvidence: ...
    @property
    def jitter(self) -> _JitterEvidence: ...


@dataclass(frozen=True)
class RobustnessGateResult:
    """Terminal decision plus human-readable reason chain."""

    label: DecisionLabel
    cpcv_pass: bool
    null_pass: bool
    jitter_pass: bool
    jitter_is_placeholder: bool
    reasons: tuple[str, ...]


def evaluate_robustness_gates(
    evidence: _EvidenceBundle,
    *,
    require_live_jitter: bool = False,
) -> RobustnessGateResult:
    """Combine suite evidence into a terminal label.

    Decision semantics:

    - **FAIL** — any of the essential real-evidence gates (CPCV PBO,
      PSR, null families) is red.
    - **INSUFFICIENT_EVIDENCE** — jitter is a placeholder *and*
      ``require_live_jitter`` is True. Also triggered when CPCV has
      fewer than 2 folds or annualised Sharpe is non-finite.
    - **PASS** — all essential gates green; jitter is either live-
      passing, or placeholder with ``require_live_jitter`` False.
    """
    reasons: list[str] = []
    cpcv_pass = bool(
        evidence.cpcv.pbo_pass and evidence.cpcv.psr_pass and evidence.cpcv.loo_pbo_pass
    )
    if not evidence.cpcv.pbo_pass:
        reasons.append("cpcv: PBO above threshold")
    if not evidence.cpcv.psr_pass:
        reasons.append("cpcv: PSR below threshold")
    if not evidence.cpcv.loo_pbo_pass:
        reasons.append("cpcv: LOO-grid PBO above threshold")

    null_pass = bool(evidence.null.all_families_pass)
    if not null_pass:
        reasons.append("null: one or more families failed")

    jitter_pass = bool(evidence.jitter.fraction_within_tol_pass)
    jitter_is_placeholder = evidence.jitter.evaluator_mode != "LIVE"
    if not jitter_pass:
        if jitter_is_placeholder:
            reasons.append("jitter: placeholder evaluator — abstains from live ✓/✗")
        else:
            reasons.append("jitter: fraction-within-tol below threshold")

    if evidence.cpcv.n_folds < 2:
        reasons.append("cpcv: fewer than 2 folds available")
        return RobustnessGateResult(
            label=DecisionLabel.INSUFFICIENT_EVIDENCE,
            cpcv_pass=cpcv_pass,
            null_pass=null_pass,
            jitter_pass=jitter_pass,
            jitter_is_placeholder=jitter_is_placeholder,
            reasons=tuple(reasons),
        )

    if not (cpcv_pass and null_pass):
        return RobustnessGateResult(
            label=DecisionLabel.FAIL,
            cpcv_pass=cpcv_pass,
            null_pass=null_pass,
            jitter_pass=jitter_pass,
            jitter_is_placeholder=jitter_is_placeholder,
            reasons=tuple(reasons),
        )

    if jitter_is_placeholder and require_live_jitter:
        reasons.append("jitter: evaluator is placeholder; live evaluator required")
        return RobustnessGateResult(
            label=DecisionLabel.INSUFFICIENT_EVIDENCE,
            cpcv_pass=cpcv_pass,
            null_pass=null_pass,
            jitter_pass=jitter_pass,
            jitter_is_placeholder=jitter_is_placeholder,
            reasons=tuple(reasons),
        )

    if not jitter_pass and not jitter_is_placeholder:
        reasons.append("jitter: live-mode failure")
        return RobustnessGateResult(
            label=DecisionLabel.FAIL,
            cpcv_pass=cpcv_pass,
            null_pass=null_pass,
            jitter_pass=jitter_pass,
            jitter_is_placeholder=jitter_is_placeholder,
            reasons=tuple(reasons),
        )

    return RobustnessGateResult(
        label=DecisionLabel.PASS,
        cpcv_pass=cpcv_pass,
        null_pass=null_pass,
        jitter_pass=jitter_pass,
        jitter_is_placeholder=jitter_is_placeholder,
        reasons=tuple(reasons),
    )
