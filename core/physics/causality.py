# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Causality — no lookahead, no fabricated knowledge of the future.

Runtime guards for causal admissibility (a read may only consume sources at or
before its own time, within a latency horizon) and provenance identity (a
payload's hash is stable iff its bytes are). Violations are recorded to an
append-only tombstone ledger (JSONL) so a breach leaves durable negative
evidence. Provenance hashing reuses the byte canonicaliser /
hasher from :mod:`core.physics.reversible_gate`.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.physics.reversible_gate import canonicalize_payload, compute_state_hash

__all__ = [
    "causal_cone",
    "assert_no_lookahead",
    "provenance_hash",
    "assert_provenance_identity",
    "tombstone_violation",
]


class CausalityError(ValueError):
    """Raised when a causal-admissibility or provenance guard rejects its input."""


def causal_cone(event_time: float, event_times: list[float], max_latency: float) -> list[int]:
    """Indices of events inside the past light-cone of ``event_time``.

    An event at time ``t`` may causally influence ``event_time`` iff
    ``event_time - max_latency <= t <= event_time``. Returns those indices.
    Fails closed on non-finite inputs or negative latency.
    """
    if not _finite(event_time):
        raise CausalityError(f"event_time must be finite, got {event_time!r}; fail-closed")
    if not _finite(max_latency) or max_latency < 0.0:
        raise CausalityError(f"max_latency must be finite and >= 0, got {max_latency!r}")
    lower = event_time - max_latency
    cone: list[int] = []
    for i, t in enumerate(event_times):
        if not _finite(t):
            raise CausalityError(f"event_times[{i}]={t!r} is non-finite; fail-closed")
        if lower <= t <= event_time:
            cone.append(i)
    return cone


def assert_no_lookahead(read_time: float, source_time: float) -> None:
    """Fail closed unless ``source_time <= read_time`` (no future read)."""
    if not _finite(read_time) or not _finite(source_time):
        raise CausalityError(
            f"times must be finite, got read_time={read_time!r} source_time={source_time!r}"
        )
    if source_time > read_time:
        raise CausalityError(
            f"CAUSAL-LOOKAHEAD VIOLATED: source_time={source_time} > read_time={read_time}; "
            f"a read consumed a source observed in its future. Required: source <= read. "
            f"Fail-closed."
        )


def provenance_hash(payload: bytes) -> str:
    """Stable SHA-256 provenance hash over canonicalised payload bytes."""
    if not isinstance(payload, (bytes, bytearray)):
        raise CausalityError(f"payload must be bytes, got {type(payload).__name__}; fail-closed")
    return compute_state_hash(canonicalize_payload(bytes(payload)))


def assert_provenance_identity(expected: str, observed_payload: bytes) -> None:
    """Fail closed unless recomputed provenance of ``observed_payload`` == ``expected``."""
    actual = provenance_hash(observed_payload)
    if actual != expected:
        raise CausalityError(
            f"PROVENANCE VIOLATED: recomputed hash {actual[:12]}… != expected "
            f"{expected[:12]}…; payload bytes changed without a matching declared hash. "
            f"Fail-closed."
        )


def tombstone_violation(
    ledger_path: str | Path,
    *,
    law_id: str,
    detail: str,
    context: dict[str, object] | None = None,
) -> dict[str, object]:
    """Append a violation record to an append-only JSONL tombstone ledger.

    Returns the record written. The ledger is the durable negative-evidence
    trail: a breach can never be silently swallowed.
    """
    record: dict[str, object] = {
        "law_id": law_id,
        "detail": detail,
        "context": context or {},
    }
    path = Path(ledger_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def _finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))
