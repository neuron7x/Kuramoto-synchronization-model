# ruff: noqa: I001

import json
from pathlib import Path
from typing import Any, cast

from BBB_NVU_Cognitive_Noise_Gate_2026.src.deterministic_engine import (
    DeterministicInferenceEngine,
    load_yaml,
)
from BBB_NVU_Cognitive_Noise_Gate_2026.src.observability import (
    build_incident_register,
    build_metrics_snapshot,
    incident_from_output,
    write_incidents,
)
from BBB_NVU_Cognitive_Noise_Gate_2026.tests.requirements import requirement

ROOT = Path(__file__).resolve().parents[1]
RULES = load_yaml(ROOT / "config" / "risk_rules.yaml")
FIXED_TIME = "2026-06-03T00:00:00Z"
FIXED_ENGINE_HASH = "engine-hash-for-observability-tests"


def output_for(input_doc: dict[str, Any], source_id: str = "memory.json") -> dict[str, Any]:
    engine = DeterministicInferenceEngine.from_rules(RULES, engine_hash=FIXED_ENGINE_HASH)
    return engine.build_output(input_doc, source_id=source_id, created_at=FIXED_TIME)


@requirement("R004")
def test_metrics_snapshot_counts_states_degradations_and_actions() -> None:
    stable = output_for(
        {
            "subject_id": "S-STABLE",
            "critical_data_invalid": False,
            "confidence": 0.95,
            "domain_indices": {"BSI": 20, "NRI": 20, "VML": 20, "GRS": 80, "CNI": 20},
            "degradations": [],
        },
        "stable.json",
    )
    watch = output_for(
        {
            "subject_id": "S-WATCH",
            "critical_data_invalid": False,
            "confidence": 0.60,
            "domain_indices": {"BSI": 20, "NRI": 20, "VML": 20, "GRS": 80, "CNI": 20},
            "degradations": ["sleep_proxy_low_specificity"],
        },
        "watch.json",
    )

    snapshot = build_metrics_snapshot([stable, watch], created_at=FIXED_TIME)

    assert snapshot.total_runs == 2
    assert snapshot.risk_state_counts["GREEN_STABLE"] == 1
    assert snapshot.risk_state_counts["YELLOW_WATCH"] == 1
    assert snapshot.degradation_counts == {"sleep_proxy_low_specificity": 1}
    assert snapshot.action_class_counts == {"OPERATIONAL_CONTROL": 3}
    assert snapshot.human_review_required == 0
    assert snapshot.autonomous_execution_prohibited == 0
    assert snapshot.low_confidence_runs == 1
    assert snapshot.incident_candidates == 1
    assert snapshot.snapshot_id.startswith("metrics-")


@requirement("R005")
def test_incident_record_maps_red_to_critical_and_blocks_autonomous_execution() -> None:
    red = output_for(
        {
            "subject_id": "S-RED",
            "critical_data_invalid": False,
            "confidence": 0.90,
            "domain_indices": {"BSI": 82, "NRI": 20, "VML": 20, "GRS": 80, "CNI": 20},
            "degradations": [],
        },
        "red.json",
    )

    incident = incident_from_output(red)

    assert incident is not None
    assert incident.severity == "CRITICAL"
    assert incident.requires_human_review
    assert incident.prohibited_autonomous_execution
    assert "block_autonomous_execution" in incident.response_steps
    assert incident.incident_id.startswith("incident-")


@requirement("R002")
def test_invalid_output_incident_uses_critical_response_ladder(tmp_path: Path) -> None:
    invalid = output_for(
        {
            "subject_id": "S-INVALID",
            "critical_data_invalid": True,
            "confidence": 1.0,
            "domain_indices": {"BSI": 20, "NRI": 20, "VML": 20, "GRS": 80, "CNI": 20},
            "degradations": [],
        },
        "invalid.json",
    )

    incidents = build_incident_register([invalid])
    path = tmp_path / "incidents.jsonl"
    write_incidents(path, incidents)
    parsed = cast(
        dict[str, Any],
        json.loads(path.read_text(encoding="utf-8")),
    )

    assert len(incidents) == 1
    assert parsed["severity"] == "CRITICAL"
    assert parsed["risk_state"] == "BLACK_INVALID"
    assert parsed["status"] == "OPEN"
    assert parsed["prohibited_autonomous_execution"] is True


@requirement("R004")
def test_green_output_does_not_open_incident() -> None:
    stable = output_for(
        {
            "subject_id": "S-STABLE",
            "critical_data_invalid": False,
            "confidence": 0.95,
            "domain_indices": {"BSI": 20, "NRI": 20, "VML": 20, "GRS": 80, "CNI": 20},
            "degradations": [],
        },
        "stable.json",
    )

    assert incident_from_output(stable) is None
    assert build_incident_register([stable]) == []
