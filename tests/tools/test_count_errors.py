# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import pytest

from tools.count_errors import FileErrorCount, scan_repository


@pytest.fixture()
def repo_with_symlinks(tmp_path: Path) -> Path:
    """Create a repository fixture containing symlink loops and externals."""

    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    (repo_root / "errors.log").write_text("ERROR first\nINFO ok\nERROR second\n", encoding="utf-8")

    # Create a directory that points back to the repository root.  The scanner
    # must not follow this because it would recurse indefinitely.
    (repo_root / "loop").symlink_to(repo_root)

    # Create an external directory and link it from inside the repository to
    # ensure we do not traverse outside of *repo_root*.
    external_dir = tmp_path / "external"
    external_dir.mkdir()
    (external_dir / "external.log").write_text("ERROR external\n", encoding="utf-8")
    (repo_root / "external").symlink_to(external_dir)

    return repo_root


def test_scan_repository_skips_symlink_loops(repo_with_symlinks: Path) -> None:
    entries = scan_repository(repo_with_symlinks)
    resolved_root = repo_with_symlinks.resolve()

    # Ensure we collected the error from the file that resides inside the root.
    assert FileErrorCount(path=(resolved_root / "errors.log"), count=2) in entries

    # Confirm the traversal did not descend into the symlink loop or the
    # external directory.  All reported files must live underneath the root.
    for entry in entries:
        assert entry.path.is_relative_to(resolved_root)
        assert entry.path.name != "external.log"


def test_scan_repository_handles_absence_of_errors(repo_with_symlinks: Path) -> None:
    # Remove the only file containing the error token and ensure the traversal
    # still completes without picking up the external symlink target.
    (repo_with_symlinks / "errors.log").unlink()

    entries = scan_repository(repo_with_symlinks)
    assert entries == []
