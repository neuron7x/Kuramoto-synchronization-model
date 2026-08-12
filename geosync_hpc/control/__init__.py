# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deterministic control comparators for GeoSync HPC runtime.

Engineering analogue only. No biological-equivalence claim is made for any
naming exported from this package; all such names are shorthand for the
bounded mathematical mechanism described in
``action_result_comparator.accept_action_result`` and the chronology
proof in ``control_episode``.
"""

from __future__ import annotations

from geosync_hpc.control.action_result_comparator import (
    ActionResultComparator,
    ActionResultEvidence,
    ActionResultStatus,
    ActionResultWitness,
    ExpectedResultModel,
    ObservedActionResult,
    accept_action_result,
    compare_action_result,
    seal_action_result_evidence,
)
from geosync_hpc.control.control_episode import (
    ControlEpisode,
    EpisodePhase,
    EpisodeRecord,
    compute_error,
    dispatch_action,
    persist_memory,
    receive_afferentation,
    render_decision,
    seal_model,
    start_episode,
    verify_chain,
)
from geosync_hpc.control.self_healing import (
    RecoveryAction,
    RecoveryPlan,
    estimate_entropy_risk,
    prescribe_recovery,
)

__all__ = [
    "ActionResultComparator",
    "ActionResultEvidence",
    "ActionResultStatus",
    "ActionResultWitness",
    "ControlEpisode",
    "EpisodePhase",
    "EpisodeRecord",
    "ExpectedResultModel",
    "ObservedActionResult",
    "prescribe_recovery",
    "estimate_entropy_risk",
    "RecoveryPlan",
    "RecoveryAction",
    "accept_action_result",
    "compare_action_result",
    "seal_action_result_evidence",
    "compute_error",
    "dispatch_action",
    "persist_memory",
    "receive_afferentation",
    "render_decision",
    "seal_model",
    "start_episode",
    "verify_chain",
]
