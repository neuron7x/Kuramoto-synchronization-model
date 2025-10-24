"""Unit tests for the backwards compatibility regression guardrail."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.backcompatibility import BackcompatConfig, BackcompatRunner, _flatten_json


def _prepare_fixture(tmp_path: Path, fixture: str) -> Path:
    source = Path("scripts/tests/data/backcompat") / fixture
    destination = tmp_path / fixture
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return destination


def test_runner_detects_violation_and_generates_artifacts(tmp_path: Path) -> None:
    config_path = _prepare_fixture(tmp_path, "config.json")
    _prepare_fixture(tmp_path, "traffic.jsonl")
    _prepare_fixture(tmp_path, "baseline.json")
    _prepare_fixture(tmp_path, "candidate.json")

    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    config = BackcompatConfig.from_mapping(raw_config, tmp_path)
    runner = BackcompatRunner(config, release_channel="stable")

    result = runner.execute()

    assert result.blocked is True
    assert len(result.summaries) == 1
    summary = result.summaries[0]
    assert summary.dataset.name == "rates"
    assert len(summary.violations) == 1
    assert summary.violations[0].path == "$.body.price"
    assert summary.whitelisted

    report_dir = config.report_dir
    reports = list(report_dir.glob("backcompat_*.md"))
    assert reports, "Expected markdown report to be generated"

    counterexample_path = tmp_path / "reports" / "counterexamples.jsonl"
    assert counterexample_path.exists()
    counterexample_lines = counterexample_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(counterexample_lines) == 1

    stability_path = tmp_path / "reports" / "stability.json"
    assert stability_path.exists()
    stability_payload = json.loads(stability_path.read_text(encoding="utf-8"))
    assert stability_payload[0]["blocking_deviations"] == 1

    alerts_path = config.report_dir / "alerts.json"
    assert alerts_path.exists()
    alert_payload = json.loads(alerts_path.read_text(encoding="utf-8"))
    assert alert_payload["total_blocking"] == 1
    assert alert_payload["label"] == "backcompat-regression"

    snapshot_path = tmp_path / "reports" / "contracts" / "rates.json"
    assert snapshot_path.exists()
    snapshot_payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    paths = {field["path"] for field in snapshot_payload["fields"]}
    assert "$.body.price" in paths


def test_auto_update_baseline_when_enabled(tmp_path: Path) -> None:
    config_path = _prepare_fixture(tmp_path, "config.json")
    traffic_path = _prepare_fixture(tmp_path, "traffic.jsonl")
    baseline_path = _prepare_fixture(tmp_path, "baseline.json")
    candidate_path = _prepare_fixture(tmp_path, "candidate.json")

    candidate_payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate_payload["req-1"]["body"]["price"] = 1.12
    candidate_payload["req-2"]["body"]["price"] = 1.26
    candidate_path.write_text(json.dumps(candidate_payload, indent=2), encoding="utf-8")

    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    raw_config["auto_update_baseline"] = True
    raw_config["blocking_threshold"] = 0.05
    raw_config["datasets"][0]["baseline"] = baseline_path.name
    raw_config["datasets"][0]["actual"] = candidate_path.name
    raw_config["datasets"][0]["traffic"] = traffic_path.name
    raw_config["datasets"][0]["tolerance"]["absolute"] = 0.2

    config = BackcompatConfig.from_mapping(raw_config, tmp_path)
    runner = BackcompatRunner(config, release_channel="prod")

    result = runner.execute()

    assert result.blocked is False
    updated_baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert updated_baseline["req-1"]["body"]["price"] == pytest.approx(1.12)
    assert updated_baseline["req-2"]["body"]["price"] == pytest.approx(1.26)

    backup_path = baseline_path.with_suffix(".backup")
    assert backup_path.exists()


def test_flatten_json_includes_nested_paths() -> None:
    payload = {"outer": {"inner": [1, {"leaf": "value"}]}}
    flattened = _flatten_json(payload)
    assert flattened["$.outer.inner[0]"] == 1
    assert flattened["$.outer.inner[1].leaf"] == "value"
