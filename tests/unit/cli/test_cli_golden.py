# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Golden snapshot tests for the GeoSync CLI commands."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable

import pandas as pd
import pytest
from click.testing import CliRunner

from geosync.cli.geosync_cli import cli
from core.config.template_manager import ConfigTemplateManager

SNAPSHOT_DIR = Path(__file__).parent / "__snapshots__"
SNAPSHOT_DIR.mkdir(exist_ok=True)

_DURATION_RE = re.compile(r"\(\d+\.\d+s\)")
_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?")
_SHA_RE = re.compile(r"sha256=[0-9a-f]{64}")


def _normalise_paths(text: str, paths: Iterable[Path]) -> str:
    normalised = text
    for path in paths:
        resolved = str(path.resolve())
        normalised = normalised.replace(resolved, "<TMP>")
        normalised = normalised.replace(str(path), "<TMP>")
    return normalised


def _normalise_output(text: str, tmp_path: Path) -> str:
    result = _normalise_paths(text, {tmp_path})
    result = _DURATION_RE.sub("(0.00s)", result)
    result = _TIMESTAMP_RE.sub("<TIMESTAMP>", result)
    result = _SHA_RE.sub("sha256=<SHA>", result)
    return result.strip() + "\n"


@pytest.fixture()
def sample_prices(tmp_path: Path) -> Path:
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=6, freq="h"),
            "price": [100.0, 101.5, 99.5, 102.0, 103.5, 104.0],
        }
    )
    path = tmp_path / "prices.csv"
    frame.to_csv(path, index=False)
    return path


def _write_yaml(path: Path, payload: Dict[str, object]) -> None:
    import yaml

    path.write_text(yaml.safe_dump(payload), encoding="utf-8")


def _render_config(
    manager: ConfigTemplateManager, command: str, destination: Path
) -> Dict[str, object]:
    manager.render(command, destination)
    import yaml

    return yaml.safe_load(destination.read_text(encoding="utf-8"))


def _run_and_assert(command: str, args: list[str], snapshot_name: str, tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, [command, *args])
    assert result.exit_code == 0, result.output

    combined = _normalise_output(result.output, tmp_path)
    payload = "STDOUT+STDERR:\n" + combined

    snapshot_path = SNAPSHOT_DIR / f"{snapshot_name}.snap"
    expected = snapshot_path.read_text(encoding="utf-8")
    assert payload == expected


def test_ingest_golden(tmp_path: Path, sample_prices: Path) -> None:
    manager = ConfigTemplateManager(Path("configs/templates"))
    cfg_path = tmp_path / "ingest.yaml"
    cfg = _render_config(manager, "ingest", cfg_path)
    cfg["source"]["path"] = str(sample_prices)
    cfg["destination"] = str(tmp_path / "ingested.csv")
    cfg["catalog"] = {"path": str(tmp_path / "catalog.json")}
    cfg["versioning"] = {"backend": "none"}
    _write_yaml(cfg_path, cfg)

    _run_and_assert("ingest", ["--config", str(cfg_path)], "ingest", tmp_path)


def test_backtest_golden(tmp_path: Path, sample_prices: Path) -> None:
    manager = ConfigTemplateManager(Path("configs/templates"))
    cfg_path = tmp_path / "backtest.yaml"
    cfg = _render_config(manager, "backtest", cfg_path)
    cfg["data"]["path"] = str(sample_prices)
    cfg["results_path"] = str(tmp_path / "backtest.json")
    cfg["catalog"] = {"path": str(tmp_path / "catalog.json")}
    cfg["versioning"] = {"backend": "none"}
    _write_yaml(cfg_path, cfg)

    _run_and_assert("backtest", ["--config", str(cfg_path)], "backtest", tmp_path)


def test_report_golden(tmp_path: Path, sample_prices: Path) -> None:
    manager = ConfigTemplateManager(Path("configs/templates"))
    backtest_results = tmp_path / "backtest.json"
    backtest_results.write_text(json.dumps({"stats": {"trades": 0}}, indent=2), encoding="utf-8")
    exec_results = tmp_path / "exec.json"
    exec_results.write_text(json.dumps({"latest_signal": 1}, indent=2), encoding="utf-8")

    cfg_path = tmp_path / "report.yaml"
    cfg = _render_config(manager, "report", cfg_path)
    cfg["inputs"] = [str(backtest_results), str(exec_results)]
    cfg["output_path"] = str(tmp_path / "report.md")
    cfg["versioning"] = {"backend": "none"}
    _write_yaml(cfg_path, cfg)

    _run_and_assert("report", ["--config", str(cfg_path)], "report", tmp_path)
