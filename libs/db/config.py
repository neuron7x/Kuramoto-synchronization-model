"""Typed configuration objects for relational database connectivity."""

from __future__ import annotations

from typing import Iterable, Tuple

from pydantic import BaseModel, Field, PositiveFloat, PositiveInt, model_validator

from core.config.cli_models import PostgresTLSConfig
from core.config.postgres import ensure_secure_postgres_uri, is_postgres_uri

__all__ = [
    "DatabasePoolConfig",
    "DatabaseRuntimeConfig",
    "DatabaseSettings",
]


class DatabasePoolConfig(BaseModel):
    """Connection pool tuning knobs shared by writer and reader engines."""

    size: PositiveInt = Field(
        10, description="Base amount of connections to keep open."
    )
    max_overflow: int = Field(
        10,
        ge=0,
        description=(
            "Maximum amount of transient connections allowed in addition to the base pool "
            "size when the demand temporarily exceeds capacity."
        ),
    )
    timeout: float | None = Field(
        5.0,
        ge=0.0,
        description="Seconds to wait when acquiring a pooled connection before failing. Use null for unlimited wait.",
    )
    recycle: PositiveFloat = Field(
        1_800.0,
        description="Seconds after which idle connections are recycled to avoid server-side disconnects.",
    )
    use_lifo: bool = Field(
        True,
        description="Prefer returning the most recently used connection to improve cache locality.",
    )


class DatabaseRuntimeConfig(BaseModel):
    """Session level runtime options applied to every connection."""

    application_name: str = Field(
        "tradepulse",
        min_length=1,
        description="Identifier visible in PostgreSQL monitoring views for tracking client activity.",
    )
    connect_timeout_seconds: PositiveFloat = Field(
        5.0,
        description="Timeout, in seconds, for establishing new database connections.",
    )
    statement_timeout_ms: PositiveInt = Field(
        5_000,
        description="Upper bound, in milliseconds, for individual SQL statements executed by the service.",
    )
    target_session_attrs: str | None = Field(
        default=None,
        description=(
            "Optional libpq target_session_attrs setting (e.g. 'read-write') enforced when establishing connections."
        ),
    )


class DatabaseSettings(BaseModel):
    """Complete database access configuration describing writer and reader endpoints."""

    writer_dsn: str = Field(
        ..., description="Primary connection string used for write transactions."
    )
    reader_dsns: Tuple[str, ...] = Field(
        default_factory=tuple,
        description="Optional additional connection strings used for read-only workloads.",
    )
    tls: PostgresTLSConfig | None = Field(
        default=None,
        description="TLS material required when connecting to PostgreSQL instances.",
    )
    pool: DatabasePoolConfig = Field(default_factory=DatabasePoolConfig)
    runtime: DatabaseRuntimeConfig = Field(default_factory=DatabaseRuntimeConfig)
    echo_statements: bool = Field(
        False,
        description="Enable SQLAlchemy statement logging. Should remain disabled in production for performance reasons.",
    )

    @model_validator(mode="after")
    def _validate_security(self) -> "DatabaseSettings":
        all_dsns: Iterable[str] = (self.writer_dsn, *self.reader_dsns)
        for dsn in all_dsns:
            ensure_secure_postgres_uri(dsn)
        if any(is_postgres_uri(dsn) for dsn in all_dsns) and self.tls is None:
            raise ValueError("TLS credentials are required for PostgreSQL connections")
        return self
