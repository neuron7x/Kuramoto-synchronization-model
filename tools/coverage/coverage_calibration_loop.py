#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deterministic coverage calibration loop.

The tool converts coverage evidence into a ranked optimization plan. It computes
deficits against the canonical target contract, weights them by claim risk, and
emits a reversible action plan that can be regenerated after the next evidence
bundle.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from tools.coverage.surface_contract import (
    CoverageTargets,
    SurfaceTarget,
    load_coverage_targets,
)

CalibrationStage = Literal["short_term", "mid_term", "final"]

_RISK_WEIGHT: dict[str, float] = {
    "critical": 4.0,
    "high": 3.0,
    "medium": 2.0,
    "low": 1.0,
}


@dataclass(frozen=True)
class SurfaceSignal:
    name: str
    line_rate: float
    branch_rate: float
    statements: int
    target: float
    final_target: float
    claim_risk: str
    deficit: float
    branch_deficit: float
    priority: float
    action: str


@dataclass(frozen=True)
class CalibrationPlan:
    schema_version: str
    stage: CalibrationStage
    verdict: str
    evidence_valid: bool
    global_release_gate: float
    global_release_actual: float
    global_release_deficit: float
    diff_gate: float
    diff_actual: float | None
    diff_deficit: float
    risk_weighted_score: float
    recommended_command: str
    top_actions: list[SurfaceSignal]
    stop_rules: list[str]


def _target_for_stage(target: SurfaceTarget, stage: CalibrationStage) -> float:
    if stage == "short_term":
        return target.short_term
    if stage == "mid_term":
        return target.mid_term
    return target.final


def _as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _surface_action(name: str, signal: SurfaceSignal) -> str:
    if signal.branch_deficit > signal.deficit and signal.branch_deficit >= 2.0:
        return f"add branch/edge tests for {name} before adding new happy paths"
    if signal.deficit >= 20.0:
        return f"add first-principles characterization tests for {name} public contracts"
    if signal.deficit >= 5.0:
        return f"add guardrail tests for {name} state transitions and fail-closed paths"
    return f"ratchet {name} with mutation-resistant edge tests"


def _surface_signal(
    name: str,
    raw: dict[str, Any],
    targets: CoverageTargets,
    stage: CalibrationStage,
) -> SurfaceSignal:
    target = targets.surfaces[name]
    line_rate = _as_float(raw.get("line_rate"))
    branch_rate = _as_float(raw.get("branch_rate"))
    statements = int(_as_float(raw.get("statements")))
    stage_target = _target_for_stage(target, stage)
    deficit = max(0.0, stage_target - line_rate)
    branch_deficit = max(0.0, stage_target - branch_rate)
    risk_weight = _RISK_WEIGHT.get(target.claim_risk.lower(), 1.0)
    size_weight = max(1.0, statements**0.5 / 10.0)
    priority = round(risk_weight * size_weight * (deficit + 0.35 * branch_deficit), 6)
    provisional = SurfaceSignal(
        name=name,
        line_rate=line_rate,
        branch_rate=branch_rate,
        statements=statements,
        target=stage_target,
        final_target=target.final,
        claim_risk=target.claim_risk,
        deficit=round(deficit, 6),
        branch_deficit=round(branch_deficit, 6),
        priority=priority,
        action="",
    )
    return SurfaceSignal(**{**asdict(provisional), "action": _surface_action(name, provisional)})


