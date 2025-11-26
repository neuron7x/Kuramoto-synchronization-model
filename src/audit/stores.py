"""Append-only persistence primitives for audit records."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterable, Iterator, Protocol

if TYPE_CHECKING:
    from .audit_logger import AuditRecord

__all__ = [
    "AuditIntegrityError",
    "AuditLedgerEntry",
    "AuditRecordStore",
    "JsonLinesAuditStore",
]

_GENESIS_HASH = "0" * 64


class AuditIntegrityError(RuntimeError):
    """Raised when the audit log fails integrity verification."""

    def __init__(self, message: str, *, line_number: int | None = None) -> None:
        detail = message if line_number is None else f"{message} (line {line_number})"
        super().__init__(detail)
        self.line_number = line_number


@dataclass(frozen=True)
class AuditLedgerEntry:
    """Materialised representation of a persisted audit record."""

    sequence: int
    record: "AuditRecord"
    record_hash: str
    chain_hash: str


class AuditRecordStore(Protocol):
    """Protocol describing append-only persistence for :class:`AuditRecord`."""

    def append(self, record: "AuditRecord") -> AuditLedgerEntry:
        """Persist *record* using an append-only strategy."""


class JsonLinesAuditStore:
    """Append audit records to a JSON Lines file with durability guarantees."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._sequence = -1
        self._chain_hash = _GENESIS_HASH
        if self._path.exists():
            self._initialise_from_log()

    def append(self, record: "AuditRecord") -> AuditLedgerEntry:
        payload = record.model_dump(mode="json")
        record_hash = _hash_payload(payload)
        with self._lock:
            sequence = self._sequence + 1
            chain_hash = _compute_chain_hash(self._chain_hash, record_hash)
            envelope = {
                "sequence": sequence,
                "record": payload,
                "record_hash": record_hash,
                "chain_hash": chain_hash,
            }
            line = json.dumps(
                envelope,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            entry = AuditLedgerEntry(
                sequence=sequence,
                record=record,
                record_hash=record_hash,
                chain_hash=chain_hash,
            )
            self._sequence = sequence
            self._chain_hash = chain_hash
            return entry

    def verify_integrity(
        self,
        *,
        verifier: Callable[["AuditRecord"], bool] | None = None,
        raise_on_error: bool = False,
    ) -> bool:
        """Verify the chain and optional signatures of persisted audit records."""

        try:
            for _ in self.replay(verifier=verifier):
                continue
        except AuditIntegrityError:
            if raise_on_error:
                raise
            return False
        return True

    def replay(
        self,
        *,
        verifier: Callable[["AuditRecord"], bool] | None = None,
    ) -> Iterator[AuditLedgerEntry]:
        """Yield persisted audit records in order, validating chain integrity."""

        with self._lock:
            yield from self._iter_entries(verifier=verifier)

    def _initialise_from_log(self) -> None:
        with self._lock:
            entries = tuple(self._iter_entries())
            if entries:
                self._sequence = entries[-1].sequence
                self._chain_hash = entries[-1].chain_hash

    def _iter_entries(
        self,
        *,
        verifier: Callable[["AuditRecord"], bool] | None = None,
    ) -> Iterable[AuditLedgerEntry]:
        previous_chain = _GENESIS_HASH
        expected_sequence = 0
        if not self._path.exists():
            return []
        with self._path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    envelope = json.loads(line)
                except json.JSONDecodeError as exc:  # pragma: no cover - defensive
                    raise AuditIntegrityError(
                        "Failed to decode audit envelope",
                        line_number=line_number,
                    ) from exc
                sequence = envelope.get("sequence")
                record_payload = envelope.get("record")
                record_hash = envelope.get("record_hash")
                chain_hash = envelope.get("chain_hash")
                if not isinstance(sequence, int):
                    raise AuditIntegrityError(
                        "Missing or invalid sequence number",
                        line_number=line_number,
                    )
                if sequence != expected_sequence:
                    raise AuditIntegrityError(
                        "Unexpected sequence number",
                        line_number=line_number,
                    )
                if not isinstance(record_payload, dict):
                    raise AuditIntegrityError(
                        "Invalid record payload",
                        line_number=line_number,
                    )
                record = _validate_record(record_payload, line_number)
                expected_hash = _hash_payload(record.model_dump(mode="json"))
                if record_hash != expected_hash:
                    raise AuditIntegrityError(
                        "Record hash mismatch",
                        line_number=line_number,
                    )
                expected_chain_hash = _compute_chain_hash(previous_chain, expected_hash)
                if chain_hash != expected_chain_hash:
                    raise AuditIntegrityError(
                        "Chain hash mismatch",
                        line_number=line_number,
                    )
                if verifier is not None and not verifier(record):
                    raise AuditIntegrityError(
                        "Signature verification failed",
                        line_number=line_number,
                    )
                yield AuditLedgerEntry(
                    sequence=sequence,
                    record=record,
                    record_hash=expected_hash,
                    chain_hash=expected_chain_hash,
                )
                expected_sequence += 1
                previous_chain = expected_chain_hash


def _hash_payload(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _compute_chain_hash(previous_hash: str, current_hash: str) -> str:
    material = (previous_hash + current_hash).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _validate_record(payload: dict[str, object], line_number: int) -> "AuditRecord":
    from .audit_logger import AuditRecord  # Local import to avoid circular dependency

    try:
        return AuditRecord.model_validate(payload)
    except Exception as exc:  # pragma: no cover - validation errors are exceptional
        raise AuditIntegrityError(
            "Failed to load persisted audit record",
            line_number=line_number,
        ) from exc
