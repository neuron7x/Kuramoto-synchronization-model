# mypy: ignore-errors
# ruff: noqa
# fmt: off
# SPDX-License-Identifier: MIT
"""Fail-closed tests for the Epistemic Rhombus manifest validator."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "validate_epistemic_rhombus_manifest.py"
MANIFEST_PATH = ROOT / "governance" / "epistemic_rhombus_manifest.jsonl"
SCHEMA_PATH = ROOT / "schemas" / "governance" / "epistemic_rhombus_manifest.schema.json"
FORBIDDEN_PR_TARGET_TRIGGER = "pull_request" + "_target"


def _load_module() -> Any:
    """Import the validator script as a testable module."""
    spec = importlib.util.spec_from_file_location(
        "validate_epistemic_rhombus_manifest",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["validate_epistemic_rhombus_manifest"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rhombus() -> Any:
    return _load_module()


@pytest.fixture()
def live_records(rhombus: Any) -> list[dict[str, Any]]:
    return [copy.deepcopy(record) for _, record in rhombus.iter_jsonl(MANIFEST_PATH)]


def _write_manifest(tmp_path: Path, records: list[dict[str, Any]]) -> Path:
    manifest = tmp_path / "epistemic_rhombus_manifest.jsonl"
    body = "\n".join(json.dumps(record, sort_keys=True) for record in records)
    manifest.write_text(f"{body}\n", encoding="utf-8")
    return manifest


def _validate_tmp(
    rhombus: Any,
    tmp_path: Path,
    records: list[dict[str, Any]],
    repo_root: Path = ROOT,
) -> list[str]:
    manifest = _write_manifest(tmp_path, records)
    return rhombus.validate_manifest(manifest, SCHEMA_PATH, repo_root)


def _write_workflow(repo_root: Path, name: str, body: str) -> str:
    workflow = repo_root / ".github" / "workflows" / name
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text(body, encoding="utf-8")
    return f".github/workflows/{name}"


def _minimal_gate_workflow() -> str:
    return """name: synthetic gate
on:
  pull_request:
    branches: [main]
permissions:
  contents: read
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
"""


def _forbidden_trigger_workflow() -> str:
    return f"""name: blocked trigger
on:
  {FORBIDDEN_PR_TARGET_TRIGGER}:
permissions:
  contents: read
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - run: echo blocked
"""


def test_live_manifest_passes(rhombus: Any) -> None:
    assert rhombus.validate_manifest(MANIFEST_PATH, SCHEMA_PATH, ROOT) == []


def test_live_manifest_covers_schema_axes_once(
    rhombus: Any,
    live_records: list[dict[str, Any]],
) -> None:
    schema = rhombus.load_schema(SCHEMA_PATH)
    required_axes = rhombus.required_axes(schema)
    axes = [record["axis"] for record in live_records]

    assert set(axes) == required_axes
    assert len(axes) == len(required_axes)


def test_schema_requires_nonempty_gate_coverage(rhombus: Any) -> None:
    schema = rhombus.load_schema(SCHEMA_PATH)
    control_gates = schema["properties"]["control_gates"]

    assert control_gates["minItems"] == 1


def test_schema_requires_external_gates_to_block_on_failure(rhombus: Any) -> None:
    schema = rhombus.load_schema(SCHEMA_PATH)
    blocks_on_failure = schema["properties"]["enforcement"]["properties"][
        "blocks_on_failure"
    ]

    assert blocks_on_failure["const"] is True


def test_schema_requires_threat_model(rhombus: Any) -> None:
    schema = rhombus.load_schema(SCHEMA_PATH)
    threat_model = schema["properties"]["threat_model"]

    assert "threat_model" in schema["required"]
    assert threat_model["properties"]["failure_modes"]["minItems"] == 1
    assert threat_model["properties"]["negative_controls"]["minItems"] == 1


def test_rejects_duplicate_record_id(
    rhombus: Any,
    live_records: list[dict[str, Any]],
    tmp_path: Path,
) -> None:
    live_records[1]["record_id"] = live_records[0]["record_id"]

    errors = _validate_tmp(rhombus, tmp_path, live_records)

    assert any("duplicate record_id" in error for error in errors)


def test_rejects_axis_record_id_mismatch(
    rhombus: Any,
    live_records: list[dict[str, Any]],
    tmp_path: Path,
) -> None:
    live_records[0]["record_id"] = "ER-99"

    errors = _validate_tmp(rhombus, tmp_path, live_records)

    assert any("must use record_id 'ER-1'" in error for error in errors)


def test_rejects_duplicate_axis(
    rhombus: Any,
    live_records: list[dict[str, Any]],
    tmp_path: Path,
) -> None:
    live_records[1]["axis"] = live_records[0]["axis"]

    errors = _validate_tmp(rhombus, tmp_path, live_records)

    assert any("duplicate axis" in error for error in errors)


def test_rejects_missing_schema_axis(
    rhombus: Any,
    live_records: list[dict[str, Any]],
    tmp_path: Path,
) -> None:
    records = [
        record
        for record in live_records
        if record["axis"] != "provenance_governance"
    ]

    errors = _validate_tmp(rhombus, tmp_path, records)

    assert any("missing axes: provenance_governance" in error for error in errors)


def test_rejects_empty_control_gate_coverage(
    rhombus: Any,
    live_records: list[dict[str, Any]],
    tmp_path: Path,
) -> None:
    live_records[0]["control_gates"] = []

    errors = _validate_tmp(rhombus, tmp_path, live_records)

    assert any("control_gates" in error for error in errors)


def test_rejects_duplicate_control_gate_across_records(
    rhombus: Any,
    live_records: list[dict[str, Any]],
    tmp_path: Path,
) -> None:
    live_records[1]["control_gates"] = [live_records[0]["control_gates"][0]]

    errors = _validate_tmp(rhombus, tmp_path, live_records)

    assert any("duplicate control gate 'G1'" in error for error in errors)


def test_rejects_missing_file_backed_enforcement_target(
    rhombus: Any,
    live_records: list[dict[str, Any]],
    tmp_path: Path,
) -> None:
    live_records[0]["enforcement"]["command"] = [
        ".github/workflows/does-not-exist.yml"
    ]

    errors = _validate_tmp(rhombus, tmp_path, live_records)

    assert any("enforcement command target does not exist" in error for error in errors)


def test_rejects_external_gate_outside_workflow_directory(
    rhombus: Any,
    live_records: list[dict[str, Any]],
    tmp_path: Path,
) -> None:
    live_records[0]["enforcement"]["command"] = ["scripts/not-a-workflow.py"]

    errors = _validate_tmp(rhombus, tmp_path, live_records)

    assert any("external_gate command must target" in error for error in errors)


def test_rejects_external_gate_with_forbidden_pr_target_trigger(
    rhombus: Any,
    live_records: list[dict[str, Any]],
    tmp_path: Path,
) -> None:
    target = _write_workflow(tmp_path, "blocked-trigger.yml", _forbidden_trigger_workflow())
    live_records[0]["enforcement"]["command"] = [target]

    errors = _validate_tmp(rhombus, tmp_path, live_records, repo_root=tmp_path)

    assert any("must not use" in error for error in errors)


def test_rejects_external_gate_without_readonly_contents_permission(
    rhombus: Any,
    live_records: list[dict[str, Any]],
    tmp_path: Path,
) -> None:
    target = _write_workflow(
        tmp_path,
        "write-permission.yml",
        """name: write permission
