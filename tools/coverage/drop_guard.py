# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Enforce coverage regression guardrails against a stored baseline."""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CoverageBaseline:
    line_rate: float
    branch_rate: float | None = None


def _normalise_rate(value: float) -> float:
    return value * 100.0 if value <= 1.0 else value


def _load_baseline(path: Path) -> CoverageBaseline:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "line_rate" not in payload:
        raise ValueError("baseline must include 'line_rate'")
    line_rate = _normalise_rate(float(payload["line_rate"]))
    branch_value = payload.get("branch_rate")
    branch_rate = _normalise_rate(float(branch_value)) if branch_value is not None else None
    return CoverageBaseline(line_rate=line_rate, branch_rate=branch_rate)


def _load_coverage_rates(report_path: Path) -> tuple[float, float | None]:
    root = ET.parse(report_path).getroot()
    line_rate = float(root.get("line-rate", 0.0)) * 100.0
    branch_attr = root.get("branch-rate")
    branch_rate = float(branch_attr) * 100.0 if branch_attr is not None else None
    return line_rate, branch_rate


def _evaluate(baseline: CoverageBaseline, report_path: Path) -> int:
    line_rate, branch_rate = _load_coverage_rates(report_path)
    failures = []

    if line_rate + 1e-9 < baseline.line_rate:
        failures.append(f"line coverage {line_rate:.2f}% below baseline {baseline.line_rate:.2f}%")

    if baseline.branch_rate is not None:
        if branch_rate is None:
            failures.append("branch coverage missing from report")
        elif branch_rate + 1e-9 < baseline.branch_rate:
            failures.append(
                "branch coverage {0:.2f}% below baseline {1:.2f}%".format(
                    branch_rate, baseline.branch_rate
                )
            )

    if failures:
        print("Coverage regression guard failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(
        "Coverage regression guard passed: "
        f"line {line_rate:.2f}% / baseline {baseline.line_rate:.2f}%"
    )
    if baseline.branch_rate is not None and branch_rate is not None:
        print(
            "Coverage regression guard passed: "
            f"branch {branch_rate:.2f}% / baseline {baseline.branch_rate:.2f}%"
        )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail CI when coverage drops below stored baselines.",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("configs/quality/coverage_baseline.json"),
        help="Path to the baseline coverage JSON file.",
    )
    parser.add_argument(
        "--coverage",
        type=Path,
        default=Path("coverage.xml"),
        help="Path to the coverage XML report.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        baseline = _load_baseline(args.baseline)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error loading baseline: {exc}", file=sys.stderr)
        return 2

    try:
        return _evaluate(baseline, args.coverage)
    except (FileNotFoundError, ET.ParseError) as exc:
        print(f"Error reading coverage report: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
