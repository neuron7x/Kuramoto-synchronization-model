# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Command-line helpers for managing GeoSync database migrations."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import click
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine

from core.config.postgres import is_postgres_uri

REPO_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI_PATH = REPO_ROOT / "alembic.ini"
ALEMBIC_SCRIPT_LOCATION = REPO_ROOT / "migrations" / "alembic"


def _resolve_database_url(candidate: str | None) -> str:
    """Return the target database URL, falling back to the standard env var."""

    if candidate:
        return candidate

    env_url = os.getenv("GEOSYNC_DB_WRITER_DSN")
    if env_url:
        return env_url

    raise click.UsageError(
        "Database URL must be provided via --database-url or GEOSYNC_DB_WRITER_DSN",
    )


def _base_config(database_url: str) -> Config:
    """Instantiate the Alembic configuration bound to the repository layout."""

    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(ALEMBIC_SCRIPT_LOCATION))
    config.set_main_option("path_separator", "os")
    config.set_main_option("sqlalchemy.url", database_url)

    # Alembic's env.py expects this environment variable to be defined.
    os.environ["GEOSYNC_DB_WRITER_DSN"] = database_url
    return config


@contextmanager
def _configured_alembic(database_url: str) -> Iterator[Config]:
    """Yield an Alembic :class:`~alembic.config.Config` with optional connection."""

    config = _base_config(database_url)
    engine: Engine | None = None
    connection: Connection | None = None

    if not is_postgres_uri(database_url):
        engine = create_engine(database_url, future=True)
        connection = engine.connect()
        config.attributes["connection"] = connection

    try:
        yield config
    finally:
        if connection is not None:
            connection.close()
        if engine is not None:
            engine.dispose()


@click.group()
def cli() -> None:
    """Manage database schema migrations for GeoSync."""


def _normalise_revision(revision: str | None, default: str) -> str:
    return revision if revision is not None else default


@cli.command()
@click.argument("revision", required=False)
@click.option(
    "database_url",
    "--database-url",
    envvar="GEOSYNC_DB_WRITER_DSN",
    help="Target database URL. Defaults to GEOSYNC_DB_WRITER_DSN if set.",
)
@click.option("--sql", "emit_sql", is_flag=True, help="Emit SQL without applying it.")
def upgrade(revision: str | None, database_url: str | None, emit_sql: bool) -> None:
    """Apply migrations up to REVISION (defaults to ``head``)."""

    target_revision = _normalise_revision(revision, "head")
    url = _resolve_database_url(database_url)

    with _configured_alembic(url) as config:
        command.upgrade(config, target_revision, sql=emit_sql)


@cli.command()
@click.argument("revision", required=False)
@click.option(
    "database_url",
    "--database-url",
    envvar="GEOSYNC_DB_WRITER_DSN",
    help="Target database URL. Defaults to GEOSYNC_DB_WRITER_DSN if set.",
)
@click.option("--sql", "emit_sql", is_flag=True, help="Emit SQL without applying it.")
def downgrade(revision: str | None, database_url: str | None, emit_sql: bool) -> None:
    """Revert migrations down to REVISION (defaults to ``base``)."""

    target_revision = _normalise_revision(revision, "base")
    url = _resolve_database_url(database_url)

    with _configured_alembic(url) as config:
        command.downgrade(config, target_revision, sql=emit_sql)


@cli.command()
@click.option(
    "database_url",
    "--database-url",
    envvar="GEOSYNC_DB_WRITER_DSN",
    help="Target database URL. Defaults to GEOSYNC_DB_WRITER_DSN if set.",
)
@click.option("--verbose", is_flag=True, help="Display additional revision metadata.")
@click.option(
    "--range",
    "rev_range",
    metavar="[start]:[end]",
    help="Optional revision range filter passed to Alembic history.",
)
def history(database_url: str | None, verbose: bool, rev_range: str | None) -> None:
    """Display the Alembic revision history."""

    url = _resolve_database_url(database_url)
    with _configured_alembic(url) as config:
        command.history(config, rev_range=rev_range, verbose=verbose)


@cli.command()
@click.option(
    "database_url",
    "--database-url",
    envvar="GEOSYNC_DB_WRITER_DSN",
    help="Target database URL. Defaults to GEOSYNC_DB_WRITER_DSN if set.",
)
@click.option("--verbose", is_flag=True, help="Display revision context and environment info.")
def current(database_url: str | None, verbose: bool) -> None:
    """Print the current database revision."""

    url = _resolve_database_url(database_url)
    with _configured_alembic(url) as config:
        command.current(config, verbose=verbose)


if __name__ == "__main__":
    cli()
