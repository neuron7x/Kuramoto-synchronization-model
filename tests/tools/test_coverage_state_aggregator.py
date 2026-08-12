from __future__ import annotations

import json
from pathlib import Path

from tools.coverage.coverage_state_aggregator import (
    build_quality_state,
    write_quality_state,
)

_COMPONENT_PATHS = [
    "tools/coverage/coverage_quality_system.py",
    "tools/coverage/coverage_orchestrator.py",
    "tools/coverage/coverage_control_plane.py",
    "tools/coverage/coverage_calibration_loop.py",
    "tools/coverage/coverage_matrix_engine.py",
    "tools/coverage/coverage_state_aggregator.py",
    "tools/coverage/coverage_behavior_profiler.py",
    "tools/coverage/geosync_coverage_intelligence.py",
]

_WORKFLOW_PATHS = [
    ".github/workflows/coverage-control-plane.yml",
    ".github/workflows/coverage-calibration-loop.yml",
    ".github/workflows/coverage-calibration-isolated.yml",
]


def _touch(root: Path, relative: str, content: str = "x") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_system_root(root: Path) -> None:
    for path in [*_COMPONENT_PATHS, *_WORKFLOW_PATHS]:
        _touch(root, path)


def test_quality_state_aggregates_components_commands_and_workflows(tmp_path: Path) -> None:
    _make_system_root(tmp_path)

    envelope = build_quality_state(root=tmp_path)

    assert envelope.schema_version == "1.0"
    assert envelope.verdict == "UNKNOWN"
    assert {component.name for component in envelope.components} == {
        "coverage_quality_system",
        "coverage_orchestrator",
        "coverage_control_plane",
        "coverage_calibration_loop",
        "coverage_matrix_engine",
        "coverage_state_aggregator",
        "coverage_behavior_profiler",
        "coverage_intelligence",
    }
    assert all(component.present for component in envelope.components)
    assert {workflow.name for workflow in envelope.workflows} == {
        "coverage_control_plane",
        "coverage_calibration_loop",
        "coverage_calibration_isolated",
    }
    assert all(workflow.present for workflow in envelope.workflows)
    assert [command.name for command in envelope.commands] == [
        "quality_system",
        "orchestrator",
        "matrix",
        "behavior_profiler",
    ]
    assert {artifact.name for artifact in envelope.artifacts} >= {
        "coverage_matrix_json",
        "behavior_profile_json",
        "control_plane_manifest",
    }
    assert "fresh remote execution evidence is not complete" in envelope.notes


def test_quality_state_uses_manifest_verdict_when_available(tmp_path: Path) -> None:
    _make_system_root(tmp_path)
    _touch(
        tmp_path,
        "reports/coverage/control_plane.json",
        json.dumps({"verdict": "PASS"}),
    )

    envelope = build_quality_state(root=tmp_path)

    assert envelope.verdict == "PASS"
    manifest = next(
        artifact for artifact in envelope.artifacts if artifact.name == "control_plane_manifest"
    )
    assert manifest.state == "PRESENT"
    assert manifest.bytes > 0


def test_quality_state_marks_empty_artifact_as_fail(tmp_path: Path) -> None:
    _make_system_root(tmp_path)
    _touch(tmp_path, "reports/coverage/coverage.xml", "")

    envelope = build_quality_state(root=tmp_path)

    assert envelope.verdict == "FAIL"
    coverage = next(artifact for artifact in envelope.artifacts if artifact.name == "coverage_xml")
    assert coverage.state == "EMPTY"


def test_write_quality_state_emits_json_contract(tmp_path: Path) -> None:
    _make_system_root(tmp_path)
    envelope = build_quality_state(root=tmp_path)
    out = tmp_path / "reports" / "coverage" / "quality_state.json"

    write_quality_state(envelope, out)

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert payload["verdict"] == "UNKNOWN"
    assert {item["name"] for item in payload["components"]} >= {
        "coverage_quality_system",
        "coverage_orchestrator",
        "coverage_matrix_engine",
        "coverage_behavior_profiler",
    }
