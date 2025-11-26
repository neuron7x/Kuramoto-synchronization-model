"""Minimal artifact versioning helpers for the CLI."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional

from core.config.cli_models import VersioningConfig


class VersioningError(RuntimeError):
    """Raised when versioning operations cannot be completed."""


class DataVersionManager:
    """Persist lightweight metadata about produced artifacts."""

    def __init__(self, config: VersioningConfig) -> None:
        self.config = config

    def snapshot(
        self, artifact_path: Path, metadata: Optional[Dict[str, object]] = None
    ) -> Dict[str, object]:
        artifact_path = Path(artifact_path)
        resolved_artifact = artifact_path.resolve()
        info: Dict[str, object] = {
            "backend": self.config.backend,
            "artifact": str(resolved_artifact),
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "metadata": metadata or {},
        }

        checksum = self._compute_checksum(resolved_artifact)
        if checksum is not None:
            info["checksum"] = checksum

        if self.config.message:
            info["message"] = self.config.message

        repo_root = None
        if self.config.backend != "none":
            repo_root = self._resolve_repo_root()
            info["repo_path"] = str(repo_root)
            relative = self._relative_to_repo(resolved_artifact, repo_root)
            if relative is not None:
                info["artifact_relative"] = relative

            git_metadata = self._collect_git_metadata(repo_root)
            if git_metadata is not None:
                info["git"] = git_metadata

        version_path = self._resolve_version_path(artifact_path)
        version_path.parent.mkdir(parents=True, exist_ok=True)
        version_path.write_text(
            json.dumps(info, indent=2, sort_keys=True), encoding="utf-8"
        )
        return info

    # ------------------------------------------------------------------
    # Helpers
    def _resolve_repo_root(self) -> Path:
        if self.config.repo_path is None:
            raise VersioningError(
                "repo_path is required when backend is configured for versioning"
            )
        repo_root = Path(self.config.repo_path).expanduser().resolve()
        if not repo_root.exists():
            raise VersioningError(f"Repository path {repo_root!s} does not exist")
        if not repo_root.is_dir():
            raise VersioningError(f"Repository path {repo_root!s} is not a directory")
        return repo_root

    def _relative_to_repo(self, path: Path, repo_root: Path) -> str | None:
        try:
            return str(path.relative_to(repo_root))
        except ValueError:
            return None

    def _collect_git_metadata(self, repo_root: Path) -> Dict[str, object] | None:
        git_dir = repo_root / ".git"
        if not git_dir.exists():
            return None

        def _run_git(*args: str) -> str | None:
            try:
                result = subprocess.run(
                    ["git", *args],
                    cwd=repo_root,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                return None
            return result.stdout.strip()

        commit = _run_git("rev-parse", "HEAD")
        if not commit:
            return None
        branch = _run_git("rev-parse", "--abbrev-ref", "HEAD")
        status = _run_git("status", "--porcelain")
        return {
            "commit": commit,
            "branch": branch,
            "dirty": bool(status),
        }

    def _resolve_version_path(self, artifact_path: Path) -> Path:
        suffix = artifact_path.suffix or ""
        version_suffix = f"{suffix}.version.json"
        return artifact_path.with_suffix(version_suffix)

    def _compute_checksum(self, artifact: Path) -> str | None:
        if artifact.is_file():
            return self._hash_file(artifact)
        if artifact.is_dir():
            return self._hash_directory(artifact)
        return None

    def _hash_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _hash_directory(self, directory: Path) -> str:
        digest = hashlib.sha256()
        for child in self._iter_directory_files(directory):
            digest.update(child.relative_to(directory).as_posix().encode("utf-8"))
            digest.update(self._hash_file(child).encode("utf-8"))
        return digest.hexdigest()

    def _iter_directory_files(self, directory: Path) -> Iterable[Path]:
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                yield path
