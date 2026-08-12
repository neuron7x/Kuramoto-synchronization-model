#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Emit the NFI physics CI evidence summary bound to the scored commit (G7).

Issue #1228 G7 ("CI snapshot record"). ``tools/physics_score.py::ci_status``
flips ``physics_runtime_green`` only when the five required physics workflows
recorded a ``completed``/``success`` run whose ``head_sha`` equals the scored
commit (``$GITHUB_SHA`` / ``git rev-parse HEAD``). A *validator*
(``tools/physics_ci_evidence.py``) already existed, but there was no *emitter*:
``artifacts/physics_validation/ci_evidence_summary.json`` was hand-maintained
and stale-bound to an earlier PR's merge SHA. This module records each completed
required-workflow run for the scored HEAD from the real GitHub Actions run
ledger and writes the summary, so the score can move **only** on same-SHA green.

Goodhart guard. This emitter NEVER fabricates a success. It records the runs
GitHub Actions actually reports for the scored commit. Runs whose ``head_sha``
differs from the scored commit are dropped before they are written, so copying
another PR's evidence cannot strip the physics CI blocker — that is the exact
attack ``physics_score.ci_status`` (BLOCK-CI-001) guards against.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_PATH = ROOT / "artifacts" / "physics_validation" / "ci_evidence_summary.json"

SCHEMA_VERSION = "2026.06.18"

# The five workflows physics_score.ci_status() requires for physics_runtime_green.
# This set is the contract; never relax it to move the score (Module 9 discipline).
REQUIRED_PHYSICS_WORKFLOWS: tuple[str, ...] = (
    "Physics Invariants",
    "Physics Kernel Gate",
    "Physics Reliability Gate",
    "Commit Acceptor Gate",
    "Repo Integrity Gate",
)


def scored_commit_sha() -> str:
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


def fetch_runs(head_sha: str, limit: int = 200) -> list[dict[str, Any]]:
    """Return the real GitHub Actions run ledger for ``head_sha`` via ``gh``.

    Each element carries ``name``/``status``/``conclusion``/``headSha``. The
    caller is responsible for filtering — this function performs no success
    fabrication; it only surfaces what GitHub Actions reports.
    """
    if not head_sha:
        return []
    proc = subprocess.run(
        [
            "gh",
            "run",
            "list",
            "--commit",
            head_sha,
            "--limit",
            str(limit),
            "--json",
            "name,status,conclusion,headSha,workflowName,databaseId,event",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(proc.stdout or "[]")
    return payload if isinstance(payload, list) else []


def _normalise_run(run: dict[str, Any]) -> dict[str, Any]:
    """Project a raw ``gh`` run record onto the persisted evidence shape.

    ``gh`` exposes the workflow name under ``name`` (and ``workflowName``);
    ``headSha`` is camelCase. The persisted ledger uses ``head_sha`` to match
    the validator/scorer contract.
    """
    name = str(run.get("name") or run.get("workflowName") or "")
    return {
        "name": name,
        "status": str(run.get("status", "")),
        "conclusion": str(run.get("conclusion", "")),
        "head_sha": str(run.get("headSha", run.get("head_sha", ""))),
    }


def build_evidence_summary(
    runs: list[dict[str, Any]],
    head_sha: str,
    *,
    pr_gate_success: bool = False,
) -> dict[str, Any]:
    """Build the commit-bound CI evidence summary from a raw run ledger.

    Pure function (no I/O) so the same-SHA / stale-SHA behaviour is unit
    testable. Only ``completed``/``success`` runs whose ``head_sha`` equals the
    scored commit are recorded; everything else is dropped fail-closed.
    """
    bound: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in runs:
        norm = _normalise_run(raw)
        if not head_sha or norm["head_sha"] != head_sha:
            continue
        if norm["status"] != "completed" or norm["conclusion"] != "success":
            continue
        if norm["name"] in seen:
            continue
        seen.add(norm["name"])
        bound.append(norm)
    bound.sort(key=lambda item: item["name"])

    recorded_required = sorted(seen & set(REQUIRED_PHYSICS_WORKFLOWS))
    missing_required = sorted(set(REQUIRED_PHYSICS_WORKFLOWS) - seen)

    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_type": "github_actions_runtime_summary",
        "scope": "NFI GeoSync physics validation lane",
        "scored_commit_sha": head_sha,
        "required_physics_workflows": sorted(REQUIRED_PHYSICS_WORKFLOWS),
        "recorded_required_workflows": recorded_required,
        "missing_required_workflows": missing_required,
        "workflow_runs": bound,
        "release_gate": {
            "pr_gate_success": bool(pr_gate_success),
            "interpretation": (
                "Physics-specific gates recorded here can reduce the physics CI "
                "blocker, but the repository-level PR Gate must be separately "
                "green before release readiness can be claimed."
            ),
        },
        "score_implication": {
            "may_upgrade_runtime_status": not missing_required,
            "may_claim_target_interval": False,
            "may_claim_final_physics_validation": False,
        },
        "binding_note": (
            "workflow_runs carry the head_sha they executed against. The emitter "
            "(tools/physics/emit_ci_evidence.py) records only completed/success "
            "runs whose head_sha equals the scored commit (git rev-parse HEAD / "
            "$GITHUB_SHA); copied evidence from another PR carries a different "
            "head_sha and is dropped fail-closed, so it can never strip the "
            "physics CI blocker or inflate the score for unrelated code."
        ),
    }


def write_summary(summary: dict[str, Any], path: Path = EVIDENCE_PATH) -> None:
    """Persist the evidence summary deterministically (sorted keys, trailing newline)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Emit artifacts/physics_validation/ci_evidence_summary.json bound to "
            "the scored commit from the real GitHub Actions run ledger (issue "
            "#1228 G7). Never fabricates a success."
        )
    )
    parser.add_argument(
        "--pr-gate-success",
        action="store_true",
        help="Record that the repository-level PR Gate is green (separate signal).",
    )
    parser.add_argument(
        "--runs-json",
        type=Path,
        default=None,
        help=(
            "Read the run ledger from a JSON file instead of calling gh. The file "
            "must be a list of {name,status,conclusion,headSha} records. Stale "
            "(non-matching head_sha) records are still dropped fail-closed."
        ),
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Persist the summary to artifacts/physics_validation/ci_evidence_summary.json.",
    )
    args = parser.parse_args(argv)

    head_sha = scored_commit_sha()
    if args.runs_json is not None:
        raw = json.loads(args.runs_json.read_text(encoding="utf-8"))
        runs = raw if isinstance(raw, list) else []
    else:
        runs = fetch_runs(head_sha)

    summary = build_evidence_summary(runs, head_sha, pr_gate_success=args.pr_gate_success)
    if args.write:
        write_summary(summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    # Fail-closed exit: non-zero unless every required physics workflow is
    # recorded green for the scored commit. This makes the emitter a gate, not
    # a passive report — copied/stale evidence keeps the blocker (exit 1).
    return 0 if not summary["missing_required_workflows"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
