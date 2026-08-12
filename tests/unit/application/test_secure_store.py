# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Tuple
from uuid import uuid4

import pytest

from application.configuration import (
    CentralConfigurationStore,
    ConfigurationStoreError,
    NamespaceDefinition,
)
from application.secrets.vault import SecretVault
from core.config.template_manager import ConfigTemplateManager
from src.audit.audit_logger import AuditLogger


@dataclass
class _RecordingSink:
    records: list

    def __init__(self) -> None:
        self.records = []

    def __call__(self, record) -> None:  # pragma: no cover - simple data capture
        self.records.append(record)


class _ControlledClock:
    def __init__(self) -> None:
        self._current = datetime(2024, 1, 1, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._current

    def advance(self, seconds: float) -> None:
        self._current = self._current + timedelta(seconds=seconds)


@pytest.fixture()
def store_components(
    tmp_path: Path,
) -> Tuple[CentralConfigurationStore, _ControlledClock, _RecordingSink]:
    clock = _ControlledClock()
    storage_path = tmp_path / "vault.json"
    master_key = SecretVault.generate_key()
    audit_sink = _RecordingSink()
    audit_logger = AuditLogger(secret="audit-secret-value", sink=audit_sink)
    vault = SecretVault(
        storage_path=storage_path,
        master_key=master_key,
        audit_logger=audit_logger,
        clock=clock.now,
    )
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "deployment.yaml.j2").write_text("token={{ token }}\n", encoding="utf-8")
    store = CentralConfigurationStore(
        vault=vault,
        template_manager=ConfigTemplateManager(template_dir),
        audit_logger=audit_logger,
        clock=clock.now,
    )
    store.register_namespace(
        NamespaceDefinition(
            name="prod",
            readers=frozenset({"deploy", "security"}),
            writers=frozenset({"platform"}),
            allow_ci=True,
        )
    )
    store.register_namespace(
        NamespaceDefinition(
            name="restricted",
            readers=frozenset({"security"}),
            writers=frozenset({"security"}),
            allow_ci=False,
        )
    )
    return store, clock, audit_sink


def test_secret_round_trip_and_access_control(store_components):
    store, _clock, _sink = store_components
    store.write_secret(
        "prod",
        "api_key",
        "super-secret",
        actor="platform",
        ip_address="198.51.100.10",
    )
    value = store.read_secret(
        "prod",
        "api_key",
        actor="deploy",
        ip_address="198.51.100.11",
    )
    assert value == "super-secret"
    with pytest.raises(ConfigurationStoreError):
        store.read_secret(
            "prod",
            "api_key",
            actor="intruder",
            ip_address="198.51.100.12",
        )


def test_namespace_access_hydrated_on_restart(tmp_path: Path):
    clock = _ControlledClock()
    storage_path = tmp_path / "vault.json"
    master_key = SecretVault.generate_key()
    audit_sink = _RecordingSink()
    audit_logger = AuditLogger(secret="audit-secret-value", sink=audit_sink)
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "config.yaml.j2").write_text("value={{ value }}\n", encoding="utf-8")

    namespace = NamespaceDefinition(
        name="prod",
        readers=frozenset({"deploy", "security"}),
        writers=frozenset({"platform"}),
        allow_ci=True,
    )

    initial_vault = SecretVault(
        storage_path=storage_path,
        master_key=master_key,
        audit_logger=audit_logger,
        clock=clock.now,
    )
    initial_store = CentralConfigurationStore(
        vault=initial_vault,
        template_manager=ConfigTemplateManager(template_dir),
        audit_logger=audit_logger,
        clock=clock.now,
    )
    initial_store.register_namespace(namespace)
    initial_store.write_secret(
        "prod",
        "api_key",
        "super-secret",
        actor="platform",
        ip_address="198.51.100.10",
    )

    reloaded_vault = SecretVault(
        storage_path=storage_path,
        master_key=master_key,
        audit_logger=audit_logger,
        clock=clock.now,
    )
    restarted_store = CentralConfigurationStore(
        vault=reloaded_vault,
        template_manager=ConfigTemplateManager(template_dir),
        audit_logger=audit_logger,
        clock=clock.now,
    )
    restarted_store.register_namespace(namespace)

    value = restarted_store.read_secret(
        "prod",
        "api_key",
        actor="deploy",
        ip_address="198.51.100.11",
    )
    assert value == "super-secret"


def test_configuration_round_trip(store_components):
    store, _, _ = store_components
    store.write_configuration(
        "prod",
        "service",
        {"endpoint": "https://api.geosync.invalid", "retries": 3},
        actor="platform",
        ip_address="198.51.100.10",
    )
    config = store.read_configuration(
        "prod",
        "service",
        actor="deploy",
        ip_address="198.51.100.11",
    )
    assert config["endpoint"] == "https://api.geosync.invalid"
    assert config["retries"] == 3


def test_template_rendering_and_ci_injection(store_components, tmp_path: Path):
    store, _, _ = store_components
    destination = tmp_path / "rendered.yaml"
    store.render_environment_template(
        "deployment",
        destination,
        context={"token": "abc"},
        actor="platform",
        ip_address="198.51.100.10",
    )
    assert "token=abc" in destination.read_text(encoding="utf-8")

    store.write_secret(
        "prod",
        "deploy_token",
        "ci-secret",
        actor="platform",
        ip_address="198.51.100.10",
    )
    env: dict[str, str] = {}
    metadata = store.inject_into_ci(
        "prod",
        {"DEPLOY_TOKEN": "deploy_token"},
        actor="deploy",
        ip_address="198.51.100.11",
        environment=env,
    )
    assert env["DEPLOY_TOKEN"] == "ci-secret"
    assert metadata["DEPLOY_TOKEN"]["secret"] == "deploy_token"

    store.write_secret(
        "restricted",
        "internal",
        "restricted-secret",
        actor="security",
        ip_address="198.51.100.50",
    )
    with pytest.raises(ConfigurationStoreError):
        store.inject_into_ci(
            "restricted",
            {"SECRET": "internal"},
            actor="security",
            ip_address="198.51.100.51",
            environment={},
        )


def test_rotation_policies_execute(store_components):
    store, clock, _ = store_components
    store.write_secret(
        "prod",
        "rotation_token",
        "initial",
        actor="platform",
        ip_address="198.51.100.10",
    )

    generator = iter(["second", "third", "fourth"])

    def _generate() -> str:
        return next(generator)

    store.register_rotation_policy(
        "prod",
        "rotation_token",
        interval=timedelta(seconds=60),
        generator=_generate,
        actor="platform",
        ip_address="198.51.100.10",
    )

    clock.advance(120)
    rotated = store.evaluate_rotations()
    assert rotated[0].version == 2

    clock.advance(120)
    rotated_again = store.evaluate_rotations()
    assert rotated_again[0].version == 3
    value = store.read_secret(
        "prod",
        "rotation_token",
        actor="deploy",
        ip_address="198.51.100.11",
    )
    assert value == "third"


def test_repository_scan_reports_findings(store_components, tmp_path: Path):
    store, _, _ = store_components
    workspace = tmp_path.parent / f"workspace-{uuid4().hex}"
    workspace.mkdir()
    secret_file = workspace / "leak.env"
    secret_file.write_text('API_KEY="supersecretvalue"\n', encoding="utf-8")
    findings = store.scan_repository_for_leaks(workspace)
    assert "leak.env" in findings
