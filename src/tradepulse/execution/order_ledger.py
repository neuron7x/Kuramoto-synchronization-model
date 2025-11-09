"""Append-only event ledger for order state reconstruction and auditing."""

from __future__ import annotations

import contextlib
import gzip
import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterator, Mapping, MutableMapping, Sequence

__all__ = ["OrderLedgerEvent", "OrderLedger", "OrderLedgerConfig"]


def _coerce(value: Any) -> Any:
    """Convert ``value`` into a JSON-serialisable representation."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Mapping):
        return {str(key): _coerce(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_coerce(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return repr(value)


def _canonical_dumps(payload: Mapping[str, Any]) -> str:
    """Return a canonical JSON representation with stable key ordering."""

    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class OrderLedgerConfig:
    """Configuration governing ledger snapshotting, indexing, and compaction."""

    snapshot_interval: int = 500
    snapshot_retention: int = 8
    compaction_threshold_events: int = 10_000
    max_journal_size: int = 128 * 1024 * 1024
    archive_retention: int = 4
    index_stride: int = 64

    def __post_init__(self) -> None:
        if self.snapshot_interval < 1:
            raise ValueError("snapshot_interval must be >= 1")
        if self.snapshot_retention < 1:
            raise ValueError("snapshot_retention must be >= 1")
        if self.compaction_threshold_events < 1:
            raise ValueError("compaction_threshold_events must be >= 1")
        if self.max_journal_size < 1024:
            raise ValueError("max_journal_size must be >= 1 KiB")
        if self.archive_retention < 1:
            raise ValueError("archive_retention must be >= 1")
        if self.index_stride < 1:
            raise ValueError("index_stride must be >= 1")


@dataclass(slots=True)
class LedgerMetadata:
    """Materialised metadata describing the persisted ledger segment."""

    version: int
    created_at: str
    updated_at: str
    event_count: int
    next_sequence: int
    tail_digest: str | None
    last_snapshot_sequence: int | None
    last_snapshot_path: str | None
    last_state_hash: str | None
    compacted_through: int
    anchor_digest: str | None
    last_compaction_at: str | None

    META_VERSION = 1

    @classmethod
    def new(cls) -> "LedgerMetadata":
        timestamp = datetime.now(timezone.utc).isoformat()
        return cls(
            version=cls.META_VERSION,
            created_at=timestamp,
            updated_at=timestamp,
            event_count=0,
            next_sequence=1,
            tail_digest=None,
            last_snapshot_sequence=None,
            last_snapshot_path=None,
            last_state_hash=None,
            compacted_through=0,
            anchor_digest=None,
            last_compaction_at=None,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LedgerMetadata":
        metadata = cls.new()
        metadata.version = int(payload.get("version", cls.META_VERSION))
        metadata.created_at = str(payload.get("created_at", metadata.created_at))
        metadata.updated_at = str(payload.get("updated_at", metadata.updated_at))
        metadata.event_count = int(payload.get("event_count", 0))
        metadata.next_sequence = int(payload.get("next_sequence", metadata.next_sequence))
        metadata.tail_digest = payload.get("tail_digest")
        metadata.last_snapshot_sequence = payload.get("last_snapshot_sequence")
        metadata.last_snapshot_path = payload.get("last_snapshot_path")
        metadata.last_state_hash = payload.get("last_state_hash")
        metadata.compacted_through = int(payload.get("compacted_through", 0))
        metadata.anchor_digest = payload.get("anchor_digest")
        metadata.last_compaction_at = payload.get("last_compaction_at")
        return metadata

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "event_count": self.event_count,
            "next_sequence": self.next_sequence,
            "tail_digest": self.tail_digest,
            "last_snapshot_sequence": self.last_snapshot_sequence,
            "last_snapshot_path": self.last_snapshot_path,
            "last_state_hash": self.last_state_hash,
            "compacted_through": self.compacted_through,
            "anchor_digest": self.anchor_digest,
            "last_compaction_at": self.last_compaction_at,
        }


@dataclass(frozen=True, slots=True)
class LedgerSnapshot:
    """Metadata describing a persisted snapshot on disk."""

    sequence: int
    timestamp: str
    digest: str | None
    state_hash: str | None
    path: Path

    def load_state(self) -> MutableMapping[str, Any]:
        with self.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        state = payload.get("state")
        if state is None:
            raise ValueError(f"Snapshot {self.path} missing state payload")
        expected_hash = payload.get("state_hash")
        if expected_hash:
            computed = sha256(_canonical_dumps(state).encode("utf-8")).hexdigest()
            if computed != expected_hash:
                raise ValueError(
                    "Snapshot integrity check failed: state hash mismatch",
                )
        return state
@dataclass(frozen=True, slots=True)
class OrderLedgerEvent:
    """Single append-only entry within the order ledger."""

    sequence: int
    event: str
    timestamp: str
    order_id: str | None
    correlation_id: str | None
    metadata: Mapping[str, Any]
    order_snapshot: MutableMapping[str, Any] | None
    state_snapshot: MutableMapping[str, Any] | None
    state_hash: str | None
    previous_digest: str | None
    digest: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation of the event."""

        return {
            "sequence": self.sequence,
            "event": self.event,
            "timestamp": self.timestamp,
            "order_id": self.order_id,
            "correlation_id": self.correlation_id,
            "metadata": dict(self.metadata),
            "order_snapshot": self.order_snapshot,
            "state_snapshot": self.state_snapshot,
            "state_hash": self.state_hash,
            "previous_digest": self.previous_digest,
            "digest": self.digest,
        }


