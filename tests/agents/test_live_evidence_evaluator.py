from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "web_agent_live_evidence_eval.py"
TRACE = ROOT / "tests" / "agents" / "fixtures" / "live_runtime_trace_github_connector.json"
MATRIX = ROOT / "artifacts" / "agents" / "web_agent_adapter_verification_matrix.json"
ARTIFACT = ROOT / "artifacts" / "agents" / "web_agent_live_evidence_eval.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("web_agent_live_evidence_eval", TOOL)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["web_agent_live_evidence_eval"] = module
    spec.loader.exec_module(module)
    return module


def test_live_evidence_eval_reproduces_artifact() -> None:
    module = _load_module()
    trace = json.loads(TRACE.read_text(encoding="utf-8"))
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    result = module.evaluate_live_evidence(trace, matrix)

    assert result["status"] == artifact["status"]
    assert result["live_runtime_trace"] == artifact["live_runtime_trace"]
    assert result["live_tool_adapter_verification"] == artifact["live_tool_adapter_verification"]
    assert result["unverified_adapters_disabled"] == artifact["unverified_adapters_disabled"]
    assert result["critical_unmitigated_adapters"] == artifact["critical_unmitigated_adapters"]


def test_unverified_adapters_are_disabled_until_verified() -> None:
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))

    unverified = [
        adapter for adapter in matrix["adapters"]
        if str(adapter["live_status"]).startswith("NOT_VERIFIED")
    ]

    assert unverified
    assert all(adapter["runtime_status"] == "DISABLED_UNTIL_VERIFIED" for adapter in unverified)
    assert matrix["coverage"]["unverified_enabled_adapters"] == 0
    assert matrix["coverage"]["critical_unmitigated_adapters"] == 0
    assert matrix["coverage"]["critical_adapter_policy_passed"] is True


def test_live_runtime_trace_is_github_subset_not_full_adapter_proof() -> None:
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    assert artifact["live_runtime_trace"] is True
    assert artifact["github_adapter_subset_verified"] is True
    assert artifact["live_tool_adapter_verification"] is False
    assert "Do not mark live_tool_adapter_verification true from this artifact unless every adapter is live verified." in artifact["failure_conditions"]
