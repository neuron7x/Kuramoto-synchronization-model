#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Profile coverage quality-system behavior and benchmark state aggregation."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from tools.coverage.coverage_state_aggregator import build_quality_state

BehaviorVerdict = Literal["PASS", "WARN", "FAIL", "UNKNOWN"]


@dataclass(frozen=True)
class ArtifactProfile:
    total: int
    present: int
    missing: int
    empty: int
    total_bytes: int
    largest: str | None


@dataclass(frozen=True)
class PhaseProfile:
    total: int
    passed: int
    failed: int
    skipped: int
    stdout_bytes: int
    stderr_bytes: int
    failed_phase: str | None


@dataclass(frozen=True)
class MatrixProfile:
    total_rows: int
    pass_rows: int
    warn_rows: int
    fail_rows: int
    unknown_rows: int
    highest_priority_surface: str | None
    highest_priority: float


@dataclass(frozen=True)
class BenchmarkProfile:
    name: str
    iterations: int
    min_ms: float
    median_ms: float
    max_ms: float
    mean_ms: float
    budget_ms: float
    verdict: BehaviorVerdict


@dataclass(frozen=True)
class BehaviorProfile:
    schema_version: str
    verdict: BehaviorVerdict
    root: str
    artifact_profile: ArtifactProfile
    phase_profile: PhaseProfile
    matrix_profile: MatrixProfile
    benchmark: BenchmarkProfile
    notes: list[str]


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size == 0:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _count(records: list[dict[str, Any]], field: str, value: str) -> int:
    return sum(1 for record in records if record.get(field) == value)


def profile_artifacts(state: dict[str, Any]) -> ArtifactProfile:
    artifacts = [item for item in state.get("artifacts", []) if isinstance(item, dict)]
    present = _count(artifacts, "state", "PRESENT")
    missing = _count(artifacts, "state", "MISSING")
    empty = _count(artifacts, "state", "EMPTY")
    total_bytes = sum(
        int(item.get("bytes", 0)) for item in artifacts if isinstance(item.get("bytes"), int)
    )
    largest_record = max(artifacts, key=lambda item: int(item.get("bytes", 0)), default=None)
    largest = None if largest_record is None else str(largest_record.get("name", "unknown"))
    return ArtifactProfile(
        total=len(artifacts),
        present=present,
        missing=missing,
        empty=empty,
        total_bytes=total_bytes,
        largest=largest,
    )


def profile_phases(orchestration: dict[str, Any]) -> PhaseProfile:
    phases = [item for item in orchestration.get("phases", []) if isinstance(item, dict)]
    failed = [phase for phase in phases if phase.get("status") == "FAIL"]
    return PhaseProfile(
        total=len(phases),
        passed=_count(phases, "status", "PASS"),
        failed=len(failed),
        skipped=_count(phases, "status", "SKIPPED"),
        stdout_bytes=sum(len(str(phase.get("stdout", ""))) for phase in phases),
        stderr_bytes=sum(len(str(phase.get("stderr", ""))) for phase in phases),
        failed_phase=None if not failed else str(failed[0].get("name", "unknown")),
    )


def profile_matrix(matrix: dict[str, Any]) -> MatrixProfile:
    rows = [item for item in matrix.get("rows", []) if isinstance(item, dict)]
    highest = max(rows, key=lambda row: float(row.get("priority", 0.0)), default=None)
    return MatrixProfile(
        total_rows=len(rows),
        pass_rows=_count(rows, "state", "PASS"),
        warn_rows=_count(rows, "state", "WARN"),
        fail_rows=_count(rows, "state", "FAIL"),
        unknown_rows=_count(rows, "state", "UNKNOWN"),
        highest_priority_surface=(
            None if highest is None else str(highest.get("surface", "unknown"))
        ),
        highest_priority=0.0 if highest is None else round(float(highest.get("priority", 0.0)), 6),
    )


