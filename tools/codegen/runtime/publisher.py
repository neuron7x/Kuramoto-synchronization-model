from __future__ import annotations

"""Artifact publication helpers."""

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .fingerprint import stable_hash


@dataclass(slots=True)
class Artifact:
    name: str
    path: Path


class ArtifactPublisher:
    """Publish generated artifacts into a versioned directory."""

    def __init__(self, root: Path, version: str) -> None:
        self.root = root
        self.version = version
        self.root.mkdir(parents=True, exist_ok=True)

    def publish(self, task_name: str, artifacts: Iterable[Artifact]) -> Path:
        target_dir = self.root / task_name / self.version
        target_dir.mkdir(parents=True, exist_ok=True)
        manifest_entries: list[str] = []
        for artifact in artifacts:
            destination = target_dir / artifact.path.name
            shutil.copy2(artifact.path, destination)
            manifest_entries.append(f"{artifact.name}:{destination.name}")
        manifest_entries.sort()
        manifest_hash = stable_hash(manifest_entries)
        (target_dir / "MANIFEST.sha256").write_text(manifest_hash + "\n", encoding="utf-8")
        return target_dir
