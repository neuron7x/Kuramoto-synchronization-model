from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "artifacts" / "agents" / "web_agent_tool_contract_inventory.json"
DOC = ROOT / "docs" / "agents" / "web_agent_tool_contract_inventory.md"


REQUIRED_TOOL_FIELDS = {
    "tool_id",
    "responsibility",
    "input_schema",
    "output_schema",
    "side_effect",
    "irreversible",
    "trusted_output",
    "failure_mode",
    "retry_policy",
    "escalation",
}


def _inventory() -> dict:
    return json.loads(INVENTORY.read_text(encoding="utf-8"))


def test_tool_contract_inventory_has_complete_static_contracts() -> None:
    payload = _inventory()

    assert payload["status"] == "STATIC_TOOL_CONTRACTS_DEFINED_NOT_LIVE_ADAPTER_VERIFIED"
    assert payload["tools"]

    tool_ids = set()
    for tool in payload["tools"]:
        missing = REQUIRED_TOOL_FIELDS - set(tool)
        assert not missing, f"{tool.get('tool_id')} missing contract fields: {sorted(missing)}"
        assert tool["tool_id"] not in tool_ids
        tool_ids.add(tool["tool_id"])
        assert tool["responsibility"]
        assert isinstance(tool["input_schema"], dict)
        assert isinstance(tool["output_schema"], dict)
        assert tool["failure_mode"]
        assert tool["retry_policy"]
        assert tool["escalation"]


def test_tool_contract_inventory_coverage_is_reproducible() -> None:
    payload = _inventory()
    tools = payload["tools"]
    coverage = payload["coverage"]

    assert coverage["total_tools"] == len(tools)
    assert coverage["tools_with_single_responsibility"] == len(tools)
    assert coverage["tools_with_input_schema"] == len(tools)
    assert coverage["tools_with_output_schema"] == len(tools)
    assert coverage["tools_with_failure_mode"] == len(tools)
    assert coverage["tools_with_retry_policy"] == len(tools)
    assert coverage["coverage_ratio"] == 1.0


def test_tool_contract_inventory_declares_static_not_live_boundary() -> None:
    text = DOC.read_text(encoding="utf-8")
    payload = _inventory()

    required_terms = [
        "STATIC_TOOL_CONTRACTS_DEFINED",
        "LIVE_ADAPTER_BEHAVIOR_NOT_VERIFIED",
        "This is **static contract coverage**, not live adapter verification.",
        "A tool output is evidence. It is not instruction authority",
    ]
    missing = [term for term in required_terms if term not in text]

    assert not missing, f"Missing tool inventory boundary terms: {missing}"
    assert "Do not treat static inventory as live adapter proof." in payload["failure_conditions"]
