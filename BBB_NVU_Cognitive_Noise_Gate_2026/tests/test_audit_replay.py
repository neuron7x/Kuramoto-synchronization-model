# ruff: noqa: I001

import json
from pathlib import Path
from typing import Any, cast

from BBB_NVU_Cognitive_Noise_Gate_2026.src.audit import (
    AuditEvent,
    build_replay_bundle,
    verify_replay_bundle,
    write_audit_event,
)
from BBB_NVU_Cognitive_Noise_Gate_2026.src.deterministic_engine import (
    DeterministicInferenceEngine,
    load_yaml,
)
from BBB_NVU_Cognitive_Noise_Gate_2026.tests.requirements import requirement

ROOT = Path(__file__).resolve().parents[1]
RULES = load_yaml(ROOT / "config" / "risk_rules.yaml")
SAMPLE_INPUT = cast(
    dict[str, Any],
    json.loads(
        (ROOT / "examples" / "sample_run_input.json").read_text(encoding="utf-8")
    ),
)
FIXED_TIME = "2026-06-03T00:00:00Z"
FIXED_ENGINE_HASH = "engine-hash-for-audit-replay-tests"


def build_output() -> dict[str, Any]:
    engine = DeterministicInferenceEngine.from_rules(RULES, engine_hash=FIXED_ENGINE_HASH)
    return engine.build_output(
        SAMPLE_INPUT, source_id="sample_run_input.json", created_at=FIXED_TIME
    )


@requirement("R003")
def test_inference_output_contains_hash_material_for_replay() -> None:
    output = build_output()
    assert output["input_hash"]
    assert output["rules_hash"]
    assert output["engine_hash"] == FIXED_ENGINE_HASH
    assert output["run_hash"]


@requirement("R003")
def test_audit_event_is_deterministic_jsonl(tmp_path: Path) -> None:
    output = build_output()
    event = AuditEvent.from_output(output)
    line = event.to_jsonl()
    parsed = cast(dict[str, Any], json.loads(line))
    assert parsed["run_hash"] == event.run_hash
    out = tmp_path / "audit.jsonl"
    write_audit_event(out, event)
    assert out.read_text(encoding="utf-8") == line


@requirement("R003")
def test_replay_bundle_verifies_against_hashes() -> None:
    output = build_output()
    bundle = build_replay_bundle(output, SAMPLE_INPUT, RULES)
    expected = cast(dict[str, Any], bundle["expected"])
    assert expected["input_hash"] == output["input_hash"]
    assert expected["rules_hash"] == output["rules_hash"]
    assert expected["run_hash"] == output["run_hash"]
    assert bundle["bundle_hash"]
    assert verify_replay_bundle(bundle)


@requirement("R003")
def test_changed_replay_bundle_is_not_accepted() -> None:
    output = build_output()
    bundle = build_replay_bundle(output, SAMPLE_INPUT, RULES)
    expected = cast(dict[str, Any], bundle["expected"])
    expected["run_hash"] = "changed"
    assert not verify_replay_bundle(bundle)
