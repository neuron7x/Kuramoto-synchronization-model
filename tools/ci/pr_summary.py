# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Aggregate CI artifacts into a PR-facing summary."""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence


ARTIFACT_DIR = Path(".ci_artifacts")


@dataclass(frozen=True)
class StageStatus:
    name: str
    result: str

    @property
    def passed(self) -> bool:
        return self.result.lower() == "success"


def _load_json(path: Path) -> Mapping[str, object] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_coverage(path: Path) -> Mapping[str, float] | None:
    if not path.exists():
        return None
    tree = ET.parse(path)
    root = tree.getroot()
    line_rate = float(root.get("line-rate", "0")) * 100.0
    branch_rate = float(root.get("branch-rate", "0")) * 100.0 if root.get("branch-rate") else None
    payload = {"line_rate": round(line_rate, 3)}
    if branch_rate is not None:
        payload["branch_rate"] = round(branch_rate, 3)
    return payload


def _determine_risk(stages: Sequence[StageStatus], release: Mapping[str, object] | None, energy: Mapping[str, object] | None) -> str:
    if any(stage.result.lower() == "failure" for stage in stages):
        return "blocked"
    release_passed = bool(release.get("passed")) if release else True
    energy_passed = bool(energy.get("passed")) if energy else True
    if not release_passed or not energy_passed:
        return "blocked"
    if any(stage.result.lower() != "success" for stage in stages):
        return "elevated"
    if release:
        negative = release.get("negative_tests")
        if isinstance(negative, Mapping):
            if any(entry.get("passed") for entry in negative.values() if isinstance(entry, Mapping)):
                return "elevated"
    return "normal"


def build_summary(
    stages: Sequence[StageStatus],
    coverage: Mapping[str, float] | None,
    release: Mapping[str, object] | None,
    energy: Mapping[str, object] | None,
) -> Mapping[str, object]:
    risk = _determine_risk(stages, release, energy)
    summary: dict[str, object] = {
        "risk_level": risk,
        "stages": [stage.__dict__ for stage in stages],
        "coverage": coverage or {},
        "release_gates": release or {},
        "energy_validation": energy or {},
    }
    return summary


def _write_artifacts(summary: Mapping[str, object]) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    (ARTIFACT_DIR / "pr_validation_summary.json").write_text(payload, encoding="utf-8")

    lines = ["# Pull Request validation summary", ""]
    lines.append(f"- **Risk level**: {summary['risk_level']}")
    coverage = summary.get("coverage") or {}
    if coverage:
        lines.append(
            f"- **Coverage**: line-rate {coverage.get('line_rate', 'n/a')}%"
            + (f", branch-rate {coverage.get('branch_rate')}%" if coverage.get("branch_rate") is not None else "")
        )
    release = summary.get("release_gates") or {}
    if release:
        release_status = "passed" if release.get("passed") else "failed"
        latency = release.get("latency", {})
        latency_metrics = latency.get("metrics") if isinstance(latency, Mapping) else None
        latency_summary = ""
        if isinstance(latency_metrics, Mapping):
            p95 = latency_metrics.get("p95_ms") or latency_metrics.get("p95")
            max_val = latency_metrics.get("max_ms") or latency_metrics.get("max")
            latency_summary = f" (p95={p95}, max={max_val})"
        lines.append(f"- **Release gates**: {release_status}{latency_summary}")
    energy = summary.get("energy_validation") or {}
    if energy:
        energy_status = "passed" if energy.get("passed") else "failed"
        free_energy = energy.get("nominal_free_energy") or energy.get("free_energy")
        entropy = energy.get("nominal_entropy") or energy.get("entropy")
        lines.append(f"- **Energy validator**: {energy_status} (F={free_energy}, S={entropy})")
    lines.append("- **Stages**:")
    for stage in summary.get("stages", []):
        lines.append(f"  - {stage['name']}: {stage['result']}")

    (ARTIFACT_DIR / "pr_validation_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate CI validation artifacts")
    parser.add_argument(
        "--stage",
        action="append",
        default=[],
        help="Stage status in the form name=result (can be passed multiple times)",
    )
    parser.add_argument("--coverage", type=Path, default=Path("coverage.xml"))
    parser.add_argument(
        "--release",
        type=Path,
        default=ARTIFACT_DIR / "release_gates.json",
        help="Path to the release gate artifact",
    )
    parser.add_argument(
        "--energy",
        type=Path,
        default=ARTIFACT_DIR / "energy_validation.json",
        help="Path to the energy validation artifact",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    stages: list[StageStatus] = []
    for raw in args.stage:
        try:
            name, result = raw.split("=", 1)
        except ValueError:
            print(f"Invalid stage specification: {raw}", file=sys.stderr)
            return 2
        stages.append(StageStatus(name=name.strip(), result=result.strip()))

    coverage_metrics = _parse_coverage(args.coverage)
    release_data = _load_json(args.release)
    energy_data = _load_json(args.energy)
    summary = build_summary(stages, coverage_metrics, release_data, energy_data)
    _write_artifacts(summary)
    return 0


def main() -> int:  # pragma: no cover - CLI entry point
    return run()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
