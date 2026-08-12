#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Aggregate the coverage quality system into one operator-facing state."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from tools.coverage.coverage_quality_system import QualitySystemConfig

ArtifactState = Literal["PRESENT", "MISSING", "EMPTY"]


@dataclass(frozen=True)
class ComponentState:
    name: str
    kind: str
    path: str
    role: str
    present: bool


@dataclass(frozen=True)
class ArtifactStateRecord:
    name: str
    path: str
    state: ArtifactState
    bytes: int
    role: str


@dataclass(frozen=True)
class CommandState:
    name: str
    command: list[str]
    role: str


@dataclass(frozen=True)
class WorkflowState:
    name: str
    path: str
    present: bool
    role: str


@dataclass(frozen=True)
class QualityStateEnvelope:
    schema_version: str
    verdict: str
    root: str
    components: list[ComponentState]
    artifacts: list[ArtifactStateRecord]
    commands: list[CommandState]
    workflows: list[WorkflowState]
    notes: list[str]


def _relative(path: Path, *, root: Path) -> str:
    absolute = path if path.is_absolute() else root / path
    try:
        return str(absolute.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(absolute)


def _exists(path: Path, *, root: Path) -> bool:
    absolute = path if path.is_absolute() else root / path
    return absolute.is_file()


def _artifact(name: str, path: Path, *, root: Path, role: str) -> ArtifactStateRecord:
    absolute = path if path.is_absolute() else root / path
    if not absolute.is_file():
        return ArtifactStateRecord(
            name=name,
            path=_relative(path, root=root),
            state="MISSING",
            bytes=0,
            role=role,
        )
    size = absolute.stat().st_size
    return ArtifactStateRecord(
        name=name,
        path=_relative(path, root=root),
        state="PRESENT" if size > 0 else "EMPTY",
        bytes=size,
        role=role,
    )


def _component(name: str, kind: str, path: str, *, root: Path, role: str) -> ComponentState:
    component_path = Path(path)
    return ComponentState(
        name=name,
        kind=kind,
        path=path,
        role=role,
        present=_exists(component_path, root=root),
    )


def _load_json(path: Path, *, root: Path) -> dict[str, Any]:
    absolute = path if path.is_absolute() else root / path
    if not absolute.is_file() or absolute.stat().st_size == 0:
        return {}
    payload = json.loads(absolute.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _derived_verdict(*, manifest: dict[str, Any], artifacts: list[ArtifactStateRecord]) -> str:
    if isinstance(manifest.get("verdict"), str):
        return str(manifest["verdict"])
    if any(artifact.state == "EMPTY" for artifact in artifacts):
        return "FAIL"
    if any(artifact.state == "PRESENT" for artifact in artifacts):
        return "PARTIAL"
    return "UNKNOWN"


def build_quality_state(
    *,
    root: Path,
    config: QualitySystemConfig | None = None,
) -> QualityStateEnvelope:
    root = root.resolve()
    cfg = config or QualitySystemConfig(root=root)

    components = [
        _component(
            "coverage_quality_system",
            "facade",
            "tools/coverage/coverage_quality_system.py",
            root=root,
            role="single operator-facing entrypoint",
        ),
        _component(
            "coverage_orchestrator",
            "orchestrator",
            "tools/coverage/coverage_orchestrator.py",
            root=root,
            role="phase dependency graph and execution trace",
        ),
        _component(
            "coverage_control_plane",
            "control_plane",
            "tools/coverage/coverage_control_plane.py",
            root=root,
            role="authority, calibration, and matrix pipeline runner",
        ),
        _component(
            "coverage_calibration_loop",
            "optimizer",
            "tools/coverage/coverage_calibration_loop.py",
            root=root,
            role="ranked deficit-to-action inference loop",
        ),
        _component(
            "coverage_matrix_engine",
            "matrix",
            "tools/coverage/coverage_matrix_engine.py",
            root=root,
            role="normalized operating matrix",
        ),
        _component(
            "coverage_state_aggregator",
            "aggregator",
            "tools/coverage/coverage_state_aggregator.py",
            root=root,
            role="single state envelope for the quality system",
        ),
        _component(
            "coverage_behavior_profiler",
            "profiler",
            "tools/coverage/coverage_behavior_profiler.py",
            root=root,
            role="behavior profile and aggregation benchmark layer",
        ),
        _component(
            "coverage_intelligence",
            "authority",
            "tools/coverage/geosync_coverage_intelligence.py",
            root=root,
            role="coverage evidence authority",
        ),
    ]

    artifacts = [
        _artifact("coverage_xml", cfg.coverage, root=root, role="raw line/branch evidence"),
        _artifact("junit_xml", cfg.junit, root=root, role="test execution evidence"),
        _artifact(
            "coverage_summary",
            cfg.intelligence_out / "coverage_summary.json",
            root=root,
            role="machine-readable authority output",
        ),
        _artifact(
            "coverage_intelligence_md",
            cfg.intelligence_out / "coverage_intelligence.md",
            root=root,
            role="human-readable authority output",
        ),
        _artifact(
            "calibration_plan_json",
            cfg.calibration_out / "calibration_plan.json",
            root=root,
            role="ranked optimization plan",
        ),
        _artifact(
            "coverage_matrix_json",
            cfg.matrix_out / "coverage_matrix.json",
            root=root,
            role="normalized operating matrix",
        ),
        _artifact(
            "behavior_profile_json",
            Path("reports/coverage/behavior_profile.json"),
            root=root,
            role="behavior profile and benchmark report",
        ),
        _artifact("control_plane_manifest", cfg.manifest, root=root, role="pipeline manifest"),
    ]

    commands = [
        CommandState(
            name="quality_system",
            command=["python", "-m", "tools.coverage.coverage_quality_system"],
            role="encapsulated end-to-end entrypoint",
        ),
        CommandState(
            name="orchestrator",
            command=["python", "-m", "tools.coverage.coverage_orchestrator"],
            role="explicit phase sequencing entrypoint",
        ),
        CommandState(
            name="matrix",
            command=["python", "-m", "tools.coverage.coverage_matrix_engine"],
            role="matrix-only regeneration entrypoint",
        ),
        CommandState(
            name="behavior_profiler",
            command=["python", "-m", "tools.coverage.coverage_behavior_profiler"],
            role="behavior profiling and benchmark entrypoint",
        ),
    ]

    workflows = [
        WorkflowState(
            name="coverage_control_plane",
            path=".github/workflows/coverage-control-plane.yml",
            present=_exists(Path(".github/workflows/coverage-control-plane.yml"), root=root),
            role="contract tests for control-plane, facade, orchestrator, matrix, and profiler",
        ),
        WorkflowState(
            name="coverage_calibration_loop",
            path=".github/workflows/coverage-calibration-loop.yml",
            present=_exists(Path(".github/workflows/coverage-calibration-loop.yml"), root=root),
            role="calibration loop contract and scenario tests",
        ),
        WorkflowState(
            name="coverage_calibration_isolated",
            path=".github/workflows/coverage-calibration-isolated.yml",
            present=_exists(Path(".github/workflows/coverage-calibration-isolated.yml"), root=root),
            role="sandboxed isolated calibration run",
        ),
    ]

    manifest = _load_json(cfg.manifest, root=root)
    verdict = _derived_verdict(manifest=manifest, artifacts=artifacts)
    missing_components = [component.name for component in components if not component.present]
    missing_workflows = [workflow.name for workflow in workflows if not workflow.present]
    notes = []
    if missing_components:
        notes.append("missing components: " + ", ".join(missing_components))
    if missing_workflows:
        notes.append("missing workflows: " + ", ".join(missing_workflows))
    if verdict in {"UNKNOWN", "PARTIAL"}:
        notes.append("fresh remote execution evidence is not complete")

    return QualityStateEnvelope(
        schema_version="1.0",
        verdict=verdict,
        root=str(root),
        components=components,
        artifacts=artifacts,
        commands=commands,
        workflows=workflows,
        notes=notes,
    )


def write_quality_state(envelope: QualityStateEnvelope, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(asdict(envelope), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--out", default="reports/coverage/quality_state.json")
    args = parser.parse_args(argv)

    envelope = build_quality_state(root=Path(args.root))
    write_quality_state(envelope, Path(args.out))
    print(f"coverage quality state: {envelope.verdict}")
    return 0 if envelope.verdict != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
