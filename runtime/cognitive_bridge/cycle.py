# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""15-stage semantic-sieve cycle as a deterministic state machine.

Pipeline:

    RAW_SIGNAL → CLAIM → CLEAN_CLAIM → INVARIANT → EROSION
        → FALSIFICATION_CONTRACT → STABILITY → CROSS_DOMAIN
        → MEANING_FACT → CRYSTALLIZED_FORM → EXECUTABLE_PROTOCOL
        → RESULT_ARTIFACT → VERIFICATION → AUDIT → KNOWLEDGE_NODE

Every transition is gated. Whoever advances the cycle MUST attach a
``ValueComponents`` sample for the new stage; the orchestrator refuses
to advance otherwise. ``commit_to_memory`` is the only terminal: it
computes V(O), classifies the artefact, and emits the immutable
``KnowledgeNode``.

Hard rules (Inference Discipline §9):

* No stage may be skipped; the transition table is the single source
  of truth.
* ``ABORT`` is the only way out; once aborted the cycle cannot resume.
* The falsification contract MUST be set before the stability stage,
  otherwise the cycle aborts with a ``CycleContractError``.
* Verification evidence MUST be set before the audit stage, otherwise
  G_v fails fail-closed.
"""

from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from runtime.cognitive_bridge.knowledge_node import (
    DEFAULT_THRESHOLDS,
    KnowledgeNode,
    KnowledgeThresholds,
)
from runtime.cognitive_bridge.value_function import (
    DEFAULT_WEIGHTS,
    GvCondition,
    ValueComponents,
    ValueWeights,
    integrate_value,
)


class Stage(str, Enum):
    RAW_SIGNAL = "raw_signal"
    CLAIM = "claim"
    CLEAN_CLAIM = "clean_claim"
    INVARIANT = "invariant"
    EROSION = "erosion"
    FALSIFICATION_CONTRACT = "falsification_contract"
    STABILITY = "stability"
    CROSS_DOMAIN = "cross_domain"
    MEANING_FACT = "meaning_fact"
    CRYSTALLIZED_FORM = "crystallized_form"
    EXECUTABLE_PROTOCOL = "executable_protocol"
    RESULT_ARTIFACT = "result_artifact"
    VERIFICATION = "verification"
    AUDIT = "audit"
    KNOWLEDGE_NODE = "knowledge_node"
    ABORT = "abort"


TRANSITIONS: dict[Stage, frozenset[Stage]] = {
    Stage.RAW_SIGNAL: frozenset({Stage.CLAIM, Stage.ABORT}),
    Stage.CLAIM: frozenset({Stage.CLEAN_CLAIM, Stage.ABORT}),
    Stage.CLEAN_CLAIM: frozenset({Stage.INVARIANT, Stage.ABORT}),
    Stage.INVARIANT: frozenset({Stage.EROSION, Stage.ABORT}),
    Stage.EROSION: frozenset({Stage.FALSIFICATION_CONTRACT, Stage.ABORT}),
    Stage.FALSIFICATION_CONTRACT: frozenset({Stage.STABILITY, Stage.ABORT}),
    Stage.STABILITY: frozenset({Stage.CROSS_DOMAIN, Stage.ABORT}),
    Stage.CROSS_DOMAIN: frozenset({Stage.MEANING_FACT, Stage.ABORT}),
    Stage.MEANING_FACT: frozenset({Stage.CRYSTALLIZED_FORM, Stage.ABORT}),
    Stage.CRYSTALLIZED_FORM: frozenset({Stage.EXECUTABLE_PROTOCOL, Stage.ABORT}),
    Stage.EXECUTABLE_PROTOCOL: frozenset({Stage.RESULT_ARTIFACT, Stage.ABORT}),
    Stage.RESULT_ARTIFACT: frozenset({Stage.VERIFICATION, Stage.ABORT}),
    Stage.VERIFICATION: frozenset({Stage.AUDIT, Stage.ABORT}),
    Stage.AUDIT: frozenset({Stage.KNOWLEDGE_NODE, Stage.ABORT}),
    Stage.KNOWLEDGE_NODE: frozenset(),
    Stage.ABORT: frozenset(),
}


def is_legal(current: Stage, nxt: Stage) -> bool:
    return nxt in TRANSITIONS.get(current, frozenset())


class CycleInvariantId(str, Enum):
    """Cycle-internal contract IDs (distinct from bridge ``CB-INV-*``).

    The semantic-sieve cycle has its own structural contracts. They are
    NOT the same as the bridge invariants in
    ``runtime.cognitive_bridge.invariants`` — keep the namespaces
    separate so audits can attribute violations precisely.
    """

    CYCLE_INV_1_SEQUENTIAL = "CYCLE-INV-1"
    CYCLE_INV_2_FALSIFIER_BEFORE_STABILITY = "CYCLE-INV-2"
    CYCLE_INV_3_VERIFICATION_BEFORE_AUDIT = "CYCLE-INV-3"
    CYCLE_INV_4_TERMINAL_SEALED = "CYCLE-INV-4"
    CYCLE_INV_5_NON_EMPTY_INPUTS = "CYCLE-INV-5"


class CycleContractError(RuntimeError):
    """The caller violated the cycle's structural contract.

    Carries the originating ``CycleInvariantId`` so the audit log can
    attribute the violation to a named contract.
    """

    def __init__(self, invariant_id: CycleInvariantId, message: str) -> None:
        super().__init__(f"[{invariant_id.value}] {message}")
        self.invariant_id = invariant_id


class StageRecord(BaseModel):
    """One tick of the cycle: stage entered + per-stage value sample."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: Stage
    summary: str = Field(min_length=1, max_length=4096)
    components: ValueComponents
    entered_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


