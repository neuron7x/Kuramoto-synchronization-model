"""Tests for sandbox subchart templates."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml

SANDBOX_CHART = (
    Path(__file__).resolve().parents[2]
    / "deploy"
    / "helm"
    / "tradepulse"
    / "charts"
    / "sandbox"
)


def _load_yaml(path: Path) -> Dict[str, Any] | List[Any]:
    """Load and parse a YAML file."""
    raw = path.read_text(encoding="utf-8")
    return yaml.safe_load(raw)


def test_sandbox_chart_exists() -> None:
    """Verify sandbox Chart.yaml exists."""
    chart_path = SANDBOX_CHART / "Chart.yaml"
    assert chart_path.exists(), "Sandbox Chart.yaml must exist"

    chart = _load_yaml(chart_path)
    assert isinstance(chart, dict)
    assert chart["name"] == "sandbox"
    assert chart["type"] == "application"


def test_sandbox_has_deployment_template() -> None:
    """Ensure sandbox has deployment template."""
    deployment_path = SANDBOX_CHART / "templates" / "deployment.yaml"
    assert deployment_path.exists(), "Deployment template must exist"

    content = deployment_path.read_text()
    # Check for key Kubernetes API fields
    assert "kind: Deployment" in content
    assert "apiVersion: apps/v1" in content


def test_sandbox_deployment_has_security_context() -> None:
    """Verify deployment uses global security context."""
    deployment_path = SANDBOX_CHART / "templates" / "deployment.yaml"
    content = deployment_path.read_text()

    assert "securityContext:" in content
    assert ".Values.global.securityContext" in content
    assert ".Values.global.containerSecurityContext" in content


def test_sandbox_has_service_template() -> None:
    """Ensure sandbox has service template."""
    service_path = SANDBOX_CHART / "templates" / "service.yaml"
    assert service_path.exists(), "Service template must exist"

    content = service_path.read_text()
    assert "kind: Service" in content
    assert "apiVersion: v1" in content


def test_sandbox_has_hpa_template() -> None:
    """Verify sandbox has HPA template."""
    hpa_path = SANDBOX_CHART / "templates" / "hpa.yaml"
    assert hpa_path.exists(), "HPA template must exist"

    content = hpa_path.read_text()
    assert "kind: HorizontalPodAutoscaler" in content
    assert "apiVersion: autoscaling/v2" in content
    assert ".Values.autoscaling.enabled" in content


def test_sandbox_hpa_has_cpu_and_memory_metrics() -> None:
    """Ensure HPA monitors both CPU and memory."""
    hpa_path = SANDBOX_CHART / "templates" / "hpa.yaml"
    content = hpa_path.read_text()

    assert "targetCPUUtilizationPercentage" in content
    assert "targetMemoryUtilizationPercentage" in content


def test_sandbox_has_pdb_template() -> None:
    """Verify sandbox has PodDisruptionBudget template."""
    pdb_path = SANDBOX_CHART / "templates" / "pdb.yaml"
    assert pdb_path.exists(), "PDB template must exist"

    content = pdb_path.read_text()
    assert "kind: PodDisruptionBudget" in content
    assert "apiVersion: policy/v1" in content
    assert ".Values.podDisruptionBudget.enabled" in content


def test_sandbox_has_network_policy_template() -> None:
    """Ensure sandbox has NetworkPolicy template."""
    netpol_path = SANDBOX_CHART / "templates" / "networkpolicy.yaml"
    assert netpol_path.exists(), "NetworkPolicy template must exist"

    content = netpol_path.read_text()
    assert "kind: NetworkPolicy" in content
    assert "apiVersion: networking.k8s.io/v1" in content
    assert ".Values.global.networkPolicy.enabled" in content


def test_sandbox_network_policy_has_ingress_egress() -> None:
    """Verify NetworkPolicy defines both ingress and egress rules."""
    netpol_path = SANDBOX_CHART / "templates" / "networkpolicy.yaml"
    content = netpol_path.read_text()

    assert "ingress:" in content
    assert "egress:" in content
    # Check for DNS egress
    assert "port: 53" in content


def test_sandbox_has_service_monitor_template() -> None:
    """Verify sandbox has ServiceMonitor for Prometheus."""
    sm_path = SANDBOX_CHART / "templates" / "servicemonitor.yaml"
    assert sm_path.exists(), "ServiceMonitor template must exist"

    content = sm_path.read_text()
    assert "kind: ServiceMonitor" in content
    assert "apiVersion: monitoring.coreos.com/v1" in content
    assert ".Values.serviceMonitor.enabled" in content


def test_sandbox_has_service_account_template() -> None:
    """Ensure sandbox has ServiceAccount template."""
    sa_path = SANDBOX_CHART / "templates" / "serviceaccount.yaml"
    assert sa_path.exists(), "ServiceAccount template must exist"

    content = sa_path.read_text()
    assert "kind: ServiceAccount" in content
    assert "apiVersion: v1" in content


def test_sandbox_has_helpers_template() -> None:
    """Verify sandbox has _helpers.tpl with template functions."""
    helpers_path = SANDBOX_CHART / "templates" / "_helpers.tpl"
    assert helpers_path.exists(), "_helpers.tpl must exist"

    content = helpers_path.read_text()
    # Check for common template functions
    assert "sandbox.name" in content
    assert "sandbox.fullname" in content
    assert "sandbox.labels" in content
    assert "sandbox.selectorLabels" in content


def test_sandbox_deployment_uses_readonly_root_filesystem() -> None:
    """Ensure deployment mounts emptyDir volumes for writable paths."""
    deployment_path = SANDBOX_CHART / "templates" / "deployment.yaml"
    content = deployment_path.read_text()

    # With readOnlyRootFilesystem, we need volumes for /tmp and cache
    assert "volumes:" in content
    assert "emptyDir:" in content
    assert "volumeMounts:" in content


def test_sandbox_deployment_has_health_probes() -> None:
    """Verify deployment has liveness and readiness probes."""
    deployment_path = SANDBOX_CHART / "templates" / "deployment.yaml"
    content = deployment_path.read_text()

    assert "livenessProbe:" in content
    assert "readinessProbe:" in content
    assert "httpGet:" in content
