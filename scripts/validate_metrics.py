#!/usr/bin/env python
"""CLI entrypoint for metrics validation."""

from __future__ import annotations

import argparse
import importlib.util
import math
import json
import os
import sys
from pathlib import Path
from typing import Mapping

from fastapi.testclient import TestClient
try:
    from prometheus_client.parser import text_string_to_metric_families
except ImportError:  # pragma: no cover - fallback for older prometheus_client versions
    text_string_to_metric_families = None

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.observability.builder import MetricDefinition, validate_metrics  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "metrics_validation", ROOT / "observability" / "metrics_validation.py"
)
_METRICS_VALIDATION = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
sys.modules[_spec.name] = _METRICS_VALIDATION
_spec.loader.exec_module(_METRICS_VALIDATION)

compare_catalog_to_code = _METRICS_VALIDATION.compare_catalog_to_code
discover_code_metrics = _METRICS_VALIDATION.discover_code_metrics
find_dead_metrics = _METRICS_VALIDATION.find_dead_metrics
reconcile_catalog = _METRICS_VALIDATION.reconcile_catalog
registry_smoke_test = _METRICS_VALIDATION.registry_smoke_test
structural_issues = _METRICS_VALIDATION.structural_issues
summarise_catalog = _METRICS_VALIDATION.summarise_catalog
write_artifact = _METRICS_VALIDATION.write_artifact

ARTIFACT_DIR = Path(os.environ.get("METRICS_VALIDATION_ARTIFACT_DIR", "artifacts/metrics-validation"))


def _default_catalogs() -> list[Path]:
    return [Path("observability/metrics.json")]


def run_sync(root: Path, catalogs: list[Path]) -> int:
    code_metrics = discover_code_metrics(root)
    catalog_defs: list[MetricDefinition] = []
    for catalog_path in catalogs:
        catalog_defs.extend(validate_metrics(catalog_path))
    catalog_map = {metric.name: metric for metric in catalog_defs}

    comparison = compare_catalog_to_code(catalog_map, code_metrics)
    reconciled = reconcile_catalog(code_metrics, catalog_defs)
    write_artifact(
        ARTIFACT_DIR / "sync.json",
        {"drift": comparison, "catalog_size": len(reconciled)},
    )

    return 0 if not (comparison["missing_in_catalog"] or comparison["missing_in_code"]) else 1


def run_structural(root: Path, catalogs: list[Path]) -> int:
    code_metrics = discover_code_metrics(root)
    catalog_defs: list[MetricDefinition] = []
    for catalog_path in catalogs:
        catalog_defs.extend(validate_metrics(catalog_path))
    catalog_map = {metric.name: metric for metric in catalog_defs}

    issues = structural_issues(catalog_map, code_metrics)
    dead_metrics = find_dead_metrics(root, code_metrics)
    registry_errors = registry_smoke_test(catalog_defs)
    write_artifact(
        ARTIFACT_DIR / "structural.json",
        {
            "issues": issues,
            "dead_metrics": dead_metrics,
            "registry_errors": registry_errors,
            "catalog_summary": summarise_catalog(catalog_map),
        },
    )
    return 0 if not issues and not registry_errors and not dead_metrics else 1


def _parse_metrics_payload(payload: str) -> dict[str, list[dict[str, object]]]:
    if text_string_to_metric_families is not None:
        parsed: dict[str, list[dict[str, object]]] = {}
        for family in text_string_to_metric_families(payload):
            parsed.setdefault(family.name, [])
            for sample in family.samples:
                record = {"labels": dict(sample.labels or {}), "value": float(sample.value)}
                parsed[family.name].append(record)
                if sample.name != family.name:
                    parsed.setdefault(sample.name, []).append(record)
        return parsed

    metrics: dict[str, list[dict[str, object]]] = {}
    for line in payload.splitlines():
        if not line or line.startswith("#"):
            continue
        try:
            left, value = line.strip().rsplit(" ", 1)
            value_f = float(value)
        except ValueError:
            continue
        if "{" in left and left.endswith("}"):
            name, raw_labels = left.split("{", 1)
            labels = {}
            raw_labels = raw_labels[:-1]
            for entry in raw_labels.split(","):
                if not entry:
                    continue
                if "=" not in entry:
                    continue
                key, raw_val = entry.split("=", 1)
                labels[key.strip()] = raw_val.strip().strip('"')
        else:
            name = left
            labels = {}
        metrics.setdefault(name, []).append({"labels": labels, "value": value_f})
    return metrics


