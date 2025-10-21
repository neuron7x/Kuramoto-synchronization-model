from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa

from tools.migrations import MigrationManager, MigrationSettings, SchemaExpectations
from tools.migrations.config import IndexExpectation, TableExpectation
from tools.migrations.validators import ValidationCheck, ValidationRule, ValidationSuite


def test_migration_settings_load(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        """
        alembic_ini: alembic.ini
        database_url: sqlite:///example.db
        artifacts:
          directory: reports/migrations
        lock_timeout_seconds: null
        validations:
          files: []
        backup:
          enabled: true
          directory: backups
          retain_last: 2
        alerts:
          enabled: true
          webhook_url: https://hooks.example.local/migrations
          channel: '#db'
        """,
        encoding="utf-8",
    )

    settings = MigrationSettings.load(config)
    assert settings.database_url == "sqlite:///example.db"
    assert settings.backup.enabled is True
    assert settings.alerting.channel == "#db"
    assert settings.lock_timeout_seconds is None


def test_validation_suite_success() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    suite = ValidationSuite(
        rules=(
            ValidationRule(
                name="one",
                query="SELECT 1 AS ok",
                params={},
                checks=(
                    ValidationCheck(kind="scalar_equals", equals=1, column="ok"),
                ),
            ),
        )
    )
    results = suite.ensure_success(engine)
    assert all(result.succeeded for result in results)


@pytest.mark.parametrize("unique", [True, False])
def test_schema_check_reports_index(tmp_path: Path, unique: bool) -> None:
    db_path = tmp_path / "db.sqlite"
    settings = MigrationSettings(
        alembic_ini=Path("alembic.ini"),
        database_url=f"sqlite:///{db_path}",
        artifacts_dir=tmp_path / "artifacts",
        schema=SchemaExpectations(
            tables={
                "accounts": TableExpectation(
                    indexes=(IndexExpectation(name="ix_accounts_symbol", columns=("symbol",), unique=unique),),
                    triggers=(),
                )
            }
        ),
    )
    manager = MigrationManager(settings)
    metadata = sa.MetaData()
    table = sa.Table(
        "accounts",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("symbol", sa.String(12), index=True, unique=unique),
    )
    metadata.create_all(manager.engine)

    report = manager.check_schema()
    assert "accounts" in report["tables"]
    index_report = report["tables"]["accounts"]["indexes"]["ix_accounts_symbol"]
    assert index_report["exists"] is True


def test_timeboxed_executes_callable(tmp_path: Path) -> None:
    settings = MigrationSettings(
        alembic_ini=Path("alembic.ini"),
        database_url="sqlite:///:memory:",
        artifacts_dir=tmp_path / "artifacts",
    )
    manager = MigrationManager(settings)

    result = manager._timeboxed(lambda x: x + 1, 2, 3)
    assert result == 4
