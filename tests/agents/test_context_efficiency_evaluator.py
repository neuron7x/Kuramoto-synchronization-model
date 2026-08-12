from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "web_agent_context_efficiency_eval.py"
TRACE = ROOT / "tests" / "agents" / "fixtures" / "context_efficiency_trace.json"
ARTIFACT = ROOT / "artifacts" / "agents" / "web_agent_context_efficiency_eval.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("web_agent_context_efficiency_eval", TOOL)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["web_agent_context_efficiency_eval"] = module
    spec.loader.exec_module(module)
    return module


def test_context_efficiency_trace_evaluates_reproducibly() -> None:
    module = _load_module()
    trace = json.loads(TRACE.read_text(encoding="utf-8"))
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    result = module.evaluate_context_trace(trace)

    assert result["context_efficiency"] == artifact["context_efficiency"]
    assert result["tokens_needed"] == artifact["tokens_needed"]
    assert result["tokens_used"] == artifact["tokens_used"]
    assert result["compaction_rate"] == artifact["compaction_rate"]


def test_context_efficiency_is_within_target_but_not_provider_telemetry() -> None:
    trace = json.loads(TRACE.read_text(encoding="utf-8"))
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    assert trace["measurement_mode"] == "synthetic_context_trace_with_compaction_gate_not_provider_telemetry"
    assert artifact["context_efficiency"] <= artifact["target_ratio"]
    assert artifact["compaction_rate"] == 1.0
    assert all(event["compaction_applied"] is True for event in trace["events"])
    assert "Do not treat synthetic token accounting as provider telemetry." in artifact["failure_conditions"]
