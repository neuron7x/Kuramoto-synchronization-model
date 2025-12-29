from __future__ import annotations

import math
import types
from pathlib import Path

import scripts.validate_metrics as vm


def test_parse_metrics_payload_histogram_and_counter() -> None:
    payload = (
        "# HELP tradepulse_api_request_latency_seconds Histogram\n"
        "tradepulse_api_request_latency_seconds_bucket{route=\"/health\",method=\"GET\",le=\"0.5\"} 1\n"
        "tradepulse_api_request_latency_seconds_sum{route=\"/health\",method=\"GET\"} 0.1\n"
        "tradepulse_api_request_latency_seconds_count{route=\"/health\",method=\"GET\"} 2\n"
        "tradepulse_api_requests_total{route=\"/health\",method=\"GET\",status=\"200\"} 3\n"
    )
    parsed = vm._parse_metrics_payload(payload)
    assert parsed["tradepulse_api_requests_total"][0]["value"] == 3.0
    assert parsed["tradepulse_api_request_latency_seconds_count"][0]["labels"]["route"] == "/health"


def test_run_runtime_rejects_non_finite(monkeypatch, tmp_path: Path) -> None:
    vm.ARTIFACT_DIR = tmp_path

    class FakeResponse:
        def __init__(self, text: str):
            self.text = text
            self.status_code = 200

        def raise_for_status(self):
            if self.status_code != 200:
                raise RuntimeError("bad")

    class FakeClient:
        def __init__(self, app):
            self.app = app

        def get(self, path):
            metric_text = (
                "tradepulse_api_requests_total{route=\"/health\",method=\"GET\",status=\"200\"} 1\n"
                "tradepulse_api_request_latency_seconds_sum{route=\"/health\",method=\"GET\"} nan\n"
            )
            return FakeResponse(metric_text)

    app = types.SimpleNamespace(state=types.SimpleNamespace(metrics=None))
    monkeypatch.setattr(vm, "TestClient", FakeClient)
    monkeypatch.setattr(vm, "create_app", lambda: app)

    result = vm.run_runtime(Path("."), [])
    assert result == 1
    assert (tmp_path / "runtime.json").exists()


def test_run_runtime_succeeds_with_finite(monkeypatch, tmp_path: Path) -> None:
    vm.ARTIFACT_DIR = tmp_path

    class FakeResponse:
        def __init__(self, text: str):
            self.text = text
            self.status_code = 200

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, app):
            self.app = app

        def get(self, path):
            metric_text = (
                "tradepulse_api_requests_total{route=\"/health\",method=\"GET\",status=\"200\"} 1\n"
                "tradepulse_api_request_latency_seconds_count{route=\"/health\",method=\"GET\"} 1\n"
                "tradepulse_api_request_latency_seconds_sum{route=\"/health\",method=\"GET\"} 0.1\n"
            )
            return FakeResponse(metric_text)

    app = types.SimpleNamespace(state=types.SimpleNamespace(metrics=None))
    monkeypatch.setattr(vm, "TestClient", FakeClient)
    monkeypatch.setattr(vm, "create_app", lambda: app)

    result = vm.run_runtime(Path("."), [])
    assert result == 0
    artifact = tmp_path / "runtime.json"
    assert artifact.exists()
    payload = artifact.read_text()
    assert "metric_deltas" in payload
