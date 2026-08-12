# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from observability.bootstrap import (
    AlertNoiseGuard,
    EndpointCheck,
    EndpointValidator,
    LoggingSetup,
    MetricsSetup,
    PostmortemTemplateBuilder,
    SLOSuite,
)


@pytest.fixture(autouse=True)
def _restore_logging_state() -> None:
    root = logging.getLogger()
    handlers = list(root.handlers)
    filters = list(root.filters)
    level = root.level
    yield
    root.handlers = handlers
    root.filters = filters
    root.setLevel(level)


class _NoopHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - defined by BaseHTTPRequestHandler
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args, **kwargs):  # type: ignore[override]
        return


@pytest.fixture()
def http_endpoint() -> str:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _NoopHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    yield f"http://{host}:{port}"
    server.shutdown()
    thread.join(timeout=5)


def test_logging_setup_applies_tags(monkeypatch) -> None:
    payloads: list[dict[str, object]] = []
    setup = LoggingSetup(tags={"service": "test", "environment": "qa"}, sink=payloads.append)
    setup.apply()

    logger = logging.getLogger("observability.test")
    logger.info("hello-world")

    assert payloads, "expected structured payload to be captured"
    payload = payloads[-1]
    assert payload["service"] == "test"
    assert payload["environment"] == "qa"


def test_metrics_setup_reports_missing_tags(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "metrics": [
                    {
                        "name": "geosync_test_metric",
                        "type": "gauge",
                        "description": "test metric",
                        "labels": ["service", "cluster"],
                        "subsystem": "tests",
                    }
                ]
            }
        )
    )

    setup = MetricsSetup(
        metrics_path=metrics_path,
        required_tags=("service", "environment"),
        cardinality_limits={"service": 5},
        max_labels_per_metric=5,
    )

    report = setup.validate()
    assert report.has_issues
    assert any("missing required tags" in issue.message for issue in report.issues)
    assert any("lacks a configured cardinality limit" in issue.message for issue in report.issues)


def test_alert_noise_guard_flags_short_hold(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "metrics": [
                    {
                        "name": "geosync_test_metric",
                        "type": "counter",
                        "description": "test",
                        "labels": ["service", "environment"],
                        "subsystem": "tests",
                    }
                ]
            }
        )
    )
    alerts_path = tmp_path / "alerts.json"
    alerts_path.write_text(
        json.dumps(
            {
                "groups": [
                    {
                        "name": "tests",
                        "rules": [
                            {
                                "alert": "TestAlert",
                                "expr": "geosync_test_metric > 0",
                                "for": "10s",
                            }
                        ],
                    }
                ]
            }
        )
    )

    guard = AlertNoiseGuard(alerts_path=alerts_path, minimum_for_seconds=60)
    findings = guard.evaluate(["geosync_test_metric"])
    assert "tests" in findings
    assert any("below minimum" in issue for issue in findings["tests"])


def test_endpoint_validator_success(http_endpoint: str) -> None:
    validator = EndpointValidator(checks=(EndpointCheck(http_endpoint),))
    results = validator.run()
    assert len(results) == 1
    assert results[0].success is True
    assert results[0].status == 200


def test_slo_suite_thresholds(tmp_path: Path) -> None:
    slo_path = tmp_path / "slo.json"
    slo_path.write_text(
        json.dumps(
            {
                "slos": [
                    {
                        "name": "demo",
                        "description": "demo slo",
                        "error_rate_threshold": 0.1,
                        "latency_threshold_ms": 100.0,
                        "min_requests": 10,
                        "evaluation_period": "5m",
                        "burn_rates": [{"window": "5m", "max_burn_rate": 2.0}],
                    }
                ]
            }
        )
    )

    suite = SLOSuite(policies_path=slo_path)
    results = suite.run_threshold_tests()
    assert results["demo"]["within_threshold"] is True
    assert results["demo"]["breach_detected"] is True


def test_postmortem_builder_creates_file(tmp_path: Path) -> None:
    path = tmp_path / "postmortem.md"
    builder = PostmortemTemplateBuilder(template_path=path, sections=("Summary",))
    builder.ensure()

    content = path.read_text()
    assert "# Postmortem Template" in content
    assert "## Summary" in content
