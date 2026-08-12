#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Build a deterministic coverage-ascent plan from machine evidence."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, cast

EXIT_OK = 0
EXIT_EVIDENCE_INVALID = 3

_RISK_WEIGHT: dict[str, float] = {
    "critical": 4.0,
    "high": 3.0,
    "medium": 2.0,
    "low": 1.0,
}
_DEFAULT_BANDS = (90.0, 92.0, 95.0, 97.0)


@dataclass(frozen=True)
class SurfaceCalibration:
    surface: str
    claim_risk: str
    risk_weight: float
    line_rate: float
    branch_rate: float
    statements: int
    target_final: float
    target_band: float
    effective_target: float
    missing_statements_to_effective_target: int
    missing_statements_to_final_target: int
    weighted_deficit: float
    priority: int
    recommended_protocol: str


@dataclass(frozen=True)
class CalibrationPlan:
    schema_version: str
    evidence_valid: bool
    source_verdict: str
    release_line_coverage: float
    risk_weighted_score: float
    next_global_band: float
    global_gap_to_next_band: float
    untested_file_count: int
    recommended_surfaces: list[SurfaceCalibration]


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"coverage summary missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"coverage summary malformed: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("coverage summary must be a JSON object")
    return cast(dict[str, Any], payload)


def _parse_bands(raw: str) -> tuple[float, ...]:
    bands: list[float] = []
    for part in raw.split(","):
        stripped = part.strip()
        if stripped:
            bands.append(float(stripped))
    if not bands or any(value <= 0.0 or value > 100.0 for value in bands):
        raise ValueError("coverage bands must be in the 0-100 interval")
    return tuple(sorted(set(bands)))


def _next_band(release_cov: float, bands: tuple[float, ...]) -> float:
    for band in bands:
        if release_cov < band - 1e-9:
            return band
    return bands[-1]


def _missing_statements(statements: int, line_rate: float, target: float) -> int:
    if statements <= 0:
        return 0
    covered = statements * (line_rate / 100.0)
    required = statements * (target / 100.0)
    return max(0, math.ceil(required - covered - 1e-9))


def _protocol_for(surface: str, risk: str, branch_gap: float, untested_count: int) -> str:
    name = surface.lower()
    risk_l = risk.lower()
    if untested_count > 0 and risk_l in {"critical", "high"}:
        return "start with fully untested production files, then add invariant tests"
    if name == "backtest":
        return "replay determinism, no-lookahead, cost monotonicity, accounting invariants"
    if name in {"execution", "risk"} or risk_l == "critical":
        return "state rejection, idempotency, exposure accounting, transition guards"
    if branch_gap >= 20.0:
        return "branch completion with boundary states and explicit rejects"
    if name in {"ingestion", "data"}:
        return "schema drift, duplicate events, deterministic normalization"
    if name == "analytics":
        return "mathematical invariants, empty structures, deterministic aggregation"
    return "target invariant-bearing functions before cosmetic execution"


def build_plan(
    summary: dict[str, Any],
    bands: tuple[float, ...],
    max_surfaces: int,
) -> CalibrationPlan:
    evidence_valid = bool(summary.get("evidence_valid", False))
    release_cov = float(summary.get("release_line_coverage", 0.0))
    risk_score = float(summary.get("risk_weighted_score", 0.0))
    next_band = _next_band(release_cov, bands)
    untested_count = int(summary.get("untested_file_count", 0))
    surfaces_raw = summary.get("surfaces", {})
    if not isinstance(surfaces_raw, dict) or not surfaces_raw:
        raise ValueError("coverage summary has no surfaces")

    calibrations: list[SurfaceCalibration] = []
    for surface, raw_surface in surfaces_raw.items():
        if not isinstance(raw_surface, dict):
            continue
        statements = int(raw_surface.get("statements", 0))
        line_rate = float(raw_surface.get("line_rate", 0.0))
        branch_rate = float(raw_surface.get("branch_rate", 0.0))
        target_final = float(raw_surface.get("target_final", next_band))
        claim_risk = str(raw_surface.get("claim_risk", "low"))
        risk_weight = _RISK_WEIGHT.get(claim_risk.lower(), 1.0)
        effective_target = min(target_final, next_band)
        missing_effective = _missing_statements(statements, line_rate, effective_target)
        missing_final = _missing_statements(statements, line_rate, target_final)
        if missing_effective == 0 and missing_final == 0:
            continue
        branch_gap = max(0.0, line_rate - branch_rate)
        calibrations.append(
            SurfaceCalibration(
                surface=str(surface),
                claim_risk=claim_risk,
                risk_weight=risk_weight,
                line_rate=round(line_rate, 2),
                branch_rate=round(branch_rate, 2),
                statements=statements,
                target_final=target_final,
                target_band=next_band,
                effective_target=effective_target,
                missing_statements_to_effective_target=missing_effective,
                missing_statements_to_final_target=missing_final,
                weighted_deficit=round(risk_weight * missing_final, 2),
                priority=0,
                recommended_protocol=_protocol_for(
                    str(surface), claim_risk, branch_gap, untested_count
                ),
            )
        )

    ranked = sorted(
        calibrations,
        key=lambda item: (
            item.weighted_deficit,
            item.missing_statements_to_final_target,
            item.risk_weight,
            item.statements,
        ),
        reverse=True,
    )[:max_surfaces]
    ranked_with_priority = [replace(item, priority=index + 1) for index, item in enumerate(ranked)]
    return CalibrationPlan(
        schema_version="1.0",
        evidence_valid=evidence_valid,
        source_verdict=str(summary.get("verdict", "UNKNOWN")),
        release_line_coverage=round(release_cov, 2),
        risk_weighted_score=round(risk_score, 2),
        next_global_band=next_band,
        global_gap_to_next_band=round(max(0.0, next_band - release_cov), 2),
        untested_file_count=untested_count,
        recommended_surfaces=ranked_with_priority,
    )


