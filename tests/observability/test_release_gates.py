from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from execution.compliance import ComplianceReport
from observability.release_gates import ReleaseGateEvaluator, ReleaseGateResult

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "recordings"


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def test_latency_gate_passes_for_recorded_samples() -> None:
    dataset = FIXTURES / "coinbase_btcusd.jsonl"
    samples: list[float] = []
    for line in dataset.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        exchange_ts = _parse_timestamp(record["exchange_ts"])
        ingest_ts = _parse_timestamp(record["ingest_ts"])
        latency_ms = (ingest_ts - exchange_ts).total_seconds() * 1000.0
        samples.append(latency_ms)
    evaluator = ReleaseGateEvaluator(
        latency_median_target_ms=60.0,
        latency_p95_target_ms=90.0,
        latency_max_target_ms=120.0,
    )
    result = evaluator.evaluate_latency(samples)
    assert result.passed is True
    assert result.metrics["median_ms"] == pytest.approx(44.568, abs=1e-3)
    assert result.metrics["p95_ms"] == pytest.approx(45.56875, abs=1e-3)
    assert result.metrics["count"] == float(len(samples))


def test_gate_results_raise_on_failure() -> None:
    passing = ReleaseGateResult(name="ok", passed=True)
    passing.raise_for_failure()
    failing = ReleaseGateResult(name="broken", passed=False, reason="latency too high")
    with pytest.raises(RuntimeError):
        failing.raise_for_failure()


def test_compliance_and_checklist_gates() -> None:
    evaluator = ReleaseGateEvaluator()
    reports = [
        ComplianceReport(
            symbol="BTC-USD",
            requested_quantity=0.1,
            requested_price=64000.0,
            normalized_quantity=0.1,
            normalized_price=64000.0,
            violations=(),
            blocked=False,
        )
    ]
    compliance_result = evaluator.evaluate_compliance(reports)
    assert compliance_result.passed is True

    checklist_path = Path("configs/production_readiness.json")
    checklist_result = evaluator.evaluate_checklist_from_path(checklist_path)
    assert checklist_result.passed is True

    failing_reports = [
        ComplianceReport(
            symbol="BTC-USD",
            requested_quantity=0.0,
            requested_price=64000.0,
            normalized_quantity=0.0,
            normalized_price=64000.0,
            violations=("below minimum",),
            blocked=True,
        )
    ]
    violation_result = evaluator.evaluate_compliance(failing_reports)
    assert violation_result.passed is False
    assert "blocked" in str(violation_result.reason)


def test_release_gate_config_matches_raw_evidence() -> None:
    config_path = Path("ci/release_gates.yml")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    latency_cfg = config["latency"]
    dataset = Path(latency_cfg["samples_source"])
    sample_latencies: list[float] = []
    for line in dataset.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        exchange_ts = _parse_timestamp(record["exchange_ts"])
        ingest_ts = _parse_timestamp(record["ingest_ts"])
        sample_latencies.append((ingest_ts - exchange_ts).total_seconds() * 1000.0)
    configured_samples = [float(value) for value in latency_cfg["samples_ms"]]
    assert configured_samples == pytest.approx(sample_latencies, abs=1e-6)
    assert len(configured_samples) == len(sample_latencies)

    perf_path = Path(config["perf_budgets_file"])
    assert perf_path.exists()
    perf_budgets = yaml.safe_load(perf_path.read_text(encoding="utf-8")).get(
        "components", {}
    )
    assert perf_budgets

    scenario_path = Path(config["scenario_file"])
    scenarios = yaml.safe_load(scenario_path.read_text(encoding="utf-8")).get(
        "scenarios", {}
    )
    assert config["energy_scenario"] in scenarios
    for name in config.get("energy_negative_tests", []):
        assert name in scenarios
