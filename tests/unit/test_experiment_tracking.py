# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unit tests for the experiment tracking helpers."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from omegaconf import OmegaConf

from analytics.runner import RunMetadata
from analytics.tracking import ExperimentDeviationError, ExperimentTracker
from core.config.cli_models import ExperimentConfig


@pytest.fixture(name="experiment_cfg")
def _experiment_cfg(tmp_path: Path) -> ExperimentConfig:
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "order_parameter": 0.75,
                "entropy": 0.5,
                "delta_entropy": 0.02,
                "mean_ricci": 0.01,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    payload = {
        "name": "dev",
        "db_uri": "sqlite:///memory",
        "debug": False,
        "log_level": "INFO",
        "random_seed": 11,
        "data": {"price_csv": str(tmp_path / "prices.csv"), "price_column": "price"},
        "analytics": {"window": 4, "bins": 16, "delta": 0.01},
        "tracking": {
            "enabled": True,
            "base_dir": str(tmp_path / "run"),
            "ci_integration": True,
            "baseline": {
                "name": "reference",
                "metrics_path": str(baseline_path),
                "metric_tolerances": {"order_parameter": 0.5},
            },
            "alerts": {
                "tolerance": 0.5,
                "strategy": "relative",
                "fail_on_deviation": True,
            },
        },
    }
    return ExperimentConfig.model_validate(payload)


@pytest.fixture(name="run_metadata")
def _run_metadata(tmp_path: Path, experiment_cfg: ExperimentConfig) -> RunMetadata:
    run_dir = Path(tmp_path / "run")
    run_dir.mkdir(parents=True, exist_ok=True)
    return RunMetadata(
        run_dir=run_dir,
        original_cwd=tmp_path,
        timestamp_utc="2024-01-01T00:00:00+00:00",
        git_sha="abcdef",
        python_version="3.11.0",
        environment=experiment_cfg.name,
        random_seed=experiment_cfg.random_seed,
    )


def _hydra_cfg(experiment_cfg: ExperimentConfig) -> "OmegaConf":
    container = experiment_cfg.model_dump()
    return OmegaConf.create({"experiment": container})


def test_tracker_generates_reports_archives(
    tmp_path: Path, experiment_cfg: ExperimentConfig, run_metadata: RunMetadata
) -> None:
    hydra_cfg = _hydra_cfg(experiment_cfg)
    tracker = ExperimentTracker.from_experiment(experiment_cfg, run_metadata)
    assert isinstance(tracker, ExperimentTracker)
    assert hydra_cfg["experiment"]["name"] == experiment_cfg.name

    tracker.log_configuration(hydra_cfg, safe_yaml=None)
    data_path = tmp_path / "prices.csv"
    data_path.write_text("price\n1\n2\n3\n4\n", encoding="utf-8")
    tracker.log_data_version(data_path)
    tracker.log_metrics(
        {
            "order_parameter": 0.8,
            "entropy": 0.52,
            "delta_entropy": 0.021,
            "mean_ricci": 0.015,
        }
    )
    tracker.record_status("analytics-completed", {"points": 4})
    tracker.log_artifact(data_path, alias="dataset.csv")
    tracker.finalize(results={"status": "ok"}, error=None)

    reports_dir = (
        Path(experiment_cfg.tracking.base_dir) / experiment_cfg.tracking.reports_dirname
    )
    artifacts_dir = (
        Path(experiment_cfg.tracking.base_dir)
        / experiment_cfg.tracking.artifacts_dirname
    )
    assert (reports_dir / experiment_cfg.tracking.reports.markdown_filename).exists()
    assert (reports_dir / experiment_cfg.tracking.reports.dashboard_filename).exists()
    assert (reports_dir / "ci_summary.json").exists()
    assert (artifacts_dir / "metrics.json").exists()
    archives = sorted(
        (Path(experiment_cfg.tracking.base_dir) / "archives").glob("*.zip")
    )
    assert archives, "expected archive to be generated"


def test_tracker_detects_baseline_deviation(
    tmp_path: Path, experiment_cfg: ExperimentConfig, run_metadata: RunMetadata
) -> None:
    hydra_cfg = _hydra_cfg(experiment_cfg)
    tracker = ExperimentTracker.from_experiment(experiment_cfg, run_metadata)
    assert hydra_cfg["experiment"]["random_seed"] == experiment_cfg.random_seed
    data_path = tmp_path / "prices.csv"
    data_path.write_text("price\n1\n2\n3\n4\n", encoding="utf-8")
    tracker.log_data_version(data_path)

    with pytest.raises(ExperimentDeviationError):
        tracker.log_metrics(
            {
                "order_parameter": 2.0,
                "entropy": 0.1,
                "delta_entropy": 0.9,
                "mean_ricci": 0.2,
            }
        )

    alerts_path = (
        Path(experiment_cfg.tracking.base_dir)
        / experiment_cfg.tracking.reports_dirname
        / "alerts.json"
    )
    assert alerts_path.exists()
