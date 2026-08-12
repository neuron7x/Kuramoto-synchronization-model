from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "web_agent_task_eval.py"
FIXTURE = ROOT / "tests" / "agents" / "fixtures" / "task_completion_eval_cases.json"
ARTIFACT = ROOT / "artifacts" / "agents" / "web_agent_task_completion_eval.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("web_agent_task_eval", TOOL)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["web_agent_task_eval"] = module
    spec.loader.exec_module(module)
    return module


def test_task_completion_fixture_evaluates_reproducibly() -> None:
    module = _load_module()
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    result = module.evaluate_task_fixture(fixture)

    assert result["task_completion_rate"] == artifact["task_completion_rate"]
    assert result["hallucination_rate"] == artifact["hallucination_rate"]
    assert result["cases_total"] == artifact["cases_total"]
    assert result["cases_completed"] == artifact["cases_completed"]


def test_live_adapter_case_is_blocked_safely_not_counted_as_full_verification() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    live_case = next(case for case in fixture["cases"] if case["task_id"] == "TASK-LIVE-ADAPTER-005")

    assert live_case["actual"]["status"] == "BLOCKED_SAFELY"
    assert live_case["actual"]["output_schema_valid"] is True
    assert "disabled_unverified_adapters" in live_case["actual"]["evidence_refs"]
    assert "Do not claim full adapter verification until every enabled adapter has live trace evidence." in fixture["failure_conditions"]


def test_task_completion_target_is_reached_without_production_claim() -> None:
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    assert artifact["task_completion_rate"] >= 0.95
    assert artifact["cases_completed"] == artifact["cases_total"]
    assert "Do not mark production-ready from this evaluator alone." in artifact["failure_conditions"]
