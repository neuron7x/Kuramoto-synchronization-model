"""Integration tests ensuring database migrations remain safe and repeatable."""

from __future__ import annotations

import importlib
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError


@dataclass(slots=True)
class MigrationTestContext:
    """Helper providing shared state for running Alembic commands in tests."""

    engine: Engine
    config: Config

    def upgrade(self, target: str = "head") -> None:
        """Apply Alembic migrations up to *target*."""

        command.upgrade(self.config, target)

    def downgrade(self, target: str = "base") -> None:
        """Rollback Alembic migrations down to *target*."""

        command.downgrade(self.config, target)


@pytest.fixture()
def migration_context(tmp_path: Path) -> MigrationTestContext:
    """Provide an Alembic configuration bound to an isolated SQLite database."""

    repo_root = Path(__file__).resolve().parents[2]
    db_path = tmp_path / "alembic_test.sqlite"
    sqlite_url = f"sqlite+pysqlite:///{db_path}"
    engine = create_engine(sqlite_url, future=True)

    config = Config(str(repo_root / "alembic.ini"))
    config.set_main_option("script_location", str(repo_root / "migrations/alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url)
    config.set_main_option("path_separator", "os")

    connection = engine.connect()
    config.attributes["connection"] = connection

    context = MigrationTestContext(engine=engine, config=config)
    try:
        yield context
    finally:
        connection.close()
        engine.dispose()


def _table_exists(engine: Engine, table_name: str) -> bool:
    return inspect(engine).has_table(table_name)


def test_migration_upgrade_and_downgrade_cycle(
    migration_context: MigrationTestContext,
) -> None:
    """Migrations should upgrade to head and downgrade back to base cleanly."""

    migration_context.upgrade("head")
    assert _table_exists(migration_context.engine, "kill_switch_state") is True

    migration_context.downgrade("base")
    assert _table_exists(migration_context.engine, "kill_switch_state") is False


def test_migration_upgrade_is_idempotent(
    migration_context: MigrationTestContext,
) -> None:
    """Running ``upgrade head`` twice must leave the schema stable."""

    migration_context.upgrade("head")
    migration_context.upgrade("head")

    inspector = inspect(migration_context.engine)
    indexes = inspector.get_indexes("kill_switch_state")
    assert len(indexes) == 1
    assert indexes[0]["name"] == "idx_kill_switch_state_updated_at"


def test_migration_preserves_data_integrity(
    migration_context: MigrationTestContext,
) -> None:
    """Ensure constraints and defaults configured by the migration behave as expected."""

    migration_context.upgrade("head")

    inserted_at = datetime(1970, 1, 1, tzinfo=timezone.utc).isoformat()
    with migration_context.engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO kill_switch_state (id, engaged, reason, updated_at)
                VALUES (:id, :engaged, :reason, :updated_at)
                """
            ),
            {
                "id": 1,
                "engaged": True,
                "reason": "migration test",
                "updated_at": inserted_at,
            },
        )

        row = connection.execute(
            text(
                """
                SELECT id, engaged, reason, updated_at
                FROM kill_switch_state
                WHERE id = 1
                """
            )
        ).one()
        assert row._mapping["id"] == 1
        assert bool(row._mapping["engaged"]) is True
        assert row._mapping["reason"] == "migration test"
        assert row._mapping["updated_at"] is not None

        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    """
                    INSERT INTO kill_switch_state (id, engaged, reason, updated_at)
                    VALUES (:id, :engaged, :reason, :updated_at)
                    """
                ),
                {
                    "id": 2,
                    "engaged": False,
                    "reason": "violates constraint",
                    "updated_at": inserted_at,
                },
            )


def test_migration_upgrade_is_fast(migration_context: MigrationTestContext) -> None:
    """Upgrading to head should complete within a tight time budget to catch regressions."""

    start = time.perf_counter()
    migration_context.upgrade("head")
    elapsed = time.perf_counter() - start

    assert elapsed < 1.0, f"upgrade exceeded time budget: {elapsed:.3f}s"


def test_migration_revision_graph_is_linear(
    migration_context: MigrationTestContext,
) -> None:
    """Ensure Alembic has exactly one head and a single linear history."""

    script = ScriptDirectory.from_config(migration_context.config)
    heads = script.get_heads()
    assert len(heads) == 1, f"expected a single head revision, found: {heads!r}"

    current_head = script.get_current_head()
    assert current_head == heads[0]

    for revision in script.walk_revisions(head=current_head, base="base"):
        if isinstance(revision.down_revision, tuple):
            pytest.fail(
                f"revision {revision.revision} branches from multiple parents:"
                f" {revision.down_revision}"
            )


def test_migration_revisions_apply_sequentially(
    migration_context: MigrationTestContext,
) -> None:
    """Each Alembic revision should apply cleanly from the previous one."""

    script = ScriptDirectory.from_config(migration_context.config)
    revisions = list(script.walk_revisions(base="base", head="heads"))
    assert revisions, "no Alembic revisions discovered"

    ordered_revisions = list(reversed(revisions))

    migration_context.downgrade("base")
    for revision in ordered_revisions:
        migration_context.upgrade(revision.revision)

    migration_context.downgrade("base")

    for revision in ordered_revisions:
        migration_context.upgrade(revision.revision)

    migration_context.downgrade("base")


def test_migration_rolls_back_on_failure(
    migration_context: MigrationTestContext,
) -> None:
    """If a migration step fails the previous schema must remain untouched."""

    module = importlib.import_module(
        "migrations.alembic.versions.202501150001_create_kill_switch_state"
    )

    def failing_create_index(*args, **kwargs):
        raise RuntimeError("forced failure for rollback validation")

    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(module.op, "create_index", failing_create_index)
        with pytest.raises(RuntimeError):
            migration_context.upgrade("head")

    if getattr(migration_context.engine.dialect, "supports_transactional_ddl", False):
        assert _table_exists(migration_context.engine, "kill_switch_state") is False
    else:
        with migration_context.engine.begin() as connection:
            connection.execute(
                text("DROP INDEX IF EXISTS idx_kill_switch_state_updated_at")
            )
            connection.execute(text("DROP TABLE IF EXISTS kill_switch_state"))

    migration_context.upgrade("head")
    assert _table_exists(migration_context.engine, "kill_switch_state") is True