on:
  pull_request:
permissions:
  contents: write
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - run: echo unsafe
""",
    )
    live_records[0]["enforcement"]["command"] = [target]

    errors = _validate_tmp(rhombus, tmp_path, live_records, repo_root=tmp_path)

    assert any("permissions.contents=read" in error for error in errors)


def test_accepts_minimal_external_gate_workflow(
    rhombus: Any,
    live_records: list[dict[str, Any]],
    tmp_path: Path,
) -> None:
    target = _write_workflow(tmp_path, "safe.yml", _minimal_gate_workflow())
    live_records[0]["enforcement"]["command"] = [target]
    for record in live_records[1:]:
        record["enforcement"]["command"] = [target]

    assert _validate_tmp(rhombus, tmp_path, live_records, repo_root=tmp_path) == []


def test_malformed_command_reports_schema_error_without_crashing(
    rhombus: Any,
    live_records: list[dict[str, Any]],
    tmp_path: Path,
) -> None:
    live_records[0]["enforcement"]["command"] = [123]

    errors = _validate_tmp(rhombus, tmp_path, live_records)

    assert any("enforcement.command.0" in error for error in errors)


def test_build_report_is_deterministic_and_hashes_inputs(rhombus: Any) -> None:
    errors: list[str] = []
    report = rhombus.build_report(MANIFEST_PATH, SCHEMA_PATH, ROOT, errors)

    assert report["status"] == "PASS"
    assert report["record_count"] == 4
    assert len(report["manifest_sha256"]) == 64
    assert len(report["schema_sha256"]) == 64
    assert report["axes"] == [
        "axiomatic_basis",
        "structural_integrity",
        "operational_determinism",
        "provenance_governance",
    ]


def test_main_writes_report(
    rhombus: Any,
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "reports" / "rhombus.json"

    assert rhombus.main(["--report", str(report_path)]) == 0

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["record_count"] == 4


def test_main_exits_zero_on_live_manifest(rhombus: Any) -> None:
    assert rhombus.main([]) == 0


def test_main_exits_one_on_invalid_manifest(
    rhombus: Any,
    live_records: list[dict[str, Any]],
    tmp_path: Path,
) -> None:
    live_records[0]["control_gates"] = []
    manifest = _write_manifest(tmp_path, live_records)

    assert rhombus.main([str(manifest), "--schema", str(SCHEMA_PATH)]) == 1
