from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.coverage.coverage_behavior_profiler import (
    BehaviorProfile,
    benchmark_operation,
    build_behavior_profile,
    profile_artifacts,
    profile_matrix,
    profile_phases,
    write_behavior_profile,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_profile_artifacts_counts_mass_and_largest_artifact() -> None:
    state = {
        "artifacts": [
            {"name": "summary", "state": "PRESENT", "bytes": 20},
            {"name": "matrix", "state": "PRESENT", "bytes": 50},
            {"name": "junit", "state": "MISSING", "bytes": 0},
            {"name": "manifest", "state": "EMPTY", "bytes": 0},
        ]
    }

    profile = profile_artifacts(state)

    assert profile.total == 4
    assert profile.present == 2
    assert profile.missing == 1
    assert profile.empty == 1
    assert profile.total_bytes == 70
    assert profile.largest == "matrix"


def test_profile_phases_exposes_failure_surface() -> None:
    orchestration = {
        "phases": [
            {"name": "authority", "status": "PASS", "stdout": "ok", "stderr": ""},
            {"name": "matrix", "status": "FAIL", "stdout": "", "stderr": "boom"},
            {"name": "profile", "status": "SKIPPED", "stdout": "", "stderr": ""},
        ]
    }

    profile = profile_phases(orchestration)

    assert profile.total == 3
    assert profile.passed == 1
    assert profile.failed == 1
    assert profile.skipped == 1
    assert profile.failed_phase == "matrix"
    assert profile.stdout_bytes == 2
    assert profile.stderr_bytes == 4


def test_profile_matrix_identifies_highest_priority_surface() -> None:
    matrix = {
        "rows": [
            {"surface": "api", "state": "WARN", "priority": 2.0},
            {"surface": "execution", "state": "FAIL", "priority": 12.5},
            {"surface": "core", "state": "PASS", "priority": 0.0},
        ]
    }

    profile = profile_matrix(matrix)

    assert profile.total_rows == 3
    assert profile.fail_rows == 1
    assert profile.warn_rows == 1
    assert profile.pass_rows == 1
    assert profile.highest_priority_surface == "execution"
    assert profile.highest_priority == 12.5


def test_benchmark_operation_is_deterministic_with_injected_timer() -> None:
    ticks = iter([0.00, 0.01, 0.02, 0.05, 0.07, 0.10])

    benchmark = benchmark_operation(
        lambda: None,
        iterations=3,
        budget_ms=40.0,
        timer=lambda: next(ticks),
    )

    assert benchmark.iterations == 3
    assert benchmark.min_ms == 10.0
    assert benchmark.median_ms == 30.0
    assert benchmark.max_ms == 30.0
    assert benchmark.verdict == "PASS"


def test_build_behavior_profile_warns_on_missing_evidence(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "state.json",
        {
            "artifacts": [
                {"name": "summary", "state": "PRESENT", "bytes": 16},
                {"name": "junit", "state": "MISSING", "bytes": 0},
            ]
        },
    )
    _write_json(
        tmp_path / "orchestration.json",
        {"phases": [{"name": "authority", "status": "PASS"}]},
    )
    _write_json(
        tmp_path / "matrix.json",
        {"rows": [{"surface": "api", "state": "WARN", "priority": 1.0}]},
    )

    profile = build_behavior_profile(
        root=tmp_path,
        state_path=Path("state.json"),
        orchestration_path=Path("orchestration.json"),
        matrix_path=Path("matrix.json"),
        iterations=1,
        budget_ms=1_000_000.0,
    )

    assert profile.verdict == "WARN"
    assert "missing artifacts: 1" in profile.notes


def test_build_behavior_profile_fails_on_phase_or_matrix_failure(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "state.json",
        {"artifacts": [{"name": "summary", "state": "PRESENT", "bytes": 16}]},
    )
    _write_json(
        tmp_path / "orchestration.json",
        {"phases": [{"name": "authority", "status": "FAIL"}]},
    )
    _write_json(
        tmp_path / "matrix.json",
        {"rows": [{"surface": "execution", "state": "FAIL", "priority": 9.0}]},
    )

    profile = build_behavior_profile(
        root=tmp_path,
        state_path=Path("state.json"),
        orchestration_path=Path("orchestration.json"),
        matrix_path=Path("matrix.json"),
        iterations=1,
        budget_ms=1_000_000.0,
    )

    assert profile.verdict == "FAIL"
    assert "failed phase: authority" in profile.notes
    assert "matrix fail rows: 1" in profile.notes


def test_write_behavior_profile_json_contract(tmp_path: Path) -> None:
    profile = BehaviorProfile(
        schema_version="1.0",
        verdict="PASS",
        root=str(tmp_path),
        artifact_profile=profile_artifacts({"artifacts": []}),
        phase_profile=profile_phases({"phases": []}),
        matrix_profile=profile_matrix({"rows": []}),
        benchmark=benchmark_operation(lambda: None, iterations=1, budget_ms=1.0),
        notes=[],
    )

    out = tmp_path / "reports" / "behavior_profile.json"
    write_behavior_profile(profile, out)
    payload = json.loads(out.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "1.0"
    assert payload["verdict"] == "PASS"
    assert payload["benchmark"]["name"] == "quality_state_aggregation"


def test_benchmark_rejects_zero_iterations() -> None:
    with pytest.raises(ValueError, match="iterations"):
        benchmark_operation(lambda: None, iterations=0, budget_ms=1.0)
