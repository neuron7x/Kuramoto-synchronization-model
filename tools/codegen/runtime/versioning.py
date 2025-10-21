from __future__ import annotations

"""Version resolution helpers for artifacts."""

from pathlib import Path


class VersionManager:
    """Resolve versions from files or explicit overrides."""

    def __init__(self, version_file: Path) -> None:
        self.version_file = version_file

    def resolve(self) -> str:
        if not self.version_file.exists():
            raise FileNotFoundError(f"Version file not found: {self.version_file}")
        version = self.version_file.read_text(encoding="utf-8").strip()
        if not version:
            raise ValueError("Version file is empty")
        return version
