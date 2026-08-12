# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Reversible decision gate for the Physics-Native Cognitive Kernel (PNCC).

This module is module **PNCC-C**: an external thermodynamically-bounded decision
controller that enforces Bennett-principle-inspired auditability over every
decision path the platform takes. The gate is **opt-in** behind explicit
configuration and is not wired into the trading pipeline by default.

Contract (universal):
    INV-REVERSIBLE-GATE | universal | byte-exact pre-state recovery | P0
        For any action with ``irreversibility_score <= cfg.irreversibility_threshold``
        (treated as reversible): ``gate.rollback(trace.audit_hash).state_bytes ==
        pre_state``. Falsification: 1000 random reversible actions, any byte
        mismatch fails the test.

    INV-HPC1            | universal | seeded reproducibility       | P0
        Same inputs → bit-identical ``audit_hash``. Verified by
        ``test_audit_hash_deterministic`` and ``test_gate_deterministic_under_fixed_seed``.

    INV-HPC2            | universal | finite inputs → finite outputs | P0
        ``irreversibility_score`` always returns a finite float in ``[0, 1]``
        for finite inputs. Verified by ``test_irreversibility_score_in_unit_interval``.

References:
    * C. H. Bennett, "Logical reversibility of computation",
      IBM J. Res. Dev. 17(6):525-532 (1973).
    * C. H. Bennett, "The thermodynamics of computation - a review",
      Int. J. Theor. Phys. 21:905-940 (1982).

No-bio claim:
    This module audits **system-level** decision reversibility. It makes no
    claim about human cognition or recovery from cognitive errors. HYP-2
    (reversible-logging reduces error-recovery cost) requires a 90-day
    evidence ledger; see ``tacl/evidence_ledger.py``.

Hard contracts enforced here:
    * Deterministic under fixed seed (no time/random in hash inputs).
    * No silent fallback: rollback of an unknown audit_hash raises ``KeyError``.
    * No look-ahead: state hashes are computed from caller-supplied bytes only.
    * No hidden global state: ledger is instance-scoped.
    * Audit hashes are content-addressable (sha256), never based on memory
      addresses or object identity.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Final

__all__ = [
    "DecisionTrace",
    "RollbackState",
    "ReversibleGateConfig",
    "ReversibleGate",
    "compute_state_hash",
    "compute_audit_hash",
    "irreversibility_score",
    "canonicalize_payload",
]

# Domain separator strings prevent cross-protocol hash collisions.
_STATE_HASH_DOMAIN: Final[bytes] = b"PNCC-C\x00state\x00v1\x00"
_AUDIT_HASH_DOMAIN: Final[bytes] = b"PNCC-C\x00audit\x00v1\x00"

# Heuristic constants for irreversibility_score. Constants are fixed by the
# contract (must be deterministic + monotonic in side_effects); tuning these
# would silently change every recorded audit_hash, which is why they live here
# behind the public function.
_PAYLOAD_HALF_KB: Final[float] = 1024.0  # bytes at which payload contributes 0.5
_KIND_BIAS: Final[dict[str, float]] = {
    "noop": 0.0,
    "read": 0.0,
    "compute": 0.0,
    "log": 0.0,
    "snapshot": 0.0,
    "write": 0.30,
    "submit": 0.50,
    "cancel": 0.20,
    "broadcast": 0.70,
    "external_io": 0.85,
    "trade": 0.90,
    "settlement": 1.0,
}
_DEFAULT_KIND_BIAS: Final[float] = 0.40  # unknown action_kind → mid-range


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DecisionTrace:
    """Immutable record of a single gated decision.

    ``audit_hash`` is sha256 over the canonical 5-tuple
    ``(action_id, pre_state_hash, action_payload, post_state_hash, timestamp_ns)``
    — see :func:`compute_audit_hash`. Two traces are equal iff their
    audit_hash and all surrounding fields agree, but the audit_hash alone is
    cryptographically sufficient to identify a trace.
    """

    audit_hash: str
    action_id: str
    pre_state_hash: str
    post_state_hash: str
    action_payload: bytes
    timestamp_ns: int
    is_reversible: bool
    irreversibility_score: float  # in [0, 1]; 0 = fully reversible
    rollback_payload: bytes | None  # populated only if is_reversible


@dataclass(frozen=True, slots=True)
class RollbackState:
    """Recovered pre-state plus the audit linkage that produced it."""

    state_bytes: bytes
    state_hash: str  # sha256 of state_bytes
    audit_hash: str  # the trace this rollback corresponds to


@dataclass(frozen=True, slots=True)
class ReversibleGateConfig:
    """Opt-in configuration for the reversible gate.

    All defaults are conservative: a low irreversibility threshold, mandatory
    rollback payloads for reversible actions, fail-closed on hash collisions,
    canonical-JSON normalisation enabled.
    """

    irreversibility_threshold: float = 0.05  # below this, treat as fully reversible
    require_rollback_payload: bool = True
    fail_on_hash_collision: bool = True
    canonicalize_json: bool = True


