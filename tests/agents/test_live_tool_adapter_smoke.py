from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "artifacts" / "agents" / "live_tool_adapter_smoke.json"


def test_live_tool_adapter_smoke_is_partial_and_fail_closed() -> None:
    smoke = json.loads(SMOKE.read_text(encoding="utf-8"))

    assert smoke["status"] == "PARTIAL_LIVE_GITHUB_ADAPTER_VERIFIED_NOT_FULL_AGENT_RUNTIME"
    assert smoke["coverage"]["github_adapter_subset_verified"] is True
    assert smoke["coverage"]["full_live_tool_adapter_verification"] is False
    assert smoke["coverage"]["web_search_adapter_verified"] is False
    assert smoke["coverage"]["code_exec_adapter_verified"] is False


def test_live_tool_adapter_smoke_records_successful_connector_actions() -> None:
    smoke = json.loads(SMOKE.read_text(encoding="utf-8"))
    checks = smoke["live_adapter_checks"]

    assert len(checks) >= 6
    assert all(check["result"].startswith("PASS") for check in checks)
    assert any(check["adapter"] == "github_update_pull_request" for check in checks)
    assert any(check["adapter"] == "github_fetch_commit_workflow_runs" for check in checks)
