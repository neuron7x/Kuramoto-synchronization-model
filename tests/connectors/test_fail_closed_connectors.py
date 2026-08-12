# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed behavior tests for unsupported connector protocols."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from mycelium_fractal_net.connectors.config import (
    BackendConfig,
    IngestionConfig,
    RestSourceConfig,
)
from mycelium_fractal_net.connectors.kafka_source import (
    KafkaConnectorUnavailableError,
    KafkaIngestor,
)
from mycelium_fractal_net.connectors.runner import RemoteBackend
from mycelium_fractal_net.connectors.transform import MFNRequest


class _DummyResponse:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("bad status")

    def json(self) -> dict[str, object]:
        return self._payload


class _DummyClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def post(self, path: str, *, json: dict[str, object]) -> _DummyResponse:  # noqa: A002
        self.calls.append((path, json))
        return _DummyResponse(self.payload)


def test_kafka_ingestor_is_explicitly_unavailable() -> None:
    with pytest.raises(KafkaConnectorUnavailableError, match="Kafka ingestion is disabled"):
        KafkaIngestor(bootstrap_servers="localhost:9092", topic="ticks")


def test_kafka_ingestor_methods_also_fail_closed() -> None:
    ingestor = object.__new__(KafkaIngestor)

    with pytest.raises(KafkaConnectorUnavailableError, match="Kafka ingestion is disabled"):
        asyncio.run(ingestor.connect())

    with pytest.raises(KafkaConnectorUnavailableError, match="Kafka ingestion is disabled"):
        asyncio.run(ingestor.close())


def test_backend_config_rejects_grpc_protocol() -> None:
    with pytest.raises(ValidationError, match="Input should be 'rest'"):
        BackendConfig(protocol="grpc")


def test_ingestion_config_rejects_kafka_source_type() -> None:
    with pytest.raises(ValidationError, match="Input should be 'rest' or 'file'"):
        IngestionConfig(
            source_type="kafka",
        )


def test_ingestion_config_rest_source_still_supported() -> None:
    cfg = IngestionConfig(
        source_type="rest",
        rest_source=RestSourceConfig(url="https://example.com/feed"),
    )
    assert cfg.get_source_config().url == "https://example.com/feed"


def test_connector_imports_do_not_pull_hydra_stack() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    src_root = repo_root / "src"
    env = dict(os.environ)
    pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{src_root}:{pythonpath}" if pythonpath else str(src_root)
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys;"
                "import mycelium_fractal_net.connectors.config;"
                "import mycelium_fractal_net.connectors.runner;"
                "sys.exit(0 if 'core.config.hydra_profiles' not in sys.modules and "
                "'omegaconf' not in sys.modules else 1)"
            ),
        ],
        check=False,
        cwd=repo_root,
        env=env,
    )
    assert probe.returncode == 0


@pytest.mark.parametrize(
    ("env_key", "env_value", "expected"),
    [
        ("MFN_BACKEND_PROTOCOL", "grpc", "MFN_BACKEND_PROTOCOL"),
        ("MFN_SOURCE_TYPE", "kafka", "MFN_SOURCE_TYPE"),
        ("MFN_BACKEND_TYPE", "edge", "MFN_BACKEND_TYPE"),
        ("MFN_FILE_FORMAT", "xml", "MFN_FILE_FORMAT"),
        ("MFN_MODE", "batch", "MFN_MODE"),
    ],
)
def test_ingestion_config_from_env_rejects_unsupported_values(
    monkeypatch: pytest.MonkeyPatch,
    env_key: str,
    env_value: str,
    expected: str,
) -> None:
    monkeypatch.setenv(env_key, env_value)
    if env_key != "MFN_FILE_FORMAT":
        monkeypatch.delenv("MFN_FILE_PATH", raising=False)
    else:
        monkeypatch.setenv("MFN_FILE_PATH", "/tmp/input.jsonl")

    with pytest.raises(ValueError, match=expected):
        IngestionConfig.from_env()


def test_remote_backend_rejects_grpc_protocol() -> None:
    with pytest.raises(ValueError, match="protocol 'grpc' is not supported"):
        RemoteBackend(endpoint="https://mfn.internal", protocol="grpc")


def test_remote_backend_rest_extract_features_calls_rest_endpoint() -> None:
    backend = RemoteBackend(endpoint="https://mfn.internal", protocol="rest")
    client = _DummyClient(payload={"features": [1.0, 2.0]})

    async def _fake_get_client() -> _DummyClient:
        return client

    backend._get_client = _fake_get_client  # type: ignore[method-assign]

    req = MFNRequest(
        request_type="feature",
        request_id="req-1",
        timestamp=datetime.now(timezone.utc),
        seeds=[1.0, 2.0],
        grid_size=8,
    )

    result = asyncio.run(backend.extract_features(req))

    assert result.success is True
    assert client.calls[0][0] == "/api/v1/features/extract"


def test_remote_backend_rest_run_simulation_calls_rest_endpoint() -> None:
    backend = RemoteBackend(endpoint="https://mfn.internal", protocol="rest")
    client = _DummyClient(payload={"status": "ok"})

    async def _fake_get_client() -> _DummyClient:
        return client

    backend._get_client = _fake_get_client  # type: ignore[method-assign]

    req = MFNRequest(
        request_type="simulation",
        request_id="req-2",
        timestamp=datetime.now(timezone.utc),
        seeds=[3.0],
        grid_size=16,
    )

    result = asyncio.run(backend.run_simulation(req))

    assert result.success is True
    assert client.calls[0][0] == "/api/v1/simulation/run"
