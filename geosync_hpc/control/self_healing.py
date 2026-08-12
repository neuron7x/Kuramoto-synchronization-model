# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deterministic self-healing policy for AAR-PRO-V1 witnesses.

This module is deliberately symbolic and side-effect free.  It does not repair
state by mutation; it emits a bounded recovery plan that orchestration layers can
execute.  The goal is to predict entropy pressure before downstream model weights
are updated from a broken action-result chronology.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from typing import Final

from geosync_hpc.control.action_result_comparator import (
    ActionResultStatus,
    ActionResultWitness,
)

FREE_ENERGY_BREAKER_WEIGHT: Final[float] = 0.35
ROLLBACK_WEIGHT: Final[float] = 0.30
UPDATE_WEIGHT: Final[float] = 0.15
CHAIN_BREACH_WEIGHT: Final[float] = 0.20
ERROR_SCALE: Final[float] = 1.0


class RecoveryAction(enum.StrEnum):
    """Stable recovery actions emitted by :func:`prescribe_recovery`."""

    ALLOW_MODEL_UPDATE = "ALLOW_MODEL_UPDATE"
    BLOCK_WEIGHT_UPDATE = "BLOCK_WEIGHT_UPDATE"
    EXPAND_CONTEXT = "EXPAND_CONTEXT"
    RESEAL_EXPECTED_MODEL = "RESEAL_EXPECTED_MODEL"
    REDUCE_RISK = "REDUCE_RISK"
    ROLLBACK_ACTION = "ROLLBACK_ACTION"
    QUARANTINE_EPISODE = "QUARANTINE_EPISODE"


@dataclass(frozen=True, slots=True)
class RecoveryPlan:
    """Immutable self-healing verdict for one action-result witness."""

    status: ActionResultStatus
    entropy_risk: float
    actions: tuple[RecoveryAction, ...]
    reason: str
    model_update_allowed: bool


def _bounded_unit(value: float) -> float:
    if not math.isfinite(value):
        return 1.0
    return max(0.0, min(1.0, value))


def estimate_entropy_risk(
    witness: ActionResultWitness,
    *,
    free_energy_circuit_breaker: bool = False,
    chain_verified: bool = True,
) -> float:
    """Return a deterministic risk score in ``[0, 1]``.

    The score is intentionally monotone in every failure flag: rollback,
    required update, chain failure, and circuit-breaker activation can only add
    risk.  Comparator error contributes through ``x / (1 + x)`` so large finite
    errors saturate without creating infinities.
    """

    if not isinstance(witness, ActionResultWitness):
        raise ValueError("INVALID_WITNESS: witness must be ActionResultWitness")

    risk = 0.0
    if witness.rollback_required:
        risk += ROLLBACK_WEIGHT
    if witness.update_required or witness.next_context_expansion_required:
        risk += UPDATE_WEIGHT
    if free_energy_circuit_breaker:
        risk += FREE_ENERGY_BREAKER_WEIGHT
    if not chain_verified:
        risk += CHAIN_BREACH_WEIGHT
    if witness.comparator_error is not None:
        risk += ERROR_SCALE * (witness.comparator_error / (1.0 + witness.comparator_error))
    if witness.status in {ActionResultStatus.INVALID_INPUT, ActionResultStatus.ACTION_MISMATCH}:
        risk += 0.10
    return round(_bounded_unit(risk), 6)


def prescribe_recovery(
    witness: ActionResultWitness,
    *,
    free_energy_circuit_breaker: bool = False,
    chain_verified: bool = True,
) -> RecoveryPlan:
    """Map one witness into a deterministic self-healing action plan."""

    entropy_risk = estimate_entropy_risk(
        witness,
        free_energy_circuit_breaker=free_energy_circuit_breaker,
        chain_verified=chain_verified,
    )
    actions: list[RecoveryAction] = []

    if not chain_verified:
        actions.append(RecoveryAction.QUARANTINE_EPISODE)
    if witness.rollback_required:
        actions.extend((RecoveryAction.BLOCK_WEIGHT_UPDATE, RecoveryAction.ROLLBACK_ACTION))
    if witness.status in {ActionResultStatus.INVALID_INPUT, ActionResultStatus.ACTION_MISMATCH}:
        actions.append(RecoveryAction.RESEAL_EXPECTED_MODEL)
    if witness.update_required or witness.next_context_expansion_required:
        actions.append(RecoveryAction.EXPAND_CONTEXT)
    if free_energy_circuit_breaker or entropy_risk >= 0.75:
        actions.append(RecoveryAction.REDUCE_RISK)

    if not actions:
        actions.append(RecoveryAction.ALLOW_MODEL_UPDATE)

    deduped = tuple(dict.fromkeys(actions))
    model_update_allowed = deduped == (RecoveryAction.ALLOW_MODEL_UPDATE,)
    return RecoveryPlan(
        status=witness.status,
        entropy_risk=entropy_risk,
        actions=deduped,
        reason=f"AAR_SELF_HEALING_PLAN: status={witness.status.value} risk={entropy_risk:.6f}",
        model_update_allowed=model_update_allowed,
    )
