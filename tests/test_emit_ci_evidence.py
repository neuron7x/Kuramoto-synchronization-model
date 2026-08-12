# SPDX-License-Identifier: MIT
"""Acceptance + falsifier tests for the G7 CI-evidence emitter (issue #1228).

The emitter (``tools/physics/emit_ci_evidence.py``) records the real GitHub
Actions runs for the *scored* commit into ``ci_evidence_summary.json`` so that
``tools/physics_score.py::ci_status`` can legitimately flip
``physics_runtime_green``.

Contract under test (S_total values are *computed*, never hand-edited):

* same-SHA green evidence  -> ``physics_runtime_green is True`` and S_total rises
  to the runtime-green tier 81.5 (acceptance).
* stale-SHA evidence       -> ``physics_runtime_green is False`` and S_total
  stays at the fail-closed tier 78.0 (falsifier: copying another PR's evidence
  must NOT raise the score — the exact BLOCK-CI-001 attack).

The two tiers are derived in tools/physics_score.py: every ``physics_ci``-gated
metric (numerical/invariant/falsifiability/baseline/UQ/reproducibility/
interface) sits at its lower tier when no same-SHA CI evidence exists. The
held-back delta between the tiers is exactly the legitimate G7 credit.

The emitter itself never fabricates a success; these tests feed it synthetic
*run ledgers* (the same shape ``gh run list --json`` returns) and assert the
fail-closed binding holds end to end through the scorer.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]

MATCHING_SHA = "a" * 40
STALE_SHA = "b" * 40

REQUIRED = (
    "Physics Invariants",
    "Physics Kernel Gate",
    "Physics Reliability Gate",
    "Commit Acceptor Gate",
    "Repo Integrity Gate",
)

# Computed tiers from tools/physics_score.py (NOT hand-set credit):
#   physics_runtime_green True  -> 81.5
#   physics_runtime_green False -> 78.0
RUNTIME_GREEN_SCORE = 81.5
RUNTIME_BLOCKED_SCORE = 78.0


def _load(module_name: str, rel_path: str) -> Any:
    path = ROOT / rel_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_emitter() -> Any:
    return _load("emit_ci_evidence", "tools/physics/emit_ci_evidence.py")


def _load_score() -> Any:
    return _load("physics_score", "tools/physics_score.py")


def _green_run_ledger(head_sha: str) -> list[dict[str, str]]:
    """A raw ``gh run list`` ledger: all five required workflows green at head_sha."""
    return [
        {
            "name": name,
            "status": "completed",
            "conclusion": "success",
            "headSha": head_sha,
        }
        for name in REQUIRED
    ]


def test_emitter_records_only_same_sha_green_runs() -> None:
    emitter = _load_emitter()
    # Ledger mixes scored-commit green runs with stale-SHA and failed runs.
    ledger = _green_run_ledger(MATCHING_SHA) + [
        {
            "name": "Physics Invariants",
            "status": "completed",
            "conclusion": "success",
            "headSha": STALE_SHA,  # stale: must be dropped
        },
        {
            "name": "Repo Integrity Gate",
            "status": "completed",
            "conclusion": "failure",
            "headSha": MATCHING_SHA,  # failed: must not double-count as success
        },
    ]
    summary = emitter.build_evidence_summary(ledger, MATCHING_SHA)
    recorded = {run["name"] for run in summary["workflow_runs"]}
    assert recorded == set(REQUIRED)
    assert summary["missing_required_workflows"] == []
    assert all(run["head_sha"] == MATCHING_SHA for run in summary["workflow_runs"])


def test_emitter_drops_evidence_bound_to_a_different_commit() -> None:
    emitter = _load_emitter()
    # All runs are green but bound to STALE_SHA; scored commit is MATCHING_SHA.
    ledger = _green_run_ledger(STALE_SHA)
    summary = emitter.build_evidence_summary(ledger, MATCHING_SHA)
    assert summary["workflow_runs"] == []
    assert sorted(summary["missing_required_workflows"]) == sorted(REQUIRED)
    assert summary["score_implication"]["may_upgrade_runtime_status"] is False


def _build_score_with_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    summary: dict[str, Any],
    scored_sha: str,
) -> dict[str, Any]:
    """Run physics_score.build_score() against a fixture evidence file + scored SHA.

    Redirects the scorer's evidence reader and SHA resolver to the fixture so no
    real artifact or git state is mutated.
    """
    score = _load_score()
    evidence_file = tmp_path / "ci_evidence_summary.json"
    evidence_file.write_text(json.dumps(summary), encoding="utf-8")

    def _fixture_json_file(path: str) -> dict[str, Any]:
        if path.endswith("ci_evidence_summary.json"):
            return json.loads(evidence_file.read_text(encoding="utf-8"))
        # Delegate every other carrier to the real reader.
        return _orig_json_file(path)

    _orig_json_file = score.json_file
    monkeypatch.setattr(score, "json_file", _fixture_json_file)
    monkeypatch.setattr(score, "_scored_commit_sha", lambda: scored_sha)
    return score.build_score()


def test_matching_sha_flips_runtime_green_and_raises_score(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # ACCEPTANCE: same-SHA green evidence -> physics_runtime_green True, score up.
    emitter = _load_emitter()
    summary = emitter.build_evidence_summary(_green_run_ledger(MATCHING_SHA), MATCHING_SHA)

    result = _build_score_with_evidence(monkeypatch, tmp_path, summary, MATCHING_SHA)

    runtime_block = [b for b in result["blockers"] if b["id"] == "BLOCK-CI-001"]
    assert runtime_block == [], "matching-SHA green evidence must clear BLOCK-CI-001"
    assert result["S_total"] == RUNTIME_GREEN_SCORE
    assert result["S_total"] > RUNTIME_BLOCKED_SCORE, "score must rise off the blocked tier"


def test_stale_sha_keeps_runtime_blocked_and_holds_score(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # FALSIFIER: copy another PR's green evidence (STALE_SHA) but score MATCHING_SHA.
    emitter = _load_emitter()
    stale_summary = emitter.build_evidence_summary(_green_run_ledger(STALE_SHA), STALE_SHA)

    result = _build_score_with_evidence(monkeypatch, tmp_path, stale_summary, MATCHING_SHA)

    runtime_block = [b for b in result["blockers"] if b["id"] == "BLOCK-CI-001"]
    assert runtime_block, "stale-SHA evidence must keep the BLOCK-CI-001 physics blocker"
    assert result["S_total"] == RUNTIME_BLOCKED_SCORE, "copied evidence must NOT raise the score"


def test_emitter_writes_deterministic_artifact(tmp_path: Path) -> None:
    emitter = _load_emitter()
    summary = emitter.build_evidence_summary(_green_run_ledger(MATCHING_SHA), MATCHING_SHA)
    out = tmp_path / "ci_evidence_summary.json"
    emitter.write_summary(summary, path=out)
    emitter.write_summary(summary, path=out)  # idempotent
    reread = json.loads(out.read_text(encoding="utf-8"))
    assert reread == summary
    assert out.read_text(encoding="utf-8").endswith("\n")
