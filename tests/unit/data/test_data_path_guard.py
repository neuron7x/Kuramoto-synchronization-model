# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import os
from pathlib import Path

import pytest

from core.data.path_guard import DataPathGuard


@pytest.fixture
def temp_files(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    target = data_dir / "payload.csv"
    target.write_text("content", encoding="utf-8")
    return data_dir, target


def test_guard_uses_environment_roots(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TRADEPULSE_DATA_ROOTS", os.pathsep.join([str(tmp_path)]))
    guard = DataPathGuard()
    assert tmp_path in guard.allowed_roots


def test_guard_rejects_missing_root(tmp_path: Path) -> None:
    missing = tmp_path / "absent"
    with pytest.raises(FileNotFoundError):
        DataPathGuard([missing])


def test_guard_rejects_non_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "file.txt"
    file_path.write_text("payload", encoding="utf-8")
    with pytest.raises(NotADirectoryError):
        DataPathGuard([file_path])


def test_guard_rejects_invalid_max_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TRADEPULSE_DATA_ROOTS", str(tmp_path))
    monkeypatch.setenv("TRADEPULSE_MAX_CSV_BYTES", "invalid")
    with pytest.raises(ValueError, match="TRADEPULSE_MAX_CSV_BYTES"):
        DataPathGuard()


def test_guard_blocks_symlink(temp_files) -> None:
    data_dir, target = temp_files
    guard = DataPathGuard([data_dir])
    link = data_dir / "link.csv"
    link.symlink_to(target)
    with pytest.raises(PermissionError):
        guard.resolve(link)


def test_guard_blocks_outside_roots(temp_files, tmp_path: Path) -> None:
    data_dir, _ = temp_files
    guard = DataPathGuard([data_dir])
    outsider = tmp_path / "other.csv"
    outsider.write_text("data", encoding="utf-8")
    with pytest.raises(PermissionError):
        guard.resolve(outsider)


def test_guard_enforces_file_size(temp_files) -> None:
    data_dir, target = temp_files
    guard = DataPathGuard([data_dir], max_bytes=1)
    with pytest.raises(ValueError):
        guard.resolve(target)


def test_guard_accepts_valid_file(temp_files) -> None:
    data_dir, target = temp_files
    guard = DataPathGuard([data_dir], max_bytes=1024)
    resolved = guard.resolve(target)
    assert resolved == target.resolve()


def test_guard_follows_symlinks_when_enabled(temp_files) -> None:
    data_dir, target = temp_files
    guard = DataPathGuard([data_dir], follow_symlinks=True)
    link = data_dir / "link.csv"
    link.symlink_to(target)
    resolved = guard.resolve(link)
    assert resolved == target.resolve()


def test_guard_rejects_non_positive_max_bytes(temp_files) -> None:
    data_dir, _ = temp_files
    with pytest.raises(ValueError):
        DataPathGuard([data_dir], max_bytes=0)


def test_guard_resolve_missing_file(temp_files) -> None:
    data_dir, _ = temp_files
    guard = DataPathGuard([data_dir])
    with pytest.raises(FileNotFoundError):
        guard.resolve(data_dir / "missing.csv")


def test_guard_rejects_directory_target(temp_files) -> None:
    data_dir, _ = temp_files
    guard = DataPathGuard([data_dir])
    directory = data_dir / "subdir"
    directory.mkdir()
    with pytest.raises(IsADirectoryError):
        guard.resolve(directory)
