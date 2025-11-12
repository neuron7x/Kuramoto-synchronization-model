from __future__ import annotations

from pathlib import Path

import pytest

from cortex_service.app.config import (
    ConfigurationError,
    CortexSettings,
    DatabaseSettings,
    DatabaseTLSSettings,
    RegimeSettings,
    RiskSettings,
    ServiceMeta,
    SignalSettings,
)
from cortex_service.app.db import create_db_engine


def _write_tls_files(tmp_path: Path) -> DatabaseTLSSettings:
    ca = tmp_path / "root-ca.pem"
    cert = tmp_path / "client.pem"
    key = tmp_path / "client.key"
    for material in (ca, cert, key):
        material.write_text("dummy", encoding="utf-8")
    return DatabaseTLSSettings(ca_file=ca, cert_file=cert, key_file=key)


def _base_settings(database: DatabaseSettings) -> CortexSettings:
    return CortexSettings(
        service=ServiceMeta(),
        database=database,
        signals=SignalSettings(),
        risk=RiskSettings(),
        regime=RegimeSettings(),
    )


def test_create_db_engine_requires_tls(tmp_path: Path) -> None:
    database = DatabaseSettings(
        url="postgresql+psycopg://cortex@cortex-db:5432/cortex?sslmode=verify-full",
        tls=None,
    )
    settings = _base_settings(database)

    with pytest.raises(ConfigurationError):
        create_db_engine(settings)


def test_create_db_engine_applies_tls_arguments(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tls = _write_tls_files(tmp_path)
    database = DatabaseSettings(
        url="postgresql+psycopg://cortex@cortex-db:5432/cortex?sslmode=verify-full",
        tls=tls,
    )
    settings = _base_settings(database)

    captured: dict[str, object] = {}

    def fake_create_engine(url: str, **kwargs: object) -> object:
        captured["url"] = url
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr("cortex_service.app.db.create_engine", fake_create_engine)

    engine = create_db_engine(settings)

    assert engine is not None
    assert captured["url"] == database.url
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    connect_args = kwargs.get("connect_args")
    assert connect_args == {
        "sslmode": "verify-full",
        "sslrootcert": str(tls.ca_file),
        "sslcert": str(tls.cert_file),
        "sslkey": str(tls.key_file),
    }
