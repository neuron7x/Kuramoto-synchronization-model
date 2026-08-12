# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Pure deterministic chronology proof for action-result control episodes.

No IO, no clocks, no random, no mutable globals. Hash chain + monotonic
seq + state machine prove order. The comparator
(``action_result_comparator.accept_action_result``) is invoked exactly
once at ``ERROR_COMPUTED``. No biological-equivalence claim.
"""

from __future__ import annotations

import enum
import hashlib
import re
from dataclasses import dataclass, field

from .action_result_comparator import (
    ActionResultWitness,
    ExpectedResultModel,
    ObservedActionResult,
    accept_action_result,
)

_SHA256_RE: re.Pattern[str] = re.compile(r"^[0-9a-f]{64}$")


class EpisodePhase(enum.StrEnum):
    """Seven-phase chronology for a single control episode.

    Order is the contract: ``INTENT_DECLARED`` always begins, and every
    later phase requires its predecessor. The state machine in this
    module rejects out-of-order calls; the chain hash binds the order
    cryptographically.
    """

    INTENT_DECLARED = "INTENT_DECLARED"
    MODEL_SEALED = "MODEL_SEALED"
    ACTION_DISPATCHED = "ACTION_DISPATCHED"
    AFFERENTATION_RECEIVED = "AFFERENTATION_RECEIVED"
    ERROR_COMPUTED = "ERROR_COMPUTED"
    DECISION_RENDERED = "DECISION_RENDERED"
    MEMORY_ANCHORED = "MEMORY_ANCHORED"


@dataclass(frozen=True, slots=True)
class EpisodeRecord:
    """Single immutable phase record inside a :class:`ControlEpisode`.

    Construction-time validation enforces structural invariants. The
    ``chain_hash`` is recomputed and re-validated by
    :func:`verify_chain` so callers cannot tamper without detection.
    """

    phase: EpisodePhase
    seq: int
    payload_digest: str
    parent_chain_hash: str
    chain_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.phase, EpisodePhase):
            raise ValueError("INVALID_RECORD: phase must be an EpisodePhase")
        if not isinstance(self.seq, int) or isinstance(self.seq, bool):
            raise ValueError("INVALID_RECORD: seq must be int")
        if self.seq < 0:
            raise ValueError("INVALID_RECORD: seq must be >= 0")
        if not _SHA256_RE.match(self.payload_digest):
            raise ValueError("INVALID_RECORD: payload_digest must be 64-char lowercase hex")
        if not _SHA256_RE.match(self.chain_hash):
            raise ValueError("INVALID_RECORD: chain_hash must be 64-char lowercase hex")
        if self.parent_chain_hash == "":
            if self.phase is not EpisodePhase.INTENT_DECLARED:
                raise ValueError(
                    "INVALID_RECORD: empty parent_chain_hash only allowed for INTENT_DECLARED"
                )
        elif not _SHA256_RE.match(self.parent_chain_hash):
            raise ValueError(
                "INVALID_RECORD: parent_chain_hash must be 64-char lowercase hex or empty"
            )


@dataclass(frozen=True, slots=True)
class ControlEpisode:
    """Immutable history of one action-result control episode.

    The seven-phase chain is append-only: every phase function returns a
    NEW :class:`ControlEpisode` whose ``records`` tuple has exactly one
    additional :class:`EpisodeRecord`. Once ``closed`` is True no further
    phase calls are accepted.
    """

    episode_id: str
    records: tuple[EpisodeRecord, ...] = field(default_factory=tuple)
    expected: ExpectedResultModel | None = None
    observed: ObservedActionResult | None = None
    witness: ActionResultWitness | None = None
    closed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.episode_id, str) or not self.episode_id:
            raise ValueError("INVALID_EPISODE: episode_id must be a non-empty string")
        if not isinstance(self.records, tuple):
            raise ValueError("INVALID_EPISODE: records must be a tuple")
        if self.records:
            first = self.records[0]
            if first.phase is not EpisodePhase.INTENT_DECLARED:
                raise ValueError("INVALID_EPISODE: first record must be INTENT_DECLARED")
            if first.parent_chain_hash != "":
                raise ValueError(
                    "INVALID_EPISODE: genesis record must have empty parent_chain_hash"
                )
            for prior, current in zip(self.records, self.records[1:], strict=False):
                if current.seq <= prior.seq:
                    raise ValueError("INVALID_EPISODE: seq must strictly increase across records")
                if current.parent_chain_hash != prior.chain_hash:
                    raise ValueError(
                        "INVALID_EPISODE: parent_chain_hash must equal prior chain_hash"
                    )
            for record in self.records:
                expected_hash = _link_chain(
                    record.parent_chain_hash,
                    record.phase,
                    record.seq,
                    record.payload_digest,
                )
                if expected_hash != record.chain_hash:
                    raise ValueError(
                        "INVALID_EPISODE: chain_hash linkage broken for "
                        f"phase={record.phase.value} seq={record.seq}"
                    )


def _digest_payload(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _link_chain(
    parent_chain_hash: str,
    phase: EpisodePhase,
    seq: int,
    payload_digest: str,
) -> str:
    canonical = b"\x00".join(
        [
            parent_chain_hash.encode("utf-8"),
            phase.value.encode("utf-8"),
            str(seq).encode("utf-8"),
            payload_digest.encode("utf-8"),
        ]
    )
    return hashlib.sha256(canonical).hexdigest()


def _canonical_expected_bytes(expected: ExpectedResultModel) -> bytes:
    parts: tuple[str, ...] = (
        f"action_id={expected.action_id!r}",
        f"action_type={expected.action_type!r}",
        f"expected_result={tuple(repr(x) for x in expected.expected_result)!r}",
        f"model_created_seq={expected.model_created_seq!r}",
        f"action_started_seq={expected.action_started_seq!r}",
        f"error_threshold={expected.error_threshold!r}",
        f"rollback_threshold={expected.rollback_threshold!r}",
    )
    return "|".join(parts).encode("utf-8")


def _canonical_observed_bytes(observed: ObservedActionResult) -> bytes:
    if observed.observed_result is None:
        observed_repr = "None"
    else:
        observed_repr = repr(tuple(repr(x) for x in observed.observed_result))
    parts: tuple[str, ...] = (
        f"action_id={observed.action_id!r}",
        f"observed_seq={observed.observed_seq!r}",
        f"observed_result={observed_repr}",
        f"reverse_afferentation_present={observed.reverse_afferentation_present!r}",
    )
    return "|".join(parts).encode("utf-8")


def _canonical_witness_bytes(witness: ActionResultWitness) -> bytes:
    comparator_error_repr = (
        "None" if witness.comparator_error is None else repr(witness.comparator_error)
    )
    parts: tuple[str, ...] = (
        f"status={witness.status.value}",
        f"comparator_error={comparator_error_repr}",
        f"reason={witness.reason!r}",
    )
    return "|".join(parts).encode("utf-8")


def _require_open(episode: ControlEpisode) -> None:
    if episode.closed:
        raise ValueError("PHASE_REJECTED: episode is closed; no further phases allowed")


def _require_phase(episode: ControlEpisode, expected_prior: EpisodePhase) -> None:
    if not episode.records:
        raise ValueError(
            f"PHASE_REJECTED: expected prior phase {expected_prior.value} but episode is empty"
        )
    last = episode.records[-1].phase
    if last is not expected_prior:
        raise ValueError(
            f"PHASE_REJECTED: expected prior phase {expected_prior.value}; got {last.value}"
        )


def _require_seq_strictly_after(episode: ControlEpisode, seq: int) -> None:
    if not isinstance(seq, int) or isinstance(seq, bool):
        raise ValueError("PHASE_REJECTED: seq must be int")
    if seq < 0:
        raise ValueError("PHASE_REJECTED: seq must be >= 0")
    if episode.records and seq <= episode.records[-1].seq:
        raise ValueError(
            "PHASE_REJECTED: seq must strictly exceed prior record seq "
            f"({seq} <= {episode.records[-1].seq})"
        )


def _append_record(
    episode: ControlEpisode,
    phase: EpisodePhase,
    seq: int,
    payload_digest: str,
    *,
    expected: ExpectedResultModel | None = None,
    observed: ObservedActionResult | None = None,
    witness: ActionResultWitness | None = None,
    closed: bool = False,
) -> ControlEpisode:
    parent_chain_hash = episode.records[-1].chain_hash if episode.records else ""
    chain_hash = _link_chain(parent_chain_hash, phase, seq, payload_digest)
    record = EpisodeRecord(
        phase=phase,
        seq=seq,
        payload_digest=payload_digest,
        parent_chain_hash=parent_chain_hash,
        chain_hash=chain_hash,
    )
    new_records = episode.records + (record,)
    return ControlEpisode(
        episode_id=episode.episode_id,
        records=new_records,
        expected=expected if expected is not None else episode.expected,
        observed=observed if observed is not None else episode.observed,
        witness=witness if witness is not None else episode.witness,
        closed=closed if closed else episode.closed,
    )


def _annul_with_invalid_observation(
    episode: ControlEpisode,
    observed: ObservedActionResult,
    witness: ActionResultWitness,
) -> ControlEpisode:
    """Bind a rejected observation and close the episode deterministically.

    This is the fail-closed path for asynchronous/out-of-order afferentation:
    the invalid observation is still hash-bound as evidence, the comparator
    witness is hash-bound exactly once, and the returned episode is closed so
    no later phase can update model weights from a broken chronology.
    """

    if not witness.rollback_required:
        raise ValueError("PHASE_REJECTED: invalid observation witness must request rollback")
    rejection_seq = episode.records[-1].seq + 1
    rejected = _append_record(
        episode,
        EpisodePhase.AFFERENTATION_RECEIVED,
        rejection_seq,
        _digest_payload(_canonical_observed_bytes(observed)),
        observed=observed,
    )
    witness_seq = rejection_seq + 1
    return _append_record(
        rejected,
        EpisodePhase.ERROR_COMPUTED,
        witness_seq,
        _digest_payload(_canonical_witness_bytes(witness)),
        witness=witness,
        closed=True,
    )


def start_episode(episode_id: str, intent_payload: bytes, seq: int) -> ControlEpisode:
    """Open a new episode at phase ``INTENT_DECLARED``."""

    if not isinstance(episode_id, str) or not episode_id:
        raise ValueError("PHASE_REJECTED: episode_id must be non-empty string")
    if not isinstance(intent_payload, (bytes, bytearray)):
        raise ValueError("PHASE_REJECTED: intent_payload must be bytes")
    if not isinstance(seq, int) or isinstance(seq, bool):
        raise ValueError("PHASE_REJECTED: seq must be int")
    if seq < 0:
        raise ValueError("PHASE_REJECTED: seq must be >= 0")

    payload_digest = _digest_payload(bytes(intent_payload))
    chain_hash = _link_chain("", EpisodePhase.INTENT_DECLARED, seq, payload_digest)
    record = EpisodeRecord(
        phase=EpisodePhase.INTENT_DECLARED,
        seq=seq,
        payload_digest=payload_digest,
        parent_chain_hash="",
        chain_hash=chain_hash,
    )
    return ControlEpisode(episode_id=episode_id, records=(record,))


def seal_model(
    episode: ControlEpisode,
    expected: ExpectedResultModel,
    seq: int,
) -> ControlEpisode:
    """Bind the :class:`ExpectedResultModel` into the chain."""

    _require_open(episode)
    _require_phase(episode, EpisodePhase.INTENT_DECLARED)
    _require_seq_strictly_after(episode, seq)
    if expected is None:
        raise ValueError("PHASE_REJECTED: expected must not be None at MODEL_SEALED")
    if not isinstance(expected, ExpectedResultModel):
        raise ValueError("PHASE_REJECTED: expected must be ExpectedResultModel")
    if expected.model_created_seq != seq:
        raise ValueError(
            "PHASE_REJECTED: seq must equal expected.model_created_seq "
            f"({seq} != {expected.model_created_seq})"
        )

    payload_digest = _digest_payload(_canonical_expected_bytes(expected))
    return _append_record(
        episode,
        EpisodePhase.MODEL_SEALED,
        seq,
        payload_digest,
        expected=expected,
    )


def dispatch_action(
    episode: ControlEpisode,
    action_payload: bytes,
    seq: int,
) -> ControlEpisode:
    """Bind the dispatched action payload into the chain."""

    _require_open(episode)
    _require_phase(episode, EpisodePhase.MODEL_SEALED)
    _require_seq_strictly_after(episode, seq)
    if episode.expected is None:
        raise ValueError("PHASE_REJECTED: expected must be sealed before dispatch")
    if not isinstance(action_payload, (bytes, bytearray)):
        raise ValueError("PHASE_REJECTED: action_payload must be bytes")
    if episode.expected.action_started_seq != seq:
        raise ValueError(
            "PHASE_REJECTED: seq must equal expected.action_started_seq "
            f"({seq} != {episode.expected.action_started_seq})"
        )

    payload_digest = _digest_payload(bytes(action_payload))
    return _append_record(
        episode,
        EpisodePhase.ACTION_DISPATCHED,
        seq,
        payload_digest,
    )


def receive_afferentation(
    episode: ControlEpisode,
    observed: ObservedActionResult,
    seq: int,
) -> ControlEpisode:
    """Bind the :class:`ObservedActionResult` into the chain."""

    _require_open(episode)
    _require_phase(episode, EpisodePhase.ACTION_DISPATCHED)
    if observed is None:
        raise ValueError("PHASE_REJECTED: observed must not be None at AFFERENTATION_RECEIVED")
    if not isinstance(observed, ObservedActionResult):
        raise ValueError("PHASE_REJECTED: observed must be ObservedActionResult")
    if episode.expected is None:
        raise ValueError("PHASE_REJECTED: expected must be sealed before afferentation")
    if observed.observed_seq <= episode.expected.action_started_seq:
        witness = accept_action_result(episode.expected, observed)
        return _annul_with_invalid_observation(episode, observed, witness)

    _require_seq_strictly_after(episode, seq)
    if observed.observed_seq != seq:
        raise ValueError(
            "PHASE_REJECTED: seq must equal observed.observed_seq "
            f"({seq} != {observed.observed_seq})"
        )

    payload_digest = _digest_payload(_canonical_observed_bytes(observed))
    return _append_record(
        episode,
        EpisodePhase.AFFERENTATION_RECEIVED,
        seq,
        payload_digest,
        observed=observed,
    )


def compute_error(episode: ControlEpisode, seq: int) -> ControlEpisode:
    """Invoke the comparator, store the witness, bind it into the chain."""

    _require_open(episode)
    _require_phase(episode, EpisodePhase.AFFERENTATION_RECEIVED)
    _require_seq_strictly_after(episode, seq)
    if episode.expected is None:
        raise ValueError("PHASE_REJECTED: expected must be sealed before compute_error")
    if episode.observed is None:
        raise ValueError("PHASE_REJECTED: observed must be received before compute_error")

    witness = accept_action_result(episode.expected, episode.observed)
    payload_digest = _digest_payload(_canonical_witness_bytes(witness))
    return _append_record(
        episode,
        EpisodePhase.ERROR_COMPUTED,
        seq,
        payload_digest,
        witness=witness,
    )


def render_decision(episode: ControlEpisode, seq: int) -> ControlEpisode:
    """Cross-bind the witness into the chain at the decision phase.

    The payload is the same canonical witness encoding used at
    ``ERROR_COMPUTED`` — this defends against witness substitution
    between the two phases.
    """

    _require_open(episode)
    _require_phase(episode, EpisodePhase.ERROR_COMPUTED)
    _require_seq_strictly_after(episode, seq)
    if episode.witness is None:
        raise ValueError("PHASE_REJECTED: witness must be computed before render_decision")

    payload_digest = _digest_payload(_canonical_witness_bytes(episode.witness))
    return _append_record(
        episode,
        EpisodePhase.DECISION_RENDERED,
        seq,
        payload_digest,
    )


def persist_memory(episode: ControlEpisode, seq: int) -> ControlEpisode:
    """Anchor the prior chain hash as the memory payload and close."""

    _require_open(episode)
    _require_phase(episode, EpisodePhase.DECISION_RENDERED)
    _require_seq_strictly_after(episode, seq)
    if not episode.records:
        raise ValueError("PHASE_REJECTED: cannot persist memory on empty episode")

    prior_chain_hash = episode.records[-1].chain_hash
    payload_digest = _digest_payload(prior_chain_hash.encode("utf-8"))
    return _append_record(
        episode,
        EpisodePhase.MEMORY_ANCHORED,
        seq,
        payload_digest,
        closed=True,
    )


def verify_chain(episode: ControlEpisode) -> bool:
    """Re-walk the chain and return ``True`` iff every link is intact."""

    if not episode.records:
        return False
    for index, record in enumerate(episode.records):
        if index == 0:
            if record.parent_chain_hash != "":
                return False
            if record.phase is not EpisodePhase.INTENT_DECLARED:
                return False
        else:
            prior = episode.records[index - 1]
            if record.parent_chain_hash != prior.chain_hash:
                return False
            if record.seq <= prior.seq:
                return False
        recomputed = _link_chain(
            record.parent_chain_hash,
            record.phase,
            record.seq,
            record.payload_digest,
        )
        if recomputed != record.chain_hash:
            return False
    return True


__all__ = [
    "ControlEpisode",
    "EpisodePhase",
    "EpisodeRecord",
    "compute_error",
    "dispatch_action",
    "persist_memory",
    "receive_afferentation",
    "render_decision",
    "seal_model",
    "start_episode",
    "verify_chain",
]
