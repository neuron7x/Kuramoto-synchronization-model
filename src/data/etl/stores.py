# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Stateful stores and metadata registries supporting ETL pipelines."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import md5
from typing import Any, Iterable

import pandas as pd


@dataclass(slots=True)
class AuditEntry:
    """Represent a single auditable event in a pipeline run."""

    run_id: str
    segment: str
    status: str
    started_at: datetime
    finished_at: datetime
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()


class AuditLog:
    """Append-only store for pipeline execution metadata."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def record(self, entry: AuditEntry) -> None:
        self._entries.append(entry)

    def history(self, run_id: str | None = None) -> list[AuditEntry]:
        if run_id is None:
            return list(self._entries)
        return [entry for entry in self._entries if entry.run_id == run_id]


@dataclass(slots=True)
class CatalogEntry:
    """Describe a dataset produced by a pipeline."""

    name: str
    version: str
    created_at: datetime
    schema_signature: str
    row_count: int
    source_run_id: str
    extras: dict[str, Any] = field(default_factory=dict)


class DataCatalog:
    """Light-weight in-memory data catalog."""

    def __init__(self) -> None:
        self._entries: dict[str, list[CatalogEntry]] = defaultdict(list)

    def register(self, entry: CatalogEntry) -> None:
        self._entries[entry.name].append(entry)

    def latest(self, name: str) -> CatalogEntry | None:
        entries = self._entries.get(name)
        if not entries:
            return None
        return max(entries, key=lambda item: item.created_at)

    def history(self, name: str) -> list[CatalogEntry]:
        return list(self._entries.get(name, ()))


class PartitionVersioner:
    """Maintain monotonically increasing versions per data partition."""

    def __init__(self) -> None:
        self._versions: dict[str, int] = defaultdict(int)

    def next_version(self, partition_key: str) -> int:
        self._versions[partition_key] += 1
        return self._versions[partition_key]

    def current_version(self, partition_key: str) -> int:
        return self._versions.get(partition_key, 0)


class IdempotencyStore:
    """Track processed run identifiers to prevent duplicate ingestion."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def check_and_register(self, run_id: str) -> bool:
        """Return ``True`` when ``run_id`` is new and now registered."""

        if run_id in self._seen:
            return False
        self._seen.add(run_id)
        return True


class QuarantineStore:
    """Accumulate problematic records for later inspection."""

    def __init__(self) -> None:
        self._frames: dict[str, list[pd.DataFrame]] = defaultdict(list)

    def append(self, reason: str, records: pd.DataFrame) -> None:
        if records.empty:
            return
        self._frames[reason].append(records.copy(deep=True))

    def as_frame(self, reason: str | None = None) -> pd.DataFrame:
        if reason is None:
            frames = [frame for lists in self._frames.values() for frame in lists]
        else:
            frames = self._frames.get(reason, [])
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def reasons(self) -> Iterable[str]:
        return list(self._frames.keys())


def dataframe_signature(frame: pd.DataFrame) -> str:
    """Return a deterministic fingerprint for schema/version tracking."""

    cols = tuple((col, str(dtype)) for col, dtype in frame.dtypes.items())
    payload = repr(cols).encode()
    return md5(payload, usedforsecurity=False).hexdigest()
