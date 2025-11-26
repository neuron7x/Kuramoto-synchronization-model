from __future__ import annotations

import json
from pathlib import Path

import pytest

from tacl.energy_model import (
    DEFAULT_THRESHOLDS,
    DEFAULT_WEIGHTS,
    EnergyMetrics,
    EnergyModel,
    EnergyValidationError,
    EnergyValidator,
)
from tacl.validate import ARTIFACTS_DIR, load_scenarios, run_validation


def test_free_energy_normalises_weights() -> None:
    metrics = EnergyMetrics(
        latency_p95=64.0,
        latency_p99=92.0,
        coherency_drift=0.031,
        cpu_burn=0.58,
        mem_cost=4.2,
        queue_depth=18.0,
        packet_loss=0.001,
    )
    model = EnergyModel()
    free_energy, internal, entropy, penalties = model.free_energy(metrics)

    assert all(value == pytest.approx(0.0, abs=1e-9) for value in penalties.values())

    weight_total = sum(DEFAULT_WEIGHTS.values())
    expected_internal = 0.92 + sum(
        penalties[name] * (DEFAULT_WEIGHTS[name] / weight_total) for name in penalties
    )
    expected_entropy = max(
        0.05,
        sum(
            max(0.0, 1.0 - metrics.as_dict()[name] / DEFAULT_THRESHOLDS[name])
            * (DEFAULT_WEIGHTS[name] / weight_total)
            for name in penalties
        ),
    )
    expected_free_energy = expected_internal - 0.6 * expected_entropy

    assert internal == pytest.approx(expected_internal, rel=1e-6)
    assert entropy == pytest.approx(expected_entropy, rel=1e-6)
    assert free_energy == pytest.approx(expected_free_energy, rel=1e-6)


def test_energy_validator_flags_regression() -> None:
    scenarios = load_scenarios()
    validator = EnergyValidator(max_free_energy=1.35)

    nominal = scenarios["nominal"]
    result = validator.validate(nominal)
    assert result.passed is True
    assert result.free_energy < validator.max_free_energy

    degraded = scenarios["degraded_high_latency"]
    with pytest.raises(EnergyValidationError) as exc:
        validator.validate(degraded)
    assert "free energy" in str(exc.value)
    assert exc.value.result.free_energy > validator.max_free_energy


def test_cli_creates_artifacts(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = Path(tmp_path_factory.mktemp("energy-artifacts"))
    monkeypatch.chdir(workspace)
    exit_code = run_validation(
        "single",
        scenarios={
            "single": EnergyMetrics(
                latency_p95=170.0,
                latency_p99=240.0,
                coherency_drift=0.18,
                cpu_burn=0.88,
                mem_cost=7.1,
                queue_depth=52.0,
                packet_loss=0.012,
            )
        },
    )
    assert exit_code == 1

    artifact = ARTIFACTS_DIR / "energy_validation.json"
    assert artifact.exists()
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["single_result"]["passed"] is False
