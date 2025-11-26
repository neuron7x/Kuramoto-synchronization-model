"""Command line entry-point for TACL energy validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping

import yaml

from .energy_model import (
    DEFAULT_THRESHOLDS,
    EnergyMetrics,
    EnergyValidationError,
    EnergyValidator,
)

SCENARIO_FILE = Path(__file__).resolve().parent / "link_activator_test_scenarios.yaml"
ARTIFACTS_DIR = Path(".ci_artifacts")


def load_scenarios(path: Path | None = None) -> Mapping[str, EnergyMetrics]:
    """Load predefined test scenarios for link activator telemetry."""

    scenario_path = path or SCENARIO_FILE
    data = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
    scenarios: dict[str, EnergyMetrics] = {}
    for name, payload in data.get("scenarios", {}).items():
        scenarios[name] = EnergyMetrics(
            latency_p95=float(payload["latency_p95"]),
            latency_p99=float(payload["latency_p99"]),
            coherency_drift=float(payload["coherency_drift"]),
            cpu_burn=float(payload["cpu_burn"]),
            mem_cost=float(payload["mem_cost"]),
            queue_depth=float(payload["queue_depth"]),
            packet_loss=float(payload["packet_loss"]),
        )
    return scenarios


def _write_artifact(name: str, payload: Mapping[str, object]) -> None:
    ARTIFACTS_DIR.mkdir(exist_ok=True)
    target = ARTIFACTS_DIR / f"{name}.json"
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    markdown = ARTIFACTS_DIR / f"{name}.md"
    lines = ["# " + name.replace("_", " ").title(), ""]
    for key, value in payload.items():
        lines.append(f"- **{key}**: {value}")
    markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_validation(mode: str, *, scenarios: Mapping[str, EnergyMetrics]) -> int:
    validator = EnergyValidator(max_free_energy=1.35)
    summary: dict[str, object] = {"mode": mode, "thresholds": dict(DEFAULT_THRESHOLDS)}
    passed = True

    if mode in {"smoke", "ci"}:
        nominal = scenarios.get("nominal")
        if nominal is None:
            raise FileNotFoundError("nominal scenario missing from fixtures")
        try:
            result = validator.validate(nominal)
        except EnergyValidationError as exc:
            passed = False
            summary["nominal_result"] = {
                "passed": False,
                "free_energy": round(exc.result.free_energy, 6),
                "reason": exc.result.reason,
            }
        else:
            summary["nominal_free_energy"] = round(result.free_energy, 6)
            summary["nominal_entropy"] = round(result.entropy, 6)

    if mode == "ci":
        degradations = {
            name: metrics for name, metrics in scenarios.items() if name != "nominal"
        }
        for name, metrics in degradations.items():
            try:
                validator.validate(metrics)
            except (
                EnergyValidationError
            ) as exc:  # noqa: PERF203 - deliberate control flow
                summary[f"{name}_result"] = {
                    "passed": False,
                    "free_energy": round(exc.result.free_energy, 6),
                    "reason": exc.result.reason,
                }
                continue
            passed = False
            summary[f"{name}_result"] = {
                "passed": True,
                "free_energy": "unexpectedly within bounds",
            }
    elif mode == "single":
        single = scenarios.get("single")
        if single is None:
            raise FileNotFoundError("single scenario not provided")
        try:
            result = validator.validate(single)
        except EnergyValidationError as exc:
            summary["single_result"] = {
                "passed": False,
                "free_energy": round(exc.result.free_energy, 6),
                "reason": exc.result.reason,
            }
            _write_artifact("energy_validation", summary)
            return 1
        summary["single_result"] = {
            "passed": True,
            "free_energy": round(result.free_energy, 6),
        }
    elif mode == "smoke":
        summary["smoke"] = "completed"
    else:
        raise ValueError(f"unknown run mode: {mode}")

    summary["passed"] = passed
    _write_artifact("energy_validation", summary)
    return 0 if passed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate thermodynamic energy")
    parser.add_argument(
        "--run",
        choices=["smoke", "ci", "single"],
        default="smoke",
        help="Select validation mode",
    )
    parser.add_argument(
        "--metrics",
        type=Path,
        help="Optional YAML file containing a single scenario under 'single'",
    )
    args = parser.parse_args(argv)

    scenario_file = args.metrics
    scenarios = load_scenarios(scenario_file) if scenario_file else load_scenarios()
    return run_validation(args.run, scenarios=scenarios)


if __name__ == "__main__":  # pragma: no cover - CLI hook
    raise SystemExit(main())
