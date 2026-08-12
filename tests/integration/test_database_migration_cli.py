# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Integration tests for the ``scripts.db_migrate`` CLI wrapper."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner
from sqlalchemy import create_engine, inspect

from scripts.db_migrate import cli


def _sqlite_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path}"  # pragma: no cover - deterministic helper


def test_cli_upgrade_and_downgrade(tmp_path: Path) -> None:
    """The CLI should apply and rollback migrations against SQLite for smoke testing."""

    db_path = tmp_path / "cli.sqlite"
    runner = CliRunner()
    url = _sqlite_url(db_path)

    result = runner.invoke(cli, ["upgrade", "head", "--database-url", url])
    assert result.exit_code == 0, result.output

    engine = create_engine(url, future=True)
    try:
        assert inspect(engine).has_table("kill_switch_state")

        history_result = runner.invoke(cli, ["history", "--database-url", url])
        assert history_result.exit_code == 0, history_result.output

        current_result = runner.invoke(cli, ["current", "--database-url", url])
        assert current_result.exit_code == 0, current_result.output

        downgrade_result = runner.invoke(cli, ["downgrade", "base", "--database-url", url])
        assert downgrade_result.exit_code == 0, downgrade_result.output

        assert inspect(engine).has_table("kill_switch_state") is False
    finally:
        engine.dispose()
