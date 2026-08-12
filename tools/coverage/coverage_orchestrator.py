#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deterministic orchestration graph for the coverage quality system.

The orchestrator turns the coverage authority, calibration loop, and operating
matrix into explicit phases with declared inputs, outputs, fail-fast semantics,
and an auditable execution trace. It is the sequencing layer above the raw
control-plane commands.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Literal, Sequence

from tools.coverage import coverage_control_plane as ccp

PhaseStatus = Literal["PASS", "FAIL", "SKIPPED"]
OrchestrationVerdict = Literal["PASS", "FAIL"]


@dataclass(frozen=True)
class PhaseSpec:
    name: str
    command: list[str]
    requires: list[Path]
    produces: list[Path]


@dataclass(frozen=True)
class PhaseTrace:
    name: str
    status: PhaseStatus
    command: list[str]
    requires: list[str]
    produces: list[str]
    returncode: int | None
    stdout: str
    stderr: str
    reason: str


@dataclass(frozen=True)
class OrchestrationManifest:
    schema_version: str
    verdict: OrchestrationVerdict
    phases: list[PhaseTrace]


Runner = Callable[[Sequence[str], Path], ccp.PhaseResult]


def _absolute(path: Path, *, root: Path) -> Path:
    return path if path.is_absolute() else root / path


def _display(path: Path, *, root: Path) -> str:
    absolute = _absolute(path, root=root)
    try:
        return str(absolute.relative_to(root))
    except ValueError:
        return str(absolute)


def _missing(paths: Sequence[Path], *, root: Path) -> list[Path]:
    return [path for path in paths if not _absolute(path, root=root).is_file()]


def _non_empty_outputs(paths: Sequence[Path], *, root: Path) -> bool:
    return all(
        _absolute(path, root=root).is_file() and _absolute(path, root=root).stat().st_size > 0
        for path in paths
    )


def _run_subprocess(command: Sequence[str], root: Path) -> ccp.PhaseResult:
    completed = subprocess.run(
        list(command),
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return ccp.PhaseResult(
        name=ccp._phase_name(command),
        command=list(command),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def build_orchestration_plan(
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
) -> list[PhaseSpec]:
    commands = ccp.build_phase_commands(
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
    )
    cursor = 0
    phases: list[PhaseSpec] = []
    summary = out_dir / "coverage_summary.json"
    intelligence_md = out_dir / "coverage_intelligence.md"
    calibration_json = calibration_dir / "calibration_plan.json"
    calibration_md = calibration_dir / "calibration_plan.md"
    matrix_json = matrix_dir / "coverage_matrix.json"
    matrix_md = matrix_dir / "coverage_matrix.md"

    if run_intelligence:
        phases.append(
            PhaseSpec(
                name="coverage_authority",
                command=commands[cursor],
                requires=[coverage, junit, targets, critical, claims],
                produces=[summary, intelligence_md],
            )
        )
        cursor += 1

    phases.append(
        PhaseSpec(
            name="calibration_optimizer",
            command=commands[cursor],
            requires=[summary, targets],
            produces=[calibration_json, calibration_md],
        )
    )
    cursor += 1
    phases.append(
        PhaseSpec(
            name="matrix_normalizer",
            command=commands[cursor],
            requires=[summary, targets, calibration_json],
            produces=[matrix_json, matrix_md],
        )
    )
    return phases


def _trace(
    phase: PhaseSpec,
    *,
    root: Path,
    status: PhaseStatus,
    returncode: int | None,
    stdout: str = "",
    stderr: str = "",
    reason: str,
) -> PhaseTrace:
    return PhaseTrace(
        name=phase.name,
        status=status,
        command=phase.command,
        requires=[_display(path, root=root) for path in phase.requires],
        produces=[_display(path, root=root) for path in phase.produces],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        reason=reason,
    )


def run_orchestration_plan(
    phases: Sequence[PhaseSpec],
    *,
    root: Path,
    runner: Runner = _run_subprocess,
) -> OrchestrationManifest:
    root = root.resolve()
    traces: list[PhaseTrace] = []
    failed = False

    for phase in phases:
        if failed:
            traces.append(
                _trace(
                    phase,
                    root=root,
                    status="SKIPPED",
                    returncode=None,
                    reason="previous phase failed",
                )
            )
            continue

        missing_inputs = _missing(phase.requires, root=root)
        if missing_inputs:
            traces.append(
                _trace(
                    phase,
                    root=root,
                    status="FAIL",
                    returncode=None,
                    reason="missing inputs: "
                    + ", ".join(_display(path, root=root) for path in missing_inputs),
                )
            )
            failed = True
            continue

        for output in phase.produces:
            _absolute(output, root=root).parent.mkdir(parents=True, exist_ok=True)
        result = runner(phase.command, root)
        if result.returncode != 0:
            traces.append(
                _trace(
                    phase,
                    root=root,
                    status="FAIL",
                    returncode=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    reason="command failed",
                )
            )
            failed = True
            continue

        if not _non_empty_outputs(phase.produces, root=root):
            traces.append(
                _trace(
                    phase,
                    root=root,
                    status="FAIL",
                    returncode=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    reason="declared outputs missing or empty",
                )
            )
            failed = True
            continue

        traces.append(
            _trace(
                phase,
                root=root,
                status="PASS",
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                reason="phase completed",
            )
        )

    verdict: OrchestrationVerdict = "FAIL" if failed else "PASS"
    return OrchestrationManifest(schema_version="1.0", verdict=verdict, phases=traces)


def write_manifest(manifest: OrchestrationManifest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n"
    path.write_text(payload, encoding="utf-8")


def run_orchestrator(
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
    run_intelligence: bool,
    manifest_path: Path,
) -> OrchestrationManifest:
    phases = build_orchestration_plan(
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
    )
    manifest = run_orchestration_plan(phases, root=root)
    write_manifest(manifest, root / manifest_path)
    return manifest


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
    parser.add_argument("--manifest", default="reports/coverage/orchestration.json")
    parser.add_argument(
        "--stage",
        choices=("short_term", "mid_term", "final"),
        default="mid_term",
    )
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--skip-intelligence", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    manifest = run_orchestrator(
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
        manifest_path=Path(args.manifest),
    )
    print(f"coverage orchestration: {manifest.verdict}")
    return 0 if manifest.verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
