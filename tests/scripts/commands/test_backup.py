# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from scripts.commands import backup


@pytest.fixture()
def backup_args(tmp_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        database_url="postgresql://user@db/geosync",
        backup_dir=tmp_path,
        archive_dir=None,
        retention_days=35,
        archive_after_days=14,
        prefix="timescale",
        pg_dump="pg_dump",
        env=[],
        no_compress=False,
        mode="full",
        dry_run=False,
    )


def test_parse_env_overrides() -> None:
    overrides = backup._parse_env_overrides(["PGPASSWORD=secret", "PGSSLMODE=require"])
    assert overrides == {"PGPASSWORD": "secret", "PGSSLMODE": "require"}


def test_parse_env_overrides_invalid() -> None:
    with pytest.raises(backup.CommandError):
        backup._parse_env_overrides(["INVALID"])


@patch("scripts.commands.backup.DatabaseBackupManager")
def test_handle_executes_backup(mock_manager: Mock, backup_args: argparse.Namespace) -> None:
    manager_instance = mock_manager.return_value
    manager_instance.run_backup_cycle.return_value.backup_path = Path("/backups/demo.dump")
    manager_instance.run_backup_cycle.return_value.archived = tuple()
    manager_instance.run_backup_cycle.return_value.pruned = tuple()

    exit_code = backup.handle(backup_args)

    assert exit_code == backup.EXIT_CODES["success"]
    mock_manager.assert_called_once()
    manager_instance.run_backup_cycle.assert_called_once_with(mode="full")


@patch("scripts.commands.backup.DatabaseBackupManager")
def test_handle_uses_env_when_missing_database_url(
    mock_manager: Mock, backup_args: argparse.Namespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    backup_args.database_url = None
    monkeypatch.setenv("DATABASE_URL", "postgresql://env@db/geosync")

    exit_code = backup.handle(backup_args)

    assert exit_code == backup.EXIT_CODES["success"]
    config = mock_manager.call_args.kwargs["config"]
    assert config.database_url == "postgresql://env@db/geosync"


def test_handle_missing_database_url(
    backup_args: argparse.Namespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    backup_args.database_url = None
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(backup.CommandError):
        backup.handle(backup_args)
