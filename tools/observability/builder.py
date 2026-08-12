# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Build artifacts for the observability-as-code workflow."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


class ObservabilityConfigError(ValueError):
    """Raised when the observability definitions are invalid."""


METRIC_NAME_RE = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_:]*$")
METRIC_TOKEN_RE = re.compile(r"[a-zA-Z_:][a-zA-Z0-9_:]*")
ALLOWED_METRIC_TYPES = {"counter", "gauge", "histogram", "summary"}


@dataclass
class MetricDefinition:
    """Representation of a metric defined in ``metrics.json``."""

    name: str
    type: str
    description: str
    labels: Sequence[str]
    subsystem: str


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - defensive guard
        raise ObservabilityConfigError(f"Missing configuration file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ObservabilityConfigError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ObservabilityConfigError(f"Configuration in {path} must be a JSON object")
    return payload


def _validate_labels(labels: Any, *, path: Path) -> List[str]:
    if labels is None:
        return []
    if not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
        raise ObservabilityConfigError(f"Metric labels must be a list of strings in {path}")
    if len({label for label in labels}) != len(labels):
        raise ObservabilityConfigError(f"Duplicate label names found in {path}")
    return labels


def validate_metrics(path: Path) -> List[MetricDefinition]:
    """Validate and normalise metric definitions."""

    payload = _load_json(path)
    metrics = payload.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        raise ObservabilityConfigError("metrics.json must define a non-empty `metrics` array")

    seen: set[str] = set()
    validated: List[MetricDefinition] = []
    for entry in metrics:
        if not isinstance(entry, dict):
            raise ObservabilityConfigError("Each metric definition must be an object")

        name = entry.get("name")
        if not isinstance(name, str) or not METRIC_NAME_RE.match(name):
            raise ObservabilityConfigError(f"Invalid metric name: {name!r}")
        if name in seen:
            raise ObservabilityConfigError(f"Duplicate metric definition detected: {name}")
        seen.add(name)

        metric_type = entry.get("type")
        if metric_type not in ALLOWED_METRIC_TYPES:
            raise ObservabilityConfigError(
                f"Metric {name} has unsupported type {metric_type!r}. "
                f"Allowed types: {', '.join(sorted(ALLOWED_METRIC_TYPES))}."
            )

        description = entry.get("description")
        if not isinstance(description, str) or not description.strip():
            raise ObservabilityConfigError(f"Metric {name} must include a description")

        subsystem = entry.get("subsystem")
        if not isinstance(subsystem, str) or not subsystem.strip():
            raise ObservabilityConfigError(f"Metric {name} must define a subsystem")

        labels = _validate_labels(entry.get("labels"), path=path)
        validated.append(
            MetricDefinition(
                name=name,
                type=metric_type,
                description=description.strip(),
                labels=labels,
                subsystem=subsystem.strip(),
            )
        )

    return validated


def _extract_metric_tokens(expr: str) -> Iterable[str]:
    suffixes = ("_bucket", "_count", "_sum")
    for token in METRIC_TOKEN_RE.findall(expr):
        if not token.startswith("geosync_"):
            continue
        base = token
        for suffix in suffixes:
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        yield base


def validate_alerts(path: Path, metric_names: Iterable[str]) -> Dict[str, Any]:
    """Validate alert definitions and ensure they reference known metrics."""

    payload = _load_json(path)
    groups = payload.get("groups")
    if not isinstance(groups, list) or not groups:
        raise ObservabilityConfigError("alerts.json must define a non-empty `groups` array")

    metric_name_set = set(metric_names)
    for group in groups:
        if not isinstance(group, dict):
            raise ObservabilityConfigError("Each alert group must be an object")
        if not isinstance(group.get("name"), str) or not group["name"].strip():
            raise ObservabilityConfigError("Each alert group requires a non-empty name")

        rules = group.get("rules")
        if not isinstance(rules, list) or not rules:
            raise ObservabilityConfigError(
                f"Alert group {group.get('name', '<unknown>')} must contain at least one rule"
            )

        for rule in rules:
            if not isinstance(rule, dict):
                raise ObservabilityConfigError("Each alert rule must be an object")
            alert_name = rule.get("alert")
            if not isinstance(alert_name, str) or not alert_name.strip():
                raise ObservabilityConfigError("Alert rules must define an `alert` name")
            expr = rule.get("expr")
            if not isinstance(expr, str) or not expr.strip():
                raise ObservabilityConfigError(f"Alert {alert_name} must define an expression")

            tokens = set(_extract_metric_tokens(expr))
            unknown = tokens - metric_name_set
            if unknown:
                raise ObservabilityConfigError(
                    f"Alert {alert_name} references unknown metrics: {', '.join(sorted(unknown))}"
                )

            labels = rule.get("labels", {})
            if labels is not None and not isinstance(labels, dict):
                raise ObservabilityConfigError(f"Alert {alert_name} labels must be an object")
            annotations = rule.get("annotations", {})
            if annotations is not None and not isinstance(annotations, dict):
                raise ObservabilityConfigError(f"Alert {alert_name} annotations must be an object")

    return payload


def _validate_dashboard_payload(payload: Dict[str, Any], source: Path) -> Dict[str, Any]:
    required_fields = ["uid", "title", "panels"]
    for field in required_fields:
        if field not in payload:
            raise ObservabilityConfigError(
                f"Dashboard {source.name} missing required field {field!r}"
            )

    if not isinstance(payload["uid"], str) or not payload["uid"].strip():
        raise ObservabilityConfigError(f"Dashboard {source.name} must define a non-empty uid")
    if not isinstance(payload["title"], str) or not payload["title"].strip():
        raise ObservabilityConfigError(f"Dashboard {source.name} must define a non-empty title")
    if not isinstance(payload["panels"], list) or not payload["panels"]:
        raise ObservabilityConfigError(f"Dashboard {source.name} requires at least one panel")

    return payload


def load_dashboards(root: Path) -> List[Dict[str, Any]]:
    dashboards: List[Dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        payload = _load_json(path)
        dashboards.append(_validate_dashboard_payload(payload, path))

    if not dashboards:
        raise ObservabilityConfigError(
            "No dashboards found. Provide at least one JSON dashboard definition."
        )

    uids = [dashboard["uid"] for dashboard in dashboards]
    if len(set(uids)) != len(uids):
        raise ObservabilityConfigError("Dashboard UIDs must be unique")

    return dashboards


_YAML_QUOTED_LITERALS = {
    "true",
    "false",
    "null",
    "~",
    "yes",
    "no",
    "on",
    "off",
}


def _needs_yaml_quotes(value: str) -> bool:
    if value == "":
        return True
    if value != value.strip():
        return True
    if value.lower() in _YAML_QUOTED_LITERALS:
        return True
    if any(ch in value for ch in ":\n#{}[],&*?|-<>=!%@\\"):
        return True
    if value[0] in "-?:@&*!|>'\"%{}[],":
        return True
    return False


def _format_yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        if _needs_yaml_quotes(value):
            return json.dumps(value)
        return value
    return json.dumps(value)


def _dump_yaml(data: Any, indent: int = 0) -> List[str]:
    """Very small YAML encoder suited for Prometheus rules output."""

    lines: List[str] = []
    prefix = " " * indent
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.extend(_dump_yaml(value, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {_format_yaml_scalar(value)}")
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}-")
                lines.extend(_dump_yaml(item, indent + 2))
            else:
                lines.append(f"{prefix}- {_format_yaml_scalar(item)}")
    else:
        lines.append(f"{prefix}{_format_yaml_scalar(data)}")
    return lines


def _render_prometheus_rules(alerts: Dict[str, Any]) -> str:
    return "\n".join(_dump_yaml({"groups": alerts["groups"]})) + "\n"


def build_bundle(root: Path, output_dir: Path) -> Dict[str, Any]:
    """Compile observability definitions into generated artifacts."""

    metrics = validate_metrics(root / "metrics.json")
    alerts = validate_alerts(root / "alerts.json", (metric.name for metric in metrics))
    dashboards = load_dashboards(root / "dashboards")

    output_dir.mkdir(parents=True, exist_ok=True)
    prom_dir = output_dir / "prometheus"
    grafana_dir = output_dir / "dashboards"
    prom_dir.mkdir(parents=True, exist_ok=True)
    grafana_dir.mkdir(parents=True, exist_ok=True)

    prom_rules = _render_prometheus_rules(alerts)
    (prom_dir / "alerts.yaml").write_text(prom_rules, encoding="utf-8")

    for dashboard in dashboards:
        uid = dashboard["uid"]
        path = grafana_dir / f"{uid}.json"
        path.write_text(json.dumps(dashboard, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest = {
        "metrics": [metric.__dict__ for metric in metrics],
        "alerts": alerts["groups"],
        "dashboards": [dashboard["uid"] for dashboard in dashboards],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    return manifest


def _default_root() -> Path:
    return Path(__file__).resolve().parents[2] / "observability"


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compile observability definitions into artifacts")
    parser.add_argument(
        "--root",
        type=Path,
        default=_default_root(),
        help="Root folder containing observability definitions",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_default_root() / "generated",
        help="Target folder for generated artifacts",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    manifest = build_bundle(args.root, args.output_dir)
    print(
        "Generated observability bundle with "
        f"{len(manifest['metrics'])} metrics, "
        f"{sum(len(group['rules']) for group in manifest['alerts'])} alerts, "
        f"{len(manifest['dashboards'])} dashboards"
    )


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    main()
