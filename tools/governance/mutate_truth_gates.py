# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""WP keystone — mutation testing for truth gates.

A green gate is not a proven gate. This harness injects a *named lie* into each
truth-gate's source (the exact failure mode the gate exists to catch) and asserts
the gate's own guard test FAILS — i.e. the mutant is killed. A surviving mutant
means the test suite does not actually exercise that gate logic: the gate is
decorative there, and the harness fails closed.

Each mutation's ``find`` string must occur EXACTLY ONCE in the target file. If it
occurs zero or many times the anchor is stale (the gate was refactored) and the
harness fails closed — a mutation can never silently degrade into a no-op.

Scope: gates already on ``main``. The release-scorecard gate (PR #1129) is added
once it lands; the harness names its own scope rather than implying full coverage.

Run::

    python tools/governance/mutate_truth_gates.py
    python tools/governance/mutate_truth_gates.py --json
    python tools/governance/mutate_truth_gates.py --list

Exit 0 iff every named mutant is killed; non-zero on any survivor or stale anchor.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Mutation:
    id: str
    file: str
    find: str
    replace: str
    killing_test: str  # pytest node id that must fail when the lie is injected
    lie: str


@dataclass(frozen=True)
class MutationResult:
    mutation_id: str
    killed: bool
    stale: bool
    detail: str


MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        id="collision_never_detected",
        file="tools/governance/check_pr_lane_collision.py",
        find="collide = bool(shared_critical) or (bool(shared_tokens) and bool(shared_files))",
        replace="collide = False  # MUTANT: collisions never flagged",
        killing_test="tests/governance/test_pr_lane_collision.py::test_real_task2_pair_is_flagged",
        lie="lane-collision detection disabled (two duplicate PRs slip through)",
    ),
    Mutation(
        id="reliability_phantom_invariant_allowed",
        file="tools/physics/check_physics_reliability.py",
        find="            if inv not in present:",
        replace="            if inv not in present and False:  # MUTANT: phantom INV link allowed",
        killing_test=(
            "tests/physics/test_physics_reliability_contract.py"
            "::test_phantom_invariant_is_rejected_by_checker"
        ),
        lie="a failure_mode may cite an invariant the code does not carry",
    ),
    Mutation(
        id="dependency_floor_bypass_undetected",
        file="tools/security/check_dependency_manifest_consistency.py",
        find="        if required is not None and declared < required:",
        replace="        if required is not None and False:  # MUTANT: floor bypass undetected",
        killing_test=(
            "tests/security/test_dependency_manifest_consistency.py::test_checker_flags_floor_below_policy"
        ),
        lie="a manifest floor below the security policy is not flagged",
    ),
    Mutation(
        id="scorecard_partial_marked_ready",
        file="tools/release/check_physics_release_scorecard.py",
        find="    if claimed_ready and blocking:",
        replace="    if claimed_ready and blocking and False:  # MUTANT: PARTIAL marked READY",
        killing_test=(
            "tests/release/test_physics_release_scorecard.py::test_partial_claimed_ready_fails_closed"
        ),
        lie="a release marked ready while a required dimension is below CI_VERIFIED",
    ),
)


def run_one(m: Mutation, repo_root: Path) -> MutationResult:
    """Inject the mutation, run its killing test, restore the file."""
    path = repo_root / m.file
    original = path.read_text(encoding="utf-8")
    occurrences = original.count(m.find)
    if occurrences != 1:
        return MutationResult(
            m.id,
            killed=False,
            stale=True,
            detail=f"anchor found {occurrences}x (expected 1) — stale mutation, update it",
        )
    try:
        path.write_text(original.replace(m.find, m.replace), encoding="utf-8")
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                m.killing_test,
                "--noconftest",
                "-p",
                "no:cacheprovider",
                "-q",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            env={"PYTHONPATH": str(repo_root), "PATH": _path_env()},
        )
        killed = proc.returncode != 0
        detail = (
            "guard test failed → mutant killed" if killed else "guard test PASSED → mutant SURVIVED"
        )
    finally:
        path.write_text(original, encoding="utf-8")
        if path.read_text(encoding="utf-8") != original:  # pragma: no cover - safety
            raise RuntimeError(f"failed to restore {m.file} after mutation")
    return MutationResult(m.id, killed=killed, stale=False, detail=detail)


def _path_env() -> str:
    import os

    return os.environ.get("PATH", "")


def run_all(repo_root: Path = REPO_ROOT) -> list[MutationResult]:
    return [run_one(m, repo_root) for m in MUTATIONS]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--list", action="store_true", help="list mutations and exit")
    args = parser.parse_args(argv)

    if args.list:
        for m in MUTATIONS:
            print(f"{m.id}: {m.lie}\n    file={m.file}\n    kill={m.killing_test}")
        return 0

    results = run_all()
    killed = sum(1 for r in results if r.killed)
    survived = [r for r in results if not r.killed and not r.stale]
    stale = [r for r in results if r.stale]
    score = killed / len(results) if results else 0.0

    if args.json:
        print(
            json.dumps(
                {
                    "total": len(results),
                    "killed": killed,
                    "survived": [r.mutation_id for r in survived],
                    "stale": [r.mutation_id for r in stale],
                    "mutation_score": round(score, 4),
                    "passed": not survived and not stale,
                    "results": [
                        {
                            "id": r.mutation_id,
                            "killed": r.killed,
                            "stale": r.stale,
                            "detail": r.detail,
                        }
                        for r in results
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print("=" * 64)
        print("Truth-Gate Mutation Harness")
        print("=" * 64)
        for r in results:
            mark = "KILLED" if r.killed else ("STALE" if r.stale else "SURVIVED")
            print(f"  [{mark:8}] {r.mutation_id}: {r.detail}")
        print(f"\nMutation score: {killed}/{len(results)} = {score:.0%}")
        if survived or stale:
            print("\nFAIL — a decorative gate or stale anchor was found.")
        else:
            print("\nEvery named lie is killed by its guard. PASS")
    return 0 if (not survived and not stale) else 1


if __name__ == "__main__":
    sys.exit(main())
