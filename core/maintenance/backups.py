# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Helpers for database backups and archival retention policies."""

from __future__ import annotations

import os
import subprocess
import tarfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

CommandRunner = Callable[
    [Sequence[str], Mapping[str, str] | None], subprocess.CompletedProcess[int]
]
Clock = Callable[[], datetime]


def _default_runner(
    command: Sequence[str], env: Mapping[str, str] | None = None
) -> subprocess.CompletedProcess[bytes]:
    """Execute *command* returning the completed process.

    The default implementation simply proxies to :func:`subprocess.run` while
    honouring :class:`CommandRunner` semantics. The caller is responsible for
    handling ``CompletedProcess.returncode`` when ``check`` is disabled.
    """

    return subprocess.run(list(command), env=None if env is None else dict(env), check=True)


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class BackupConfig:
    """Configuration describing how database backups should be produced."""

    database_url: str
    backup_dir: Path
    archive_dir: Path | None = None
    file_prefix: str = "timescale"
    retention_days: int = 35
    archive_after_days: int = 14
    pg_dump_binary: str = "pg_dump"
    env: Mapping[str, str] | None = None
    compress: bool = True

    def __post_init__(self) -> None:
        if not self.database_url:
            raise ValueError("database_url must be provided")
        if not self.file_prefix:
            raise ValueError("file_prefix must be a non-empty string")
        if self.retention_days <= 0:
            raise ValueError("retention_days must be positive")
        if self.archive_after_days < 0:
            raise ValueError("archive_after_days must be non-negative")
        if self.archive_after_days > self.retention_days:
            raise ValueError("archive_after_days cannot exceed retention_days")
        self.backup_dir = Path(self.backup_dir)
        self.archive_dir = (
            Path(self.archive_dir) if self.archive_dir else self.backup_dir / "archive"
        )
        self.pg_dump_binary = self.pg_dump_binary or "pg_dump"


@dataclass(slots=True)
class BackupResult:
    """Summary of a single backup cycle including archival actions."""

    backup_path: Path
    archived: tuple[Path, ...]
    pruned: tuple[Path, ...]


@dataclass(slots=True)
class DatabaseBackupManager:
    """Coordinate database backups and lifecycle management."""

    config: BackupConfig
    command_runner: CommandRunner = _default_runner
    clock: Clock = _default_clock
    dry_run: bool = False
    _backup_dir: Path = field(init=False)
    _archive_dir: Path = field(init=False)
    _env: dict[str, str] = field(init=False)

    def __post_init__(self) -> None:
        self._backup_dir = self.config.backup_dir
        self._archive_dir = self.config.archive_dir or (self._backup_dir / "archive")
        if not self._backup_dir.is_absolute():
            self._backup_dir = self._backup_dir.resolve()
        if not self._archive_dir.is_absolute():
            self._archive_dir = self._archive_dir.resolve()
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        self._archive_dir.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        if self.config.env:
            env.update(self.config.env)
        self._env = env

    # ------------------------------------------------------------------
    # Public API
    def run_backup_cycle(self, *, mode: str = "full") -> BackupResult:
        """Execute a backup, archive stale artefacts, and prune expired ones."""

        backup_path = self._create_backup(mode=mode)
        archived = tuple(self._archive_stale_backups())
        pruned = tuple(self._prune_archives())
        return BackupResult(backup_path=backup_path, archived=archived, pruned=pruned)

    # ------------------------------------------------------------------
    # Internal helpers
    def _create_backup(self, *, mode: str = "full") -> Path:
        timestamp = self.clock().strftime("%Y%m%dT%H%M%SZ")
        suffix = "incremental" if mode.lower() == "incremental" else "full"
        extension = ".dump" if self.config.compress else ".sql"
        filename = f"{self.config.file_prefix}_{suffix}_{timestamp}{extension}"
        target = self._backup_dir / filename

        if self.dry_run:
            return target

        command: list[str] = [
            self.config.pg_dump_binary,
            "--no-owner",
            "--clean",
            f"--file={str(target)}",
        ]
        if self.config.compress:
            command.extend(["--format=custom", "--compress=9"])
        else:
            command.append("--format=plain")
        command.append(self.config.database_url)

        self.command_runner(command, self._env)
        return target

    def _archive_stale_backups(self) -> list[Path]:
        if self.config.archive_after_days == 0:
            return []

        cutoff = self.clock() - timedelta(days=self.config.archive_after_days)
        archived: list[Path] = []
        for candidate in sorted(self._backup_dir.glob(f"{self.config.file_prefix}_*")):
            if not candidate.is_file():
                continue
            if candidate.parent == self._archive_dir:
                continue
            if candidate.suffixes and candidate.suffixes[-2:] == [".tar", ".gz"]:
                continue
            modified = datetime.fromtimestamp(candidate.stat().st_mtime, tz=timezone.utc)
            if modified > cutoff:
                continue
            archive_path = self._archive_dir / f"{candidate.name}.tar.gz"
            if not self.dry_run:
                with tarfile.open(archive_path, "w:gz") as tar:
                    tar.add(candidate, arcname=candidate.name)
                candidate.unlink(missing_ok=True)
            archived.append(archive_path)
        return archived

    def _prune_archives(self) -> list[Path]:
        cutoff = self.clock() - timedelta(days=self.config.retention_days)
        removed: list[Path] = []
        for candidate in sorted(self._archive_dir.glob("*.tar.gz")):
            if not candidate.is_file():
                continue
            modified = datetime.fromtimestamp(candidate.stat().st_mtime, tz=timezone.utc)
            if modified > cutoff:
                continue
            if not self.dry_run:
                candidate.unlink(missing_ok=True)
            removed.append(candidate)
        return removed


__all__ = ["BackupConfig", "BackupResult", "DatabaseBackupManager"]
