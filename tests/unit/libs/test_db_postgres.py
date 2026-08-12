# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regression tests for the PostgreSQL connection factory."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest

from core.config.cli_models import PostgresTLSConfig
from libs.db.postgres import create_postgres_connection


class _FakePsycopgModule(SimpleNamespace):
    """Collect the arguments used to construct a connection."""

    def __call__(self, **kwargs: Any) -> object:  # pragma: no cover - compatibility shim.
        return self.connect(**kwargs)

    def connect(self, **kwargs: Any) -> object:
        self.kwargs = kwargs
        return object()


@pytest.fixture()
def fake_psycopg(monkeypatch: pytest.MonkeyPatch) -> _FakePsycopgModule:
    module = _FakePsycopgModule()
    monkeypatch.setitem(sys.modules, "psycopg", module)
    return module


def _tls(tmp_path: pytest.TempPathFactory) -> PostgresTLSConfig:
    base = tmp_path.mktemp("tls")
    return PostgresTLSConfig(
        ca_file=base / "root-ca.pem",
        cert_file=base / "client.crt",
        key_file=base / "client.key",
    )


def test_factory_passes_tls_parameters(
    fake_psycopg: _FakePsycopgModule, tmp_path_factory: pytest.TempPathFactory
) -> None:
    tls = _tls(tmp_path_factory)
    uri = "postgresql://user:pass@db/prod?sslmode=verify-full"

    conn = create_postgres_connection(uri, tls, application_name="geosync")

    assert conn is not None
    assert fake_psycopg.kwargs["conninfo"] == uri
    assert fake_psycopg.kwargs["sslrootcert"] == str(tls.ca_file)
    assert fake_psycopg.kwargs["sslcert"] == str(tls.cert_file)
    assert fake_psycopg.kwargs["sslkey"] == str(tls.key_file)
    assert fake_psycopg.kwargs["application_name"] == "geosync"


@pytest.mark.parametrize(
    "uri",
    [
        "postgresql://user:pass@db/prod?sslmode=prefer",
        "postgresql://user:pass@db/prod?sslmode=require",
    ],
)
def test_factory_rejects_insecure_sslmode(
    uri: str, fake_psycopg: _FakePsycopgModule, tmp_path_factory: pytest.TempPathFactory
) -> None:
    tls = _tls(tmp_path_factory)

    with pytest.raises(ValueError):
        create_postgres_connection(uri, tls)


def test_factory_requires_tls(
    fake_psycopg: _FakePsycopgModule, tmp_path_factory: pytest.TempPathFactory
) -> None:
    uri = "postgresql://user:pass@db/prod?sslmode=verify-full"

    with pytest.raises(ValueError):
        create_postgres_connection(uri, None)
