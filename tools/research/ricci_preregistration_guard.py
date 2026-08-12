# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Promotion guard for the ricci_microstructure_v1 preregistration (TASK 935).

Encodes the preregistration's promotion/rejection logic as executable, fail-closed
rules so that placeholder or synthetic data can never be promoted to empirical
evidence. The guard is the machine-checkable counterpart of
``docs/research/ricci_microstructure_v1_PREREGISTRATION.md``.

A run may promote past ``HYPOTHESIS`` only when ALL hold:

* the dataset carries a real (non-zero) ``data_sha256`` and is not synthetic;
* the dataset depth meets the preregistered minimum;
* the config declares all four required nulls, a cost model, and a replay command;
* if a result is supplied, it is net-of-cost positive and its OOS IC clears the
  failure threshold.

Otherwise the guard returns a non-promotable decision with the violated reasons.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

ZERO_SHA256 = "0" * 64

REQUIRED_NULLS: frozenset[str] = frozenset(
    {"permutation_null", "lag_sweep_no_future_data", "cost_model", "multi_session_replay"}
)


@dataclass(frozen=True)
class PromotionDecision:
    """Outcome of evaluating a run against the preregistration."""

    allowed: bool
    claim_tier: str
    decision: str
    falsification_status: str
    reasons: tuple[str, ...]


def _is_real_hash(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value != ZERO_SHA256
        and all(c in "0123456789abcdef" for c in value)
    )


def evaluate_promotion(
    dataset: Mapping[str, Any],
    config: Mapping[str, Any],
    result: Mapping[str, Any] | None = None,
) -> PromotionDecision:
    """Return the promotion decision for a (dataset, config, result) triple."""
    blockers: list[str] = []

    has_real_data = _is_real_hash(dataset.get("data_sha256"))
    if not has_real_data:
        blockers.append("no real data hash (placeholder/zero data_sha256)")

    is_synthetic = bool(dataset.get("is_synthetic", True))
    if is_synthetic:
        blockers.append("synthetic data caps state at INSTRUMENTED; cannot promote claim tier")

    missing_nulls = REQUIRED_NULLS - set(config.get("null_baselines", []) or [])
    if missing_nulls:
        blockers.append("missing null baselines: " + ", ".join(sorted(missing_nulls)))

    replay = config.get("replay_command")
    if not (isinstance(replay, str) and replay.strip()):
        blockers.append("missing replay_command")

    if not isinstance(config.get("cost_model"), Mapping):
        blockers.append("missing cost_model")

    min_depth = 3600
    promo = config.get("promotion_criteria")
    if isinstance(promo, Mapping) and isinstance(promo.get("min_data_depth_sec"), int):
        min_depth = promo["min_data_depth_sec"]
    depth = dataset.get("min_data_depth_sec")
    if not isinstance(depth, int) or depth < min_depth:
        blockers.append(f"insufficient data depth (< {min_depth}s)")

    decision = "OBSERVE"
    falsification_status = "NOT_RUN"

    if result is not None:
        net = result.get("net_pnl_after_costs")
        if isinstance(net, (int, float)) and not isinstance(net, bool) and net < 0:
            blockers.append("negative net-of-cost result")
            decision, falsification_status = "REJECT", "REJECT"
        ic = result.get("oos_ic")
        threshold = 0.0
        ft = config.get("failure_threshold")
        if isinstance(ft, Mapping) and isinstance(ft.get("oos_ic_min"), (int, float)):
            threshold = float(ft["oos_ic_min"])
        if isinstance(ic, (int, float)) and not isinstance(ic, bool) and ic <= threshold:
            blockers.append("OOS IC at or below failure threshold")
            decision, falsification_status = "REJECT", "REJECT"

    if not blockers:
        claim_tier = (
            "MEASURED" if config.get("data_source") == "real_multi" else "TESTED_REAL_SINGLE"
        )
        return PromotionDecision(
            allowed=True,
            claim_tier=claim_tier,
            decision="OBSERVE",
            falsification_status="PASS",
            reasons=(),
        )

    if falsification_status != "REJECT":
        falsification_status = "BLOCKED" if has_real_data else "NOT_RUN"
    return PromotionDecision(
        allowed=False,
        claim_tier="HYPOTHESIS",
        decision=decision,
        falsification_status=falsification_status,
        reasons=tuple(blockers),
    )
