# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import subprocess
import types
from pathlib import Path

import scripts.deploy.docker_compose_smoke as smoke


def _args(tmp_path: Path) -> types.SimpleNamespace:
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services:{}")
    return types.SimpleNamespace(
        compose_file=compose,
        project_name="proj",
        service_name="svc",
        health_url="http://localhost:8000/health",
        metrics_url="http://localhost:8000/metrics",
        prometheus_runtime_url="http://localhost:9090/api",
        prometheus_up_url="http://localhost:9090/up",
        artifact_dir=tmp_path / "artifacts",
        timeout=1.0,
        http_timeout=1.0,
    )


def test_smoke_builds_expected_commands(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        cmd, check=True, text=True, capture_output=False, env=None, stdout=None, stderr=None
    ):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(smoke.subprocess, "run", fake_run)
    monkeypatch.setattr(smoke, "_wait_for_service", lambda *a, **k: None)
    monkeypatch.setattr(smoke, "_fetch_json", lambda *a, **k: {"status": "ok"})
    monkeypatch.setattr(smoke, "_fetch_text", lambda *a, **k: "metrics")
    monkeypatch.setattr(
        smoke, "_run", lambda cmd, capture_output=False: types.SimpleNamespace(stdout="list")
    )

    smoke.run_smoke_test(_args(tmp_path))

    assert any(cmd[:3] == ["docker", "compose", "-f"] for cmd in calls)
    assert (tmp_path / "artifacts" / "api-health.json").exists()
    assert (tmp_path / "artifacts" / "prometheus-runtime.json").exists()
    assert (tmp_path / "artifacts" / "api-metrics.txt").exists()


def test_main_returns_error_on_subprocess_failure(monkeypatch, tmp_path: Path) -> None:
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services:{}")

    def failing_run(*a, **k):
        raise subprocess.CalledProcessError(returncode=1, cmd=a[0])

    monkeypatch.setattr(smoke.subprocess, "run", failing_run)
    argv = [
        "--compose-file",
        str(compose),
        "--artifact-dir",
        str(tmp_path / "art"),
        "--health-url",
        "http://localhost:8000/health",
        "--metrics-url",
        "http://localhost:8000/metrics",
        "--prometheus-runtime-url",
        "http://localhost:9090/api/v1/status/runtimeinfo",
        "--prometheus-up-url",
        "http://localhost:9090/api/v1/query?query=up",
        "--timeout",
        "1",
        "--http-timeout",
        "1",
    ]

    assert smoke.main(argv) == 1