@dataclass
class _CycleState:
    stage: Stage = Stage.RAW_SIGNAL
    falsification_contract: str = ""
    verification_evidence: str = ""
    aborted_reason: str = ""
    samples: deque[StageRecord] = field(default_factory=lambda: deque(maxlen=64))
    cross_domain_hits: list[str] = field(default_factory=list)


class Cycle:
    """Deterministic 15-stage semantic-sieve runner.

    Usage::

        cycle = Cycle(seed_summary="OFI imbalance > κ_critical implies ...")
        cycle.advance(Stage.CLAIM, summary="...", components=...)
        ...
        cycle.set_falsification_contract("...")
        ...
        cycle.set_verification_evidence("...")
        node = cycle.commit_to_memory()

    Every transition checks the table; ``commit_to_memory`` is the
    only path that produces a ``KnowledgeNode``.
    """

    def __init__(
        self,
        *,
        seed_summary: str,
        weights: ValueWeights = DEFAULT_WEIGHTS,
        thresholds: KnowledgeThresholds = DEFAULT_THRESHOLDS,
        seed_components: ValueComponents | None = None,
    ) -> None:
        if not seed_summary.strip():
            raise CycleContractError(
                CycleInvariantId.CYCLE_INV_5_NON_EMPTY_INPUTS,
                "seed_summary must be non-empty",
            )
        self._weights = weights
        self._thresholds = thresholds
        self._state = _CycleState()
        seed_components = seed_components or ValueComponents(
            invariance=0.0,
            falsifiability=0.0,
            stability=0.0,
            cross_domain=0.0,
            actionability=0.0,
            reproducibility=0.0,
            productivity=0.0,
            noise=0.0,
            hallucination=0.0,
            cognitive_cost=0.0,
        )
        self._state.samples.append(
            StageRecord(
                stage=Stage.RAW_SIGNAL,
                summary=seed_summary,
                components=seed_components,
            )
        )
        self._cycle_id = hashlib.sha256(
            f"{seed_summary}|{self._state.samples[0].entered_at.isoformat()}".encode()
        ).hexdigest()

    @property
    def cycle_id(self) -> str:
        return self._cycle_id

    @property
    def stage(self) -> Stage:
        return self._state.stage

    @property
    def history(self) -> tuple[StageRecord, ...]:
        return tuple(self._state.samples)

    def advance(
        self,
        next_stage: Stage,
        *,
        summary: str,
        components: ValueComponents,
        cross_domain_hits: tuple[str, ...] = (),
    ) -> None:
        if self._state.stage is Stage.ABORT:
            raise CycleContractError(
                CycleInvariantId.CYCLE_INV_4_TERMINAL_SEALED,
                "cycle is ABORTed; cannot advance",
            )
        if self._state.stage is Stage.KNOWLEDGE_NODE:
            raise CycleContractError(
                CycleInvariantId.CYCLE_INV_4_TERMINAL_SEALED,
                "cycle is sealed; cannot advance",
            )
        if not is_legal(self._state.stage, next_stage):
            raise CycleContractError(
                CycleInvariantId.CYCLE_INV_1_SEQUENTIAL,
                f"illegal transition {self._state.stage.value} -> {next_stage.value}",
            )
        if next_stage is Stage.STABILITY and not self._state.falsification_contract:
            raise CycleContractError(
                CycleInvariantId.CYCLE_INV_2_FALSIFIER_BEFORE_STABILITY,
                "falsification contract must be set before STABILITY",
            )
        if next_stage is Stage.AUDIT and not self._state.verification_evidence:
            raise CycleContractError(
                CycleInvariantId.CYCLE_INV_3_VERIFICATION_BEFORE_AUDIT,
                "verification evidence must be set before AUDIT",
            )
        if next_stage is Stage.CROSS_DOMAIN and cross_domain_hits:
            self._state.cross_domain_hits.extend(cross_domain_hits)
        self._state.samples.append(
            StageRecord(stage=next_stage, summary=summary, components=components)
        )
        self._state.stage = next_stage

    def set_falsification_contract(self, contract: str) -> None:
        if not contract.strip():
            raise CycleContractError(
                CycleInvariantId.CYCLE_INV_5_NON_EMPTY_INPUTS,
                "falsification contract must be non-empty",
            )
        self._state.falsification_contract = contract

    def set_verification_evidence(self, evidence: str) -> None:
        if not evidence.strip():
            raise CycleContractError(
                CycleInvariantId.CYCLE_INV_5_NON_EMPTY_INPUTS,
                "verification evidence must be non-empty",
            )
        self._state.verification_evidence = evidence

    def abort(self, reason: str) -> None:
        if not reason.strip():
            raise CycleContractError(
                CycleInvariantId.CYCLE_INV_5_NON_EMPTY_INPUTS,
                "abort reason must be non-empty",
            )
        self._state.stage = Stage.ABORT
        self._state.aborted_reason = reason

    @property
    def aborted_reason(self) -> str:
        return self._state.aborted_reason

    def commit_to_memory(self, *, summary: str) -> KnowledgeNode:
        if self._state.stage is not Stage.AUDIT:
            raise CycleContractError(
                CycleInvariantId.CYCLE_INV_1_SEQUENTIAL,
                "commit_to_memory requires the cycle to be at AUDIT; "
                f"current stage={self._state.stage.value}",
            )
        gv = GvCondition(
            has_falsification_contract=bool(self._state.falsification_contract),
            has_verification_evidence=bool(self._state.verification_evidence),
            completed_audit=True,
        )
        samples = tuple(record.components for record in self._state.samples)
        value = integrate_value(samples, weights=self._weights, gv=gv)
        status = self._thresholds.classify(value=value, gv=gv)
        self._state.stage = Stage.KNOWLEDGE_NODE
        return KnowledgeNode(
            cycle_id=self._cycle_id,
            status=status,
            value_score=value,
            falsification_contract=self._state.falsification_contract,
            verification_evidence=self._state.verification_evidence,
            summary=summary,
            cross_domain_hits=tuple(self._state.cross_domain_hits),
        )


__all__ = [
    "Cycle",
    "CycleContractError",
    "CycleInvariantId",
    "Stage",
    "StageRecord",
    "TRANSITIONS",
    "is_legal",
]
