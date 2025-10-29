"""Tests for the GitHub Actions oriented MLOps helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.mlops import PipelineConfig, orchestrate_pipeline
from scripts.mlops.github_actions_pipeline import _derive_seed


SAMPLE_DATASET = Path(__file__).resolve().parents[3] / "data" / "sample.csv"


@pytest.fixture()
def pipeline_config(tmp_path: Path) -> PipelineConfig:
    return PipelineConfig(
        artifact_root=tmp_path / "artifacts",
        registry_root=tmp_path / "registry",
        experiment="ci/test-experiment",
        commit_sha="0123456789abcdef0123456789abcdef01234567",
        environment="staging",
        dataset_path=SAMPLE_DATASET,
    )


def test_orchestrate_pipeline_creates_expected_artifacts(pipeline_config: PipelineConfig) -> None:
    summary = orchestrate_pipeline(pipeline_config)

    model_path = Path(summary["model_path"])
    metrics_path = Path(summary["metrics_path"])
    context_path = Path(summary["context_path"])

    assert model_path.exists(), "model artifact should be materialised"
    assert metrics_path.exists(), "metrics artifact should be materialised"
    assert context_path.exists(), "context artifact should be materialised"
    metrics = summary["metrics"]
    assert {"mae", "rmse", "r2_score", "mean_abs_weight", "stability_index"} <= metrics.keys()
    assert metrics["mae"] >= 0.0
    assert metrics["rmse"] >= 0.0
    assert -1.0 <= metrics["r2_score"] <= 1.0
    assert 0.0 <= metrics["stability_index"] <= 1.0
    assert summary["run_id"], "a run identifier should be returned"

    assert (
        pipeline_config.registry_root / "experiments"
    ).exists(), "registry directory must be created"


def test_pipeline_copies_dataset_when_present(tmp_path: Path, pipeline_config: PipelineConfig) -> None:
    dataset = tmp_path / "dataset.csv"
    dataset.write_text(
        "ts,price,volume\n"
        "0,101.0,1000\n"
        "1,101.5,1005\n"
        "2,102.0,1007\n"
        "3,102.5,1010\n",
        encoding="utf-8",
    )

    config = PipelineConfig(
        artifact_root=pipeline_config.artifact_root,
        registry_root=pipeline_config.registry_root,
        experiment=pipeline_config.experiment,
        commit_sha=pipeline_config.commit_sha,
        environment=pipeline_config.environment,
        dataset_path=dataset,
    )

    orchestrate_pipeline(config)

    copied_dataset = config.artifact_root / "datasets" / dataset.name
    assert copied_dataset.exists()
    assert copied_dataset.read_text(encoding="utf-8") == dataset.read_text(encoding="utf-8")


def test_pipeline_is_deterministic_for_same_inputs(pipeline_config: PipelineConfig) -> None:
    first_summary = orchestrate_pipeline(pipeline_config)
    second_summary = orchestrate_pipeline(pipeline_config)

    assert first_summary["metrics"] == second_summary["metrics"]
    assert (
        _derive_seed(pipeline_config)
        == _derive_seed(pipeline_config)
    ), "seed generation must be deterministic"