def build_calibration_plan(
    summary: dict[str, Any],
    targets: CoverageTargets,
    *,
    stage: CalibrationStage,
    limit: int,
) -> CalibrationPlan:
    global_thresholds = targets.global_thresholds
    release_gate = _as_float(global_thresholds.get("current_release_gate"))
    diff_gate = _as_float(global_thresholds.get("diff_coverage_gate"))
    release_actual = _as_float(summary.get("release_line_coverage"))
    release_deficit = max(0.0, release_gate - release_actual)
    risk_score = _as_float(summary.get("risk_weighted_score"))

    raw_diff = summary.get("diff_coverage")
    diff_payload = raw_diff if isinstance(raw_diff, dict) else {}
    diff_applicable = bool(diff_payload.get("applicable"))
    diff_actual = _as_float(diff_payload.get("rate")) if diff_applicable else None
    diff_deficit = max(0.0, diff_gate - diff_actual) if diff_actual is not None else 0.0

    raw_surfaces = summary.get("surfaces")
    surfaces = raw_surfaces if isinstance(raw_surfaces, dict) else {}
    signals: list[SurfaceSignal] = []
    for name, raw in surfaces.items():
        if name not in targets.surfaces or not isinstance(raw, dict):
            continue
        signal = _surface_signal(name, raw, targets, stage)
        if signal.deficit > 0.0 or signal.branch_deficit > 0.0:
            signals.append(signal)

    signals.sort(key=lambda item: (-item.priority, item.name))

    stop_rules = [
        "stop if evidence_valid is false; regenerate coverage.xml and junit.xml first",
        "stop if a changed production line has no executable coverage evidence",
        "stop if a critical/high surface regresses below its previous calibrated floor",
        "stop if a new test only asserts implementation detail without public behavior value",
    ]
    command = (
        "python -m tools.coverage.geosync_coverage_intelligence "
        "--coverage reports/coverage/coverage.xml "
        "--junit reports/coverage/junit.xml "
        "--targets configs/quality/coverage_targets.toml "
        "--out reports/coverage/intelligence "
        "--enforce-release-90 --enforce-critical --enforce-diff"
    )

    return CalibrationPlan(
        schema_version="1.0",
        stage=stage,
        verdict=str(summary.get("verdict", "HUMAN_REVIEW_ONLY")),
        evidence_valid=bool(summary.get("evidence_valid")),
        global_release_gate=round(release_gate, 6),
        global_release_actual=round(release_actual, 6),
        global_release_deficit=round(release_deficit, 6),
        diff_gate=round(diff_gate, 6),
        diff_actual=None if diff_actual is None else round(diff_actual, 6),
        diff_deficit=round(diff_deficit, 6),
        risk_weighted_score=round(risk_score, 6),
        recommended_command=command,
        top_actions=signals[:limit],
        stop_rules=stop_rules,
    )


def write_plan(plan: CalibrationPlan, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = asdict(plan)
    (out_dir / "calibration_plan.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# Coverage Calibration Plan",
        "",
        f"Schema: `{plan.schema_version}`",
        f"Stage: `{plan.stage}`",
        f"Verdict: `{plan.verdict}`",
        f"Evidence valid: `{plan.evidence_valid}`",
        "",
        "## Objective",
        "",
        "Maximize risk-weighted verified coverage while minimizing stale, missing, or",
        "non-executable evidence. Every action must be reversible by re-running the",
        "same coverage-intelligence command and comparing the emitted JSON plan.",
        "",
        "## Global gates",
        "",
        f"- Release: {plan.global_release_actual:.2f}% / {plan.global_release_gate:.2f}% "
        f"(deficit {plan.global_release_deficit:.2f})",
        f"- Diff: {plan.diff_actual if plan.diff_actual is not None else 'n/a'} / "
        f"{plan.diff_gate:.2f}% (deficit {plan.diff_deficit:.2f})",
        f"- Risk-weighted score: {plan.risk_weighted_score:.2f}",
        "",
        "## Ranked actions",
        "",
        "| rank | surface | risk | line % | branch % | target | deficit | priority | action |",
        "|---:|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for idx, action in enumerate(plan.top_actions, start=1):
        lines.append(
            f"| {idx} | {action.name} | {action.claim_risk} | "
            f"{action.line_rate:.2f} | {action.branch_rate:.2f} | "
            f"{action.target:.2f} | {action.deficit:.2f} | "
            f"{action.priority:.2f} | {action.action} |"
        )
    if not plan.top_actions:
        lines.append("| 1 | _none_ | _n/a_ | 0 | 0 | 0 | 0 | 0 | no deficit detected |")
    lines += [
        "",
        "## Deterministic command",
        "",
        "```bash",
        plan.recommended_command,
        "```",
        "",
    ]
    lines += ["## Stop rules", ""] + [f"- {rule}" for rule in plan.stop_rules]
    (out_dir / "calibration_plan.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", default="reports/coverage/intelligence/coverage_summary.json")
    parser.add_argument("--targets", default="configs/quality/coverage_targets.toml")
    parser.add_argument("--out", default="reports/coverage/calibration")
    parser.add_argument("--stage", choices=("short_term", "mid_term", "final"), default="mid_term")
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args(argv)

    summary_path = Path(args.summary)
    if not summary_path.exists():
        raise SystemExit(f"coverage summary missing: {summary_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    targets = load_coverage_targets(Path(args.targets))
    plan = build_calibration_plan(summary, targets, stage=args.stage, limit=args.limit)
    write_plan(plan, Path(args.out))
    print(f"wrote {Path(args.out) / 'calibration_plan.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
