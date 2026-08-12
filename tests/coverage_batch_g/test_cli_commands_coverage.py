# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""End-to-end command coverage for ``geosync.cli.geosync_cli``.

Each GeoSync subcommand is driven through ``click.testing.CliRunner`` to cover
the template-generation guards, config-required guards, the happy path, and the
per-format output emitters. Heavy or non-deterministic backends (kubectl, the
V21 causal pipeline, HTML/PDF renderers) are stubbed so the tests stay hermetic.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

import numpy as np
import pandas as pd
import pytest
import yaml
from click.testing import CliRunner

import geosync.cli.geosync_cli as gc
from core.config.cli_models import ReportConfig
from core.config.template_manager import ConfigTemplateManager

TEMPLATES = Path("configs/templates")


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def sample_prices(tmp_path: Path) -> Path:
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=6, freq="D"),
            "price": [100.0, 101.0, 99.0, 102.0, 103.0, 104.0],
        }
    )
    path = tmp_path / "prices.csv"
    frame.to_csv(path, index=False)
    return path


def _load_yaml(path: Path) -> Dict[str, Any]:
    data = yaml.safe_load(path.read_text())
    assert isinstance(data, dict)
    return data


def _write_yaml(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


def _rendered(tmp_path: Path, command: str) -> Path:
    manager = ConfigTemplateManager(TEMPLATES)
    dest = tmp_path / f"{command}.yaml"
    manager.render(command, dest)
    return dest


# --------------------------------------------------------------------------
# completion + top-level guards
# --------------------------------------------------------------------------
@pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
def test_completion_emits_snippet(runner: CliRunner, shell: str) -> None:
    result = runner.invoke(gc.cli, ["completion", shell])
    assert result.exit_code == 0, result.output
    assert "_COMPLETE" in result.output


def test_completion_rejects_unknown_shell(runner: CliRunner) -> None:
    result = runner.invoke(gc.cli, ["completion", "powershell"])
    assert result.exit_code != 0


# --------------------------------------------------------------------------
# generate-config guard + config-required guard (shared across commands)
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "command",
    ["ingest", "backtest", "optimize", "exec", "report", "parity", "deploy"],
)
def test_generate_config_requires_output(runner: CliRunner, command: str) -> None:
    result = runner.invoke(gc.cli, [command, "--generate-config"])
    assert result.exit_code == 2
    assert "--template-output is required" in result.output


@pytest.mark.parametrize(
    "command",
    ["ingest", "backtest", "optimize", "exec", "report", "parity", "deploy"],
)
def test_generate_config_writes_template(
    runner: CliRunner, tmp_path: Path, command: str
) -> None:
    dest = tmp_path / f"{command}.yaml"
    result = runner.invoke(
        gc.cli, [command, "--generate-config", "--template-output", str(dest)]
    )
    assert result.exit_code == 0, result.output
    assert dest.exists()


@pytest.mark.parametrize(
    "command",
    ["ingest", "backtest", "optimize", "exec", "report", "parity", "deploy"],
)
def test_command_requires_config(runner: CliRunner, command: str) -> None:
    result = runner.invoke(gc.cli, [command])
    assert result.exit_code == 2
    assert "--config is required" in result.output


# --------------------------------------------------------------------------
# ingest happy path
# --------------------------------------------------------------------------
def test_ingest_runs(runner: CliRunner, tmp_path: Path, sample_prices: Path) -> None:
    cfg_path = _rendered(tmp_path, "ingest")
    cfg = _load_yaml(cfg_path)
    cfg["source"]["path"] = str(sample_prices)
    cfg["destination"] = str(tmp_path / "ingested.csv")
    cfg["catalog"] = {"path": str(tmp_path / "catalog.json")}
    cfg["versioning"] = {"backend": "dvc", "repo_path": str(tmp_path / "repo")}
    (tmp_path / "repo").mkdir()
    _write_yaml(cfg_path, cfg)

    result = runner.invoke(gc.cli, ["ingest", "--config", str(cfg_path)])
    assert result.exit_code == 0, result.output
    assert "completed records=6" in result.output


