# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

from tools.coverage import coverage_control_plane as ccp
from tools.coverage import coverage_orchestrator as orchestrator


def _touch(path: Path, text: str = "ok\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_build_orchestration_plan_declares_dependencies_in_order(tmp_path: Path) -> None:
    phases = orchestrator.build_orchestration_plan(
        coverage=Path("reports/coverage/coverage.xml"),
        junit=Path("reports/coverage/junit.xml"),
        targets=Path("configs/quality/coverage_targets.toml"),
        critical=Path("configs/quality/critical_surface.toml"),
        claims=Path("docs/CLAIMS.yaml"),
        out_dir=Path("reports/coverage/intelligence"),
        calibration_dir=Path("reports/coverage/calibration"),
        matrix_dir=Path("reports/coverage/matrix"),
        stage="mid_term",
        limit=8,
        run_intelligence=True,
    )

    assert [phase.name for phase in phases] == [
        "coverage_authority",
        "calibration_optimizer",
        "matrix_normalizer",
    ]
    assert phases[0].requires == [
        Path("reports/coverage/coverage.xml"),
        Path("reports/coverage/junit.xml"),
        Path("configs/quality/coverage_targets.toml"),
        Path("configs/quality/critical_surface.toml"),
        Path("docs/CLAIMS.yaml"),
    ]
    assert phases[1].requires == [
        Path("reports/coverage/intelligence/coverage_summary.json"),
        Path("configs/quality/coverage_targets.toml"),
    ]
    assert phases[2].requires == [
        Path("reports/coverage/intelligence/coverage_summary.json"),
        Path("configs/quality/coverage_targets.toml"),
        Path("reports/coverage/calibration/calibration_plan.json"),
    ]


def test_build_orchestration_plan_can_start_from_existing_evidence() -> None:
    phases = orchestrator.build_orchestration_plan(
        coverage=Path("coverage.xml"),
        junit=Path("junit.xml"),
        targets=Path("targets.toml"),
        critical=Path("critical.toml"),
        claims=Path("CLAIMS.yaml"),
        out_dir=Path("intelligence"),
        calibration_dir=Path("calibration"),
        matrix_dir=Path("matrix"),
        stage="final",
        limit=2,
        run_intelligence=False,
    )

    assert [phase.name for phase in phases] == ["calibration_optimizer", "matrix_normalizer"]
    assert phases[0].requires == [
        Path("intelligence/coverage_summary.json"),
        Path("targets.toml"),
    ]


def test_orchestrator_fails_before_command_when_inputs_are_missing(tmp_path: Path) -> None:
    calls: list[Sequence[str]] = []

    def runner(command: Sequence[str], root: Path) -> ccp.PhaseResult:
        calls.append(command)
        return ccp.PhaseResult("phase", list(command), 0, "", "")

    phase = orchestrator.PhaseSpec(
        name="needs_input",
        command=["python", "-m", "module"],
        requires=[Path("missing.json")],
        produces=[Path("out.json")],
    )

    manifest = orchestrator.run_orchestration_plan([phase], root=tmp_path, runner=runner)

    assert manifest.verdict == "FAIL"
    assert calls == []
    assert manifest.phases[0].status == "FAIL"
    assert manifest.phases[0].reason == "missing inputs: missing.json"


def test_orchestrator_fail_fast_skips_downstream_phases(tmp_path: Path) -> None:
    _touch(tmp_path / "input.json")

    def runner(command: Sequence[str], root: Path) -> ccp.PhaseResult:
        return ccp.PhaseResult("first", list(command), 17, "", "boom")

    first = orchestrator.PhaseSpec(
        name="first",
        command=["python", "first.py"],
        requires=[Path("input.json")],
        produces=[Path("first.json")],
    )
    second = orchestrator.PhaseSpec(
        name="second",
        command=["python", "second.py"],
        requires=[Path("first.json")],
        produces=[Path("second.json")],
    )

    manifest = orchestrator.run_orchestration_plan([first, second], root=tmp_path, runner=runner)

    assert manifest.verdict == "FAIL"
    assert [(phase.name, phase.status) for phase in manifest.phases] == [
        ("first", "FAIL"),
        ("second", "SKIPPED"),
    ]
    assert manifest.phases[0].reason == "command failed"
    assert manifest.phases[1].reason == "previous phase failed"


def test_orchestrator_requires_declared_outputs(tmp_path: Path) -> None:
    _touch(tmp_path / "input.json")

    def runner(command: Sequence[str], root: Path) -> ccp.PhaseResult:
        return ccp.PhaseResult("phase", list(command), 0, "ok", "")

    phase = orchestrator.PhaseSpec(
        name="silent_phase",
        command=["python", "silent.py"],
        requires=[Path("input.json")],
        produces=[Path("missing_output.json")],
    )

    manifest = orchestrator.run_orchestration_plan([phase], root=tmp_path, runner=runner)

    assert manifest.verdict == "FAIL"
    assert manifest.phases[0].status == "FAIL"
    assert manifest.phases[0].reason == "declared outputs missing or empty"


def test_orchestrator_passes_and_writes_manifest(tmp_path: Path) -> None:
    _touch(tmp_path / "input.json")

    def runner(command: Sequence[str], root: Path) -> ccp.PhaseResult:
        _touch(root / "output.json")
        return ccp.PhaseResult("phase", list(command), 0, "ok", "")

    phase = orchestrator.PhaseSpec(
        name="phase",
        command=["python", "phase.py"],
        requires=[Path("input.json")],
        produces=[Path("output.json")],
    )

    manifest = orchestrator.run_orchestration_plan([phase], root=tmp_path, runner=runner)
    output = tmp_path / "reports/coverage/orchestration.json"
    orchestrator.write_manifest(manifest, output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert manifest.verdict == "PASS"
    assert payload["verdict"] == "PASS"
    assert payload["phases"][0]["requires"] == ["input.json"]
    assert payload["phases"][0]["produces"] == ["output.json"]
