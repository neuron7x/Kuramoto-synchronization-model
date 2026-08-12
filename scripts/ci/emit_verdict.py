#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Aggregate the claim-governance gates into one machine-readable VERDICT.json.

GeoSync already enforces claim hygiene through several independent CI gates
(``check_claim_boundary``, ``check_claims``, ``check_claim_maturity``,
``check_claim_artifact_graph``, ``check_invariant_count_sync``). They each
exit 0/1 and print a human summary, but there is no single artifact a release
manager or external reviewer can read to answer one question: *is the claim
surface release-ready, yes or no, and which gate blocks it?*

This is the evidence-bundle capstone: it runs those gates (reusing them as the
single source of truth — it does NOT re-implement any check), and emits a
fail-closed ``VERDICT.json`` with a per-gate result and an overall
``release_ready`` boolean. Any gate failure ⇒ ``release_ready`` false ⇒ the
script exits non-zero, so ``make evidence`` is a release gate, not a report.

Determinism: the bundle records the resolved ``git`` HEAD and a timestamp; the
timestamp is injectable (``--timestamp``) so the artifact is byte-reproducible
in tests and replayable in CI.
"""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404 - fixed argv lists, no shell, trusted repo scripts
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT: Path = REPO_ROOT / "artifacts" / "audit" / "VERDICT.json"
SCHEMA_VERSION: str = "1"


@dataclass(frozen=True)
class Gate:
    """A governance gate: a stable name and the argv that runs it."""

    name: str
    argv: tuple[str, ...]
    description: str


# The canonical claim-governance surface. ``python`` is resolved to the current
# interpreter at call time so the bundle runs under the same env as CI.
GATES: tuple[Gate, ...] = (
    Gate(
        "claim-boundary",
        ("scripts/ci/check_claim_boundary.py",),
        "Product-category boundary held over the canonical doc surface.",
    ),
    Gate(
        "claims-evidence",
        ("scripts/ci/check_claims.py",),
        "Every gated claim has a tier and a present evidence path.",
    ),
    Gate(
        "claim-maturity",
        ("scripts/ci/check_claim_maturity.py",),
        "No claim is promoted beyond its earned maturity tier.",
    ),
    Gate(
        "claim-artifact-graph",
        ("scripts/ci/check_claim_artifact_graph.py",),
        "Every claim maps to an honest proof chain (artifact + falsifier).",
    ),
    Gate(
        "invariant-count-sync",
        ("-m", "scripts.check_invariant_count_sync"),
        "Documented invariant counts match the canonical registry.",
    ),
)


@dataclass(frozen=True)
class GateOutcome:
    """The result of running one gate."""

    name: str
    command: str
    description: str
    returncode: int
    passed: bool
    summary: str


def _last_meaningful_line(text: str) -> str:
    """Return the last non-empty output line (the gate's human summary)."""
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped:
            return stripped[:500]
    return ""


def run_gate(gate: Gate, *, root: Path = REPO_ROOT) -> GateOutcome:
    """Run a single gate as a subprocess and capture its verdict.

    A non-zero exit OR a process error both map to ``passed=False`` — the
    aggregation is fail-closed: an un-runnable gate is a blocking gate, never
    a silent pass.
    """
    argv = [sys.executable, *gate.argv]
    command = " ".join(argv)
    try:
        proc = subprocess.run(  # nosec B603 - fixed argv, no shell, repo-internal scripts
            argv,
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return GateOutcome(
            name=gate.name,
            command=command,
            description=gate.description,
            returncode=-1,
            passed=False,
            summary=f"gate failed to run: {exc}"[:500],
        )
    combined = proc.stdout + ("\n" + proc.stderr if proc.stderr else "")
    return GateOutcome(
        name=gate.name,
        command=command,
        description=gate.description,
        returncode=proc.returncode,
        passed=proc.returncode == 0,
        summary=_last_meaningful_line(combined),
    )


def build_verdict(
    outcomes: Sequence[GateOutcome],
    *,
    commit: str,
    timestamp: str,
) -> dict[str, object]:
    """Assemble the verdict mapping from gate outcomes (pure, testable).

    ``release_ready`` is the AND of every gate; ``blocking_gates`` lists the
    names of the failing ones so the verdict is self-explaining.
    """
    blocking = [o.name for o in outcomes if not o.passed]
    return {
        "schema_version": SCHEMA_VERSION,
        "commit": commit,
        "generated_at": timestamp,
        "release_ready": not blocking,
        "blocking_gates": blocking,
        "gate_count": len(outcomes),
        "gates": [
            {
                "name": o.name,
                "command": o.command,
                "description": o.description,
                "returncode": o.returncode,
                "passed": o.passed,
                "summary": o.summary,
            }
            for o in outcomes
        ],
    }


def _git_head(root: Path) -> str:
    """Return the short-circuit-safe HEAD sha, or 'unknown' off a worktree."""
    try:
        proc = subprocess.run(  # nosec B603 B607 - fixed argv, no shell
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    sha = proc.stdout.strip()
    return sha if proc.returncode == 0 and sha else "unknown"


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def main(
    argv: list[str] | None = None,
    *,
    runner: Callable[[Gate], GateOutcome] = run_gate,
) -> int:
    """Run all gates, write VERDICT.json, return 0 iff release-ready."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to write VERDICT.json (default: artifacts/audit/VERDICT.json).",
    )
    parser.add_argument(
        "--timestamp",
        default=None,
        help="ISO-8601 UTC timestamp to stamp (default: now). Set for reproducible artifacts.",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="Also print the verdict JSON to stdout.",
    )
    args = parser.parse_args(argv)

    timestamp = args.timestamp or datetime.now(UTC).isoformat()
    commit = _git_head(REPO_ROOT)

    outcomes = [runner(gate) for gate in GATES]
    verdict = build_verdict(outcomes, commit=commit, timestamp=timestamp)
    _atomic_write_json(args.output, verdict)

    if args.print:
        print(json.dumps(verdict, indent=2, sort_keys=True))

    for outcome in outcomes:
        mark = "PASS" if outcome.passed else "FAIL"
        print(f"[{mark}] {outcome.name}: {outcome.summary}")

    blocking_names = [o.name for o in outcomes if not o.passed]
    if not blocking_names:
        print(f"VERDICT: release_ready=true ({len(outcomes)} gates) → {args.output}")
        return 0
    print(
        f"VERDICT: release_ready=false; blocking gates: {', '.join(blocking_names)} → {args.output}"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
