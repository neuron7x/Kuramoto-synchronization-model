#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Validate the persisted NFI physics CI evidence summary.

The evidence summary is not a release certificate. It records which CI gates
actually completed for the NFI physics lane and keeps the physics score
fail-closed while full PR-gate evidence is incomplete.

Commit binding (BLOCK-CI-001 hardening). A ``workflow_run`` counts as evidence
*for the scored commit* only when its ``head_sha`` equals ``git rev-parse HEAD``
(or ``$GITHUB_SHA`` in CI). Evidence copied from an earlier PR/branch records a
different ``head_sha`` and is therefore ignored — stale CI evidence can never
strip the physics CI blocker or inflate the score for unrelated code.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = ROOT / "artifacts" / "physics_validation" / "ci_evidence_summary.json"

REQUIRED_SUCCESS_WORKFLOWS = {
    "Physics Invariants",
    "Physics Kernel Gate",
    "Physics Reliability Gate",
    "Commit Acceptor Gate",
    "Repo Integrity Gate",
}


def current_head_sha() -> str:
    """Resolve the commit being scored: ``$GITHUB_SHA`` then ``git rev-parse HEAD``."""
    env_sha = os.environ.get("GITHUB_SHA", "").strip()
    if env_sha:
        return env_sha
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:
        return ""


def load_evidence(path: Path = EVIDENCE_PATH) -> dict[str, Any]:
    """Load the CI evidence artifact as a JSON object."""
    return json.loads(path.read_text(encoding="utf-8"))


def successful_workflows(evidence: dict[str, Any], head_sha: str) -> set[str]:
    """Workflows recorded successful AND bound to ``head_sha`` (the scored commit).

    A run with no ``head_sha`` or a ``head_sha`` that differs from the scored
    commit is treated as stale and excluded (fail-closed).
    """
    if not head_sha:
        return set()
    workflows = evidence.get("workflow_runs", [])
    return {
        str(item.get("name", ""))
        for item in workflows
        if item.get("status") == "completed"
        and item.get("conclusion") == "success"
        and str(item.get("head_sha", "")) == head_sha
    }


def validate_evidence(evidence: dict[str, Any], head_sha: str | None = None) -> dict[str, Any]:
    """Compute a fail-closed, commit-bound validation result for the CI evidence."""
    if head_sha is None:
        head_sha = current_head_sha()
    successes = successful_workflows(evidence, head_sha)
    missing = sorted(REQUIRED_SUCCESS_WORKFLOWS - successes)
    release = evidence.get("release_gate", {})
    pr_gate_success = bool(release.get("pr_gate_success"))
    all_required_physics_gates_green = not missing
    status = "PHYSICS_CI_PARTIAL_PASS"
    blockers: list[str] = []

    recorded = evidence.get("workflow_runs", [])
    sha_bound = [w for w in recorded if str(w.get("head_sha", "")) == head_sha]
    if not head_sha:
        blockers.append("head_sha_unresolved")
    if recorded and not sha_bound:
        blockers.append("ci_evidence_not_bound_to_scored_commit")

    if missing:
        status = "PHYSICS_CI_INCOMPLETE"
        blockers.append("missing_required_physics_workflows")
    if not pr_gate_success:
        blockers.append("full_pr_gate_not_green")
    return {
        "status": status,
        "scored_commit_sha": head_sha,
        "required_success_workflows": sorted(REQUIRED_SUCCESS_WORKFLOWS),
        "successful_required_workflows": sorted(REQUIRED_SUCCESS_WORKFLOWS & successes),
        "missing_required_workflows": missing,
        "all_required_physics_gates_green": all_required_physics_gates_green,
        "full_pr_gate_green": pr_gate_success,
        "blockers": blockers,
    }


def main() -> int:
    evidence = load_evidence()
    result = validate_evidence(evidence)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["all_required_physics_gates_green"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
