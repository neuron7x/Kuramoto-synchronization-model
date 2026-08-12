"""Contract tests for Integration Systems Architect Kernel governance data."""

from __future__ import annotations

import json
from pathlib import Path

DATA_PATH = Path("data/governance/integration_systems_architect_kernel_v1_0.json")
SCHEMA_PATH = Path("schemas/governance/integration_systems_architect_kernel.schema.json")
DOC_PATH = Path("docs/prompts/integration_systems_architect_kernel_v1_0.md")


def _data() -> dict[str, object]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def _schema() -> dict[str, object]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_kernel_artifacts_exist_and_parse() -> None:
    assert DOC_PATH.is_file()
    assert DATA_PATH.is_file()
    assert SCHEMA_PATH.is_file()
    assert _data()["artifact_id"] == "integration-systems-architect-kernel-v1.0"


def test_kernel_has_all_required_functions() -> None:
    data = _data()
    functions = data["functions"]
    assert isinstance(functions, list)
    assert len(functions) == 10
    ids = {item["id"] for item in functions if isinstance(item, dict)}
    assert "FUNCTION_01_INTERFACE_MAP" in ids
    assert "FUNCTION_10_ROLLBACK_PROTOCOL" in ids


def test_output_contract_contains_required_integration_fields() -> None:
    data = _data()
    output_contract = data["output_contract"]
    assert isinstance(output_contract, dict)
    required_fields = set(output_contract["required_fields"])
    assert {
        "modules",
        "contracts",
        "dependency_graph",
        "integration_points",
        "incompatibilities",
        "adapters_needed",
        "validation_gates",
        "commands",
        "rollback_plan",
        "acceptance_gate",
    } <= required_fields


def test_final_gate_blocks_pass_without_required_evidence() -> None:
    data = _data()
    final_gate = data["final_gate"]
    assert isinstance(final_gate, dict)
    pass_requires = set(final_gate["pass_requires"])
    assert {
        "install evidence",
        "config evidence",
        "contract test evidence",
        "integration test evidence",
        "smoke path evidence",
        "observability evidence",
        "rollback evidence",
    } <= pass_requires
    assert "PARTIAL" in final_gate["weakest_link_rule"]


def test_claim_boundary_blocks_runtime_and_market_claims() -> None:
    data = _data()
    scope = data["scope"]
    assert isinstance(scope, dict)
    blocked_claims = set(scope["blocked_claims"])
    assert "runtime integration completed" in blocked_claims
    assert "production readiness" in blocked_claims
    assert "physics validity" in blocked_claims
    assert "trading readiness" in blocked_claims
    assert "market prediction" in blocked_claims


def test_schema_required_keys_match_data_keys() -> None:
    data = _data()
    schema = _schema()
    required = schema["required"]
    assert isinstance(required, list)
    for key in required:
        assert key in data
