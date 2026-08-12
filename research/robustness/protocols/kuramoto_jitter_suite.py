# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Parameter-jitter suite for the Kuramoto contract.

Anchors at the frozen ``PARAMETER_LOCK.json`` values, applies the
anti-inflation candidate-name guard, and calls the placeholder
evaluator (see :mod:`.kuramoto_jitter_executor`). The result carries
the executor mode so downstream decisions can downgrade evidence when
running against the placeholder.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from research.robustness.stability import JitterStabilityResult, parameter_jitter_stability

from .kuramoto_candidate_set import (
    assert_anchor_covers_candidates,
    validate_candidate_parameter_names,
)
from .kuramoto_contract import KuramotoRobustnessContract
from .kuramoto_jitter_executor import EVALUATOR_MODE, make_placeholder_evaluator

DEFAULT_JITTER_FRACTIONS: Final[dict[str, float]] = {
    "cost_bps": 0.20,
    "vol_target_annualised": 0.10,
    "return_clip_abs": 0.15,
    "vol_cap_leverage": 0.10,
    "regime_quantile_low": 0.05,
    "regime_quantile_high": 0.05,
}
DEFAULT_SHARPE_TOLERANCE: Final[float] = 0.20


@dataclass(frozen=True)
class KuramotoJitterSuiteResult:
    """Result wrapper tagging the evaluator mode on top of primitive output."""

    stability: JitterStabilityResult
    evaluator_mode: str
    fraction_within_tol_pass: bool
    pass_threshold: float


def _anchor_numeric_parameters(
    param_lock: Mapping[str, object],
) -> dict[str, float]:
    numeric_keys = (
        "cost_bps",
        "vol_target_annualised",
        "return_clip_abs",
        "vol_cap_leverage",
        "regime_quantile_low",
        "regime_quantile_high",
    )
    out: dict[str, float] = {}
    for key in numeric_keys:
        raw = param_lock.get(key)
        if isinstance(raw, int | float):
            out[key] = float(raw)
    return out


def run_kuramoto_jitter_suite(
    contract: KuramotoRobustnessContract,
    *,
    jitter_fractions: Mapping[str, float] | None = None,
    n_candidates: int = 64,
    sharpe_tolerance: float = DEFAULT_SHARPE_TOLERANCE,
    fraction_within_tol_pass: float = 0.80,
    seed: int = 42,
) -> KuramotoJitterSuiteResult:
    """Execute the jitter suite against the frozen anchor parameters."""
    fractions = dict(jitter_fractions or DEFAULT_JITTER_FRACTIONS)
    validate_candidate_parameter_names(fractions)
    anchor = _anchor_numeric_parameters(contract.parameter_lock)
    assert_anchor_covers_candidates(anchor, fractions)

    anchor_sharpe = float(contract.risk_metrics["sharpe"].iloc[0])
    evaluator = make_placeholder_evaluator(anchor_sharpe, anchor)
    stability = parameter_jitter_stability(
        anchor_parameters=anchor,
        evaluator=evaluator,
        jitter_fractions=fractions,
        n_candidates=n_candidates,
        sharpe_tolerance=sharpe_tolerance,
        seed=seed,
    )
    # When the evaluator is the placeholder, jitter evidence is NOT
    # decision-grade — force the pass boolean to False regardless of the
    # observed fraction-within-tol. The decision layer carries a separate
    # 'jitter_is_placeholder' flag that routes to INSUFFICIENT_EVIDENCE
    # when require_live_jitter is True; otherwise placeholder-with-False
    # simply abstains from asserting a live pass.
    is_placeholder = EVALUATOR_MODE != "LIVE"
    raw_pass = stability.fraction_within_tol >= fraction_within_tol_pass
    return KuramotoJitterSuiteResult(
        stability=stability,
        evaluator_mode=EVALUATOR_MODE,
        fraction_within_tol_pass=False if is_placeholder else raw_pass,
        pass_threshold=fraction_within_tol_pass,
    )
