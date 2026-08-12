# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Contract tests for the centralized logging Kubernetes manifests.

The tests in this module validate that the Kubernetes resources and
configuration files introduced for centralized logging remain consistent
with the expectations of the observability platform. They intentionally
focus on structural assertions so that accidental regressions (for
example, removing a required volume or annotation) are caught quickly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_yaml_documents(path: Path) -> list[dict[str, object]]:
    raw = path.read_text(encoding="utf-8")
    documents = [doc for doc in yaml.safe_load_all(raw) if doc is not None]
    if not documents:
        raise AssertionError(f"{path} did not contain any YAML documents")
    return documents


def _single_document(path: Path) -> dict[str, object]:
    documents = _load_yaml_documents(path)
    if len(documents) != 1:
        raise AssertionError(f"Expected a single document in {path}, got {len(documents)}")
    return documents[0]


@pytest.mark.parametrize(
    "overlay_path",
    (
        REPO_ROOT / "deploy/kustomize/overlays/staging/kustomization.yaml",
        REPO_ROOT / "deploy/kustomize/overlays/production/kustomization.yaml",
    ),
)
def test_kustomize_overlays_include_logging_addon(overlay_path: Path) -> None:
    doc = _single_document(overlay_path)
    resources: Iterable[str] = doc.get("resources", [])  # type: ignore[assignment]
    assert "../../addons/logging" in set(
        resources
    ), f"{overlay_path} must include the centralized logging addon"


def test_logging_addon_kustomization_wires_configmaps() -> None:
    doc = _single_document(REPO_ROOT / "deploy/kustomize/addons/logging/kustomization.yaml")

    resources: list[str] = doc.get("resources", [])  # type: ignore[assignment]
    assert resources == [
        "filebeat-rbac.yaml",
        "filebeat-daemonset.yaml",
        "logstash-deployment.yaml",
        "logstash-service.yaml",
    ]

    config_maps = doc.get("configMapGenerator", [])  # type: ignore[assignment]
    assert isinstance(config_maps, list) and len(config_maps) == 2

    filebeat_entry = next(
        (entry for entry in config_maps if entry.get("name") == "geosync-filebeat-config"),
        None,
    )
    assert filebeat_entry is not None
    assert filebeat_entry.get("files") == [
        "filebeat.yml=../../../../observability/logging/filebeat.kubernetes.yml"
    ]

    logstash_entry = next(
        (entry for entry in config_maps if entry.get("name") == "geosync-logstash-pipeline"),
        None,
    )
    assert logstash_entry is not None
    assert logstash_entry.get("files") == [
        "logstash.conf=../../../../observability/logstash/pipeline/logstash.conf"
    ]

    replacements = doc.get("replacements", [])  # type: ignore[assignment]
    assert replacements, "Namespace replacements for Filebeat RBAC must remain configured"


def test_filebeat_daemonset_mounts_required_paths() -> None:
    doc = _single_document(REPO_ROOT / "deploy/kustomize/addons/logging/filebeat-daemonset.yaml")
    spec = doc["spec"]
    template = spec["template"]
    pod_spec = template["spec"]

    assert pod_spec["serviceAccountName"] == "filebeat"

    containers = pod_spec["containers"]
    assert len(containers) == 1
    container = containers[0]

    env_names = {env["name"] for env in container["env"]}
    assert {"NODE_NAME", "GEOSYNC_ENVIRONMENT", "LOGSTASH_HOSTS"} <= env_names

    volume_mounts = {mount["name"]: mount["mountPath"] for mount in container["volumeMounts"]}
    expected_mounts = {
        "config": "/etc/filebeat.yml",
        "data": "/usr/share/filebeat/data",
        "varlibdockercontainers": "/var/lib/docker/containers",
        "varlog": "/var/log",
        "varlogpods": "/var/log/pods",
    }
    for name, mount_path in expected_mounts.items():
        assert volume_mounts.get(name) == mount_path

    volumes = {volume["name"]: volume for volume in pod_spec["volumes"]}
    assert volumes["config"]["configMap"]["name"] == "geosync-filebeat-config"
    assert volumes["data"]["hostPath"]["path"] == "/var/lib/filebeat-data"


