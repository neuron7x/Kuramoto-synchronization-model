# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests covering experiment configuration validation rules."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from core.config.cli_models import ExperimentConfig


def _base_payload(tmp_path: Path) -> dict[str, object]:
    return {
        "name": "prod",
        "db_uri": "postgresql://user:pass@db/prod?sslmode=verify-full",
        "db_tls": {
            "ca_file": str(tmp_path / "root-ca.pem"),
            "cert_file": str(tmp_path / "client.crt"),
            "key_file": str(tmp_path / "client.key"),
        },
        "debug": False,
        "log_level": "INFO",
        "random_seed": 7,
        "data": {"price_csv": str(tmp_path / "prices.csv"), "price_column": "price"},
        "analytics": {"window": 64, "bins": 32, "delta": 0.01},
        "tracking": {"enabled": True, "base_dir": str(tmp_path)},
    }


def test_postgres_requires_sslmode(tmp_path: Path) -> None:
    payload = _base_payload(tmp_path)
    payload["db_uri"] = "postgresql://user:pass@db/prod"

    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate(payload)


@pytest.mark.parametrize(
    "uri",
    [
        "postgresql://user:pass@db/prod?sslmode=prefer",
        "postgresql://user:pass@db/prod?sslmode=require",
    ],
)
def test_postgres_rejects_insecure_sslmode(tmp_path: Path, uri: str) -> None:
    payload = _base_payload(tmp_path)
    payload["db_uri"] = uri

    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate(payload)


def test_postgres_requires_tls_material(tmp_path: Path) -> None:
    payload = _base_payload(tmp_path)
    payload.pop("db_tls")

    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate(payload)


def test_non_postgres_does_not_require_tls(tmp_path: Path) -> None:
    payload = _base_payload(tmp_path)
    payload["db_uri"] = "sqlite:///local.db"
    payload.pop("db_tls")

    config = ExperimentConfig.model_validate(payload)

    assert config.db_uri == "sqlite:///local.db"
    assert config.db_tls is None