def benchmark_operation(
    operation: Callable[[], Any],
    *,
    iterations: int,
    budget_ms: float,
    timer: Callable[[], float] = time.perf_counter,
) -> BenchmarkProfile:
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    samples: list[float] = []
    for _ in range(iterations):
        started = timer()
        operation()
        stopped = timer()
        samples.append(max(0.0, (stopped - started) * 1000.0))
    median_ms = statistics.median(samples)
    verdict: BehaviorVerdict = "PASS" if median_ms <= budget_ms else "WARN"
    return BenchmarkProfile(
        name="quality_state_aggregation",
        iterations=iterations,
        min_ms=round(min(samples), 6),
        median_ms=round(median_ms, 6),
        max_ms=round(max(samples), 6),
        mean_ms=round(statistics.fmean(samples), 6),
        budget_ms=round(budget_ms, 6),
        verdict=verdict,
    )


def _derive_verdict(
    *,
    artifacts: ArtifactProfile,
    phases: PhaseProfile,
    matrix: MatrixProfile,
    benchmark: BenchmarkProfile,
) -> BehaviorVerdict:
    if phases.failed > 0 or artifacts.empty > 0:
        return "FAIL"
    if matrix.fail_rows > 0:
        return "FAIL"
    if artifacts.missing > 0 or phases.skipped > 0 or matrix.unknown_rows > 0:
        return "WARN"
    return benchmark.verdict


def build_behavior_profile(
    *,
    root: Path,
    state_path: Path,
    orchestration_path: Path,
    matrix_path: Path,
    iterations: int,
    budget_ms: float,
) -> BehaviorProfile:
    root = root.resolve()
    state = _load_json(root / state_path)
    if not state:
        state = asdict(build_quality_state(root=root))
    orchestration = _load_json(root / orchestration_path)
    matrix = _load_json(root / matrix_path)

    artifacts = profile_artifacts(state)
    phases = profile_phases(orchestration)
    matrix_profile = profile_matrix(matrix)
    benchmark = benchmark_operation(
        lambda: asdict(build_quality_state(root=root)),
        iterations=iterations,
        budget_ms=budget_ms,
    )
    verdict = _derive_verdict(
        artifacts=artifacts,
        phases=phases,
        matrix=matrix_profile,
        benchmark=benchmark,
    )
    notes: list[str] = []
    if artifacts.missing:
        notes.append(f"missing artifacts: {artifacts.missing}")
    if phases.failed:
        notes.append(f"failed phase: {phases.failed_phase}")
    if matrix_profile.fail_rows:
        notes.append(f"matrix fail rows: {matrix_profile.fail_rows}")
    if benchmark.verdict != "PASS":
        notes.append("aggregation benchmark exceeded budget")
    return BehaviorProfile(
        schema_version="1.0",
        verdict=verdict,
        root=str(root),
        artifact_profile=artifacts,
        phase_profile=phases,
        matrix_profile=matrix_profile,
        benchmark=benchmark,
        notes=notes,
    )


def write_behavior_profile(profile: BehaviorProfile, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(asdict(profile), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--state", default="reports/coverage/quality_state.json")
    parser.add_argument("--orchestration", default="reports/coverage/orchestration.json")
    parser.add_argument("--matrix", default="reports/coverage/matrix/coverage_matrix.json")
    parser.add_argument("--out", default="reports/coverage/behavior_profile.json")
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--budget-ms", type=float, default=250.0)
    args = parser.parse_args(argv)

    profile = build_behavior_profile(
        root=Path(args.root),
        state_path=Path(args.state),
        orchestration_path=Path(args.orchestration),
        matrix_path=Path(args.matrix),
        iterations=args.iterations,
        budget_ms=args.budget_ms,
    )
    write_behavior_profile(profile, Path(args.out))
    print(f"coverage behavior profile: {profile.verdict}")
    return 0 if profile.verdict != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