def _write_json(plan: CalibrationPlan, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = asdict(plan)
    (out_dir / "coverage_calibration_plan.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_markdown(plan: CalibrationPlan, out_dir: Path) -> None:
    table_header = (
        "| priority | surface | risk | line % | branch % | final target | "
        "missing to band | missing to final | weighted deficit | protocol |"
    )
    lines = [
        "# Coverage Ascent Calibration Plan",
        "",
        f"Evidence valid: **{plan.evidence_valid}**",
        f"Source verdict: **{plan.source_verdict}**",
        f"Release line coverage: **{plan.release_line_coverage:.2f}%**",
        f"Risk-weighted score: **{plan.risk_weighted_score:.2f}%**",
        f"Next global band: **{plan.next_global_band:.2f}%**",
        f"Gap to next band: **{plan.global_gap_to_next_band:.2f}%**",
        f"Untested production files: **{plan.untested_file_count}**",
        "",
        "## Ranked surfaces",
        "",
        table_header,
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in plan.recommended_surfaces:
        lines.append(
            "| "
            f"{item.priority} | `{item.surface}` | {item.claim_risk} | "
            f"{item.line_rate:.2f} | {item.branch_rate:.2f} | "
            f"{item.target_final:.0f} | "
            f"{item.missing_statements_to_effective_target} | "
            f"{item.missing_statements_to_final_target} | "
            f"{item.weighted_deficit:.2f} | {item.recommended_protocol} |"
        )
    if not plan.recommended_surfaces:
        lines.append("| 0 | _none_ | - | - | - | - | - | - | - | - |")
    lines += [
        "",
        "## Acceptance discipline",
        "",
        "- Do not lower coverage thresholds.",
        "- Do not expand omit rules.",
        "- Do not claim a new global percentage without same-commit coverage artifacts.",
        "- Prefer tests that catch plausible wrong implementations.",
        "- Every slice must state its protected production contract.",
    ]
    (out_dir / "coverage_calibration_plan.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def run(args: argparse.Namespace) -> int:
    try:
        bands = _parse_bands(args.bands)
        summary = _load_json(Path(args.summary))
        plan = build_plan(summary, bands, args.max_surfaces)
    except ValueError as exc:
        print(f"CALIBRATION_EVIDENCE_INVALID: {exc}")
        return EXIT_EVIDENCE_INVALID

    out_dir = Path(args.out)
    _write_json(plan, out_dir)
    _write_markdown(plan, out_dir)
    print(f"CALIBRATION: next band {plan.next_global_band:.2f}%")
    print(f"  release line coverage: {plan.release_line_coverage:.2f}%")
    print(f"  surfaces ranked: {len(plan.recommended_surfaces)}")
    print(f"  output: {out_dir / 'coverage_calibration_plan.json'}")
    print(f"  output: {out_dir / 'coverage_calibration_plan.md'}")

    if args.enforce_evidence and not plan.evidence_valid:
        return EXIT_EVIDENCE_INVALID
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Calibrate coverage-ascent work from evidence")
    parser.add_argument("--summary", default="reports/coverage/coverage_summary.json")
    parser.add_argument("--out", default="reports/coverage")
    parser.add_argument(
        "--bands",
        default=",".join(str(int(value)) for value in _DEFAULT_BANDS),
    )
    parser.add_argument("--max-surfaces", type=int, default=6)
    parser.add_argument("--enforce-evidence", action="store_true", default=True)
    parser.add_argument(
        "--no-enforce-evidence",
        dest="enforce_evidence",
        action="store_false",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