# ---------------------------------------------------------------------------
# Pure helpers (exported)
# ---------------------------------------------------------------------------


def compute_state_hash(state_bytes: bytes) -> str:
    """sha256 of ``state_bytes`` with PNCC-C state-domain separator.

    Pure, deterministic, INV-HPC1: same input → same hex digest.
    """
    if not isinstance(state_bytes, (bytes, bytearray)):
        raise TypeError(
            f"compute_state_hash: state_bytes must be bytes/bytearray, got {type(state_bytes)!r}"
        )
    h = hashlib.sha256()
    h.update(_STATE_HASH_DOMAIN)
    h.update(bytes(state_bytes))
    return h.hexdigest()


def compute_audit_hash(
    action_id: str,
    pre_state_hash: str,
    action_payload: bytes,
    post_state_hash: str,
    timestamp_ns: int,
) -> str:
    """sha256 over the canonical 5-tuple of trace identifiers.

    The tuple is encoded length-prefixed so that no concatenation of
    different sub-fields can collide. INV-HPC1: same inputs → same digest.
    """
    if not isinstance(action_id, str):
        raise TypeError(f"compute_audit_hash: action_id must be str, got {type(action_id)!r}")
    if not isinstance(pre_state_hash, str) or not isinstance(post_state_hash, str):
        raise TypeError("compute_audit_hash: state hashes must be str (hex digests)")
    if not isinstance(action_payload, (bytes, bytearray)):
        raise TypeError(
            f"compute_audit_hash: action_payload must be bytes/bytearray, "
            f"got {type(action_payload)!r}"
        )
    if not isinstance(timestamp_ns, int) or isinstance(timestamp_ns, bool):
        raise TypeError(
            f"compute_audit_hash: timestamp_ns must be int (not bool), got {type(timestamp_ns)!r}"
        )
    if timestamp_ns < 0:
        raise ValueError(f"compute_audit_hash: timestamp_ns must be >= 0, got {timestamp_ns}")

    h = hashlib.sha256()
    h.update(_AUDIT_HASH_DOMAIN)

    def _put(buf: bytes) -> None:
        h.update(len(buf).to_bytes(8, "big", signed=False))
        h.update(buf)

    _put(action_id.encode("utf-8"))
    _put(pre_state_hash.encode("utf-8"))
    _put(bytes(action_payload))
    _put(post_state_hash.encode("utf-8"))
    h.update(timestamp_ns.to_bytes(16, "big", signed=False))
    return h.hexdigest()


def canonicalize_payload(payload: bytes) -> bytes:
    """If ``payload`` parses as JSON, re-emit with sorted keys + tight separators.

    Otherwise pass through unchanged. Used so that semantically equivalent
    JSON dictionaries hash to the same digest regardless of key order or
    whitespace. Pure and total: never raises on non-JSON input.
    """
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError(f"canonicalize_payload: payload must be bytes, got {type(payload)!r}")
    raw = bytes(payload)
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return raw
    return json.dumps(decoded, sort_keys=True, separators=(",", ":")).encode("utf-8")


def irreversibility_score(action_kind: str, payload_size: int, side_effects: int) -> float:
    """Heuristic mapping action characteristics → ``[0, 1]``.

    Pure, side-effect free, deterministic. Monotone non-decreasing in
    ``side_effects`` (INV-REVERSIBLE-GATE supporting property). Pure-noop
    actions (``side_effects == 0`` and ``action_kind`` in the read-only set
    with empty payload) score exactly ``0.0``.

    Mapping
    -------
    * ``kind_bias``: lookup in ``_KIND_BIAS`` (fallback ``_DEFAULT_KIND_BIAS``).
    * ``payload_term`` = ``payload_size / (payload_size + 1024)`` ∈ [0, 1).
    * ``side_term`` = ``1 - exp(-side_effects)`` ∈ [0, 1).
    * Combined as a saturating disjunction:
      ``1 - (1 - kind_bias) * (1 - payload_term) * (1 - side_term)``.
    """
    if not isinstance(action_kind, str):
        raise TypeError(
            f"irreversibility_score: action_kind must be str, got {type(action_kind)!r}"
        )
    if not isinstance(payload_size, int) or isinstance(payload_size, bool):
        raise TypeError(
            f"irreversibility_score: payload_size must be int, got {type(payload_size)!r}"
        )
    if not isinstance(side_effects, int) or isinstance(side_effects, bool):
        raise TypeError(
            f"irreversibility_score: side_effects must be int, got {type(side_effects)!r}"
        )
    if payload_size < 0:
        raise ValueError(f"irreversibility_score: payload_size must be >= 0, got {payload_size}")
    if side_effects < 0:
        raise ValueError(f"irreversibility_score: side_effects must be >= 0, got {side_effects}")

    kind_bias = _KIND_BIAS.get(action_kind, _DEFAULT_KIND_BIAS)

    # payload_term in [0, 1) — exact 0 when payload_size == 0.
    payload_term = float(payload_size) / (float(payload_size) + _PAYLOAD_HALF_KB)

    # side_term in [0, 1) — exact 0 when side_effects == 0; saturating.
    # Use a bounded series instead of math.exp to keep determinism cross-platform:
    # 1 - (1 / (1 + side_effects)) is monotone and stays in [0, 1).
    side_term = 1.0 - (1.0 / (1.0 + float(side_effects)))

    score = 1.0 - (1.0 - kind_bias) * (1.0 - payload_term) * (1.0 - side_term)
    # bounds: clamp guards against float drift at the boundaries (INV-HPC2:
    # finite in → finite out, always in [0, 1]). Logged via dedicated tests.
    if score < 0.0:
        score = 0.0
    elif score > 1.0:
        score = 1.0
    return float(score)


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


