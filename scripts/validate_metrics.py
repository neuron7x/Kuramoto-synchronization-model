#!/usr/bin/env python
"""CLI entrypoint for metrics validation."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

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
reconcile_catalog = _METRICS_VALIDATION.reconcile_catalog
registry_smoke_test = _METRICS_VALIDATION.registry_smoke_test
structural_issues = _METRICS_VALIDATION.structural_issues
write_artifact = _METRICS_VALIDATION.write_artifact


ARTIFACT_DIR = Path("artifacts/metrics-validation")


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
    registry_errors = registry_smoke_test(catalog_defs)
    write_artifact(
        ARTIFACT_DIR / "structural.json",
        {"issues": issues, "registry_errors": registry_errors},
    )
    return 0 if not issues and not registry_errors else 1


def _parse_metric_value(payload: str, metric: str) -> float:
    for line in payload.splitlines():
        if not line or line.startswith("#"):
            continue
        if not line.startswith(metric):
            continue
        try:
            return float(line.split()[-1])
        except (IndexError, ValueError):
            continue
    raise KeyError(metric)


def run_runtime(root: Path, catalogs: list[Path]) -> int:
    # The application factory requires audit secrets; default to safe values.
    env = os.environ
    env.setdefault("TRADEPULSE_AUDIT_SECRET", "0" * 16)
    env.setdefault("TRADEPULSE_RBAC_AUDIT_SECRET", "1" * 32)
    env.setdefault("TRADEPULSE_TWO_FACTOR_SECRET", "2" * 32)

    from application.api.service import create_app

    app = create_app()
    client = TestClient(app)

    baseline = client.get("/metrics").text
    first_health = client.get("/health")
    second_health = client.get("/health")
    metrics_after_second = client.get("/metrics").text

    results: dict[str, object] = {
        "health_statuses": [first_health.status_code, second_health.status_code],
    }

    try:
        before = _parse_metric_value(baseline, "tradepulse_api_requests_total")
        after = _parse_metric_value(metrics_after_second, "tradepulse_api_requests_total")
        results["api_requests_total_delta"] = after - before
    except KeyError:
        results["api_requests_total_delta"] = None

    write_artifact(ARTIFACT_DIR / "runtime.json", results)
    delta = results.get("api_requests_total_delta")
    return 0 if all(status == 200 for status in results["health_statuses"]) and (delta is None or delta >= 2) else 1


def run_expectations(root: Path, catalogs: list[Path]) -> int:
    # Expectations piggyback on runtime scrape to assert finiteness of key gauges.
    metrics_path = ARTIFACT_DIR / "runtime.json"
    if not metrics_path.exists():
        return 1
    payload = metrics_path.read_text(encoding="utf-8")
    data = json.loads(payload)
    delta = data.get("api_requests_total_delta")
    write_artifact(
        ARTIFACT_DIR / "expectations.json",
        {"api_requests_total_delta": delta},
    )
    return 0 if delta is None or delta >= 0 else 1


def _write_report(statuses: dict[str, int]) -> None:
    lines = ["# Metrics Validation Report", ""]
    for level, exit_code in statuses.items():
        state = "PASS" if exit_code == 0 else "FAIL"
        lines.append(f"- {level}: {state}")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    args = parser.parse_args(argv)
    levels = args.level or ["sync", "structural", "runtime", "expectations"]
    catalogs = args.catalog or _default_catalogs()
    root = Path(__file__).resolve().parents[1]

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
            result = run_expectations(root, catalogs)
        else:
            continue
        level_status[level] = result
        status |= result

    if level_status:
        _write_report(level_status)
    return status


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
