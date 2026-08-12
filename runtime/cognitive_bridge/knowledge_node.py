# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""KnowledgeNode — terminal artefact of the semantic sieve.

A ``KnowledgeNode`` is what survives after the 15-stage cycle. The
status is **derived** from V(O) and the G_v gate, never assigned ad
hoc — that keeps the memory layer auditable and forbids cherry-picked
"this is core, trust me" entries.

Status mapping (deterministic):

    G_v fails             → REJECTED
    V(O) ≥ 0.45            → CORE_FACT
    0.30 ≤ V(O) < 0.45     → WORKING_HYPOTHESIS
    0.18 ≤ V(O) < 0.30     → CONTEXTUAL_TOOL
    V(O) < 0.18, audit OK  → ARCHIVED_ERROR
    V(O) < 0.18, no audit  → NOISE

Thresholds are anchored to the default weight sum (Σ positive ≈ 0.70,
Σ penalty ≈ 0.30) so a perfect artefact reaches ~0.70, a half-clean
one ~0.35 (CORE on the boundary). The numbers are configurable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field

from runtime.cognitive_bridge.value_function import GvCondition


class KnowledgeStatus(str, Enum):
    CORE_FACT = "core_fact"
    WORKING_HYPOTHESIS = "working_hypothesis"
    CONTEXTUAL_TOOL = "contextual_tool"
    ARCHIVED_ERROR = "archived_error"
    NOISE = "noise"
    REJECTED = "rejected"


class KnowledgeThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    core_fact: float = Field(default=0.45, ge=0.0, le=1.0)
    working_hypothesis: float = Field(default=0.30, ge=0.0, le=1.0)
    contextual_tool: float = Field(default=0.18, ge=0.0, le=1.0)

    def classify(
        self,
        *,
        value: float,
        gv: GvCondition,
    ) -> KnowledgeStatus:
        if not gv.passes():
            return KnowledgeStatus.REJECTED
        if value >= self.core_fact:
            return KnowledgeStatus.CORE_FACT
        if value >= self.working_hypothesis:
            return KnowledgeStatus.WORKING_HYPOTHESIS
        if value >= self.contextual_tool:
            return KnowledgeStatus.CONTEXTUAL_TOOL
        if gv.completed_audit:
            return KnowledgeStatus.ARCHIVED_ERROR
        return KnowledgeStatus.NOISE


DEFAULT_THRESHOLDS = KnowledgeThresholds()


class KnowledgeNode(BaseModel):
    """Terminal record produced by ``Cycle.commit_to_memory``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cycle_id: str = Field(min_length=1)
    status: KnowledgeStatus
    value_score: float = Field(ge=0.0)
    falsification_contract: str = Field(min_length=1)
    verification_evidence: str = Field(min_length=1)
    summary: str = Field(min_length=1, max_length=4096)
    cross_domain_hits: tuple[str, ...] = Field(default_factory=tuple)
    sealed_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    metadata: Mapping[str, str] = Field(default_factory=dict)


__all__ = [
    "DEFAULT_THRESHOLDS",
    "KnowledgeNode",
    "KnowledgeStatus",
    "KnowledgeThresholds",
]
