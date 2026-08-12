# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""PostgreSQL connection factory enforcing TLS requirements."""

from __future__ import annotations

from typing import Any

from core.config.cli_models import PostgresTLSConfig
from core.config.postgres import ensure_secure_postgres_uri, is_postgres_uri

__all__ = ["create_postgres_connection"]


def create_postgres_connection(
    db_uri: str,
    tls: PostgresTLSConfig | None,
    **connect_kwargs: Any,
) -> Any:
    """Return a psycopg connection configured with strict TLS settings."""

    if not is_postgres_uri(db_uri):
        msg = "create_postgres_connection() only accepts PostgreSQL connection URIs"
        raise ValueError(msg)

    ensure_secure_postgres_uri(db_uri)

    if tls is None:
        msg = "TLS credentials are required when connecting to PostgreSQL"
        raise ValueError(msg)

    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - defensive guard when dependency is missing.
        msg = "psycopg must be installed to create PostgreSQL connections"
        raise RuntimeError(msg) from exc

    return psycopg.connect(
        conninfo=db_uri,
        sslrootcert=str(tls.ca_file),
        sslcert=str(tls.cert_file),
        sslkey=str(tls.key_file),
        **connect_kwargs,
    )