def test_filebeat_rbac_definitions_present() -> None:
    documents = _load_yaml_documents(
        REPO_ROOT / "deploy/kustomize/addons/logging/filebeat-rbac.yaml"
    )
    kinds = {doc["kind"] for doc in documents}
    assert {"ServiceAccount", "ClusterRole", "ClusterRoleBinding"} <= kinds

    cluster_role = next(doc for doc in documents if doc["kind"] == "ClusterRole")
    rules = cluster_role["rules"]
    core_rule = next(rule for rule in rules if rule["apiGroups"] == [""])
    assert set(core_rule["resources"]) == {"pods", "namespaces", "nodes"}


def test_logstash_deployment_mounts_pipeline_config() -> None:
    doc = _single_document(REPO_ROOT / "deploy/kustomize/addons/logging/logstash-deployment.yaml")
    container = doc["spec"]["template"]["spec"]["containers"][0]

    env_defaults = {item["name"]: item.get("value", "") for item in container["env"]}
    assert env_defaults["ELASTICSEARCH_HOSTS"] == "http://elasticsearch:9200"
    assert env_defaults["ELASTICSEARCH_API_KEY"] == ""
    assert env_defaults["LOG_INDEX_PREFIX"] == "geosync-logs"

    volume_mounts = {item["name"]: item for item in container["volumeMounts"]}
    pipeline_mount = volume_mounts["pipeline"]
    assert pipeline_mount["mountPath"] == "/usr/share/logstash/pipeline/logstash.conf"
    assert pipeline_mount["subPath"] == "logstash.conf"


def test_logstash_service_exposes_expected_ports() -> None:
    doc = _single_document(REPO_ROOT / "deploy/kustomize/addons/logging/logstash-service.yaml")
    ports = {port["name"]: port["port"] for port in doc["spec"]["ports"]}
    assert ports == {"beats": 5044, "monitoring": 9600}


def test_filebeat_kubernetes_config_filters_geosync_workloads() -> None:
    config = _single_document(REPO_ROOT / "observability/logging/filebeat.kubernetes.yml")
    inputs = config["filebeat.inputs"]
    assert len(inputs) == 1
    input_config = inputs[0]

    processors = input_config["processors"]
    drop_event = next(proc for proc in processors if "drop_event" in proc)
    filter_condition = drop_event["drop_event"]["when"]["not"]["equals"]
    assert filter_condition["kubernetes.labels.app_kubernetes_io/part-of"] == "geosync"

    add_fields = next(proc for proc in processors if "add_fields" in proc)
    geosync_fields = add_fields["add_fields"]["fields"]
    assert geosync_fields["environment"] == "${GEOSYNC_ENVIRONMENT:unknown}"


@pytest.mark.parametrize(
    "deployment_path",
    (
        REPO_ROOT / "deploy/kustomize/base/deployment.yaml",
        REPO_ROOT / "deploy/geosync-deployment.yaml",
    ),
)
def test_backend_deployments_emit_filebeat_hints(deployment_path: Path) -> None:
    doc = _single_document(deployment_path)
    annotations = doc["spec"]["template"]["metadata"]["annotations"]
    assert annotations["co.elastic.logs/enabled"] == "true"
    assert annotations["co.elastic.logs/module"] == "geosync-api"


def test_logstash_pipeline_prefers_api_key_authentication() -> None:
    pipeline_source = (REPO_ROOT / "observability/logstash/pipeline/logstash.conf").read_text(
        encoding="utf-8"
    )
    api_key_condition = 'if "${ELASTICSEARCH_API_KEY}" != ""'
    username_condition = 'else if "${ELASTICSEARCH_USERNAME}" != ""'
    assert pipeline_source.index(api_key_condition) < pipeline_source.index(username_condition)

    assert "stdout" in pipeline_source, "Logstash pipeline must keep stdout debugging output"