class OrderLedger:
    """Append-only ledger capturing every order mutation and state snapshot."""

    def __init__(
        self,
        path: Path | str,
        *,
        config: OrderLedgerConfig | None = None,
        snapshot_dir: Path | str | None = None,
    ) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._config = config or OrderLedgerConfig()
        self._snapshot_dir = (
            Path(snapshot_dir)
            if snapshot_dir is not None
            else self._path.with_suffix(self._path.suffix + ".snapshots")
        )
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)
        self._archives_dir = self._snapshot_dir / "archives"
        self._archives_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._path.with_suffix(self._path.suffix + ".index")
        self._metadata_path = self._path.with_suffix(self._path.suffix + ".meta.json")
        self._lock = threading.RLock()
        self._metadata = LedgerMetadata.new()
        self._offset_index: list[tuple[int, int, str | None]] = []
        self._snapshots: list[LedgerSnapshot] = []
        self._anchor_digest: str | None = None
        self._tail_digest: str | None = None
        self._last_state_event: tuple[int, str, str | None, Any, str | None] | None = None
        self._rebuild_from_disk()

    @property
    def path(self) -> Path:
        """Return the file backing the ledger."""

        return self._path

    @property
    def snapshot_dir(self) -> Path:
        """Return the directory where state snapshots are materialised."""

        return self._snapshot_dir

    @property
    def metadata_path(self) -> Path:
        """Return the metadata manifest file path."""

        return self._metadata_path

    @property
    def index_path(self) -> Path:
        """Return the on-disk offset index."""

        return self._index_path

    def append(
        self,
        event: str,
        *,
        order: Mapping[str, Any] | None = None,
        correlation_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        state_snapshot: Mapping[str, Any] | None = None,
    ) -> OrderLedgerEvent:
        """Append a new entry to the ledger and return the structured event."""

        timestamp = datetime.now(timezone.utc).isoformat()
        with self._lock:
            sequence = self._metadata.next_sequence
            previous_digest = self._tail_digest
            if previous_digest is None:
                previous_digest = self._anchor_digest
            payload: dict[str, Any] = {
                "sequence": sequence,
                "event": str(event),
                "timestamp": timestamp,
                "order_id": None,
                "correlation_id": correlation_id,
                "metadata": _coerce(metadata or {}),
                "order_snapshot": None,
                "state_snapshot": None,
                "state_hash": None,
                "previous_digest": previous_digest,
            }
            if order is not None:
                order_snapshot = _coerce(order)
                payload["order_snapshot"] = order_snapshot
                payload["order_id"] = _coerce(order.get("order_id"))
            coerced_state: Any = None
            if state_snapshot is not None:
                coerced_state = _coerce(state_snapshot)
                payload["state_snapshot"] = coerced_state
                payload["state_hash"] = sha256(
                    _canonical_dumps(coerced_state).encode("utf-8")
                ).hexdigest()

            digest_source = dict(payload)
            digest = sha256(_canonical_dumps(digest_source).encode("utf-8")).hexdigest()
            payload["digest"] = digest

            record = json.dumps(payload, sort_keys=True, ensure_ascii=False)
            with self._path.open("a", encoding="utf-8") as handle:
                offset = handle.tell()
                handle.write(record + "\n")

            event_obj = OrderLedgerEvent(
                sequence=sequence,
                event=str(event),
                timestamp=timestamp,
                order_id=payload["order_id"],
                correlation_id=correlation_id,
                metadata=payload["metadata"],
                order_snapshot=payload["order_snapshot"],
                state_snapshot=payload["state_snapshot"],
                state_hash=payload["state_hash"],
                previous_digest=previous_digest,
                digest=digest,
            )

            self._tail_digest = digest
            self._metadata.next_sequence = sequence + 1
            self._metadata.event_count += 1
            self._metadata.updated_at = timestamp
            self._metadata.tail_digest = digest
            if self._metadata.event_count == 1:
                self._metadata.compacted_through = sequence - 1
                self._metadata.anchor_digest = previous_digest
            self._anchor_digest = self._metadata.anchor_digest
            if coerced_state is not None:
                self._last_state_event = (
                    sequence,
                    timestamp,
                    payload["state_hash"],
                    coerced_state,
                    digest,
                )
            if (
                self._metadata.event_count == 1
                or self._metadata.event_count % self._config.index_stride == 0
            ):
                self._offset_index.append((sequence, offset, previous_digest))
                self._append_index_entry(sequence, offset, previous_digest)

            self._maybe_create_snapshot(
                sequence=sequence,
                timestamp=timestamp,
                digest=digest,
                state_hash=payload["state_hash"],
                state_payload=payload["state_snapshot"],
            )

            compacted = self._maybe_compact()
            if compacted:
                created_at = self._metadata.created_at
                compaction_ts = datetime.now(timezone.utc).isoformat()
                self._rebuild_from_disk(preserve_created_at=created_at)
                self._metadata.last_compaction_at = compaction_ts
                self._metadata.updated_at = compaction_ts
                self._write_metadata()
            else:
                self._write_metadata()

            return event_obj

    def replay(self, *, verify: bool = True) -> Iterator[OrderLedgerEvent]:
        """Iterate through recorded events in chronological order."""

        yield from self._iter_events(
            verify=verify,
            start_offset=0,
            initial_previous=self._anchor_digest,
            min_sequence=None,
        )

    def replay_from(
        self, sequence: int, *, verify: bool = True
    ) -> Iterator[OrderLedgerEvent]:
        """Replay events starting from the first entry with ``sequence`` or greater."""

        if sequence < 1:
            raise ValueError("sequence must be >= 1")
        offset, previous = self._find_offset(sequence)
        yield from self._iter_events(
            verify=verify,
            start_offset=offset,
            initial_previous=previous,
            min_sequence=sequence,
        )

    def latest_event(self, *, verify: bool = True) -> OrderLedgerEvent | None:
        """Return the last event recorded in the ledger."""

        last: OrderLedgerEvent | None = None
        start_offset = 0
        start_previous = self._anchor_digest
        if self._offset_index:
            start_offset, start_previous = self._offset_index[-1][1:]
        for event in self._iter_events(
            verify=verify,
            start_offset=start_offset,
            initial_previous=start_previous,
            min_sequence=None,
        ):
            last = event
        return last

    def latest_state(self, *, verify: bool = True) -> MutableMapping[str, Any] | None:
        """Return the most recent state snapshot if available."""

        event = self.latest_event(verify=verify)
        if event is None:
            return None
        snapshot = event.state_snapshot
        if snapshot is not None:
            return snapshot
        return self.load_snapshot()

    def verify(self) -> None:
        """Validate ledger integrity by replaying the digest chain."""

        for _ in self.replay(verify=True):
            continue

    def snapshot_sequences(self) -> Sequence[int]:
        """Return the ordered list of persisted snapshot sequence numbers."""

        with self._lock:
            return [snapshot.sequence for snapshot in self._snapshots]

    def load_snapshot(
        self, sequence: int | None = None
    ) -> MutableMapping[str, Any] | None:
        """Load a snapshot by sequence, defaulting to the most recent."""

        with self._lock:
            if not self._snapshots:
                return None
            target: LedgerSnapshot | None = None
            if sequence is None:
                target = self._snapshots[-1]
            else:
                for snapshot in reversed(self._snapshots):
                    if snapshot.sequence <= sequence:
                        target = snapshot
                        break
            if target is None:
                return None
            state = target.load_state()
            return json.loads(json.dumps(state, ensure_ascii=False))

    def _iter_events(
        self,
        *,
        verify: bool,
        start_offset: int,
        initial_previous: str | None,
        min_sequence: int | None,
    ) -> Iterator[OrderLedgerEvent]:
        if not self._path.exists():
            return
        with self._path.open("r", encoding="utf-8") as handle:
            if start_offset:
                handle.seek(start_offset)
            previous_digest = initial_previous
            for line in handle:
                if not line.strip():
                    continue
                payload = json.loads(line)
                digest = str(payload["digest"])
                if verify:
                    content = dict(payload)
                    del content["digest"]
                    computed = sha256(
                        _canonical_dumps(content).encode("utf-8")
                    ).hexdigest()
                    expected_previous = content.get("previous_digest")
                    if computed != digest:
                        raise ValueError(
                            "Ledger integrity check failed: digest mismatch",
                        )
                    if expected_previous != previous_digest:
                        raise ValueError(
                            "Ledger integrity check failed: broken digest chain",
                        )
                sequence = int(payload["sequence"])
                event = OrderLedgerEvent(
                    sequence=sequence,
                    event=str(payload["event"]),
                    timestamp=str(payload["timestamp"]),
                    order_id=payload.get("order_id"),
                    correlation_id=payload.get("correlation_id"),
                    metadata=payload.get("metadata", {}),
                    order_snapshot=payload.get("order_snapshot"),
                    state_snapshot=payload.get("state_snapshot"),
                    state_hash=payload.get("state_hash"),
                    previous_digest=payload.get("previous_digest"),
                    digest=digest,
                )
                previous_digest = digest
                if min_sequence is not None and sequence < min_sequence:
                    continue
                yield event

    def _maybe_create_snapshot(
        self,
        *,
        sequence: int,
        timestamp: str,
        digest: str | None,
        state_hash: str | None,
        state_payload: Any,
    ) -> None:
        if state_payload is None:
            return
        if self._snapshots and sequence - self._snapshots[-1].sequence < self._config.snapshot_interval:
            return
        self._create_snapshot(sequence, timestamp, digest, state_hash, state_payload)

    def _create_snapshot(
        self,
        sequence: int,
        timestamp: str,
        digest: str | None,
        state_hash: str | None,
        state_payload: Any,
    ) -> LedgerSnapshot:
        path = self._snapshot_dir / f"snapshot_{sequence:020d}.json"
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        snapshot_payload = {
            "sequence": sequence,
            "timestamp": timestamp,
            "digest": digest,
            "state_hash": state_hash,
            "state": json.loads(json.dumps(state_payload, ensure_ascii=False)),
        }
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(snapshot_payload, handle, sort_keys=True, ensure_ascii=False)
        tmp_path.replace(path)
        snapshot = LedgerSnapshot(
            sequence=sequence,
            timestamp=timestamp,
            digest=digest,
            state_hash=state_hash,
            path=path,
        )
        self._snapshots.append(snapshot)
        self._snapshots.sort(key=lambda item: item.sequence)
        self._metadata.last_snapshot_sequence = sequence
        self._metadata.last_snapshot_path = str(path)
        self._metadata.last_state_hash = state_hash
        self._enforce_snapshot_retention()
        return snapshot

    def _enforce_snapshot_retention(self) -> None:
        if len(self._snapshots) <= self._config.snapshot_retention:
            return
        excess = self._snapshots[:-self._config.snapshot_retention]
        for snapshot in excess:
            with contextlib.suppress(FileNotFoundError):
                snapshot.path.unlink()
        self._snapshots = self._snapshots[-self._config.snapshot_retention :]
        latest = self._snapshots[-1]
        self._metadata.last_snapshot_sequence = latest.sequence
        self._metadata.last_snapshot_path = str(latest.path)
        self._metadata.last_state_hash = latest.state_hash

    def _maybe_compact(self) -> bool:
        if not self._snapshots:
            return False
        latest_snapshot = self._snapshots[-1]
        if latest_snapshot.sequence <= self._metadata.compacted_through:
            return False
        events_since_compaction = (
            (self._metadata.next_sequence - 1) - self._metadata.compacted_through
        )
        size_exceeded = self._path.exists() and self._path.stat().st_size > self._config.max_journal_size
        threshold_exceeded = events_since_compaction >= self._config.compaction_threshold_events
        if not size_exceeded and not threshold_exceeded:
            return False
        return self._compact(latest_snapshot)

    def _compact(self, base_snapshot: LedgerSnapshot) -> bool:
        if not self._path.exists():
            return False
        archive_name = (
            f"ledger_{base_snapshot.sequence}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
        )
        archive_path = self._archives_dir / f"{archive_name}.jsonl.gz"
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        removed = False
        anchor_digest: str | None = None
        with (
            self._path.open("r", encoding="utf-8") as source,
            tmp_path.open("w", encoding="utf-8") as target,
            gzip.open(archive_path, "wt", encoding="utf-8") as archive,
        ):
            for line in source:
                if not line.strip():
                    continue
                payload = json.loads(line)
                sequence = int(payload.get("sequence", 0))
                if sequence < base_snapshot.sequence:
                    archive.write(line)
                    anchor_digest = str(payload.get("digest")) or anchor_digest
                    removed = True
                    continue
                target.write(line)
        if not removed:
            with contextlib.suppress(FileNotFoundError):
                tmp_path.unlink()
            with contextlib.suppress(FileNotFoundError):
                archive_path.unlink()
            return False
        tmp_path.replace(self._path)
        self._metadata.compacted_through = base_snapshot.sequence - 1
        self._metadata.anchor_digest = anchor_digest
        self._anchor_digest = anchor_digest
        self._prune_archives()
        return True

    def _prune_archives(self) -> None:
        archives = sorted(self._archives_dir.glob("*.jsonl.gz"))
        if len(archives) <= self._config.archive_retention:
            return
        for path in archives[:-self._config.archive_retention]:
            with contextlib.suppress(FileNotFoundError):
                path.unlink()

    def _find_offset(self, sequence: int) -> tuple[int, str | None]:
        offset = 0
        previous = self._anchor_digest
        for entry_sequence, entry_offset, entry_previous in self._offset_index:
            if entry_sequence <= sequence:
                offset = entry_offset
                previous = entry_previous
            else:
                break
        return offset, previous

    def _append_index_entry(
        self, sequence: int, offset: int, previous_digest: str | None
    ) -> None:
        entry = {
            "sequence": sequence,
            "offset": offset,
            "previous_digest": previous_digest,
        }
        with self._index_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")

    def _write_index_full(self) -> None:
        tmp_path = self._index_path.with_suffix(self._index_path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            for sequence, offset, previous in self._offset_index:
                entry = {
                    "sequence": sequence,
                    "offset": offset,
                    "previous_digest": previous,
                }
                handle.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
        tmp_path.replace(self._index_path)

    def _write_metadata(self) -> None:
        tmp_path = self._metadata_path.with_suffix(self._metadata_path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(self._metadata.to_dict(), handle, sort_keys=True, ensure_ascii=False, indent=2)
        tmp_path.replace(self._metadata_path)

    def _read_metadata_file(self) -> LedgerMetadata | None:
        if not self._metadata_path.exists():
            return None
        with self._metadata_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return LedgerMetadata.from_dict(payload)

    def _rebuild_from_disk(self, *, preserve_created_at: str | None = None) -> None:
        metadata = LedgerMetadata.new()
        existing = self._read_metadata_file()
        if preserve_created_at is not None:
            metadata.created_at = preserve_created_at
        elif existing is not None:
            metadata.created_at = existing.created_at
        metadata.updated_at = metadata.created_at
        if existing is not None:
            metadata.last_compaction_at = existing.last_compaction_at
            metadata.anchor_digest = existing.anchor_digest
        self._offset_index = []
        self._snapshots = []
        self._anchor_digest = metadata.anchor_digest
        self._tail_digest = None
        self._last_state_event = None
        first_sequence: int | None = None
        last_timestamp = metadata.updated_at
        last_sequence = 0
        last_state_event: tuple[int, str, str | None, Any, str | None] | None = None
        offsets: list[tuple[int, int, str | None]] = []
        anchor_digest: str | None = metadata.anchor_digest
        if self._path.exists():
            with self._path.open("r+", encoding="utf-8") as handle:
                previous_digest: str | None = None
                event_count = 0
                while True:
                    offset = handle.tell()
                    line = handle.readline()
                    if not line:
                        break
                    if not line.strip():
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        handle.seek(offset)
                        handle.truncate()
                        break
                    digest = str(payload.get("digest"))
                    content = dict(payload)
                    content.pop("digest", None)
                    computed = sha256(
                        _canonical_dumps(content).encode("utf-8")
                    ).hexdigest()
                    if computed != digest:
                        handle.seek(offset)
                        handle.truncate()
                        break
                    previous = content.get("previous_digest")
                    if event_count == 0:
                        anchor_digest = previous
                        first_sequence = int(content["sequence"])
                    else:
                        if previous != previous_digest:
                            handle.seek(offset)
                            handle.truncate()
                            break
                    event_count += 1
                    previous_digest = digest
                    sequence = int(content["sequence"])
                    last_sequence = sequence
                    last_timestamp = str(content.get("timestamp", last_timestamp))
                    if (
                        event_count == 1
                        or event_count % self._config.index_stride == 0
                    ):
                        offsets.append((sequence, offset, previous))
                    state_snapshot = payload.get("state_snapshot")
                    if state_snapshot is not None:
                        last_state_event = (
                            sequence,
                            str(payload.get("timestamp", last_timestamp)),
                            payload.get("state_hash"),
                            state_snapshot,
                            digest,
                        )
                metadata.event_count = event_count
                if event_count:
                    metadata.next_sequence = last_sequence + 1
                    metadata.tail_digest = previous_digest
                    metadata.updated_at = last_timestamp
                    metadata.compacted_through = (
                        first_sequence - 1 if first_sequence is not None else 0
                    )
                else:
                    metadata.next_sequence = 1
                    metadata.tail_digest = None
                    metadata.compacted_through = 0
        metadata.anchor_digest = anchor_digest
        self._metadata = metadata
        self._anchor_digest = metadata.anchor_digest
        self._tail_digest = metadata.tail_digest
        self._offset_index = offsets
        self._last_state_event = last_state_event
        self._write_index_full()
        self._snapshots = self._load_snapshot_catalog()
        if (
            last_state_event is not None
            and (
                not self._snapshots
                or self._snapshots[-1].sequence < last_state_event[0]
            )
        ):
            self._create_snapshot(
                last_state_event[0],
                last_state_event[1],
                last_state_event[4],
                last_state_event[2],
                last_state_event[3],
            )
        if self._snapshots:
            latest = self._snapshots[-1]
            self._metadata.last_snapshot_sequence = latest.sequence
            self._metadata.last_snapshot_path = str(latest.path)
            self._metadata.last_state_hash = latest.state_hash
        else:
            self._metadata.last_snapshot_sequence = None
            self._metadata.last_snapshot_path = None
            self._metadata.last_state_hash = None
        self._write_metadata()

    def _load_snapshot_catalog(self) -> list[LedgerSnapshot]:
        snapshots: list[LedgerSnapshot] = []
        if not self._snapshot_dir.exists():
            return snapshots
        for path in sorted(self._snapshot_dir.glob("snapshot_*.json")):
            try:
                with path.open("r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                sequence = int(payload["sequence"])
                timestamp = str(payload.get("timestamp"))
                digest = payload.get("digest")
                state = payload.get("state")
                state_hash = payload.get("state_hash")
                if state is None:
                    raise ValueError("missing state payload")
                if state_hash:
                    computed = sha256(
                        _canonical_dumps(state).encode("utf-8")
                    ).hexdigest()
                    if computed != state_hash:
                        raise ValueError("state hash mismatch")
            except Exception:
                with contextlib.suppress(FileNotFoundError):
                    path.unlink()
                continue
            snapshots.append(
                LedgerSnapshot(
                    sequence=sequence,
                    timestamp=timestamp,
                    digest=digest,
                    state_hash=state_hash,
                    path=path,
                )
            )
        snapshots.sort(key=lambda snapshot: snapshot.sequence)
        if len(snapshots) > self._config.snapshot_retention:
            for stale in snapshots[:-self._config.snapshot_retention]:
                with contextlib.suppress(FileNotFoundError):
                    stale.path.unlink()
            snapshots = snapshots[-self._config.snapshot_retention :]
        return snapshots

