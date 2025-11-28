# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unit tests for core/maintenance/backups.py."""

from __future__ import annotations

import os
import subprocess
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Sequence
from unittest.mock import MagicMock

import pytest

from core.maintenance.backups import (
    BackupConfig,
    BackupResult,
    DatabaseBackupManager,
    _default_clock,
    _default_runner,
)


class TestDefaultRunner:
    """Tests for _default_runner function."""

    def test_default_runner_executes_command(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_run = MagicMock(return_value=subprocess.CompletedProcess([], 0))
        monkeypatch.setattr(subprocess, "run", mock_run)

        result = _default_runner(["echo", "test"], None)

        assert result.returncode == 0
        mock_run.assert_called_once_with(["echo", "test"], env=None, check=True)

    def test_default_runner_with_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_run = MagicMock(return_value=subprocess.CompletedProcess([], 0))
        monkeypatch.setattr(subprocess, "run", mock_run)
        env = {"FOO": "bar"}

        result = _default_runner(["echo", "test"], env)

        assert result.returncode == 0
        mock_run.assert_called_once_with(
            ["echo", "test"], env={"FOO": "bar"}, check=True
        )


class TestDefaultClock:
    """Tests for _default_clock function."""

    def test_default_clock_returns_utc_datetime(self) -> None:
        result = _default_clock()

        assert isinstance(result, datetime)
        assert result.tzinfo == timezone.utc


class TestBackupConfig:
    """Tests for BackupConfig dataclass."""

    def test_valid_config(self, tmp_path: Path) -> None:
        backup_dir = tmp_path / "backups"
        config = BackupConfig(
            database_url="postgres://localhost:5432/test",
            backup_dir=backup_dir,
        )

        assert config.database_url == "postgres://localhost:5432/test"
        assert config.backup_dir == backup_dir
        assert config.file_prefix == "timescale"
        assert config.retention_days == 35
        assert config.archive_after_days == 14
        assert config.compress is True

    def test_empty_database_url_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="database_url must be provided"):
            BackupConfig(database_url="", backup_dir=tmp_path)

    def test_empty_file_prefix_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="file_prefix must be a non-empty string"):
            BackupConfig(
                database_url="postgres://localhost:5432/test",
                backup_dir=tmp_path,
                file_prefix="",
            )

    def test_invalid_retention_days_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="retention_days must be positive"):
            BackupConfig(
                database_url="postgres://localhost:5432/test",
                backup_dir=tmp_path,
                retention_days=0,
            )

    def test_negative_archive_after_days_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="archive_after_days must be non-negative"):
            BackupConfig(
                database_url="postgres://localhost:5432/test",
                backup_dir=tmp_path,
                archive_after_days=-1,
            )

    def test_archive_after_exceeds_retention_raises(self, tmp_path: Path) -> None:
        with pytest.raises(
            ValueError, match="archive_after_days cannot exceed retention_days"
        ):
            BackupConfig(
                database_url="postgres://localhost:5432/test",
                backup_dir=tmp_path,
                retention_days=7,
                archive_after_days=14,
            )

    def test_default_archive_dir(self, tmp_path: Path) -> None:
        backup_dir = tmp_path / "backups"
        config = BackupConfig(
            database_url="postgres://localhost:5432/test",
            backup_dir=backup_dir,
        )

        assert config.archive_dir == backup_dir / "archive"

    def test_custom_archive_dir(self, tmp_path: Path) -> None:
        backup_dir = tmp_path / "backups"
        archive_dir = tmp_path / "archive"
        config = BackupConfig(
            database_url="postgres://localhost:5432/test",
            backup_dir=backup_dir,
            archive_dir=archive_dir,
        )

        assert config.archive_dir == archive_dir


class TestBackupResult:
    """Tests for BackupResult dataclass."""

    def test_backup_result_structure(self, tmp_path: Path) -> None:
        backup_path = tmp_path / "backup.dump"
        archived = (tmp_path / "old.tar.gz",)
        pruned = (tmp_path / "expired.tar.gz",)

        result = BackupResult(backup_path=backup_path, archived=archived, pruned=pruned)

        assert result.backup_path == backup_path
        assert result.archived == archived
        assert result.pruned == pruned


