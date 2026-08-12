# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.observability.builder import (
    ObservabilityConfigError,
    build_bundle,
    validate_alerts,
    validate_metrics,
)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_validate_metrics_requires_unique_names(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.json"
    _write_json(
        metrics_path,
        {
            "metrics": [
                {
                    "name": "geosync_metric_one",
                    "type": "counter",
                    "description": "A metric",
                    "labels": ["label"],
                    "subsystem": "demo",
                },
                {
                    "name": "geosync_metric_one",
                    "type": "gauge",
                    "description": "Duplicate",
                    "labels": [],
                    "subsystem": "demo",
                },
            ]
        },
    )

    with pytest.raises(ObservabilityConfigError, match="Duplicate metric definition"):
        validate_metrics(metrics_path)


def test_validate_alerts_rejects_unknown_metric(tmp_path: Path) -> None:
    alerts_path = tmp_path / "alerts.json"
    _write_json(
        alerts_path,
        {
            "groups": [
                {
                    "name": "demo",
                    "rules": [
                        {
                            "alert": "DemoAlert",
                            "expr": "sum(geosync_unknown_total)",
                            "labels": {},
                            "annotations": {},
                        }
                    ],
                }
            ]
        },
    )

    with pytest.raises(ObservabilityConfigError, match="unknown metrics"):
        validate_alerts(alerts_path, ["geosync_known_total"])


def test_build_bundle_generates_artifacts(tmp_path: Path) -> None:
    root = tmp_path
    dashboards = root / "dashboards"
    dashboards.mkdir()

    _write_json(
        root / "metrics.json",
        {
            "metrics": [
                {
                    "name": "geosync_metric_one",
                    "type": "counter",
                    "description": "A metric",
                    "labels": [],
                    "subsystem": "demo",
                },
                {
                    "name": "geosync_metric_two",
                    "type": "histogram",
                    "description": "Another metric",
                    "labels": ["label"],
                    "subsystem": "demo",
                },
            ]
        },
    )

    _write_json(
        root / "alerts.json",
        {
            "groups": [
                {
                    "name": "demo",
                    "rules": [
                        {
                            "alert": "DemoAlert",
                            "expr": "sum(rate(geosync_metric_one[5m])) > 10",
                            "labels": {"severity": "warning"},
                            "annotations": {"summary": "Demo"},
                        }
                    ],
                }
            ]
        },
    )

    _write_json(
        dashboards / "demo.json",
        {
            "uid": "demo",
            "title": "Demo",
            "panels": [
                {
                    "type": "timeseries",
                    "targets": [
                        {
                            "expr": "sum(geosync_metric_one)",
                            "refId": "A",
                        }
                    ],
                }
            ],
        },
    )

    output_dir = root / "generated"
    manifest = build_bundle(root, output_dir)

    alerts_file = output_dir / "prometheus" / "alerts.yaml"
    dashboard_file = output_dir / "dashboards" / "demo.json"
    manifest_file = output_dir / "manifest.json"

    assert alerts_file.exists()
    assert dashboard_file.exists()
    assert manifest_file.exists()

    rendered = alerts_file.read_text(encoding="utf-8")
    assert "groups:" in rendered
    assert "DemoAlert" in rendered

    dashboard_payload = json.loads(dashboard_file.read_text(encoding="utf-8"))
    assert dashboard_payload["uid"] == "demo"
    assert manifest["dashboards"] == ["demo"]
    assert len(manifest["metrics"]) == 2


def test_build_bundle_quotes_special_yaml_strings(tmp_path: Path) -> None:
    root = tmp_path
    dashboards = root / "dashboards"
    dashboards.mkdir()

    _write_json(
        root / "metrics.json",
        {
            "metrics": [
                {
                    "name": "geosync_latency_seconds",
                    "type": "histogram",
                    "description": "Latency histogram",
                    "labels": [],
                    "subsystem": "api",
                }
            ]
        },
    )

    _write_json(
        root / "alerts.json",
        {
            "groups": [
                {
                    "name": "api",
                    "rules": [
                        {
                            "alert": "LatencySLOViolation",
                            "expr": "histogram_quantile(0.99, geosync_latency_seconds_bucket) > 1.5",
                            "annotations": {
                                "summary": "Latency: 99th percentile breached",
                                "description": "Investigate upstream: dependency #1",
                            },
                        }
                    ],
                }
            ]
        },
    )

    _write_json(
        dashboards / "latency.json",
        {
            "uid": "latency",
            "title": "Latency",
            "panels": [
                {
                    "type": "timeseries",
                    "targets": [
                        {
                            "expr": "histogram_quantile(0.99, geosync_latency_seconds_bucket)",
                            "refId": "A",
                        }
                    ],
                }
            ],
        },
    )

    output_dir = root / "generated"
    build_bundle(root, output_dir)

    alerts_file = output_dir / "prometheus" / "alerts.yaml"
    rendered = alerts_file.read_text(encoding="utf-8")

    assert 'summary: "Latency: 99th percentile breached"' in rendered
    assert 'description: "Investigate upstream: dependency #1"' in rendered
