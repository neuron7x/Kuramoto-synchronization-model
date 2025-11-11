from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from tacl.energy_model import EnergyValidationError, EnergyValidator
from tacl.release_gates import evaluate_release_gates
from tacl.validate import ARTIFACTS_DIR, load_scenarios


def _write_mutation_summary(path: Path, *, kill_rate: float, counted: int = 100) -> None:
    killed = int(round(counted * kill_rate))
    payload = {
        "kill_rate": kill_rate,
        "counted_mutants": counted,
        "killed_mutants": killed,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


class ProgressiveRolloutController:
    """Toy orchestration layer mirroring the rollout workflow."""

    def __init__(
        self,
        *,
        gate_config: dict[str, object],
        scenarios_path: Path | None = None,
    ) -> None:
        self._base_config = copy.deepcopy(gate_config)
        self._scenarios = load_scenarios(scenarios_path)
        self._validator = EnergyValidator(max_free_energy=1.35)
        self.audit_log: list[dict[str, object]] = []

    def run(self, scenario_name: str) -> bool:
        if scenario_name not in self._scenarios:
            raise KeyError(f"scenario '{scenario_name}' not known to controller")

        metrics = self._scenarios[scenario_name]
        try:
            result = self._validator.validate(metrics)
        except EnergyValidationError as exc:
            self.audit_log.append(
                {
                    "stage": "validate-energy",
                    "status": "failed",
                    "reason": exc.result.reason,
                }
            )
            self.audit_log.append(
                {
                    "stage": "automated-rollback",
                    "status": "triggered",
                    "reason": exc.result.reason,
                }
            )
            return False

        self.audit_log.append(
            {
                "stage": "validate-energy",
                "status": "passed",
                "free_energy": round(result.free_energy, 6),
            }
        )

        gate_config = copy.deepcopy(self._base_config)
        gate_config["energy_scenario"] = scenario_name
        passed, summary = evaluate_release_gates(gate_config)
        ARTIFACTS_DIR.mkdir(exist_ok=True)
        (ARTIFACTS_DIR / "e2e_rollout_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        gate_entry = {
            "stage": "quality-gates",
            "status": "passed" if passed else "failed",
            "summary": summary,
        }
        self.audit_log.append(gate_entry)
        if not passed:
            self.audit_log.append(
                {
                    "stage": "automated-rollback",
                    "status": "triggered",
                    "reason": "quality gate failure",
                }
            )
            return False

        for stage in ("blue-green", "canary", "automated-rollback-check"):
            self.audit_log.append({"stage": stage, "status": "passed"})
        return True


@pytest.fixture(name="gate_config")
def gate_config_fixture() -> dict[str, object]:
    config_path = Path("ci/release_gates.yml").resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["perf_budgets_file"] = str(Path("configs/perf_budgets.yaml").resolve())
    config["scenario_file"] = str(Path("tacl/link_activator_test_scenarios.yaml").resolve())
    return config


def test_progressive_rollout_succeeds_nominal(
    tmp_path_factory: pytest.TempPathFactory,
    gate_config: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = Path(tmp_path_factory.mktemp("rollout-nominal"))
    monkeypatch.chdir(workspace)
    summary_path = workspace / "reports" / "mutmut" / "summary.json"
    gate_config.setdefault("mutation_testing", {})
    gate_config["mutation_testing"]["summary_file"] = str(summary_path)
    _write_mutation_summary(summary_path, kill_rate=0.95)
    controller = ProgressiveRolloutController(gate_config=gate_config)
    assert controller.run("nominal") is True
    stages = [entry["stage"] for entry in controller.audit_log]
    assert stages == [
        "validate-energy",
        "quality-gates",
        "blue-green",
        "canary",
        "automated-rollback-check",
    ]
    assert controller.audit_log[1]["status"] == "passed"


def test_progressive_rollout_triggers_rollback_on_degradation(
    tmp_path_factory: pytest.TempPathFactory,
    gate_config: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = Path(tmp_path_factory.mktemp("rollout-degraded"))
    monkeypatch.chdir(workspace)
    summary_path = workspace / "reports" / "mutmut" / "summary.json"
    gate_config.setdefault("mutation_testing", {})
    gate_config["mutation_testing"]["summary_file"] = str(summary_path)
    _write_mutation_summary(summary_path, kill_rate=0.95)
    controller = ProgressiveRolloutController(gate_config=gate_config)
    assert controller.run("degraded_packet_loss") is False
    assert controller.audit_log[-1]["stage"] == "automated-rollback"
    failure_reasons = [entry.get("reason") for entry in controller.audit_log if entry["stage"] == "validate-energy"]
    assert any("free energy" in (reason or "") for reason in failure_reasons)


def test_progressive_rollout_blocks_on_mutation_regression(
    tmp_path_factory: pytest.TempPathFactory,
    gate_config: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = Path(tmp_path_factory.mktemp("rollout-mutation"))
    monkeypatch.chdir(workspace)
    summary_path = workspace / "reports" / "mutmut" / "summary.json"
    gate_config.setdefault("mutation_testing", {})
    gate_config["mutation_testing"]["summary_file"] = str(summary_path)
    _write_mutation_summary(summary_path, kill_rate=0.72)
    controller = ProgressiveRolloutController(gate_config=gate_config)
    assert controller.run("nominal") is False
    gate_entry = controller.audit_log[1]
    assert gate_entry["stage"] == "quality-gates"
    assert gate_entry["status"] == "failed"
    mutation_summary = gate_entry["summary"]["mutation_testing"]
    assert mutation_summary["passed"] is False
    assert "kill rate" in mutation_summary["reason"]
