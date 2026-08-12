from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import pytest
import yaml
from click.testing import CliRunner

from cli.tradepulse_cli import cli
from core.config.cli_models import IngestConfig, VersioningConfig
from core.config.template_manager import ConfigTemplateManager
from core.data.feature_catalog import FeatureCatalog
from core.data.feature_store import OnlineFeatureStore
from core.data.versioning import DataVersionManager


@pytest.fixture()
def sample_prices(tmp_path: Path) -> Path:
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=5, freq="D"),
            "price": [100.0, 101.0, 99.0, 102.0, 103.0],
        }
    )
    path = tmp_path / "prices.csv"
    frame.to_csv(path, index=False)
    return path


def _load_yaml(path: Path) -> Dict[str, Any]:
    return yaml.safe_load(path.read_text())


def _write_yaml(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


def test_cli_generates_templates(tmp_path: Path) -> None:
    runner = CliRunner()
    for command in (
        "ingest",
        "backtest",
        "optimize",
        "exec",
        "report",
        "parity",
        "deploy",
    ):
        destination = tmp_path / f"{command}.yaml"
        result = runner.invoke(
            cli, [command, "--generate-config", "--template-output", str(destination)]
        )
        assert result.exit_code == 0, result.output
        assert destination.exists()


def test_cli_aliases_generate_templates(tmp_path: Path) -> None:
    runner = CliRunner()
    for alias in ("materialize", "train", "serve"):
        destination = tmp_path / f"{alias}.yaml"
        result = runner.invoke(
            cli, [alias, "--generate-config", "--template-output", str(destination)]
        )
        assert result.exit_code == 0, result.output
        assert destination.exists()


def test_full_cli_flow(tmp_path: Path, sample_prices: Path) -> None:
    manager = ConfigTemplateManager(Path("configs/templates"))

    catalog_path = tmp_path / "catalog.json"
    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    # Ingest
    ingest_cfg_path = tmp_path / "ingest.yaml"
    manager.render("ingest", ingest_cfg_path)
    ingest_cfg = _load_yaml(ingest_cfg_path)
    ingest_cfg["source"]["path"] = str(sample_prices)
    ingest_destination = tmp_path / "ingested.csv"
    ingest_cfg["destination"] = str(ingest_destination)
    ingest_cfg["catalog"] = {"path": str(catalog_path)}
    ingest_cfg["versioning"] = {"backend": "dvc", "repo_path": str(repo_path)}
    _write_yaml(ingest_cfg_path, ingest_cfg)

    runner = CliRunner()
    result = runner.invoke(cli, ["ingest", "--config", str(ingest_cfg_path)])
    assert result.exit_code == 0, result.output
    assert ingest_destination.exists()
    assert (ingest_destination.with_suffix(".csv.version.json")).exists()

    # Backtest
    backtest_cfg_path = tmp_path / "backtest.yaml"
    manager.render("backtest", backtest_cfg_path)
    backtest_cfg = _load_yaml(backtest_cfg_path)
    backtest_cfg["data"]["path"] = str(sample_prices)
    backtest_results = tmp_path / "backtest.json"
    backtest_cfg["results_path"] = str(backtest_results)
    backtest_cfg["catalog"] = {"path": str(catalog_path)}
    backtest_cfg["versioning"] = {"backend": "dvc", "repo_path": str(repo_path)}
    _write_yaml(backtest_cfg_path, backtest_cfg)

    result = runner.invoke(cli, ["backtest", "--config", str(backtest_cfg_path)])
    assert result.exit_code == 0, result.output
    backtest_payload = json.loads(backtest_results.read_text())
    assert backtest_payload["stats"]["trades"] >= 0

    # Exec
    exec_cfg_path = tmp_path / "exec.yaml"
    manager.render("exec", exec_cfg_path)
    exec_cfg = _load_yaml(exec_cfg_path)
    exec_cfg["data"]["path"] = str(sample_prices)
    exec_results = tmp_path / "exec.json"
    exec_cfg["results_path"] = str(exec_results)
    exec_cfg["catalog"] = {"path": str(catalog_path)}
    exec_cfg["versioning"] = {"backend": "dvc", "repo_path": str(repo_path)}
    _write_yaml(exec_cfg_path, exec_cfg)

    result = runner.invoke(cli, ["exec", "--config", str(exec_cfg_path)])
    assert result.exit_code == 0, result.output
    exec_payload = json.loads(exec_results.read_text())
    assert "latest_signal" in exec_payload

    # Optimize
    optimize_cfg_path = tmp_path / "optimize.yaml"
    manager.render("optimize", optimize_cfg_path)
    optimize_cfg = _load_yaml(optimize_cfg_path)
    optimize_cfg["metadata"]["backtest"]["data"]["path"] = str(sample_prices)
    optimize_cfg["metadata"]["backtest"]["results_path"] = str(
        tmp_path / "opt_backtest.json"
    )
    optimize_cfg["results_path"] = str(tmp_path / "optimize.json")
    optimize_cfg["versioning"] = {"backend": "dvc", "repo_path": str(repo_path)}
    _write_yaml(optimize_cfg_path, optimize_cfg)

    result = runner.invoke(cli, ["optimize", "--config", str(optimize_cfg_path)])
    assert result.exit_code == 0, result.output
    optimize_payload = json.loads((tmp_path / "optimize.json").read_text())
    assert optimize_payload["best_params"] is not None
    assert optimize_payload["trials"]

    # Report
    report_cfg_path = tmp_path / "report.yaml"
    manager.render("report", report_cfg_path)
    report_cfg = _load_yaml(report_cfg_path)
    report_output = tmp_path / "report.md"
    report_cfg["inputs"] = [str(backtest_results), str(exec_results)]
    report_cfg["output_path"] = str(report_output)
    report_cfg["versioning"] = {"backend": "dvc", "repo_path": str(repo_path)}
    _write_yaml(report_cfg_path, report_cfg)

    result = runner.invoke(cli, ["report", "--config", str(report_cfg_path)])
    assert result.exit_code == 0, result.output
    text = report_output.read_text()
    lower_text = text.lower()
    assert "backtest" in lower_text
    assert "exec" in lower_text

    catalog = json.loads(catalog_path.read_text())
    assert len(catalog["artifacts"]) >= 3


def test_deploy_cli_applies_manifests(tmp_path: Path) -> None:
    runner = CliRunner()
    manager = ConfigTemplateManager(Path("configs/templates"))
    config_path = tmp_path / "deploy.yaml"
    manager.render("deploy", config_path)

    config_data = _load_yaml(config_path)
    config_data["artifact"] = "ghcr.io/neuron7x/tradepulse@sha256:1234"
    config_data["strategy"] = "alpha-live"
    config_data["kubectl"]["extra_args"] = []
    manifests_cfg = config_data.setdefault("manifests", {})
    manifests_cfg.pop("name", None)
    manifests_cfg["path"] = str(Path("deploy/kustomize/overlays/staging").resolve())

    log_path = tmp_path / "kubectl.log"
    kubectl_stub = tmp_path / "kubectl"
    kubectl_stub.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys

log = os.environ["KUBECTL_LOG"]
with open(log, "a", encoding="utf-8") as handle:
    json.dump({"argv": sys.argv[1:]}, handle)
    handle.write("\\n")
""",
        encoding="utf-8",
    )
    kubectl_stub.chmod(0o755)

    config_data["kubectl"]["binary"] = str(kubectl_stub)
    config_data["kubectl"]["env"] = {"KUBECTL_LOG": str(log_path)}
    config_data["summary_path"] = str(tmp_path / "summary.json")
    _write_yaml(config_path, config_data)

    result = runner.invoke(cli, ["deploy", "--config", str(config_path)])
    assert result.exit_code == 0, result.output

    entries = [
        json.loads(line)["argv"]
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(entries) == 4
    assert entries[0][0] == "apply"
    assert "--dry-run=client" in entries[0]
    assert entries[1][0] == "apply"
    assert all("--dry-run=" not in arg for arg in entries[1])
    assert entries[2][0] == "annotate"
    assert f"deployment/{config_data['deployment_name']}" in entries[2]
    assert entries[3][:2] == ["rollout", "status"]

    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["artifact"] == config_data["artifact"]
    assert summary["strategy"] == config_data["strategy"]
    assert summary["environment"] == config_data["environment"]
    assert (
        summary["annotations"]["tradepulse.dev/artifact-digest"]
        == config_data["artifact"]
    )
    assert (
        summary["annotations"]["tradepulse.dev/strategy-id"] == config_data["strategy"]
    )


def test_parity_cli_synchronizes_store(tmp_path: Path) -> None:
    runner = CliRunner()
    manager = ConfigTemplateManager(Path("configs/templates"))

    parity_cfg_path = tmp_path / "parity.yaml"
    manager.render("parity", parity_cfg_path)
    cfg = _load_yaml(parity_cfg_path)

    offline_frame = pd.DataFrame(
        {
            "entity_id": ["A", "A"],
            "ts": ["2024-01-01T00:00:00Z", "2024-01-01T00:01:00Z"],
            "value": [1.0, 1.5],
        }
    )
    offline_path = tmp_path / "offline_features.csv"
    offline_frame.to_csv(offline_path, index=False)

    feature_view = "demo_features"
    online_store = tmp_path / "online"
    cfg["offline"]["path"] = str(offline_path)
    cfg["online_store"] = str(online_store)
    cfg["spec"]["feature_view"] = feature_view
    cfg["spec"]["timestamp_granularity"] = "1min"
    cfg["spec"]["numeric_tolerance"] = 0.0
    cfg["mode"] = "overwrite"
    _write_yaml(parity_cfg_path, cfg)

    result = runner.invoke(cli, ["parity", "--config", str(parity_cfg_path)])
    assert result.exit_code == 0, result.output
    assert "feature_view=demo_features" in result.output
    assert "inserted=2" in result.output

    store = OnlineFeatureStore(online_store)
    stored = store.load(feature_view)
    assert stored.shape[0] == 2
    assert set(stored.columns) == {"entity_id", "ts", "value"}


def test_backtest_outputs_jsonl(tmp_path: Path, sample_prices: Path) -> None:
    manager = ConfigTemplateManager(Path("configs/templates"))
    backtest_cfg_path = tmp_path / "backtest.yaml"
    manager.render("backtest", backtest_cfg_path)
    cfg = _load_yaml(backtest_cfg_path)
    cfg["data"]["path"] = str(sample_prices)
    cfg["results_path"] = str(tmp_path / "results.json")
    _write_yaml(backtest_cfg_path, cfg)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "backtest",
            "--config",
            str(backtest_cfg_path),
            "--output",
            "jsonl",
        ],
    )
    assert result.exit_code == 0, result.output
    lines = [line for line in result.output.splitlines() if line.startswith("{")]
    assert any('"metric": "total_return"' in line for line in lines)


def test_versioning_manager_writes_metadata(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("hello", encoding="utf-8")

    cfg = VersioningConfig(backend="dvc", repo_path=tmp_path)
    manager = DataVersionManager(cfg)
    result = manager.snapshot(artifact, metadata={"size": 5})
    metadata_path = artifact.with_suffix(".txt.version.json")
    assert metadata_path.exists()
    assert result["backend"] == "dvc"
    assert result["metadata"]["size"] == 5


def test_feature_catalog_register(tmp_path: Path, sample_prices: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog = FeatureCatalog(catalog_path)
    config = IngestConfig(
        name="test",
        source={"kind": "csv", "path": sample_prices},
        destination=tmp_path / "dest.csv",
    )
    config.destination.write_text("data", encoding="utf-8")
    entry = catalog.register(
        "artifact",
        config.destination,
        config=config,
        lineage=["input"],
        metadata={"owner": "qa"},
    )
    assert entry.name == "artifact"
    stored = catalog.find("artifact")
    assert stored is not None and stored.checksum == entry.checksum
