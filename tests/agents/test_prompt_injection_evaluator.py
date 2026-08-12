from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVAL_TOOL = ROOT / "tools" / "web_agent_injection_eval.py"
FIXTURE = ROOT / "tests" / "agents" / "fixtures" / "prompt_injection_cases.json"


def _load_eval_module():
    spec = importlib.util.spec_from_file_location("web_agent_injection_eval", EVAL_TOOL)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["web_agent_injection_eval"] = module
    spec.loader.exec_module(module)
    return module


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _passing_events(suite: dict) -> list[dict]:
    return [
        {
            "case_id": case["case_id"],
            "observed_classification": case["expected_classification"],
            "observed_action": case["expected_agent_action"],
            "performed_actions": [],
        }
        for case in suite["cases"]
    ]


def test_injection_evaluator_reports_no_runtime_trace_without_events() -> None:
    module = _load_eval_module()
    result = module.evaluate_suite(_fixture(), [])

    assert result["status"] == "NO_RUNTIME_TRACE"
    assert result["injection_resistance"] is False
    assert result["failed_cases"] == result["evaluated_cases"]


def test_injection_evaluator_accepts_safe_runtime_trace() -> None:
    module = _load_eval_module()
    suite = _fixture()
    result = module.evaluate_suite(suite, _passing_events(suite))

    assert result["status"] == "PASS"
    assert result["injection_resistance"] is True
    assert result["failed_cases"] == 0


def test_injection_evaluator_rejects_forbidden_action() -> None:
    module = _load_eval_module()
    suite = _fixture()
    events = _passing_events(suite)
    events[0]["performed_actions"] = [suite["cases"][0]["must_not_do"][0]]

    result = module.evaluate_suite(suite, events)

    assert result["status"] == "FAIL"
    assert result["injection_resistance"] is False
    assert result["failed_cases"] == 1
    assert result["results"][0]["failure_reasons"][0].startswith("forbidden_action:")
