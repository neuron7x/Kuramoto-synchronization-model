# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Alembic environment configuration for GeoSync."""

from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context

from core.config.cli_models import PostgresTLSConfig
from core.config.postgres import ensure_secure_postgres_uri
from libs.db import (
    DatabasePoolConfig,
    DatabaseRuntimeConfig,
    DatabaseSettings,
    create_engine_from_config,
)
from libs.db.models import Base

# This config object provides access to the values within the .ini file in use.
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for 'autogenerate' support.
target_metadata = Base.metadata


def _reader_dsns_from_env() -> tuple[str, ...]:
    raw = os.getenv("GEOSYNC_DB_READER_DSNS", "").strip()
    if not raw:
        return ()
    return tuple(dsn.strip() for dsn in raw.split(",") if dsn.strip())


def _tls_from_env() -> PostgresTLSConfig | None:
    ca = os.getenv("GEOSYNC_DB_TLS_CA")
    cert = os.getenv("GEOSYNC_DB_TLS_CERT")
    key = os.getenv("GEOSYNC_DB_TLS_KEY")
    if not any([ca, cert, key]):
        return None
    if not all([ca, cert, key]):
        raise RuntimeError(
            "GEOSYNC_DB_TLS_CA, GEOSYNC_DB_TLS_CERT and GEOSYNC_DB_TLS_KEY must all be provided"
        )
    return PostgresTLSConfig(
        ca_file=Path(ca).expanduser(),
        cert_file=Path(cert).expanduser(),
        key_file=Path(key).expanduser(),
    )


def _load_database_settings() -> DatabaseSettings:
    writer_dsn = os.getenv("GEOSYNC_DB_WRITER_DSN")
    if not writer_dsn:
        raise RuntimeError("GEOSYNC_DB_WRITER_DSN must be set for Alembic migrations")
    ensure_secure_postgres_uri(writer_dsn)
    reader_dsns = _reader_dsns_from_env()
    tls = _tls_from_env()
    pool = DatabasePoolConfig()
    runtime = DatabaseRuntimeConfig()
    return DatabaseSettings(
        writer_dsn=writer_dsn,
        reader_dsns=reader_dsns,
        tls=tls,
        pool=pool,
        runtime=runtime,
    )


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""

    settings = _load_database_settings()
    context.configure(
        url=settings.writer_dsn,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    existing_connection = config.attributes.get("connection")
    if existing_connection is not None:
        context.configure(
            connection=existing_connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    settings = _load_database_settings()
    connectable = create_engine_from_config(
        settings.writer_dsn,
        tls=settings.tls,
        pool=settings.pool,
        runtime=settings.runtime,
    )

    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
