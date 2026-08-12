# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed contracts for the typed database configuration objects.

Defects these guard against: dropping the TLS-required rule, accepting a
malformed / plaintext PostgreSQL DSN, leaking a password into ``repr``/logs,
admitting a non-positive pool/timeout, or non-deterministic serialisation.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.config.cli_models import PostgresTLSConfig
from core.config.postgres import ensure_secure_postgres_uri
from libs.db.config import (
    DatabasePoolConfig,
    DatabaseRuntimeConfig,
    DatabaseSettings,
    _redact_dsn,
)

# Synthetic, non-functional credentials used only to prove the redaction /
# fail-closed contracts. Not real secrets; marked for detect-secrets.
_SECRET = "s3cr3t-PLAINTEXT-pw"  # pragma: allowlist secret
_PG = f"postgresql://user:{_SECRET}@db.internal:5432/geosync?sslmode=verify-full"  # pragma: allowlist secret


def _tls() -> PostgresTLSConfig:
    return PostgresTLSConfig(ca_file="/tls/ca.pem", cert_file="/tls/cert.pem", key_file="/tls/key.pem")


def test_explicit_overrides_beat_defaults() -> None:
    settings = DatabaseSettings(
        writer_dsn="sqlite:///local.db",
        pool=DatabasePoolConfig(size=25, timeout=None),
        runtime=DatabaseRuntimeConfig(application_name="explicit-app"),
        echo_statements=True,
    )
    assert settings.pool.size == 25
    assert settings.pool.timeout is None
    assert settings.runtime.application_name == "explicit-app"
    assert settings.echo_statements is True
    # Untouched knobs keep their documented defaults.
    assert DatabasePoolConfig().size == 10
    assert DatabaseRuntimeConfig().application_name == "geosync"


def test_missing_writer_dsn_fails_closed() -> None:
    # Construct via **kwargs so the required-field omission is a RUNTIME failure
    # (ValidationError) rather than a static call-arg error to suppress.
    no_fields: dict[str, object] = {}
    with pytest.raises(ValidationError):
        DatabaseSettings(**no_fields)


def test_postgres_without_sslmode_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DatabaseSettings(writer_dsn="postgresql://user@db.internal:5432/geosync")


def test_postgres_with_weak_sslmode_is_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        DatabaseSettings(writer_dsn="postgresql://user@db/geosync?sslmode=require")
    assert "sslmode" in str(excinfo.value)


def test_postgres_requires_tls_material() -> None:
    with pytest.raises(ValidationError) as excinfo:
        DatabaseSettings(writer_dsn=_PG)
    assert "TLS credentials are required" in str(excinfo.value)


def test_postgres_with_tls_is_accepted() -> None:
    settings = DatabaseSettings(writer_dsn=_PG, tls=_tls())
    assert settings.tls is not None


def test_reader_dsns_are_validated_too() -> None:
    with pytest.raises(ValidationError):
        DatabaseSettings(
            writer_dsn="sqlite:///w.db",
            reader_dsns=("postgresql://u@r/db?sslmode=require",),
        )


def test_non_postgres_dsn_does_not_require_tls() -> None:
    settings = DatabaseSettings(writer_dsn="sqlite:///local.db")
    assert settings.tls is None


def test_secret_absent_from_repr_and_str() -> None:
    settings = DatabaseSettings(
        writer_dsn=_PG,
        reader_dsns=(_PG.replace("geosync", "geosync_ro"),),
        tls=_tls(),
    )
    assert _SECRET not in repr(settings)
    assert _SECRET not in str(settings)
    assert "***" in repr(settings)


def test_secret_absent_from_validation_error_messages() -> None:
    # The library's OWN error text must not interpolate the DSN credential.
    with pytest.raises(ValueError) as weak:
        ensure_secure_postgres_uri(
            f"postgresql://u:{_SECRET}@h/db?sslmode=require"  # pragma: allowlist secret
        )
    assert _SECRET not in str(weak.value)
    with pytest.raises(ValueError) as tls_required:
        DatabaseSettings(writer_dsn=_PG)
    assert _SECRET not in str(tls_required.value)


def test_model_dump_preserves_dsn_for_connection() -> None:
    # Redaction is repr-only; the real DSN must survive serialisation so the
    # engine factory can actually connect.
    settings = DatabaseSettings(writer_dsn=_PG, tls=_tls())
    assert settings.model_dump()["writer_dsn"] == _PG


def test_negative_timeout_rejected() -> None:
    with pytest.raises(ValidationError):
        DatabasePoolConfig(timeout=-1.0)


def test_negative_max_overflow_rejected() -> None:
    with pytest.raises(ValidationError):
        DatabasePoolConfig(max_overflow=-1)


def test_zero_pool_size_rejected() -> None:
    with pytest.raises(ValidationError):
        DatabasePoolConfig(size=0)


def test_non_positive_connect_timeout_rejected() -> None:
    with pytest.raises(ValidationError):
        DatabaseRuntimeConfig(connect_timeout_seconds=0.0)


def test_non_positive_statement_timeout_rejected() -> None:
    with pytest.raises(ValidationError):
        DatabaseRuntimeConfig(statement_timeout_ms=0)


def test_serialization_is_deterministic() -> None:
    kwargs = dict(writer_dsn=_PG, reader_dsns=(_PG,), tls=_tls())
    first = DatabaseSettings(**kwargs).model_dump_json()
    second = DatabaseSettings(**kwargs).model_dump_json()
    assert first == second


def test_redact_dsn_helper_passes_through_credential_free_urls() -> None:
    assert _redact_dsn("sqlite:///local.db") == "sqlite:///local.db"
    assert _redact_dsn("postgresql://user@host/db") == "postgresql://user@host/db"
    assert (
        _redact_dsn("postgresql://u:pw@host:5432/db")  # pragma: allowlist secret
        == "postgresql://u:***@host:5432/db"
    )
