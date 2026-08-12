# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for Helm chart structure and configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

HELM_BASE = Path(__file__).resolve().parents[2] / "deploy" / "helm" / "geosync"


def _load_yaml(path: Path) -> Dict[str, Any]:
    """Load and parse a YAML file."""
    raw = path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw)
    if not isinstance(loaded, dict):
        raise TypeError(f"{path} should deserialize into a mapping")
    return loaded


def test_umbrella_chart_exists() -> None:
    """Verify umbrella Chart.yaml exists and is valid."""
    chart_path = HELM_BASE / "Chart.yaml"
    assert chart_path.exists(), "Umbrella Chart.yaml must exist"

    chart = _load_yaml(chart_path)
    assert chart["name"] == "geosync"
    assert chart["type"] == "application"
    assert "version" in chart
    assert "appVersion" in chart


def test_umbrella_chart_has_subcharts() -> None:
    """Verify umbrella chart declares subchart dependencies."""
    chart_path = HELM_BASE / "Chart.yaml"
    chart = _load_yaml(chart_path)

    dependencies = chart.get("dependencies", [])
    assert len(dependencies) >= 3, "Should have at least 3 subcharts"

    subchart_names = {dep["name"] for dep in dependencies}
    assert "sandbox" in subchart_names
    assert "admin" in subchart_names
    assert "observability" in subchart_names


def test_values_yaml_exists() -> None:
    """Verify values.yaml exists with required configuration."""
    values_path = HELM_BASE / "values.yaml"
    assert values_path.exists(), "values.yaml must exist"

    values = _load_yaml(values_path)
    assert "global" in values
    assert "sandbox" in values
    assert "admin" in values
    assert "observability" in values


def test_global_security_context_is_strict() -> None:
    """Ensure global security context has strict settings."""
    values_path = HELM_BASE / "values.yaml"
    values = _load_yaml(values_path)

    security_context = values["global"]["securityContext"]
    assert security_context["runAsNonRoot"] is True
    assert security_context["runAsUser"] == 1000
    assert security_context["fsGroup"] == 1000
    assert security_context["seccompProfile"]["type"] == "RuntimeDefault"

    container_security = values["global"]["containerSecurityContext"]
    assert container_security["allowPrivilegeEscalation"] is False
    assert container_security["readOnlyRootFilesystem"] is True
    assert container_security["capabilities"]["drop"] == ["ALL"]


def test_global_network_policy_enabled() -> None:
    """Verify NetworkPolicy is enabled globally."""
    values_path = HELM_BASE / "values.yaml"
    values = _load_yaml(values_path)

    network_policy = values["global"]["networkPolicy"]
    assert network_policy["enabled"] is True
    assert "Ingress" in network_policy["policyTypes"]
    assert "Egress" in network_policy["policyTypes"]


def test_global_otel_configuration() -> None:
    """Ensure OpenTelemetry is configured globally."""
    values_path = HELM_BASE / "values.yaml"
    values = _load_yaml(values_path)

    otel = values["global"]["otel"]
    assert otel["enabled"] is True
    assert "endpoint" in otel
    assert "serviceName" in otel


def test_global_slo_configuration() -> None:
    """Verify SLO thresholds are defined."""
    values_path = HELM_BASE / "values.yaml"
    values = _load_yaml(values_path)

    slo = values["global"]["slo"]
    assert slo["enabled"] is True
    assert "errorBudget" in slo
    assert "latencyP99Threshold" in slo
    # 99.9% uptime = 0.001 error budget
    assert slo["errorBudget"] == 0.001


def test_sandbox_has_autoscaling() -> None:
    """Ensure sandbox service has HPA configured."""
    values_path = HELM_BASE / "values.yaml"
    values = _load_yaml(values_path)

    sandbox = values["sandbox"]
    assert sandbox["autoscaling"]["enabled"] is True
    assert sandbox["autoscaling"]["minReplicas"] >= 2
    assert sandbox["autoscaling"]["maxReplicas"] >= sandbox["autoscaling"]["minReplicas"]


def test_sandbox_has_pod_disruption_budget() -> None:
    """Verify sandbox has PDB for high availability."""
    values_path = HELM_BASE / "values.yaml"
    values = _load_yaml(values_path)

    sandbox = values["sandbox"]
    assert sandbox["podDisruptionBudget"]["enabled"] is True
    assert sandbox["podDisruptionBudget"]["minAvailable"] >= 1


def test_sandbox_has_resource_limits() -> None:
    """Ensure sandbox has resource requests and limits."""
    values_path = HELM_BASE / "values.yaml"
    values = _load_yaml(values_path)

    resources = values["sandbox"]["resources"]
    assert "requests" in resources
    assert "limits" in resources
    assert "cpu" in resources["requests"]
    assert "memory" in resources["requests"]
    assert "cpu" in resources["limits"]
    assert "memory" in resources["limits"]


def test_sandbox_has_service_monitor() -> None:
    """Verify sandbox has Prometheus ServiceMonitor."""
    values_path = HELM_BASE / "values.yaml"
    values = _load_yaml(values_path)

    sandbox = values["sandbox"]
    assert sandbox["serviceMonitor"]["enabled"] is True
    assert "interval" in sandbox["serviceMonitor"]
    assert "scrapeTimeout" in sandbox["serviceMonitor"]


def test_no_hardcoded_passwords() -> None:
    """Ensure no hardcoded passwords in values."""
    values_path = HELM_BASE / "values.yaml"
    values = _load_yaml(values_path)

    # Check Grafana password is not hardcoded
    if "observability" in values and "grafana" in values["observability"]:
        grafana = values["observability"]["grafana"]
        password = grafana.get("adminPassword", "")
        # Should be empty or require explicit setting
        assert password != "changeme", "Password must not be 'changeme'"
        assert password != "admin", "Password must not be 'admin'"
