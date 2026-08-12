# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""File-backed feature catalog helpers used by the CLI."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from core.config.cli_models import CatalogConfig, GeoSyncBaseConfig


@dataclass
class CatalogEntry:
    """Represents a stored artifact in the feature catalog."""

    name: str
    path: Path
    checksum: str
    created_at: datetime
    metadata: Dict[str, object]
    lineage: List[str]


class FeatureCatalog:
    """A minimal JSON file catalog for CLI artifact registration."""

    def __init__(self, config: CatalogConfig | Path) -> None:
        if isinstance(config, CatalogConfig):
            self.path = config.path
        else:
            self.path = Path(config)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load_entries(self) -> List[Dict[str, object]]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return data.get("artifacts", []) if isinstance(data, dict) else []

    def _write_entries(self, entries: Iterable[Dict[str, object]]) -> None:
        payload = {"artifacts": list(entries)}
        self.path.write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )

    def register(
        self,
        name: str,
        artifact_path: Path,
        *,
        config: GeoSyncBaseConfig,
        lineage: Optional[Iterable[str]] = None,
        metadata: Optional[Dict[str, object]] = None,
    ) -> CatalogEntry:
        artifact_path = artifact_path.resolve()
        checksum = _sha256_file(artifact_path)
        config_dump = json.loads(config.model_dump_json())
        entry = {
            "name": name,
            "path": str(artifact_path),
            "checksum": checksum,
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
            "config": config_dump,
            "metadata": metadata or {},
            "lineage": list(lineage or []),
        }
        entries = self._load_entries()
        existing = [item for item in entries if item.get("name") != name]
        existing.append(entry)
        self._write_entries(existing)
        return CatalogEntry(
            name=name,
            path=artifact_path,
            checksum=checksum,
            created_at=datetime.fromisoformat(entry["created_at"]),
            metadata=entry["metadata"],
            lineage=list(entry["lineage"]),
        )

    def find(self, name: str) -> Optional[CatalogEntry]:
        for raw in self._load_entries():
            if raw.get("name") == name:
                return CatalogEntry(
                    name=name,
                    path=Path(raw["path"]),
                    checksum=str(raw["checksum"]),
                    created_at=datetime.fromisoformat(raw["created_at"]),
                    metadata=dict(raw.get("metadata", {})),
                    lineage=list(raw.get("lineage", [])),
                )
        return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()
