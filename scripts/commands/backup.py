"""CLI command orchestrating pg_dump backups and archival cleanup."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Sequence

from core.maintenance import BackupConfig, DatabaseBackupManager
from scripts.commands.base import CommandError, register, run_subprocess
from scripts.runtime import EXIT_CODES

LOGGER = logging.getLogger(__name__)


def build_parser(subparsers: argparse._SubParsersAction[object]) -> None:
    parser = subparsers.add_parser(
        "backup",
        help="Execute database backups and manage archival retention.",
    )
    parser.set_defaults(command="backup", handler=handle)
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="PostgreSQL connection URL. Defaults to the DATABASE_URL environment variable.",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=Path("/var/backups"),
        help="Directory where pg_dump artefacts will be stored.",
    )
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=None,
        help="Optional directory for archived backups. Defaults to <backup-dir>/archive.",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=35,
        help="Number of days to retain archived backups before pruning.",
    )
    parser.add_argument(
        "--archive-after-days",
        type=int,
        default=14,
        help="Age in days after which backups are moved into the archive directory.",
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default="timescale",
        help="Filename prefix applied to generated backups.",
    )
    parser.add_argument(
        "--pg-dump",
        type=str,
        default="pg_dump",
        help="pg_dump binary to invoke (defaults to pg_dump in PATH).",
    )
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Additional environment variables passed to pg_dump.",
    )
    parser.add_argument(
        "--no-compress",
        action="store_true",
        help="Disable pg_dump compression (useful when external compression is preferred).",
    )
    parser.add_argument(
        "--mode",
        choices=("full", "incremental"),
        default="full",
        help="Backup mode label used when naming artefacts.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Construct backup paths without executing pg_dump or modifying files.",
    )


def _parse_env_overrides(pairs: Sequence[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for item in pairs:
        if "=" not in item:
            raise CommandError(
                f"Invalid environment override '{item}'. Expected KEY=VALUE"
            )
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise CommandError(f"Environment override '{item}' is missing a key")
        overrides[key] = value
    return overrides


@register("backup")
def handle(args: argparse.Namespace) -> int:
    database_url = args.database_url or os.getenv("DATABASE_URL")
    if not database_url:
        raise CommandError(
            "--database-url must be provided or DATABASE_URL must be set"
        )

    env = _parse_env_overrides(getattr(args, "env", []))
    config = BackupConfig(
        database_url=database_url,
        backup_dir=args.backup_dir,
        archive_dir=args.archive_dir,
        retention_days=int(args.retention_days),
        archive_after_days=int(args.archive_after_days),
        file_prefix=args.prefix,
        pg_dump_binary=args.pg_dump,
        env=env or None,
        compress=not args.no_compress,
    )
    manager = DatabaseBackupManager(
        config=config,
        command_runner=lambda command, env=None: run_subprocess(command, env=env),
        dry_run=bool(args.dry_run),
    )

    result = manager.run_backup_cycle(mode=args.mode)

    LOGGER.info(
        "Backup completed",
        extra={
            "backup_path": str(result.backup_path),
            "archived": [str(path) for path in result.archived],
            "pruned": [str(path) for path in result.pruned],
        },
    )

    return EXIT_CODES["success"]


__all__ = ["build_parser", "handle"]
