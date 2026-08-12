# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""CLI utilities mirroring the Progressive Rollout quality gates."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping

import yaml

# Allow running this module as a standalone script without requiring installation
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from observability.release_gates import ReleaseGateEvaluator  # noqa: E402
from tacl.energy_model import EnergyValidationError, EnergyValidator  # noqa: E402
from tacl.validate import ARTIFACTS_DIR, load_scenarios  # noqa: E402


@dataclass(frozen=True, slots=True)
class PerfBudget:
    component: str
    observed_ms: float
    budget_ms: float

    def passed(self) -> bool:
        return self.observed_ms <= self.budget_ms


def _write_artifact(name: str, payload: Mapping[str, object]) -> None:
    ARTIFACTS_DIR.mkdir(exist_ok=True)
    target = ARTIFACTS_DIR / f"{name}.json"
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    lines = ["# " + name.replace("_", " ").title(), ""]
    for key, value in payload.items():
        lines.append(f"- **{key}**: {value}")
    (ARTIFACTS_DIR / f"{name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_perf_budgets(path: Path) -> list[PerfBudget]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    budgets: list[PerfBudget] = []
    for component, payload in data.get("components", {}).items():
        budgets.append(
            PerfBudget(
                component=component,
                observed_ms=float(payload["observed_ms"]),
                budget_ms=float(payload["budget_ms"]),
            )
        )
    return budgets


def evaluate_release_gates(
    config: Mapping[str, object],
) -> tuple[bool, Mapping[str, object]]:
    latency_cfg = config.get("latency") or {}
    evaluator = ReleaseGateEvaluator(
        latency_median_target_ms=float(latency_cfg.get("median_target_ms", 60.0)),
        latency_p95_target_ms=float(latency_cfg.get("p95_target_ms", 90.0)),
        latency_max_target_ms=float(latency_cfg.get("max_target_ms", 140.0)),
    )
    samples = [float(x) for x in latency_cfg.get("samples_ms", [])]
    latency_result = evaluator.evaluate_latency(samples)

    coverage_cfg = config.get("coverage", {})
    coverage_observed = float(coverage_cfg.get("observed", 0.0))
    coverage_required = float(coverage_cfg.get("required", 1.0))
    coverage_passed = coverage_observed >= coverage_required

    perf_path = Path(config.get("perf_budgets_file", "configs/perf_budgets.yaml"))
    perf_budgets = _load_perf_budgets(perf_path)
    perf_passed = all(budget.passed() for budget in perf_budgets)

    validator = EnergyValidator()
    scenarios = load_scenarios(
        Path(config.get("scenario_file", "")) if config.get("scenario_file") else None
    )
    energy_scenario = str(config.get("energy_scenario", "nominal"))
    if energy_scenario not in scenarios:
        raise KeyError(f"energy scenario '{energy_scenario}' not present in fixtures")
    energy_result = validator.evaluate(scenarios[energy_scenario])

    degradations: Iterable[str] = config.get("energy_negative_tests", [])
    degradations_outcome: MutableMapping[str, Mapping[str, object]] = {}
    negative_failures = 0
    for scenario_name in degradations:
        if scenario_name not in scenarios:
            raise KeyError(f"negative test scenario '{scenario_name}' missing")
        try:
            validator.validate(scenarios[scenario_name])
        except EnergyValidationError as exc:
            degradations_outcome[scenario_name] = {
                "passed": False,
                "free_energy": round(exc.result.free_energy, 6),
            }
        else:
            degradations_outcome[scenario_name] = {"passed": True}
            negative_failures += 1

    passed = (
        latency_result.passed
        and coverage_passed
        and perf_passed
        and energy_result.passed
        and negative_failures == 0
    )
    summary: dict[str, object] = {
        "latency": {
            "passed": latency_result.passed,
            "reason": latency_result.reason,
            "metrics": dict(latency_result.metrics),
        },
        "coverage": {
            "passed": coverage_passed,
            "observed": coverage_observed,
            "required": coverage_required,
        },
        "performance": {
            "passed": perf_passed,
            "budgets": [
                {
                    "component": budget.component,
                    "observed_ms": budget.observed_ms,
                    "budget_ms": budget.budget_ms,
                    "passed": budget.passed(),
                }
                for budget in perf_budgets
            ],
        },
        "energy": {
            "passed": energy_result.passed,
            "free_energy": round(energy_result.free_energy, 6),
            "entropy": round(energy_result.entropy, 6),
        },
        "negative_tests": degradations_outcome,
        "passed": passed,
    }
    return passed, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate progressive rollout gates")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("ci/release_gates.yml"),
        help="Path to the release gate configuration file",
    )
    args = parser.parse_args(argv)

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    passed, summary = evaluate_release_gates(config)
    _write_artifact("release_gates", summary)
    return 0 if passed else 1


if __name__ == "__main__":  # pragma: no cover - CLI shim
    raise SystemExit(main())
