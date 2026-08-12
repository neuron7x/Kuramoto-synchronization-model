# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from core.config.cli_models import VersioningConfig
from core.data.versioning import DataVersionManager, VersioningError


def _git_available() -> bool:
    return shutil.which("git") is not None


@pytest.mark.skipif(not _git_available(), reason="git binary is required for this test")
def test_snapshot_records_git_metadata(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    subprocess.run(["git", "init"], check=True, cwd=repo_root)
    subprocess.run(
        ["git", "config", "user.email", "ci@example.com"], check=True, cwd=repo_root
    )
    subprocess.run(["git", "config", "user.name", "CI Bot"], check=True, cwd=repo_root)

    artifact = repo_root / "data" / "artifact.txt"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("payload", encoding="utf-8")
    subprocess.run(["git", "add", "data/artifact.txt"], check=True, cwd=repo_root)
    subprocess.run(["git", "commit", "-m", "Add artifact"], check=True, cwd=repo_root)

    cfg = VersioningConfig(backend="dvc", repo_path=repo_root, message="sync artifacts")
    manager = DataVersionManager(cfg)
    info = manager.snapshot(artifact, metadata={"rows": 10})

    assert info["backend"] == "dvc"
    assert info["artifact_relative"] == "data/artifact.txt"
    assert info["message"] == "sync artifacts"
    assert info["checksum"]
    git_info = info.get("git")
    assert git_info is not None
    assert git_info["commit"]
    assert git_info["branch"]
    assert git_info["dirty"] is False

    version_path = artifact.with_suffix(".txt.version.json")
    on_disk = json.loads(version_path.read_text(encoding="utf-8"))
    assert on_disk == info


def test_snapshot_requires_existing_repo(tmp_path: Path) -> None:
    cfg = VersioningConfig(backend="lakefs", repo_path=tmp_path / "missing")
    manager = DataVersionManager(cfg)
    artifact = tmp_path / "artifact.csv"
    artifact.write_text("value", encoding="utf-8")

    with pytest.raises(VersioningError):
        manager.snapshot(artifact)


def test_snapshot_handles_artifacts_outside_repo(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cfg = VersioningConfig(backend="dvc", repo_path=repo_root)
    manager = DataVersionManager(cfg)

    artifact = tmp_path / "standalone.parquet"
    artifact.write_text("data", encoding="utf-8")
    info = manager.snapshot(artifact)

    assert "artifact_relative" not in info
    assert info["checksum"]


def test_snapshot_directory_computes_checksum(tmp_path: Path) -> None:
    """Test that directory artifacts compute a proper checksum."""
    cfg = VersioningConfig(backend="none")
    manager = DataVersionManager(cfg)

    artifact_dir = tmp_path / "dataset"
    artifact_dir.mkdir()
    (artifact_dir / "file1.txt").write_text("content1", encoding="utf-8")
    (artifact_dir / "file2.txt").write_text("content2", encoding="utf-8")
    (artifact_dir / "subdir").mkdir()
    (artifact_dir / "subdir" / "file3.txt").write_text("content3", encoding="utf-8")

    info = manager.snapshot(artifact_dir)

    # Checksum should be computed for directory
    assert "checksum" in info
    assert isinstance(info["checksum"], str)
    assert len(info["checksum"]) == 64  # SHA-256 hex digest

    # Checksum should be deterministic
    info2 = manager.snapshot(artifact_dir)
    assert info["checksum"] == info2["checksum"]


def test_snapshot_directory_checksum_is_content_sensitive(tmp_path: Path) -> None:
    """Test that directory checksum changes when file content changes."""
    cfg = VersioningConfig(backend="none")
    manager = DataVersionManager(cfg)

    artifact_dir = tmp_path / "dataset"
    artifact_dir.mkdir()
    (artifact_dir / "file.txt").write_text("original", encoding="utf-8")

    info1 = manager.snapshot(artifact_dir)

    # Modify file content
    (artifact_dir / "file.txt").write_text("modified", encoding="utf-8")

    info2 = manager.snapshot(artifact_dir)

    # Checksums should differ
    assert info1["checksum"] != info2["checksum"]


def test_snapshot_with_none_backend_skips_repo_resolution(tmp_path: Path) -> None:
    """Test that backend='none' skips repo resolution."""
    cfg = VersioningConfig(backend="none")
    manager = DataVersionManager(cfg)

    artifact = tmp_path / "data.csv"
    artifact.write_text("values", encoding="utf-8")

    info = manager.snapshot(artifact)

    assert info["backend"] == "none"
    assert "repo_path" not in info
    assert "git" not in info
    assert "checksum" in info