def test_ingest_worker_propagates_error(
    runner: CliRunner, tmp_path: Path
) -> None:
    cfg_path = _rendered(tmp_path, "ingest")
    cfg = _load_yaml(cfg_path)
    cfg["source"]["path"] = str(tmp_path / "missing.csv")
    cfg["destination"] = str(tmp_path / "ingested.csv")
    _write_yaml(cfg_path, cfg)

    result = runner.invoke(gc.cli, ["ingest", "--config", str(cfg_path)])
    assert result.exit_code == 3
    assert "does not exist" in result.output


# --------------------------------------------------------------------------
# backtest happy path + output formats
# --------------------------------------------------------------------------
def _backtest_cfg(tmp_path: Path, sample_prices: Path) -> Path:
    cfg_path = _rendered(tmp_path, "backtest")
    cfg = _load_yaml(cfg_path)
    cfg["data"]["path"] = str(sample_prices)
    cfg["results_path"] = str(tmp_path / "backtest.json")
    cfg["catalog"] = {"path": str(tmp_path / "catalog.json")}
    cfg["versioning"] = {"backend": "none"}
    _write_yaml(cfg_path, cfg)
    return cfg_path


@pytest.mark.parametrize("fmt", ["table", "jsonl", "parquet"])
def test_backtest_runs_with_output(
    runner: CliRunner, tmp_path: Path, sample_prices: Path, fmt: str
) -> None:
    cfg_path = _backtest_cfg(tmp_path, sample_prices)
    result = runner.invoke(
        gc.cli, ["backtest", "--config", str(cfg_path), "--output", fmt]
    )
    assert result.exit_code == 0, result.output
    assert "completed" in result.output


# --------------------------------------------------------------------------
# optimize happy path + output formats + guard
# --------------------------------------------------------------------------
def _optimize_cfg(tmp_path: Path, sample_prices: Path) -> Path:
    cfg_path = _rendered(tmp_path, "optimize")
    cfg = _load_yaml(cfg_path)
    cfg["metadata"]["backtest"]["data"]["path"] = str(sample_prices)
    cfg["metadata"]["backtest"]["results_path"] = str(tmp_path / "opt_bt.json")
    cfg["results_path"] = str(tmp_path / "optimize.json")
    cfg["versioning"] = {"backend": "none"}
    _write_yaml(cfg_path, cfg)
    return cfg_path


@pytest.mark.parametrize("fmt", ["table", "jsonl", "parquet"])
def test_optimize_runs_with_output(
    runner: CliRunner, tmp_path: Path, sample_prices: Path, fmt: str
) -> None:
    cfg_path = _optimize_cfg(tmp_path, sample_prices)
    result = runner.invoke(
        gc.cli, ["optimize", "--config", str(cfg_path), "--output", fmt]
    )
    assert result.exit_code == 0, result.output
    assert "completed trials=" in result.output


def test_optimize_requires_embedded_backtest(
    runner: CliRunner, tmp_path: Path
) -> None:
    cfg_path = _rendered(tmp_path, "optimize")
    cfg = _load_yaml(cfg_path)
    cfg["metadata"] = {}
    cfg["versioning"] = {"backend": "none"}
    _write_yaml(cfg_path, cfg)
    result = runner.invoke(gc.cli, ["optimize", "--config", str(cfg_path)])
    assert result.exit_code == 2
    assert "embedded backtest metadata" in result.output


# --------------------------------------------------------------------------
# exec happy path + output formats + serve alias
# --------------------------------------------------------------------------
def _exec_cfg(tmp_path: Path, sample_prices: Path) -> Path:
    cfg_path = _rendered(tmp_path, "exec")
    cfg = _load_yaml(cfg_path)
    cfg["data"]["path"] = str(sample_prices)
    cfg["results_path"] = str(tmp_path / "exec.json")
    cfg["catalog"] = {"path": str(tmp_path / "catalog.json")}
    cfg["versioning"] = {"backend": "none"}
    _write_yaml(cfg_path, cfg)
    return cfg_path


@pytest.mark.parametrize("fmt", ["table", "jsonl", "parquet"])
def test_exec_runs_with_output(
    runner: CliRunner, tmp_path: Path, sample_prices: Path, fmt: str
) -> None:
    cfg_path = _exec_cfg(tmp_path, sample_prices)
    result = runner.invoke(
        gc.cli, ["exec", "--config", str(cfg_path), "--output", fmt]
    )
    assert result.exit_code == 0, result.output
    assert "completed latest_signal=" in result.output