def _sample_value(
    metrics: dict[str, list[dict[str, object]]],
    name: str,
    labels: Mapping[str, str] | None = None,
    default: float | None = None,
) -> float | None:
    samples = metrics.get(name, [])
    for sample in samples:
        sample_labels = sample.get("labels", {})
        if labels is None or dict(labels) == sample_labels:
            return float(sample["value"])
    return default


def _validate_regression_baselines(root: Path) -> list[str]:
    path = root / "configs" / "nightly" / "baselines.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"failed to parse baselines.json: {exc}"]

    errors: list[str] = []
    backtests = payload.get("backtests", {})
    for scenario_name, scenario in backtests.items():
        thresholds = scenario.get("thresholds", {})
        if not isinstance(thresholds, dict):
            errors.append(f"{scenario_name}: thresholds must be an object")
            continue
        for metric_name, cfg in thresholds.items():
            if not isinstance(cfg, dict):
                errors.append(f"{scenario_name}.{metric_name}: threshold must be an object")
                continue
            for key in ("max_relative_change", "max_absolute_change"):
                if key in cfg and cfg[key] is not None and cfg[key] < 0:
                    errors.append(f"{scenario_name}.{metric_name}: {key} cannot be negative")
            for bound in ("min_value", "max_value"):
                if bound in cfg and cfg[bound] is not None and not isinstance(
                    cfg[bound], (int, float)
                ):
                    errors.append(f"{scenario_name}.{metric_name}: {bound} must be numeric when set")
    return errors