class TestDatabaseBackupManager:
    """Tests for DatabaseBackupManager class."""

    @pytest.fixture
    def mock_runner(self) -> MagicMock:
        """Mock command runner."""
        return MagicMock(return_value=subprocess.CompletedProcess([], 0))

    @pytest.fixture
    def fixed_clock(self) -> datetime:
        """Fixed datetime for testing."""
        return datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    @pytest.fixture
    def manager(
        self, tmp_path: Path, mock_runner: MagicMock, fixed_clock: datetime
    ) -> DatabaseBackupManager:
        """Create a backup manager for testing."""
        backup_dir = tmp_path / "backups"
        config = BackupConfig(
            database_url="postgres://localhost:5432/test",
            backup_dir=backup_dir,
            archive_after_days=7,
            retention_days=14,
        )
        return DatabaseBackupManager(
            config=config,
            command_runner=mock_runner,
            clock=lambda: fixed_clock,
        )

    def test_manager_creates_directories(self, tmp_path: Path) -> None:
        backup_dir = tmp_path / "backups"
        config = BackupConfig(
            database_url="postgres://localhost:5432/test",
            backup_dir=backup_dir,
        )

        _manager = DatabaseBackupManager(config=config, dry_run=True)  # noqa: F841
        del _manager  # Ensure side-effects are tested

        assert backup_dir.exists()
        assert (backup_dir / "archive").exists()

    def test_create_backup_dry_run(self, manager: DatabaseBackupManager) -> None:
        manager.dry_run = True

        result = manager.run_backup_cycle()

        assert result.backup_path.name.startswith("timescale_full_")
        assert result.backup_path.suffix == ".dump"
        assert result.archived == ()
        assert result.pruned == ()

    def test_create_backup_executes_pg_dump(
        self, manager: DatabaseBackupManager, mock_runner: MagicMock
    ) -> None:
        _result = manager.run_backup_cycle()  # noqa: F841
        del _result  # Result verified through mock

        assert mock_runner.called
        call_args = mock_runner.call_args[0][0]
        assert "pg_dump" in call_args[0]
        assert "--no-owner" in call_args
        assert "--clean" in call_args
        assert "--compress=9" in call_args

    def test_create_backup_incremental_mode(
        self, manager: DatabaseBackupManager, mock_runner: MagicMock
    ) -> None:
        result = manager.run_backup_cycle(mode="incremental")

        assert "incremental" in result.backup_path.name

    def test_create_backup_uncompressed(
        self, tmp_path: Path, mock_runner: MagicMock
    ) -> None:
        backup_dir = tmp_path / "backups"
        config = BackupConfig(
            database_url="postgres://localhost:5432/test",
            backup_dir=backup_dir,
            compress=False,
        )
        manager = DatabaseBackupManager(config=config, command_runner=mock_runner)

        result = manager.run_backup_cycle()

        call_args = mock_runner.call_args[0][0]
        assert "--format=plain" in call_args
        assert result.backup_path.suffix == ".sql"

    def test_archive_stale_backups_zero_days(
        self, tmp_path: Path, mock_runner: MagicMock, fixed_clock: datetime
    ) -> None:
        backup_dir = tmp_path / "backups"
        config = BackupConfig(
            database_url="postgres://localhost:5432/test",
            backup_dir=backup_dir,
            archive_after_days=0,
        )
        manager = DatabaseBackupManager(
            config=config,
            command_runner=mock_runner,
            clock=lambda: fixed_clock,
        )

        result = manager.run_backup_cycle()

        assert result.archived == ()

    def test_archive_stale_backups(
        self, tmp_path: Path, mock_runner: MagicMock
    ) -> None:
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Create an old backup file
        old_backup = backup_dir / "timescale_full_old.dump"
        old_backup.write_bytes(b"test data")
        # Set mtime to 10 days ago
        old_mtime = datetime.now(timezone.utc) - timedelta(days=10)
        os.utime(old_backup, (old_mtime.timestamp(), old_mtime.timestamp()))

        config = BackupConfig(
            database_url="postgres://localhost:5432/test",
            backup_dir=backup_dir,
            archive_after_days=7,
        )
        manager = DatabaseBackupManager(config=config, command_runner=mock_runner)

        result = manager.run_backup_cycle()

        assert len(result.archived) == 1
        assert not old_backup.exists()

    def test_prune_old_archives(self, tmp_path: Path, mock_runner: MagicMock) -> None:
        backup_dir = tmp_path / "backups"
        archive_dir = backup_dir / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)

        # Create an expired archive
        old_archive = archive_dir / "timescale_full_old.dump.tar.gz"
        with tarfile.open(old_archive, "w:gz"):
            pass  # Create empty archive
        # Set mtime to 40 days ago
        old_mtime = datetime.now(timezone.utc) - timedelta(days=40)
        os.utime(old_archive, (old_mtime.timestamp(), old_mtime.timestamp()))

        config = BackupConfig(
            database_url="postgres://localhost:5432/test",
            backup_dir=backup_dir,
            retention_days=35,
        )
        manager = DatabaseBackupManager(config=config, command_runner=mock_runner)

        result = manager.run_backup_cycle()

        assert len(result.pruned) == 1
        assert not old_archive.exists()

    def test_prune_archives_dry_run(
        self, tmp_path: Path, mock_runner: MagicMock
    ) -> None:
        backup_dir = tmp_path / "backups"
        archive_dir = backup_dir / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)

        # Create an expired archive
        old_archive = archive_dir / "timescale_full_old.dump.tar.gz"
        with tarfile.open(old_archive, "w:gz"):
            pass  # Create empty archive
        # Set mtime to 40 days ago
        old_mtime = datetime.now(timezone.utc) - timedelta(days=40)
        os.utime(old_archive, (old_mtime.timestamp(), old_mtime.timestamp()))

        config = BackupConfig(
            database_url="postgres://localhost:5432/test",
            backup_dir=backup_dir,
            retention_days=35,
        )
        manager = DatabaseBackupManager(
            config=config, command_runner=mock_runner, dry_run=True
        )

        result = manager.run_backup_cycle()

        assert len(result.pruned) == 1
        # In dry run, archive should still exist
        assert old_archive.exists()

    def test_manager_with_custom_env(
        self, tmp_path: Path, mock_runner: MagicMock
    ) -> None:
        backup_dir = tmp_path / "backups"
        config = BackupConfig(
            database_url="postgres://localhost:5432/test",
            backup_dir=backup_dir,
            env={"PGPASSWORD": "secret"},
        )
        manager = DatabaseBackupManager(config=config, command_runner=mock_runner)

        manager.run_backup_cycle()

        _, env = mock_runner.call_args[0]
        assert "PGPASSWORD" in env
        assert env["PGPASSWORD"] == "secret"


class TestBackupIntegration:
    """Integration-style tests for full backup workflow."""

    def test_full_backup_cycle_e2e(self, tmp_path: Path) -> None:
        """Test complete backup cycle with mocked pg_dump."""
        backup_dir = tmp_path / "backups"
        executed_commands: list[tuple[list[str], dict]] = []

        def track_runner(
            command: Sequence[str], env: Mapping[str, str] | None = None
        ) -> subprocess.CompletedProcess[int]:
            executed_commands.append((list(command), dict(env) if env else {}))
            # Simulate successful pg_dump by creating the file
            for arg in command:
                if arg.startswith("--file="):
                    path = Path(arg.split("=")[1])
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"backup data")
            return subprocess.CompletedProcess([], 0)

        config = BackupConfig(
            database_url="postgres://localhost:5432/test",
            backup_dir=backup_dir,
            retention_days=14,
            archive_after_days=7,
        )
        manager = DatabaseBackupManager(config=config, command_runner=track_runner)

        result = manager.run_backup_cycle()

        assert result.backup_path.exists()
        assert len(executed_commands) == 1
        assert result.archived == ()
        assert result.pruned == ()
