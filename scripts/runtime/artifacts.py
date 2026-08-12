# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Helpers for managing script output directories and artefacts."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ARTIFACT_ROOT = Path("reports") / "scripts"


@dataclass(slots=True)
class ArtifactManager:
    """Create timestamped directories for script outputs.

    The helper enforces the convention ``reports/scripts/<script>/<ts>`` so that
    artefacts are easy to locate regardless of where scripts are executed.
    """

    script_name: str
    root: Path = DEFAULT_ARTIFACT_ROOT
    timestamp: datetime | None = None

    def __post_init__(self) -> None:
        if not self.script_name:
            raise ValueError("script_name must be a non-empty string")
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)

    @property
    def directory(self) -> Path:
        ts = self.timestamp or datetime.now(timezone.utc)
        safe_ts = ts.strftime("%Y%m%dT%H%M%SZ")
        path = self.root / self.script_name / safe_ts
        path.mkdir(parents=True, exist_ok=True)
        return path

    def path_for(self, relative: str | Path) -> Path:
        """Return an absolute path inside the artefact directory."""

        relative_path = Path(relative)
        if relative_path.is_absolute():
            raise ValueError("relative path must not be absolute")
        destination = self.directory / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        return destination


def create_artifact_manager(script_name: str, *, root: Path | None = None) -> ArtifactManager:
    """Factory that selects a root directory when one is not supplied."""

    return ArtifactManager(script_name=script_name, root=root or DEFAULT_ARTIFACT_ROOT)
