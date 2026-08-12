# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import pytest

from core.experiments import ArtifactSpec, ModelRegistry


def test_register_run_persists_artifacts_and_metadata(tmp_path: Path) -> None:
    registry_dir = tmp_path / "registry"
    artifact_file = tmp_path / "model.bin"
    artifact_file.write_bytes(b"weights")

    registry = ModelRegistry(registry_dir)

    run = registry.register_run(
        experiment="baseline",
        parameters={"lr": 0.01, "random_seed": 7},
        metrics={"accuracy": 0.9},
        artifacts=[ArtifactSpec(path=artifact_file, name="model.bin", kind="model")],
        tags=["baseline", "v1"],
        notes="initial run",
        metadata={"commit": "abc123"},
    )

    stored_artifact_path = registry_dir / run.artifacts[0].stored_path
    assert stored_artifact_path.exists()
    assert stored_artifact_path.read_bytes() == artifact_file.read_bytes()

    run_again = registry.get_run(run.id)
    assert run_again == run

    reproduction = registry.reproduction_plan(run.id)
    assert reproduction["run_id"] == run.id
    assert reproduction["parameters"]["lr"] == 0.01
    assert reproduction["artifacts"][0]["checksum"] == run.artifacts[0].checksum
    assert Path(reproduction["artifacts"][0]["path"]).exists()


def test_history_orders_runs_and_audit_changes(tmp_path: Path) -> None:
    registry_dir = tmp_path / "registry"
    registry = ModelRegistry(registry_dir)

    artifact_v1 = tmp_path / "model_v1.bin"
    artifact_v1.write_text("v1")
    first_run = registry.register_run(
        experiment="baseline",
        parameters={"lr": 0.01, "layers": 2},
        metrics={"accuracy": 0.8},
        artifacts=[artifact_v1],
    )

    assert first_run.audit.reference_run_id is None
    assert first_run.audit.hyperparameters is None
    assert first_run.audit.metrics is None

    artifact_v2 = tmp_path / "model_v2.bin"
    artifact_v2.write_text("v2")
    second_run = registry.register_run(
        experiment="baseline",
        parameters={"lr": 0.02, "layers": 2},
        metrics={"accuracy": 0.82, "loss": 0.5},
        artifacts=[artifact_v2],
    )

    history = registry.history("baseline")
    assert [run.id for run in history] == [first_run.id, second_run.id]

    audit = second_run.audit
    assert audit.reference_run_id == first_run.id
    assert audit.hyperparameters is not None
    assert audit.metrics is not None

    lr_change = {change.key: change for change in audit.hyperparameters.changed}
    assert lr_change["lr"].previous == 0.01
    assert lr_change["lr"].current == 0.02

    assert "loss" in audit.metrics.added
    assert pytest.approx(audit.metrics.added["loss"], rel=1e-12) == 0.5
    accuracy_change = {change.key: change for change in audit.metrics.changed}
    assert pytest.approx(accuracy_change["accuracy"].previous, rel=1e-12) == 0.8
    assert pytest.approx(accuracy_change["accuracy"].current, rel=1e-12) == 0.82


def test_list_experiments_is_sorted(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path / "registry")

    artifact = tmp_path / "artifact.txt"
    artifact.write_text("data")

    registry.register_run(experiment="b", parameters={}, artifacts=[artifact])
    registry.register_run(experiment="a", parameters={}, artifacts=[artifact])

    assert registry.list_experiments() == ["a", "b"]


def test_artifact_spec_rejects_path_escape_names(tmp_path: Path) -> None:
    artifact = tmp_path / "model.bin"
    artifact.write_text("data")

    spec_with_parent = ArtifactSpec(path=artifact, name="../../../../etc/passwd")
    with pytest.raises(ValueError):
        spec_with_parent.resolved_name()

    spec_with_separator = ArtifactSpec(path=artifact, name="nested/evil.bin")
    with pytest.raises(ValueError):
        spec_with_separator.resolved_name()

    spec_absolute = ArtifactSpec(path=artifact, name="/tmp/evil.bin")
    with pytest.raises(ValueError):
        spec_absolute.resolved_name()