def run_runtime(root: Path, catalogs: list[Path]) -> int:
    # The application factory requires audit secrets; default to safe values.
    env = os.environ
    env.setdefault("TRADEPULSE_AUDIT_SECRET", "0" * 16)
    env.setdefault("TRADEPULSE_RBAC_AUDIT_SECRET", "1" * 32)
    env.setdefault("TRADEPULSE_TWO_FACTOR_SECRET", "2" * 32)

    from application.api.service import create_app

    app = create_app()
    client = TestClient(app)

    request_trace: list[str] = []
    collector = getattr(app.state, "metrics", None)
    if collector is not None and getattr(collector, "enabled", False):
        try:
            collector.set_process_resource_usage(
                "runtime", cpu_percent=0.0, memory_bytes=0.0, memory_percent=0.0
            )
        except Exception:
            request_trace.append("collector.set_process_resource_usage_failed")

    def _scrape() -> tuple[str, dict[str, list[dict[str, object]]]]:
        response = client.get("/metrics")
        request_trace.append("/metrics")
        response.raise_for_status()
        body = response.text
        return body, _parse_metrics_payload(body)

    baseline_text, baseline_metrics = _scrape()
    first_health = client.get("/health")
    request_trace.append("/health")
    second_health = client.get("/health")
    request_trace.append("/health")
    metrics_after_text, metrics_after = _scrape()

    collector = getattr(app.state, "metrics", None)
    if collector is not None and getattr(collector, "enabled", False):
        request_trace.append("collector.record_tick_processed")
        try:
            collector.record_tick_processed("runtime", "TEST", count=2)
        except Exception:
            request_trace.append("collector.record_tick_processed_failed")
    final_metrics_text, final_metrics = _scrape()

    labels_health = {"route": "/health", "method": "GET"}
    status_labels = {"route": "/health", "method": "GET", "status": "200"}

    requests_before = _sample_value(
        baseline_metrics, "tradepulse_api_requests_total", status_labels, default=0.0
    )
    requests_after = _sample_value(
        metrics_after, "tradepulse_api_requests_total", status_labels, default=0.0
    )
    latency_before = _sample_value(
        baseline_metrics,
        "tradepulse_api_request_latency_seconds_count",
        labels_health,
        default=0.0,
    )
    latency_after = _sample_value(
        metrics_after,
        "tradepulse_api_request_latency_seconds_count",
        labels_health,
        default=0.0,
    )
    latency_sum = _sample_value(
        metrics_after,
        "tradepulse_api_request_latency_seconds_sum",
        labels_health,
    )

    inflight_value = _sample_value(
        metrics_after, "tradepulse_api_requests_in_flight", labels_health
    )

    queue_depth_samples = [
        sample["value"]
        for sample in final_metrics.get("tradepulse_api_queue_depth", [])
        if isinstance(sample.get("value"), (int, float))
    ]

    ticks_before = _sample_value(
        metrics_after,
        "tradepulse_ticks_processed_total",
        {"source": "runtime", "symbol": "TEST"},
        default=0.0,
    )
    ticks_after = _sample_value(
        final_metrics,
        "tradepulse_ticks_processed_total",
        {"source": "runtime", "symbol": "TEST"},
        default=0.0,
    )

    deltas = {
        "tradepulse_api_requests_total": None
        if requests_before is None or requests_after is None
        else requests_after - requests_before,
        "tradepulse_api_request_latency_seconds_count": None
        if latency_before is None or latency_after is None
        else latency_after - latency_before,
        "tradepulse_ticks_processed_total": ticks_after - ticks_before
        if ticks_after is not None and ticks_before is not None
        else None,
    }

    invariants = {
        "health_counter_incremented": deltas["tradepulse_api_requests_total"] is not None
        and deltas["tradepulse_api_requests_total"] >= 2,
        "health_latency_incremented": deltas["tradepulse_api_request_latency_seconds_count"] is not None
        and deltas["tradepulse_api_request_latency_seconds_count"] >= 2,
        "latency_finite": latency_sum is None or (math.isfinite(latency_sum) and latency_sum >= 0),
        "inflight_finite": inflight_value is None
        or (math.isfinite(float(inflight_value)) and float(inflight_value) >= 0.0),
        "queue_depth_finite": not queue_depth_samples
        or all(math.isfinite(float(value)) and float(value) >= 0 for value in queue_depth_samples),
        "non_api_metric_delta": deltas["tradepulse_ticks_processed_total"] is not None
        and deltas["tradepulse_ticks_processed_total"] > 0,
    }

    results: dict[str, object] = {
        "health_statuses": [first_health.status_code, second_health.status_code],
        "request_trace": request_trace,
        "metric_deltas": deltas,
        "invariants": invariants,
        "snapshots": {
            "baseline": baseline_text,
            "after_health": metrics_after_text,
            "final": final_metrics_text,
        },
    }

    write_artifact(ARTIFACT_DIR / "runtime.json", results)
    invariant_pass = all(invariants.values())
    health_pass = all(status == 200 for status in results["health_statuses"])
    return 0 if health_pass and invariant_pass else 1