def test_serve_alias_runs(
    runner: CliRunner, tmp_path: Path, sample_prices: Path
) -> None:
    cfg_path = _exec_cfg(tmp_path, sample_prices)
    result = runner.invoke(gc.cli, ["serve", "--config", str(cfg_path)])
    assert result.exit_code == 0, result.output


# --------------------------------------------------------------------------
# report happy path + html/pdf render + output + FileNotFound
# --------------------------------------------------------------------------
def test_report_runs_with_html_pdf(
    runner: CliRunner,
    tmp_path: Path,
    sample_prices: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backtest_json = tmp_path / "bt.json"
    backtest_json.write_text('{"stats": {"total_return": 0.1}}', encoding="utf-8")

    def _render(_text: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("rendered", encoding="utf-8")

    monkeypatch.setattr(gc, "render_markdown_to_html", _render)
    monkeypatch.setattr(gc, "render_markdown_to_pdf", _render)

    cfg_path = _rendered(tmp_path, "report")
    cfg = _load_yaml(cfg_path)
    cfg["inputs"] = [str(backtest_json)]
    cfg["output_path"] = str(tmp_path / "report.md")
    cfg["html_output_path"] = str(tmp_path / "report.html")
    cfg["pdf_output_path"] = str(tmp_path / "report.pdf")
    cfg["versioning"] = {"backend": "none"}
    _write_yaml(cfg_path, cfg)

    result = runner.invoke(
        gc.cli, ["report", "--config", str(cfg_path), "--output", "table"]
    )
    assert result.exit_code == 0, result.output
    assert "html sha256=" in result.output
    assert "pdf sha256=" in result.output


def test_report_missing_input_raises_artifact_error(
    runner: CliRunner, tmp_path: Path
) -> None:
    cfg_path = _rendered(tmp_path, "report")
    cfg = _load_yaml(cfg_path)
    cfg["inputs"] = [str(tmp_path / "missing.json")]
    cfg["output_path"] = str(tmp_path / "report.md")
    cfg.pop("html_output_path", None)
    cfg.pop("pdf_output_path", None)
    cfg["versioning"] = {"backend": "none"}
    _write_yaml(cfg_path, cfg)

    result = runner.invoke(gc.cli, ["report", "--config", str(cfg_path)])
    assert result.exit_code == 3


# --------------------------------------------------------------------------
# parity happy path + error
# --------------------------------------------------------------------------
def _parity_cfg(tmp_path: Path, offline: Path) -> Path:
    cfg_path = _rendered(tmp_path, "parity")
    cfg = _load_yaml(cfg_path)
    cfg["offline"]["path"] = str(offline)
    cfg["online_store"] = str(tmp_path / "online")
    cfg["spec"]["feature_view"] = "demo"
    cfg["spec"]["timestamp_granularity"] = "1min"
    cfg["spec"]["numeric_tolerance"] = 0.0
    cfg["mode"] = "overwrite"
    _write_yaml(cfg_path, cfg)
    return cfg_path


def test_parity_runs(runner: CliRunner, tmp_path: Path) -> None:
    offline = tmp_path / "offline.csv"
    pd.DataFrame(
        {
            "entity_id": ["A", "A"],
            "ts": ["2024-01-01T00:00:00Z", "2024-01-01T00:01:00Z"],
            "value": [1.0, 1.5],
        }
    ).to_csv(offline, index=False)
    cfg_path = _parity_cfg(tmp_path, offline)
    result = runner.invoke(gc.cli, ["parity", "--config", str(cfg_path)])
    assert result.exit_code == 0, result.output
    assert "feature_view=demo" in result.output


def test_parity_reports_error(runner: CliRunner, tmp_path: Path) -> None:
    offline = tmp_path / "offline.csv"
    pd.DataFrame({"entity_id": ["A"], "ts": ["2024-01-01T00:00:00Z"]}).to_csv(
        offline, index=False
    )
    cfg_path = _parity_cfg(tmp_path, offline)

    def _boom(*_a: Any, **_k: Any) -> None:
        raise gc.FeatureParityError("mismatch")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(gc.FeatureParityCoordinator, "synchronize", _boom)
    try:
        result = runner.invoke(gc.cli, ["parity", "--config", str(cfg_path)])
    finally:
        monkeypatch.undo()
    assert result.exit_code == 5


# --------------------------------------------------------------------------
# deploy happy path (dry-run + rollout) and skip-branches
# --------------------------------------------------------------------------
def _kubectl_stub(tmp_path: Path) -> Path:
    stub = tmp_path / "kubectl"
    stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    stub.chmod(0o755)
    return stub


def test_deploy_full_flow(runner: CliRunner, tmp_path: Path) -> None:
    cfg_path = _rendered(tmp_path, "deploy")
    cfg = _load_yaml(cfg_path)
    cfg["manifests"] = {"path": str(Path("deploy/kustomize/overlays/staging").resolve())}
    cfg["kubectl"]["binary"] = str(_kubectl_stub(tmp_path))
    cfg["summary_path"] = str(tmp_path / "summary.json")
    _write_yaml(cfg_path, cfg)

    result = runner.invoke(gc.cli, ["deploy", "--config", str(cfg_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "summary.json").exists()


def test_deploy_skips_dry_run_and_rollout(runner: CliRunner, tmp_path: Path) -> None:
    cfg_path = _rendered(tmp_path, "deploy")
    cfg = _load_yaml(cfg_path)
    cfg["manifests"] = {"path": str(Path("deploy/kustomize/overlays/staging").resolve())}
    cfg["kubectl"]["binary"] = str(_kubectl_stub(tmp_path))
    cfg["kubectl"]["dry_run"] = "none"
    cfg["wait_for_rollout"] = False
    cfg["summary_path"] = str(tmp_path / "summary.json")
    _write_yaml(cfg_path, cfg)

    result = runner.invoke(gc.cli, ["deploy", "--config", str(cfg_path)])
    assert result.exit_code == 0, result.output


def test_deploy_missing_manifests_raises(runner: CliRunner, tmp_path: Path) -> None:
    cfg_path = _rendered(tmp_path, "deploy")
    cfg = _load_yaml(cfg_path)
    cfg["manifests"] = {"path": str(tmp_path / "does-not-exist")}
    cfg["kubectl"]["binary"] = str(_kubectl_stub(tmp_path))
    _write_yaml(cfg_path, cfg)

    result = runner.invoke(gc.cli, ["deploy", "--config", str(cfg_path)])
    assert result.exit_code == 3


# --------------------------------------------------------------------------
# fete-backtest command
# --------------------------------------------------------------------------
def test_fete_backtest_synthetic_and_output(
    runner: CliRunner, tmp_path: Path
) -> None:
    csv_path = tmp_path / "prices.csv"
    pd.DataFrame({"price": np.linspace(100.0, 110.0, 40)}).to_csv(
        csv_path, index=False
    )
    out_path = tmp_path / "equity.csv"
    result = runner.invoke(
        gc.cli,
        ["fete-backtest", "--csv", str(csv_path), "--out", str(out_path)],
    )
    assert result.exit_code == 0, result.output
    assert "FETE Backtest" in result.output
    assert out_path.exists()


# --------------------------------------------------------------------------
# causal-pipeline command (stubbed V21 pipeline)
# --------------------------------------------------------------------------
class _FakeV21:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def build(self, *args: Any, **kwargs: Any) -> str:
        return "FEATURES"

    def run(self, *args: Any, **kwargs: Any) -> str:
        return "RESULT"


def _patch_v21(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "StrictCausalFeatureBuilder",
        "FeatureBuilderConfig",
        "LogisticIsotonicTrainer",
        "ModelTrainingConfig",
        "RegimeHMMAdapter",
        "RegimeHMMConfig",
        "ProbabilityBacktester",
        "BacktestConfig",
        "GeoSyncV21Pipeline",
        "EnsembleConfig",
    ):
        monkeypatch.setattr(gc.v21, name, _FakeV21)
    monkeypatch.setattr(gc.v21, "result_to_json", lambda _r: '{"ok": true}')


def test_causal_pipeline_requires_exactly_one_source(runner: CliRunner) -> None:
    result = runner.invoke(gc.cli, ["causal-pipeline"])
    assert result.exit_code == 2
    assert "exactly one" in result.output


def test_causal_pipeline_from_returns(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_v21(monkeypatch)
    returns = tmp_path / "returns.csv"
    pd.DataFrame(
        {"date": ["2024-01-01", "2024-01-02"], "AAA": [0.01, -0.02]}
    ).to_csv(returns, index=False)
    output = tmp_path / "out.json"
    result = runner.invoke(
        gc.cli,
        ["causal-pipeline", "--returns-csv", str(returns), "--output", str(output)],
    )
    assert result.exit_code == 0, result.output
    assert output.exists()
    assert '"ok"' in result.output


def test_causal_pipeline_from_features(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_v21(monkeypatch)
    features = tmp_path / "features.csv"
    pd.DataFrame(
        {
            "dr": [0.1, 0.2],
            "ricci_mean": [0.0, 0.1],
            "topo_intensity": [0.3, 0.4],
            "causal_strength": [0.5, 0.6],
            "y": [0, 1],
        }
    ).to_csv(features, index=False)
    result = runner.invoke(
        gc.cli,
        ["causal-pipeline", "--features-csv", str(features), "--hmm-states", "3"],
    )
    assert result.exit_code == 0, result.output
    assert '"ok"' in result.output


# --------------------------------------------------------------------------
# output-emitter unsupported-format guards (direct calls)
# --------------------------------------------------------------------------
def test_emit_backtest_output_none_and_unsupported(tmp_path: Path) -> None:
    cfg: Any = SimpleNamespace(results_path=tmp_path / "r.json")
    result = {"stats": {"a": 1.0}, "signals": [0.0, 1.0], "returns": [0.0, 0.1]}
    gc._emit_backtest_output(cfg, result, None, command="t")
    with pytest.raises(gc.ConfigError, match="Unsupported output format"):
        gc._emit_backtest_output(cfg, result, "bogus", command="t")


def test_emit_optimize_output_none_and_unsupported(tmp_path: Path) -> None:
    cfg: Any = SimpleNamespace(results_path=tmp_path / "r.json")
    payload = {"best_score": 1.0, "best_params": {"w": 3}, "trials": [{"params": {}}]}
    gc._emit_optimize_output(cfg, payload, None, command="t")
    with pytest.raises(gc.ConfigError, match="Unsupported output format"):
        gc._emit_optimize_output(cfg, payload, "bogus", command="t")


def test_emit_optimize_output_table_without_params(tmp_path: Path) -> None:
    cfg: Any = SimpleNamespace(results_path=tmp_path / "r.json")
    payload = {"best_score": 0.0, "best_params": None, "trials": []}
    gc._emit_optimize_output(cfg, payload, "table", command="t")
    gc._emit_optimize_output(cfg, payload, "jsonl", command="t")


def test_emit_exec_output_none_and_unsupported(tmp_path: Path) -> None:
    cfg: Any = SimpleNamespace(results_path=tmp_path / "r.json")
    result = {"latest_signal": 1.0, "count": 2}
    signals = np.array([0.0, 1.0])
    gc._emit_exec_output(cfg, result, signals, None, command="t")
    with pytest.raises(gc.ConfigError, match="Unsupported output format"):
        gc._emit_exec_output(cfg, result, signals, "bogus", command="t")


def test_emit_report_output_formats_and_unsupported(tmp_path: Path) -> None:
    cfg = ReportConfig(
        name="r",
        inputs=[tmp_path / "a.json", tmp_path / "b.json"],
        output_path=tmp_path / "r.md",
    )
    gc._emit_report_output(cfg, "line1\nline2", None, command="t")
    gc._emit_report_output(cfg, "line1\nline2", "table", command="t")
    gc._emit_report_output(cfg, "line1\nline2", "jsonl", command="t")
    gc._emit_report_output(cfg, "line1\nline2", "parquet", command="t")
    with pytest.raises(gc.ConfigError, match="Unsupported output format"):
        gc._emit_report_output(cfg, "line1", "bogus", command="t")
