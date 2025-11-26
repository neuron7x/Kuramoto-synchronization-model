"""Tests for the experiment registry responsible for tracking model runs."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.data.experiment_registry import ArtifactRecord, ExperimentRegistry


def deterministic_ids() -> Iterator[str]:
    yield from (f"run-{index}" for index in range(1, 100))


def deterministic_clock() -> Iterator[datetime]:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for offset in range(100):
        yield base + timedelta(days=offset)


def _next(iterator: Iterator):
    return next(iterator)


def test_register_run_persists_payload(tmp_path: Path) -> None:
    id_iter = deterministic_ids()
    clock_iter = deterministic_clock()
    registry = ExperimentRegistry(
        tmp_path,
        run_id_factory=lambda: _next(id_iter),
        clock=lambda: _next(clock_iter),
        fsync=False,
    )

    artifact = ArtifactRecord(name="model", uri="s3://bucket/model.pt", kind="model")
    record = registry.register_run(
        "volatility-model",
        params={"lr": 0.01, "epochs": 20},
        metrics={"loss": 0.42},
        artifacts=[artifact],
        tags={"baseline"},
        notes="Initial benchmark run.",
        training_data_hash="data-hash",
        code_revision="abc123",
    )

    run_path = tmp_path / "volatility-model" / record.run_id / "run.json"
    assert run_path.exists()
    with run_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    assert payload["params"] == {"epochs": 20, "lr": 0.01}
    assert payload["metrics"] == {"loss": pytest.approx(0.42)}
    assert payload["artifacts"][0]["uri"] == "s3://bucket/model.pt"
    assert record.param_hash
    assert (
        registry.get_run(record.run_id, experiment_name="volatility-model").model_dump()
        == record.model_dump()
    )


def test_list_runs_is_sorted_by_creation_time(tmp_path: Path) -> None:
    id_iter = iter(["run-1", "run-2", "run-3"])
    clock_iter = iter(
        [
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 3, tzinfo=timezone.utc),
            datetime(2024, 1, 2, tzinfo=timezone.utc),
        ]
    )
    registry = ExperimentRegistry(
        tmp_path,
        run_id_factory=lambda: _next(id_iter),
        clock=lambda: _next(clock_iter),
        fsync=False,
    )

    registry.register_run("alpha", params={"lr": 0.01})
    registry.register_run("alpha", params={"lr": 0.02})
    registry.register_run("alpha", params={"lr": 0.03})

    runs = registry.list_runs("alpha")
    assert [run.run_id for run in runs] == ["run-1", "run-3", "run-2"]
    assert runs[0].created_at <= runs[1].created_at <= runs[2].created_at


def test_audit_trail_highlights_hyperparameter_and_metric_changes(
    tmp_path: Path,
) -> None:
    id_iter = iter(["base", "tuned"])
    clock_iter = iter(
        [
            datetime(2024, 2, 1, tzinfo=timezone.utc),
            datetime(2024, 2, 2, tzinfo=timezone.utc),
        ]
    )
    registry = ExperimentRegistry(
        tmp_path,
        run_id_factory=lambda: _next(id_iter),
        clock=lambda: _next(clock_iter),
        fsync=False,
    )

    registry.register_run(
        "risk-model",
        params={"lr": 0.1, "batch": 32},
        metrics={"loss": 0.6},
    )
    registry.register_run(
        "risk-model",
        params={"lr": 0.05, "batch": 32, "dropout": 0.1},
        metrics={"loss": 0.45, "accuracy": 0.82},
    )

    audit_entries = registry.audit_trail("risk-model")
    assert len(audit_entries) == 2

    first, second = audit_entries
    assert first.compared_to is None
    assert first.changed_params == {
        "batch": {"change": "added", "current": 32},
        "lr": {"change": "added", "current": 0.1},
    }

    assert second.compared_to == "base"
    assert second.changed_params == {
        "dropout": {"change": "added", "current": 0.1},
        "lr": {"change": "modified", "previous": 0.1, "current": 0.05},
    }
    assert second.metrics_delta["loss"]["change"] == pytest.approx(-0.14999999999999997)
    assert second.metrics_delta["accuracy"]["previous"] is None


def test_reproducibility_manifest_matches_run(tmp_path: Path) -> None:
    registry = ExperimentRegistry(
        tmp_path, run_id_factory=lambda: "manifest", fsync=False
    )
    record = registry.register_run(
        "signal-model",
        params={"window": 30},
        metrics={"sharpe": 1.8},
        artifacts=[{"name": "model", "uri": "./model.pkl", "kind": "model"}],
    )

    manifest = registry.reproducibility_manifest(
        record.run_id, experiment_name="signal-model"
    )
    assert manifest["run_id"] == record.run_id
    assert manifest["param_hash"] == record.param_hash
    assert manifest["artifacts"][0]["uri"] == "./model.pkl"
    assert manifest["metrics"]["sharpe"] == pytest.approx(1.8)


def test_register_run_rejects_path_traversal_inputs(tmp_path: Path) -> None:
    registry = ExperimentRegistry(tmp_path, run_id_factory=lambda: "safe", fsync=False)

    with pytest.raises(ValueError, match="Experiment name"):
        registry.register_run("../malicious")


def test_get_run_rejects_invalid_run_identifier(tmp_path: Path) -> None:
    registry = ExperimentRegistry(tmp_path, run_id_factory=lambda: "safe", fsync=False)
    registry.register_run("secure")

    with pytest.raises(ValueError, match="Run identifier"):
        registry.get_run("../unsafe", experiment_name="secure")


def test_delete_run_removes_persisted_state(tmp_path: Path) -> None:
    registry = ExperimentRegistry(tmp_path, run_id_factory=lambda: "run-1", fsync=False)
    record = registry.register_run("alpha", params={"lr": 0.01})

    run_dir = tmp_path / "alpha" / record.run_id
    assert run_dir.exists()

    registry.delete_run(record.run_id, experiment_name="alpha")

    assert not run_dir.exists()
    assert registry.list_runs("alpha") == []

    with pytest.raises(KeyError):
        registry.get_run(record.run_id, experiment_name="alpha")

    with pytest.raises(KeyError):
        registry.delete_run(record.run_id, experiment_name="alpha")