def run_expectations(
    root: Path, catalogs: list[Path], *, with_regression_baseline_check: bool = False
) -> int:
    expectations_path = root / "observability" / "metrics_expectations.json"
    try:
        expectations = json.loads(expectations_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - defensive
        write_artifact(
            ARTIFACT_DIR / "expectations.json",
            {"issues": [{"code": "load_error", "message": str(exc), "metric": None}]},
        )
        return 1

    env = os.environ
    env.setdefault("TRADEPULSE_AUDIT_SECRET", "0" * 16)
    env.setdefault("TRADEPULSE_RBAC_AUDIT_SECRET", "1" * 32)
    env.setdefault("TRADEPULSE_TWO_FACTOR_SECRET", "2" * 32)

    snapshots: list[dict[str, list[dict[str, object]]]] = []
    runtime_artifact = ARTIFACT_DIR / "runtime.json"
    if runtime_artifact.exists():
        runtime_data = json.loads(runtime_artifact.read_text(encoding="utf-8"))
        snap_payloads = runtime_data.get("snapshots", {})
        for key in ("baseline", "final"):
            payload = snap_payloads.get(key)
            if isinstance(payload, str):
                snapshots.append(_parse_metrics_payload(payload))
    if len(snapshots) < 2:
        from application.api.service import create_app

        app = create_app()
        client = TestClient(app)
        collector = getattr(app.state, "metrics", None)
        if collector is not None and getattr(collector, "enabled", False):
            collector.set_process_resource_usage(
                "runtime", cpu_percent=0.0, memory_bytes=0.0, memory_percent=0.0
            )
        for _ in range(2):
            response = client.get("/metrics")
            response.raise_for_status()
            snapshots.append(_parse_metrics_payload(response.text))

    if len(snapshots) >= 2:
        first, second = snapshots[0], snapshots[1]
    else:
        first = second = snapshots[0] if snapshots else {}

    issues: list[dict[str, object]] = []
    for metric_name, rule in expectations.items():
        samples_first = first.get(metric_name, [])
        samples_second = second.get(metric_name, [])
        if not samples_second:
            issues.append(
                {
                    "metric": metric_name,
                    "code": "missing",
                    "message": "metric missing from scrape",
                }
            )
            continue

        if rule.get("finite"):
            for sample in samples_second:
                value = float(sample["value"])
                if not math.isfinite(value):
                    issues.append(
                        {
                            "metric": metric_name,
                            "code": "non_finite",
                            "message": "metric value is not finite",
                        }
                    )
                    break

        lower = rule.get("min")
        upper = rule.get("max")
        if lower is not None or upper is not None:
            for sample in samples_second:
                value = float(sample["value"])
                if lower is not None and value < lower:
                    issues.append(
                        {
                            "metric": metric_name,
                            "code": "below_min",
                            "message": f"value {value} below minimum {lower}",
                        }
                    )
                    break
                if upper is not None and value > upper:
                    issues.append(
                        {
                            "metric": metric_name,
                            "code": "above_max",
                            "message": f"value {value} exceeds maximum {upper}",
                        }
                    )
                    break

        if rule.get("monotonic"):
            first_total = sum(float(sample["value"]) for sample in samples_first)
            second_total = sum(float(sample["value"]) for sample in samples_second)
            if second_total < first_total:
                issues.append(
                    {
                        "metric": metric_name,
                        "code": "monotonicity",
                        "message": "counter decreased between scrapes",
                    }
                )

    baseline_errors: list[str] = []
    if with_regression_baseline_check:
        baseline_errors = _validate_regression_baselines(root)
        if baseline_errors:
            issues.extend(
                [
                    {
                        "metric": "<regression_baseline>",
                        "code": "baseline_invalid",
                        "message": error,
                    }
                    for error in baseline_errors
                ]
            )

    write_artifact(
        ARTIFACT_DIR / "expectations.json",
        {
            "issues": issues,
            "regression_baseline_errors": baseline_errors,
        },
    )
    return 0 if not issues else 1


def _write_report(statuses: dict[str, int]) -> None:
    lines = ["# Metrics Validation Report", ""]
    for level, exit_code in statuses.items():
        state = "PASS" if exit_code == 0 else "FAIL"
        lines.append(f"- {level}: {state}")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_artifact(ARTIFACT_DIR / "report.json", {"statuses": statuses})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate TradePulse metrics")
    parser.add_argument(
        "--level",
        action="append",
        choices=["sync", "structural", "runtime", "expectations"],
        help="Validation level(s) to execute",
    )
    parser.add_argument(
        "--catalog",
        action="append",
        type=Path,
        help="Additional metrics catalog JSON file",
    )
    parser.add_argument(
        "--with-regression-baseline-check",
        action="store_true",
        help="Validate nightly regression baseline structure",
    )
    args = parser.parse_args(argv)
    levels = args.level or ["sync", "structural", "runtime", "expectations"]
    catalogs = args.catalog or _default_catalogs()
    root = Path(__file__).resolve().parents[1]
    with_baseline_check = bool(getattr(args, "with_regression_baseline_check", False))

    status = 0
    level_status: dict[str, int] = {}
    for level in levels:
        if level == "sync":
            result = run_sync(root, catalogs)
        elif level == "structural":
            result = run_structural(root, catalogs)
        elif level == "runtime":
            result = run_runtime(root, catalogs)
        elif level == "expectations":
            result = run_expectations(
                root,
                catalogs,
                with_regression_baseline_check=with_baseline_check,
            )
        else:
            continue
        level_status[level] = result
        status |= result

    if level_status:
        _write_report(level_status)
    return status


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
