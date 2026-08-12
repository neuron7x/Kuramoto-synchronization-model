from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VERDICT = ROOT / "artifacts" / "agents" / "web_agent_readiness_verdict.json"
DOC = ROOT / "docs" / "agents" / "web_agent_readiness_verdict.md"
BASELINE = ROOT / "artifacts" / "agents" / "web_agent_baseline_score.json"


def test_readiness_verdict_remains_fail_closed() -> None:
    verdict = json.loads(VERDICT.read_text(encoding="utf-8"))
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))

    assert verdict["status"] == "FAIL_NOT_PRODUCTION_READY"
    assert verdict["score"] == baseline["score"]["value"]
    assert verdict["score_status"] == baseline["score"]["status"]
    assert verdict["pass_conditions"]["score_at_or_above_90"] is True
    assert verdict["pass_conditions"]["task_completion_at_or_above_0_95"] is True
    assert verdict["pass_conditions"]["context_efficiency_at_or_below_1_2"] is True
    assert verdict["pass_conditions"]["live_runtime_trace"] is True
    assert verdict["pass_conditions"]["unverified_adapters_disabled"] is True
    assert verdict["pass_conditions"]["live_tool_adapter_verification"] is False
    assert "production_ready" in verdict["forbidden_claims"]
    assert "full_live_verified" in verdict["forbidden_claims"]


def test_readiness_doc_matches_machine_verdict() -> None:
    verdict = json.loads(VERDICT.read_text(encoding="utf-8"))
    text = DOC.read_text(encoding="utf-8")

    assert verdict["status"] in text
    assert "score = 98.19 / 100" in text
    for blocker in verdict["blocking_reasons"]:
        assert blocker in text
    for mitigated in verdict["mitigated_critical_risks"]:
        assert mitigated in text
