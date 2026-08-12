#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unified coverage control plane.

This module composes the coverage authority, calibration optimizer, and operating
matrix into one operator-facing deterministic pipeline:

1. build coverage-intelligence evidence from coverage.xml + junit.xml;
2. transform evidence into a ranked calibration plan;
3. normalize the plan into an operating matrix;
4. verify the required output artifacts exist and are non-empty;
5. emit a compact control-plane manifest for CI and human audit.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class PhaseResult:
    name: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class ArtifactStatus:
    path: str
    exists: bool
    bytes: int


@dataclass(frozen=True)
class ControlPlaneManifest:
    schema_version: str
    verdict: str
    stages: list[PhaseResult]
    artifacts: list[ArtifactStatus]


def _phase_name(command: Sequence[str]) -> str:
    if len(command) > 2 and command[1] == "-m":
        return command[2]
    return Path(command[0]).name


def _run_command(command: Sequence[str], *, cwd: Path) -> PhaseResult:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return PhaseResult(
        name=_phase_name(command),
        command=list(command),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _absolute_under_root(path: Path, *, root: Path) -> Path:
    return path if path.is_absolute() else root / path


def _display_path(path: Path, *, root: Path) -> str:
    absolute = _absolute_under_root(path, root=root)
    try:
        return str(absolute.relative_to(root))
    except ValueError:
        return str(absolute)


def _artifact_status(path: Path, *, root: Path) -> ArtifactStatus:
    absolute = _absolute_under_root(path, root=root)
    exists = absolute.exists()
    size = absolute.stat().st_size if exists and absolute.is_file() else 0
    return ArtifactStatus(path=_display_path(path, root=root), exists=exists, bytes=size)


def _required_artifacts(out_dir: Path, calibration_dir: Path, matrix_dir: Path) -> list[Path]:
    return [
        out_dir / "coverage_summary.json",
        out_dir / "coverage_intelligence.md",
        calibration_dir / "calibration_plan.json",
        calibration_dir / "calibration_plan.md",
        matrix_dir / "coverage_matrix.json",
        matrix_dir / "coverage_matrix.md",
    ]


def build_phase_commands(
    *,
    coverage: Path,
    junit: Path,
    targets: Path,
    critical: Path,
    claims: Path,
    out_dir: Path,
    calibration_dir: Path,
    matrix_dir: Path,
    stage: str,
    limit: int,
    run_intelligence: bool,
) -> list[list[str]]:
    commands: list[list[str]] = []
    if run_intelligence:
        commands.append(
            [
                sys.executable,
                "-m",
                "tools.coverage.geosync_coverage_intelligence",
                "--coverage",
                str(coverage),
                "--junit",
                str(junit),
                "--targets",
                str(targets),
                "--critical",
                str(critical),
                "--claims",
                str(claims),
                "--out",
                str(out_dir),
            ]
        )
    commands.append(
        [
            sys.executable,
            "-m",
            "tools.coverage.coverage_calibration_loop",
            "--summary",
            str(out_dir / "coverage_summary.json"),
            "--targets",
            str(targets),
            "--out",
            str(calibration_dir),
            "--stage",
            stage,
            "--limit",
            str(limit),
        ]
    )
    commands.append(
        [
            sys.executable,
            "-m",
            "tools.coverage.coverage_matrix_engine",
            "--summary",
            str(out_dir / "coverage_summary.json"),
            "--targets",
            str(targets),
            "--plan",
            str(calibration_dir / "calibration_plan.json"),
            "--out",
            str(matrix_dir),
            "--stage",
            stage,
        ]
    )
    return commands


def run_control_plane(
    *,
    root: Path,
    coverage: Path,
    junit: Path,
    targets: Path,
    critical: Path,
    claims: Path,
    out_dir: Path,
    calibration_dir: Path,
    matrix_dir: Path,
    stage: str,
    limit: int,
    run_intelligence: bool = True,
) -> ControlPlaneManifest:
    root = root.resolve()
    _absolute_under_root(out_dir, root=root).mkdir(parents=True, exist_ok=True)
    _absolute_under_root(calibration_dir, root=root).mkdir(parents=True, exist_ok=True)
    _absolute_under_root(matrix_dir, root=root).mkdir(parents=True, exist_ok=True)

    phases: list[PhaseResult] = []
    for command in build_phase_commands(
        coverage=coverage,
        junit=junit,
        targets=targets,
        critical=critical,
        claims=claims,
        out_dir=out_dir,
        calibration_dir=calibration_dir,
        matrix_dir=matrix_dir,
        stage=stage,
        limit=limit,
        run_intelligence=run_intelligence,
    ):
        phase = _run_command(command, cwd=root)
        phases.append(phase)
        if phase.returncode != 0:
            artifacts = [
                _artifact_status(path, root=root)
                for path in _required_artifacts(out_dir, calibration_dir, matrix_dir)
            ]
            return ControlPlaneManifest(
                schema_version="1.0",
                verdict="FAIL",
                stages=phases,
                artifacts=artifacts,
            )

    artifacts = [
        _artifact_status(path, root=root)
        for path in _required_artifacts(out_dir, calibration_dir, matrix_dir)
    ]
    verdict = "PASS" if all(item.exists and item.bytes > 0 for item in artifacts) else "FAIL"
    return ControlPlaneManifest(
        schema_version="1.0",
        verdict=verdict,
        stages=phases,
        artifacts=artifacts,
    )


def write_manifest(manifest: ControlPlaneManifest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--coverage", default="reports/coverage/coverage.xml")
    parser.add_argument("--junit", default="reports/coverage/junit.xml")
    parser.add_argument("--targets", default="configs/quality/coverage_targets.toml")
    parser.add_argument("--critical", default="configs/quality/critical_surface.toml")
    parser.add_argument("--claims", default="docs/CLAIMS.yaml")
    parser.add_argument("--out", default="reports/coverage/intelligence")
    parser.add_argument("--calibration-out", default="reports/coverage/calibration")
    parser.add_argument("--matrix-out", default="reports/coverage/matrix")
    parser.add_argument("--manifest", default="reports/coverage/control_plane.json")
    parser.add_argument("--stage", choices=("short_term", "mid_term", "final"), default="mid_term")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--skip-intelligence", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    manifest = run_control_plane(
        root=root,
        coverage=Path(args.coverage),
        junit=Path(args.junit),
        targets=Path(args.targets),
        critical=Path(args.critical),
        claims=Path(args.claims),
        out_dir=Path(args.out),
        calibration_dir=Path(args.calibration_out),
        matrix_dir=Path(args.matrix_out),
        stage=args.stage,
        limit=args.limit,
        run_intelligence=not args.skip_intelligence,
    )
    write_manifest(manifest, root / args.manifest)
    print(f"wrote {args.manifest}: {manifest.verdict}")
    return 0 if manifest.verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
