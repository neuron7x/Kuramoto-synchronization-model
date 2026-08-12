from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TRACE_TOOL = ROOT / "tools" / "web_agent_runtime_trace_eval.py"
INJECTION_TOOL = ROOT / "tools" / "web_agent_injection_eval.py"
DECISION_TRACE = ROOT / "tests" / "agents" / "fixtures" / "decision_runtime_trace.json"
MEMORY_TRACE = ROOT / "tests" / "agents" / "fixtures" / "memory_runtime_trace.json"
INJECTION_SUITE = ROOT / "tests" / "agents" / "fixtures" / "prompt_injection_cases.json"
INJECTION_TRACE = ROOT / "tests" / "agents" / "fixtures" / "prompt_injection_runtime_trace_pass.json"
TRACE_ARTIFACT = ROOT / "artifacts" / "agents" / "web_agent_runtime_trace_eval.json"
INJECTION_ARTIFACT = ROOT / "artifacts" / "agents" / "web_agent_prompt_injection_eval.json"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_runtime_trace_evaluator_accepts_decision_and_memory_traces() -> None:
    module = _load_module(TRACE_TOOL, "web_agent_runtime_trace_eval")

    result = module.evaluate_traces(_json(DECISION_TRACE), _json(MEMORY_TRACE))

    assert result["status"] == "PASS"
    assert result["derived_metrics"] == {
        "irreversible_actions_without_confirmation": 0,
        "escalation_precision": 1.0,
        "retry_budget_compliance": 1.0,
        "memory_minimization": 0.85,
        "explanation_completeness": 1.0,
    }


def test_runtime_trace_evaluator_rejects_missing_confirmation() -> None:
    module = _load_module(TRACE_TOOL, "web_agent_runtime_trace_eval")
    decision = _json(DECISION_TRACE)
    decision["events"][1]["confirmation_requested"] = False

    result = module.evaluate_traces(decision, _json(MEMORY_TRACE))

    assert result["status"] == "FAIL"
    assert result["decision"]["irreversible_actions_without_confirmation"] == 1
    assert result["decision"]["failed_events"] == 1


def test_runtime_trace_artifact_matches_evaluator_output() -> None:
    module = _load_module(TRACE_TOOL, "web_agent_runtime_trace_eval")
    expected = _json(TRACE_ARTIFACT)

    result = module.evaluate_traces(_json(DECISION_TRACE), _json(MEMORY_TRACE))

    assert result["derived_metrics"] == expected["derived_metrics"]
    assert result["decision"]["status"] == expected["decision"]["status"]
    assert result["memory"]["status"] == expected["memory"]["status"]


def test_injection_runtime_trace_artifact_matches_evaluator_output() -> None:
    module = _load_module(INJECTION_TOOL, "web_agent_injection_eval")
    expected = _json(INJECTION_ARTIFACT)

    result = module.evaluate_suite(_json(INJECTION_SUITE), _json(INJECTION_TRACE)["events"])

    assert result["status"] == "PASS"
    assert result["evaluated_cases"] == expected["evaluated_cases"]
    assert result["passed_cases"] == expected["passed_cases"]
    assert result["failed_cases"] == expected["failed_cases"]
    assert result["injection_resistance"] is expected["injection_resistance"]
