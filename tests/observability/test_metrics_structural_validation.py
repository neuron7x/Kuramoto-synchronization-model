# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

from observability import metrics_validation as mv
from tools.observability.builder import MetricDefinition


def _metric(
    name: str,
    *,
    metric_type: str = "counter",
    description: str = "A sufficiently descriptive metric.",
    labels: list[str] | None = None,
) -> MetricDefinition:
    return MetricDefinition(
        name=name,
        type=metric_type,
        description=description,
        labels=labels or [],
        subsystem="test",
    )


def test_missing_description_triggers_issue() -> None:
    catalog_metric = _metric("geosync_missing_total", description="short", metric_type="counter")
    code_metric = mv.CodeMetric(
        name=catalog_metric.name,
        type="counter",
        description="a longer description",
        labels=(),
        sources=("source.py",),
    )

    issues = mv.structural_issues(
        {catalog_metric.name: catalog_metric}, {catalog_metric.name: code_metric}
    )

    assert any(issue["code"] == "description_too_short" for issue in issues)
    assert any(issue["metric_name"] == catalog_metric.name for issue in issues)


def test_denylisted_label_detected() -> None:
    catalog_metric = _metric(
        "geosync_with_denylist_total",
        labels=["request_id"],
    )
    code_metric = mv.CodeMetric(
        name=catalog_metric.name,
        type="counter",
        description=catalog_metric.description,
        labels=tuple(catalog_metric.labels),
        sources=("source.py",),
    )

    issues = mv.structural_issues(
        {catalog_metric.name: catalog_metric}, {catalog_metric.name: code_metric}
    )

    assert any(issue["code"] == "denylisted_label" for issue in issues)


def test_dead_metric_is_reported(tmp_path: Path) -> None:
    module = tmp_path / "dead_metric.py"
    module.write_text(
        "\n".join(
            [
                "from prometheus_client import Counter",
                'dead = Counter("geosync_dead_total", "Dead metric")',
            ]
        ),
        encoding="utf-8",
    )

    code_metrics = mv.discover_code_metrics(tmp_path)
    dead = mv.find_dead_metrics(tmp_path, code_metrics)

    assert any(entry["metric"] == "geosync_dead_total" for entry in dead)


def test_whitelisted_metrics_not_reported(tmp_path: Path) -> None:
    module = tmp_path / "whitelisted_metric.py"
    module.write_text(
        "\n".join(
            [
                "from prometheus_client import Gauge",
                'g = Gauge("geosync_api_requests_in_flight", "whitelisted", ["route", "method"])',
            ]
        ),
        encoding="utf-8",
    )

    code_metrics = mv.discover_code_metrics(tmp_path)
    dead = mv.find_dead_metrics(tmp_path, code_metrics)

    assert all(entry["metric"] != "geosync_api_requests_in_flight" for entry in dead)


def test_known_good_catalog_subset_passes(tmp_path: Path) -> None:
    module = tmp_path / "live_metric.py"
    module.write_text(
        "\n".join(
            [
                "from prometheus_client import Counter",
                'live = Counter("geosync_live_total", "Live metric with updates")',
                "def tick():",
                "    live.inc()",
            ]
        ),
        encoding="utf-8",
    )

    code_metrics = mv.discover_code_metrics(tmp_path)
    catalog_metric = _metric("geosync_live_total")

    issues = mv.structural_issues({catalog_metric.name: catalog_metric}, code_metrics)
    dead = mv.find_dead_metrics(tmp_path, code_metrics)

    assert issues == []
    assert dead == []
