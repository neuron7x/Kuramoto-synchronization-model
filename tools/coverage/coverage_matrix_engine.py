#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Build an operational coverage matrix from verified evidence and calibration output."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from tools.coverage.coverage_calibration_loop import CalibrationStage, _target_for_stage
from tools.coverage.surface_contract import CoverageTargets, load_coverage_targets

MatrixState = Literal["PASS", "WARN", "FAIL", "UNKNOWN"]

_RISK_WEIGHT: dict[str, float] = {
    "critical": 4.0,
    "high": 3.0,
    "medium": 2.0,
    "low": 1.0,
}


@dataclass(frozen=True)
class MatrixRow:
    surface: str
    state: MatrixState
    risk: str
    line_rate: float
    branch_rate: float
    target: float
    line_deficit: float
    branch_deficit: float
    priority: float
    action: str
    rationale: str


@dataclass(frozen=True)
class CoverageMatrix:
    schema_version: str
    stage: CalibrationStage
    verdict: str
    evidence_valid: bool
    release_state: MatrixState
    diff_state: MatrixState
    rows: list[MatrixRow]


def _as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _matrix_state(
    *,
    evidence_valid: bool,
    risk: str,
    line_deficit: float,
    branch_deficit: float,
) -> MatrixState:
    if not evidence_valid:
        return "UNKNOWN"
    if line_deficit <= 0.0 and branch_deficit <= 0.0:
        return "PASS"
    if risk.lower() in {"critical", "high"} and line_deficit > 0.0:
        return "FAIL"
    return "WARN"


def _global_state(actual: float | None, gate: float, *, evidence_valid: bool) -> MatrixState:
    if not evidence_valid or actual is None:
        return "UNKNOWN"
    return "PASS" if actual >= gate else "FAIL"


def _actions_by_surface(plan: dict[str, Any]) -> dict[str, str]:
    actions: dict[str, str] = {}
    for raw in plan.get("top_actions", []):
        if not isinstance(raw, dict):
            continue
        surface = raw.get("name")
        action = raw.get("action")
        if isinstance(surface, str) and isinstance(action, str) and action.strip():
            actions[surface] = action
    return actions


def build_coverage_matrix(
    summary: dict[str, Any],
    targets: CoverageTargets,
    *,
    plan: dict[str, Any] | None = None,
    stage: CalibrationStage,
) -> CoverageMatrix:
    evidence_valid = bool(summary.get("evidence_valid"))
    release_gate = _as_float(targets.global_thresholds.get("current_release_gate"))
    diff_gate = _as_float(targets.global_thresholds.get("diff_coverage_gate"))
    release_actual = _as_float(summary.get("release_line_coverage"), default=-1.0)

    diff_payload = summary.get("diff_coverage")
    diff = diff_payload if isinstance(diff_payload, dict) else {}
    diff_actual = _as_float(diff.get("rate")) if diff.get("applicable") else None

    raw_surfaces = summary.get("surfaces")
    surfaces = raw_surfaces if isinstance(raw_surfaces, dict) else {}
    planned_actions = _actions_by_surface(plan or {})

    rows: list[MatrixRow] = []
    for name, target in targets.surfaces.items():
        raw = surfaces.get(name)
        payload = raw if isinstance(raw, dict) else {}
        line_rate = _as_float(payload.get("line_rate"))
        branch_rate = _as_float(payload.get("branch_rate"))
        stage_target = _target_for_stage(target, stage)
        line_deficit = max(0.0, stage_target - line_rate)
        branch_deficit = max(0.0, stage_target - branch_rate)
        risk_weight = _RISK_WEIGHT.get(target.claim_risk.lower(), 1.0)
        priority = round(risk_weight * (line_deficit + 0.35 * branch_deficit), 6)
        state = _matrix_state(
            evidence_valid=evidence_valid,
            risk=target.claim_risk,
            line_deficit=line_deficit,
            branch_deficit=branch_deficit,
        )
        action = planned_actions.get(name)
        if action is None:
            action = (
                "hold calibrated floor" if state == "PASS" else "regenerate evidence before ratchet"
            )
        rows.append(
            MatrixRow(
                surface=name,
                state=state,
                risk=target.claim_risk,
                line_rate=round(line_rate, 6),
                branch_rate=round(branch_rate, 6),
                target=round(stage_target, 6),
                line_deficit=round(line_deficit, 6),
                branch_deficit=round(branch_deficit, 6),
                priority=priority,
                action=action,
                rationale=target.rationale,
            )
        )

    rows.sort(
        key=lambda row: (
            {"FAIL": 0, "WARN": 1, "UNKNOWN": 2, "PASS": 3}[row.state],
            -row.priority,
            row.surface,
        )
    )
    return CoverageMatrix(
        schema_version="1.0",
        stage=stage,
        verdict=str(summary.get("verdict", "HUMAN_REVIEW_ONLY")),
        evidence_valid=evidence_valid,
        release_state=_global_state(release_actual, release_gate, evidence_valid=evidence_valid),
        diff_state=_global_state(diff_actual, diff_gate, evidence_valid=evidence_valid),
        rows=rows,
    )


def write_matrix(matrix: CoverageMatrix, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = asdict(matrix)
    (out_dir / "coverage_matrix.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# Coverage Operating Matrix",
        "",
        f"Schema: `{matrix.schema_version}`",
        f"Stage: `{matrix.stage}`",
        f"Verdict: `{matrix.verdict}`",
        f"Evidence valid: `{matrix.evidence_valid}`",
        f"Release state: `{matrix.release_state}`",
        f"Diff state: `{matrix.diff_state}`",
        "",
        "| rank | state | surface | risk | line % | branch % | target | line deficit | branch deficit | priority | action |",
        "|---:|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for index, row in enumerate(matrix.rows, start=1):
        lines.append(
            f"| {index} | {row.state} | {row.surface} | {row.risk} | "
            f"{row.line_rate:.2f} | {row.branch_rate:.2f} | {row.target:.2f} | "
            f"{row.line_deficit:.2f} | {row.branch_deficit:.2f} | {row.priority:.2f} | "
            f"{row.action} |"
        )
    (out_dir / "coverage_matrix.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", default="reports/coverage/intelligence/coverage_summary.json")
    parser.add_argument("--targets", default="configs/quality/coverage_targets.toml")
    parser.add_argument("--plan", default="reports/coverage/calibration/calibration_plan.json")
    parser.add_argument("--out", default="reports/coverage/matrix")
    parser.add_argument("--stage", choices=("short_term", "mid_term", "final"), default="mid_term")
    args = parser.parse_args(argv)

    summary_path = Path(args.summary)
    plan_path = Path(args.plan)
    if not summary_path.exists():
        raise SystemExit(f"coverage summary missing: {summary_path}")
    if not plan_path.exists():
        raise SystemExit(f"calibration plan missing: {plan_path}")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    targets = load_coverage_targets(Path(args.targets))
    matrix = build_coverage_matrix(summary, targets, plan=plan, stage=args.stage)
    write_matrix(matrix, Path(args.out))
    print(f"wrote {Path(args.out) / 'coverage_matrix.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
