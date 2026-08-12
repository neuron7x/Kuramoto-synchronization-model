# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
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

_METRIC_PREFIXES = ("geosync_", "cortex_")
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
    "order_id",
    "raw_path",
    "address",
    "uid",
}


@dataclass(frozen=True, slots=True)
class CodeMetric:
    """Representation of a metric discovered in Python sources."""

    name: str
    type: str
    description: str
    labels: tuple[str, ...]
    sources: tuple[str, ...]
    bindings: tuple[str, ...] = ()


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


def _binding_names(target: ast.AST) -> tuple[str, ...]:
    """Return possible binding identifiers for an assignment target."""

    if isinstance(target, ast.Name):
        return (target.id,)
    if isinstance(target, ast.Attribute):
        parts: list[str] = []
        current: ast.AST | None = target
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        parts = list(reversed(parts))
        dotted = ".".join(parts)
        if dotted.startswith("self."):
            return (dotted, dotted[len("self.") :], parts[-1])
        return (dotted,)
    if isinstance(target, ast.Tuple):
        names: list[str] = []
        for element in target.elts:
            names.extend(_binding_names(element))
        return tuple(names)
    return ()


def discover_code_metrics(root: Path) -> dict[str, CodeMetric]:
    """Parse Python sources to discover Prometheus metric declarations."""

    metrics: dict[str, CodeMetric] = {}
    for path in root.rglob("*.py"):
        parents: dict[ast.AST, ast.AST] = {}
        try:
            content = path.read_text(encoding="utf-8")
            tree = ast.parse(content)
        except (UnicodeDecodeError, SyntaxError, OSError):
            continue

        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node

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
            bindings: tuple[str, ...] = ()

            parent = parents.get(node)
            if isinstance(parent, (ast.Assign, ast.AnnAssign)):
                targets: list[ast.AST] = []
                if isinstance(parent, ast.Assign):
                    targets = list(parent.targets)
                elif isinstance(parent, ast.AnnAssign) and parent.target is not None:
                    targets = [parent.target]
                binding_names: list[str] = []
                for target in targets:
                    binding_names.extend(_binding_names(target))
                bindings = tuple(sorted(set(binding_names)))

            existing = metrics.get(metric_name)
            if existing:
                merged_sources = tuple(sorted(set(existing.sources + (str(path),))))
                merged_labels = existing.labels or labels
                merged_bindings = tuple(sorted(set(existing.bindings + bindings)))
                metrics[metric_name] = CodeMetric(
                    name=metric_name,
                    type=existing.type,
                    description=existing.description or description,
                    labels=merged_labels,
                    sources=merged_sources,
                    bindings=merged_bindings,
                )
            else:
                metrics[metric_name] = CodeMetric(
                    name=metric_name,
                    type=metric_type,
                    description=description,
                    labels=tuple(labels),
                    sources=(str(path),),
                    bindings=bindings,
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
    ratio_pattern = re.compile(r"(^|_)ratio($|_)")
    if ratio_pattern.search(metric.name) and not metric.name.endswith("_ratio"):
        issues.append("ratio metrics should end with _ratio")
    return issues


_DEAD_METRIC_WHITELIST = frozenset(
    {
        # Metrics updated indirectly via helper methods or background samplers.
        "geosync_api_requests_in_flight",
        "geosync_model_inference_latency_quantiles_seconds",
        "geosync_data_ingestion_latency_quantiles_seconds",
        "geosync_order_submission_latency_quantiles_seconds",
        "geosync_order_ack_latency_quantiles_seconds",
        "geosync_order_fill_latency_quantiles_seconds",
        "geosync_signal_to_fill_latency_quantiles_seconds",
        "geosync_signal_generation_latency_quantiles_seconds",
        "geosync_optimization_duration_seconds",
        "geosync_optimization_iterations_total",
    }
)

_UPDATE_METHODS = {
    "counter": {"inc"},
    "gauge": {"inc", "dec", "set"},
    "histogram": {"observe"},
    "summary": {"observe"},
}


def _attribute_chain(node: ast.AST | None) -> str | None:
    parts: list[str] = []
    current = node
    while current is not None:
        if isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
            continue
        if isinstance(current, ast.Call):
            current = current.func
            continue
        if isinstance(current, ast.Name):
            parts.append(current.id)
            return ".".join(reversed(parts))
        break
    return None


def _binding_index(code_metrics: Mapping[str, CodeMetric]) -> dict[str, tuple[str, str]]:
    index: dict[str, tuple[str, str]] = {}
    for metric in code_metrics.values():
        for binding in metric.bindings:
            index[binding] = (metric.name, metric.type)
    return index


def _match_binding(
    chain: str | None, index: Mapping[str, tuple[str, str]]
) -> tuple[str, str] | None:
    if chain is None:
        return None
    candidates = set()
    candidates.add(chain)
    if chain.startswith("self."):
        candidates.add(chain[len("self.") :])
    segments = chain.split(".")
    for idx in range(len(segments), 0, -1):
        candidates.add(".".join(segments[:idx]))
    for candidate in candidates:
        if candidate in index:
            return index[candidate]
    return None


def find_dead_metrics(
    root: Path, code_metrics: Mapping[str, CodeMetric]
) -> list[dict[str, object]]:
    """Return metrics that are declared but never updated."""

    index = _binding_index(code_metrics)
    used: set[str] = set()
    allowed_methods = {method for methods in _UPDATE_METHODS.values() for method in methods}

    for path in root.rglob("*.py"):
        try:
            content = path.read_text(encoding="utf-8")
            tree = ast.parse(content)
        except (UnicodeDecodeError, SyntaxError, OSError):
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = node.func
            if not isinstance(target, ast.Attribute):
                continue
            method = target.attr
            if method not in allowed_methods:
                continue
            chain = _attribute_chain(target.value)
            match = _match_binding(chain, index)
            if match is None:
                continue
            metric_name, metric_type = match
            if method not in _UPDATE_METHODS.get(metric_type, allowed_methods):
                continue
            used.add(metric_name)

    dead: list[dict[str, object]] = []
    for metric in code_metrics.values():
        if metric.name in _DEAD_METRIC_WHITELIST:
            continue
        if metric.name not in used:
            dead.append(
                {
                    "metric": metric.name,
                    "metric_name": metric.name,
                    "sources": sorted(set(metric.sources)),
                }
            )
    return dead


def _issue(
    metric: str, code: str, message: str, sources: Sequence[str] | None
) -> dict[str, object]:
    return {
        "metric": metric,
        "metric_name": metric,
        "code": code,
        "message": message,
        "sources": sorted(set(sources or ())),
    }


def structural_issues(
    catalog: Mapping[str, MetricDefinition], code_metrics: Mapping[str, CodeMetric]
) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    code_names = set(code_metrics)

    for name, metric in catalog.items():
        code_metric = code_metrics.get(name)
        sources = code_metric.sources if code_metric else ()

        if len(metric.description.strip()) <= 8:
            issues.append(
                _issue(
                    name,
                    "description_too_short",
                    "metric description must be longer than 8 characters",
                    sources,
                )
            )

        type_mismatches = _validate_naming(metric)
        for mismatch in type_mismatches:
            issues.append(_issue(name, "naming", mismatch, sources))

        denylisted = [label for label in metric.labels if label.lower() in _HIGH_CARDINALITY_LABELS]
        if denylisted:
            issues.append(
                _issue(
                    name,
                    "denylisted_label",
                    f"denylisted labels present: {', '.join(sorted(denylisted))}",
                    sources,
                )
            )

        if code_metric is None:
            issues.append(
                _issue(
                    name,
                    "missing_in_code",
                    "metric not found in code inventory",
                    (),
                )
            )
            continue

        if metric.type != code_metric.type:
            issues.append(
                _issue(
                    name,
                    "type_mismatch",
                    f"type mismatch: catalog={metric.type} code={code_metric.type}",
                    sources,
                )
            )

        if tuple(metric.labels) != tuple(code_metric.labels):
            issues.append(
                _issue(
                    name,
                    "label_mismatch",
                    f"label mismatch: catalog={metric.labels} code={list(code_metric.labels)}",
                    sources,
                )
            )

        code_names.discard(name)

    for orphan in sorted(code_names):
        issues.append(
            _issue(
                orphan,
                "missing_in_catalog",
                "metric declared in code is missing from catalog",
                code_metrics[orphan].sources,
            )
        )

    return issues


def summarise_catalog(catalog: Mapping[str, MetricDefinition]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for metric in catalog.values():
        counts[metric.type] = counts.get(metric.type, 0) + 1
    return counts


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
