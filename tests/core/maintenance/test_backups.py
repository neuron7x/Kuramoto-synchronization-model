from __future__ import annotations

import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

import pytest

from core.maintenance.backups import BackupConfig, DatabaseBackupManager


class _Recorder:
    def __init__(self) -> None:
        self.commands: list[Sequence[str]] = []
        self.env: list[dict[str, str]] = []

    def __call__(self, command: Sequence[str], env: dict[str, str] | None = None):
        self.commands.append(list(command))
        self.env.append(dict(env or {}))
        class _Result:
            returncode = 0

        return _Result()


def _fixed_clock() -> datetime:
    return datetime(2024, 5, 18, 12, 30, tzinfo=timezone.utc)


def test_create_backup_invokes_pg_dump(tmp_path: Path) -> None:
    recorder = _Recorder()
    config = BackupConfig(
        database_url="postgresql://user:secret@db:5432/tradepulse",
        backup_dir=tmp_path,
        archive_after_days=7,
        retention_days=30,
    )
    manager = DatabaseBackupManager(
        config=config,
        command_runner=recorder,
        clock=_fixed_clock,
    )

    path = manager.run_backup_cycle().backup_path

    assert path.name == "timescale_full_20240518T123000Z.dump"
    assert path.parent == tmp_path
    assert recorder.commands, "expected pg_dump command to be executed"
    command = recorder.commands[-1]
    assert command[0].endswith("pg_dump")
    assert "--format=custom" in command
    assert command[-1] == config.database_url


def test_archive_old_backups_moves_to_archive(tmp_path: Path) -> None:
    old_backup = tmp_path / "timescale_full_20240101T000000Z.dump"
    old_backup.write_text("demo", encoding="utf-8")
    cutoff = datetime.now(timezone.utc) - timedelta(days=10)
    atime = cutoff - timedelta(days=1)
    mtime = cutoff - timedelta(days=1)
    ts = mtime.timestamp()
    at = atime.timestamp()
    import os

    os.utime(old_backup, times=(at, ts))

    config = BackupConfig(
        database_url="postgresql://user:secret@db/tradepulse",
        backup_dir=tmp_path,
        archive_after_days=7,
        retention_days=30,
    )
    manager = DatabaseBackupManager(
        config=config,
        dry_run=False,
    )

    archived = manager._archive_stale_backups()

    assert not old_backup.exists()
    assert archived, "expected archive to be generated"
    archive_path = archived[0]
    assert archive_path.parent == config.archive_dir
    with tarfile.open(archive_path, "r:gz") as tar:
        names = tar.getnames()
        assert old_backup.name in names


def test_prune_archives_removes_expired(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    archive = archive_dir / "timescale_full_20230101T000000Z.dump.tar.gz"
    archive.write_bytes(b"demo")
    past = datetime.now(timezone.utc) - timedelta(days=40)
    ts = past.timestamp()
    import os

    os.utime(archive, times=(ts, ts))

    config = BackupConfig(
        database_url="postgresql://user@db/tradepulse",
        backup_dir=tmp_path,
        archive_after_days=7,
        retention_days=30,
    )
    manager = DatabaseBackupManager(config=config)

    removed = manager._prune_archives()

    assert removed == [archive]
    assert not archive.exists()


def test_invalid_config_raises() -> None:
    with pytest.raises(ValueError):
        BackupConfig(
            database_url="postgresql://user@db/tradepulse",
            backup_dir=Path("/tmp"),
            archive_after_days=10,
            retention_days=5,
        )