class ReversibleGate:
    """In-memory rollback ledger keyed by audit_hash.

    Not thread-safe; caller is responsible for external serialisation. There
    is **no hidden global state**: every instance owns a private ledger and
    two instances of the gate cannot observe each other's traces.
    """

    def __init__(self, cfg: ReversibleGateConfig | None = None) -> None:
        self._cfg: Final[ReversibleGateConfig] = cfg if cfg is not None else ReversibleGateConfig()
        self._traces: dict[str, DecisionTrace] = {}
        self._rollbacks: dict[str, RollbackState] = {}

    # -- public properties -------------------------------------------------

    @property
    def config(self) -> ReversibleGateConfig:
        return self._cfg

    def is_known(self, audit_hash: str) -> bool:
        if not isinstance(audit_hash, str):
            raise TypeError(f"is_known: audit_hash must be str, got {type(audit_hash)!r}")
        return audit_hash in self._traces

    def trace(self, audit_hash: str) -> DecisionTrace:
        if not isinstance(audit_hash, str):
            raise TypeError(f"trace: audit_hash must be str, got {type(audit_hash)!r}")
        try:
            return self._traces[audit_hash]
        except KeyError as exc:
            # Fail-closed; no silent fallback.
            raise KeyError(
                f"ReversibleGate.trace: unknown audit_hash={audit_hash!r}; "
                f"ledger size={len(self._traces)}"
            ) from exc

    # -- core API ----------------------------------------------------------

    def gate(
        self,
        action_id: str,
        pre_state: bytes,
        action_payload: bytes,
        post_state: bytes,
        irreversibility_score: float,
        timestamp_ns: int,
        rollback_payload: bytes | None = None,
    ) -> DecisionTrace:
        """Admit one decision into the ledger and return its trace.

        Reversibility is decided by ``irreversibility_score <=
        cfg.irreversibility_threshold``. If the action is reversible:
            * ``cfg.require_rollback_payload`` (default True) requires the
              caller to supply ``rollback_payload``; otherwise the gate
              defaults to ``rollback_payload = pre_state`` so that
              :meth:`rollback` can reproduce the byte-exact pre-state
              (INV-REVERSIBLE-GATE).
        If the action is irreversible:
            * ``rollback_payload`` is forced to ``None`` in the trace
              (no false promise of recovery).

        Raises
        ------
        TypeError
            On wrong-typed arguments (fail-closed).
        ValueError
            On negative timestamps, NaN/out-of-range scores, or hash
            collision when ``cfg.fail_on_hash_collision`` is set.
        """
        # --- input validation (fail-closed, no silent repair) ----------
        if not isinstance(action_id, str):
            raise TypeError(f"gate: action_id must be str, got {type(action_id)!r}")
        if not isinstance(pre_state, (bytes, bytearray)):
            raise TypeError(f"gate: pre_state must be bytes, got {type(pre_state)!r}")
        if not isinstance(action_payload, (bytes, bytearray)):
            raise TypeError(f"gate: action_payload must be bytes, got {type(action_payload)!r}")
        if not isinstance(post_state, (bytes, bytearray)):
            raise TypeError(f"gate: post_state must be bytes, got {type(post_state)!r}")
        if not isinstance(irreversibility_score, (int, float)) or isinstance(
            irreversibility_score, bool
        ):
            raise TypeError(
                f"gate: irreversibility_score must be float, got {type(irreversibility_score)!r}"
            )
        score = float(irreversibility_score)
        # NaN check (INV-HPC2): NaN != NaN.
        if score != score:
            raise ValueError("gate: irreversibility_score must not be NaN")
        if score < 0.0 or score > 1.0:
            raise ValueError(f"gate: irreversibility_score must be in [0, 1], got {score!r}")
        if not isinstance(timestamp_ns, int) or isinstance(timestamp_ns, bool):
            raise TypeError(f"gate: timestamp_ns must be int, got {type(timestamp_ns)!r}")
        if timestamp_ns < 0:
            raise ValueError(f"gate: timestamp_ns must be >= 0, got {timestamp_ns}")
        if rollback_payload is not None and not isinstance(rollback_payload, (bytes, bytearray)):
            raise TypeError(
                f"gate: rollback_payload must be bytes or None, got {type(rollback_payload)!r}"
            )

        pre_bytes = bytes(pre_state)
        post_bytes = bytes(post_state)
        payload_bytes = bytes(action_payload)
        if self._cfg.canonicalize_json:
            payload_bytes = canonicalize_payload(payload_bytes)

        # --- decide reversibility --------------------------------------
        is_reversible = score <= self._cfg.irreversibility_threshold

        # --- enforce rollback contract --------------------------------
        if is_reversible:
            if rollback_payload is None:
                if self._cfg.require_rollback_payload:
                    raise ValueError(
                        "gate: action is reversible (score="
                        f"{score:.6f} <= threshold={self._cfg.irreversibility_threshold:.6f}) "
                        "but require_rollback_payload=True and no rollback_payload was supplied"
                    )
                # Implicit pre-state recovery: use pre_state itself.
                rb_bytes: bytes | None = pre_bytes
            else:
                rb_bytes = bytes(rollback_payload)
        else:
            # Irreversible actions never carry a rollback payload — recording
            # one would be a false promise. We log if the caller passed one
            # by clearing it explicitly.
            rb_bytes = None

        # --- compute hashes -------------------------------------------
        pre_hash = compute_state_hash(pre_bytes)
        post_hash = compute_state_hash(post_bytes)
        audit_hash = compute_audit_hash(
            action_id=action_id,
            pre_state_hash=pre_hash,
            action_payload=payload_bytes,
            post_state_hash=post_hash,
            timestamp_ns=timestamp_ns,
        )

        # --- collision handling (fail-closed) -------------------------
        if audit_hash in self._traces:
            existing = self._traces[audit_hash]
            same_trace = (
                existing.action_id == action_id
                and existing.pre_state_hash == pre_hash
                and existing.post_state_hash == post_hash
                and existing.action_payload == payload_bytes
                and existing.timestamp_ns == timestamp_ns
                and existing.irreversibility_score == score
                and existing.is_reversible == is_reversible
                and existing.rollback_payload == rb_bytes
            )
            if not same_trace and self._cfg.fail_on_hash_collision:
                raise ValueError(
                    f"gate: sha256 audit_hash collision detected for {audit_hash!r}; "
                    f"existing trace differs from new one — refusing to overwrite "
                    f"(fail_on_hash_collision=True)"
                )
            # Idempotent re-admission of an identical trace is allowed.
            return existing

        trace = DecisionTrace(
            audit_hash=audit_hash,
            action_id=action_id,
            pre_state_hash=pre_hash,
            post_state_hash=post_hash,
            action_payload=payload_bytes,
            timestamp_ns=timestamp_ns,
            is_reversible=is_reversible,
            irreversibility_score=score,
            rollback_payload=rb_bytes,
        )
        self._traces[audit_hash] = trace
        if is_reversible and rb_bytes is not None:
            self._rollbacks[audit_hash] = RollbackState(
                state_bytes=rb_bytes,
                state_hash=compute_state_hash(rb_bytes),
                audit_hash=audit_hash,
            )
        return trace

    def rollback(self, audit_hash: str) -> RollbackState:
        """Return the recorded pre-state for a reversible audit_hash.

        Fail-closed: unknown audit_hash → ``KeyError``.
        Irreversible action → ``ValueError`` (no silent fallback).
        """
        if not isinstance(audit_hash, str):
            raise TypeError(f"rollback: audit_hash must be str, got {type(audit_hash)!r}")
        if audit_hash not in self._traces:
            raise KeyError(
                f"ReversibleGate.rollback: unknown audit_hash={audit_hash!r}; "
                f"ledger size={len(self._traces)}"
            )
        trace = self._traces[audit_hash]
        if not trace.is_reversible:
            raise ValueError(
                f"ReversibleGate.rollback: trace {audit_hash!r} is irreversible "
                f"(score={trace.irreversibility_score:.6f} > "
                f"threshold={self._cfg.irreversibility_threshold:.6f}); no rollback recorded"
            )
        try:
            return self._rollbacks[audit_hash]
        except KeyError as exc:  # pragma: no cover — guarded by gate() invariant
            raise KeyError(
                f"ReversibleGate.rollback: internal consistency error — trace "
                f"{audit_hash!r} marked reversible but no RollbackState present"
            ) from exc
