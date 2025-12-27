"""Utilities for validating Prometheus metric definitions and runtime exposure."""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from tools.observability.builder import MetricDefinition, validate_metrics

_METRIC_PREFIXES = ("tradepulse_", "cortex_")
_METRIC_TYPES = {"Counter", "Gauge", "Histogram", "Summary"}
_HIGH_CARDINALITY_LABELS = {
    "id",
    "request_id",
    "trace_id",
    "span_id",
    "session",
    "session_id",
    "user",
    "user_id",
    "hash",
    "token",
    "uuid",
}


@dataclass(frozen=True, slots=True)
class CodeMetric:
    """Representation of a metric discovered in Python sources."""

    name: str
    type: str
    description: str
    labels: tuple[str, ...]
    sources: tuple[str, ...]


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _extract_labels(node: ast.Call) -> tuple[str, ...]:
    if len(node.args) >= 3:
        candidate = node.args[2]
        if isinstance(candidate, (ast.List, ast.Tuple)):
            values = [
                element.value
                for element in candidate.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            ]
            if values:
                return tuple(values)

    for kw in node.keywords or []:
        if kw.arg == "labelnames" and isinstance(kw.value, (ast.List, ast.Tuple)):
            values = [
                element.value
                for element in kw.value.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            ]
            if values:
                return tuple(values)

    return ()


def _extract_description(node: ast.Call) -> str:
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
        value = node.args[1].value
        if isinstance(value, str):
            return value.strip()
    return ""


def discover_code_metrics(root: Path) -> dict[str, CodeMetric]:
    """Parse Python sources to discover Prometheus metric declarations."""

    metrics: dict[str, CodeMetric] = {}
    for path in root.rglob("*.py"):
        try:
            content = path.read_text(encoding="utf-8")
            tree = ast.parse(content)
        except (UnicodeDecodeError, SyntaxError, OSError):
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node.func)
            if name not in _METRIC_TYPES:
                continue
            if not node.args:
                continue
            metric_name_node = node.args[0]
            if not isinstance(metric_name_node, ast.Constant):
                continue
            metric_name = metric_name_node.value
            if not isinstance(metric_name, str):
                continue
            if not metric_name.startswith(_METRIC_PREFIXES):
                continue
            metric_type = name.lower()
            description = _extract_description(node)
            labels = _extract_labels(node)

            existing = metrics.get(metric_name)
            if existing:
                merged_sources = tuple(sorted(set(existing.sources + (str(path),))))
                merged_labels = existing.labels or labels
                metrics[metric_name] = CodeMetric(
                    name=metric_name,
                    type=existing.type,
                    description=existing.description or description,
                    labels=merged_labels,
                    sources=merged_sources,
                )
            else:
                metrics[metric_name] = CodeMetric(
                    name=metric_name,
                    type=metric_type,
                    description=description,
                    labels=tuple(labels),
                    sources=(str(path),),
                )
    return metrics


def load_catalog(path: Path) -> dict[str, MetricDefinition]:
    return {metric.name: metric for metric in validate_metrics(path)}


def write_artifact(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _guess_subsystem(name: str) -> str:
    stripped = name
    for prefix in _METRIC_PREFIXES:
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix) :]
            break
    token = stripped.split("_", 1)[0]
    mapping = {
        "api": "api",
        "process": "observability",
        "feature": "features",
        "indicator": "indicators",
        "backtest": "backtest",
        "data": "data",
        "ticks": "data",
        "order": "execution",
        "orders": "execution",
        "signal": "signals",
        "model": "observability",
        "response": "observability",
        "watchdog": "operations",
        "health": "observability",
        "database": "database",
        "cache": "cache",
        "risk": "risk",
        "trading": "trading",
        "drawdown": "risk",
        "environment": "operations",
        "regression": "observability",
        "optimization": "optimization",
        "cortex": "cortex",
    }
    return mapping.get(token, token or "unspecified")


def reconcile_catalog(
    code_metrics: Mapping[str, CodeMetric], existing_catalog: Sequence[MetricDefinition]
) -> list[MetricDefinition]:
    catalog_map = {metric.name: metric for metric in existing_catalog}
    reconciled: list[MetricDefinition] = []
    for name in sorted(code_metrics):
        code_metric = code_metrics[name]
        current = catalog_map.get(name)
        subsystem = _guess_subsystem(name)
        labels = list(code_metric.labels)
        description = code_metric.description or (current.description if current else "")
        metric_type = code_metric.type
        reconciled.append(
            MetricDefinition(
                name=name,
                type=metric_type,
                description=description or f"Metric {name}",
                labels=labels,
                subsystem=subsystem if subsystem else "unspecified",
            )
        )
    return reconciled


def compare_catalog_to_code(
    catalog: Mapping[str, MetricDefinition], code_metrics: Mapping[str, CodeMetric]
) -> dict[str, list[str]]:
    catalog_names = set(catalog)
    code_names = set(code_metrics)
    return {
        "missing_in_catalog": sorted(code_names - catalog_names),
        "missing_in_code": sorted(catalog_names - code_names),
    }


def _validate_naming(metric: MetricDefinition) -> list[str]:
    issues: list[str] = []
    if metric.type == "counter" and not metric.name.endswith("_total"):
        issues.append("counter name must end with _total")
    duration_pattern = re.compile(r"(duration|latency)")
    if duration_pattern.search(metric.name) and not metric.name.endswith("_seconds"):
        issues.append("duration/latency metrics should be expressed in seconds")
    return issues


def structural_issues(
    catalog: Mapping[str, MetricDefinition], code_metrics: Mapping[str, CodeMetric]
) -> dict[str, list[str]]:
    issues: dict[str, list[str]] = {}
    for name, metric in catalog.items():
        metric_issues: list[str] = []
        code_metric = code_metrics.get(name)
        if code_metric is None:
            metric_issues.append("metric not found in code inventory")
        else:
            if metric.type != code_metric.type:
                metric_issues.append(
                    f"type mismatch: catalog={metric.type} code={code_metric.type}"
                )
            if tuple(metric.labels) != tuple(code_metric.labels):
                metric_issues.append(
                    f"label mismatch: catalog={metric.labels} code={list(code_metric.labels)}"
                )
        metric_issues.extend(_validate_naming(metric))
        denylisted = [label for label in metric.labels if label.lower() in _HIGH_CARDINALITY_LABELS]
        if denylisted:
            metric_issues.append(f"denylisted labels present: {', '.join(sorted(denylisted))}")
        if metric_issues:
            issues[name] = metric_issues
    return issues


def registry_smoke_test(definitions: Iterable[MetricDefinition]) -> list[str]:
    registry = CollectorRegistry()
    errors: list[str] = []
    for metric in definitions:
        ctor = {"counter": Counter, "gauge": Gauge, "histogram": Histogram}.get(metric.type)
        if ctor is None:
            errors.append(f"{metric.name}: unsupported type {metric.type}")
            continue
        try:
            ctor(metric.name, metric.description or metric.name, metric.labels, registry=registry)
        except Exception as exc:  # pragma: no cover - defensive
            errors.append(f"{metric.name}: failed to register ({exc})")
    return errors
