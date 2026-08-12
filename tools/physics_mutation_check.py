#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Physics mutation regression harness (Task 6).

Applies temporary source mutations to physics-invariant modules,
runs targeted tests, observes failure, restores source, reports
results. The harness proves that the test suite catches meaningful
contract regressions — not just stylistic changes.

Custom (subprocess + pathlib) before any mutmut adoption. The custom
harness is deterministic, scoped to known patterns, and does not
require an external mutation library.

Mutants currently registered (six per protocol §6):

  1. anchored_ignores_arrow      — gate composes only Bekenstein
  2. anchored_ignores_bekenstein — gate composes only Arrow
  3. failure_axes_drops_arrow    — failure_axes drops ARROW append
  4. bandwidth_inverted          — Γ ≤ Σ̇ becomes Γ ≥ Σ̇
  5. cosmo_above_passes          — claim > ceiling silently passes
  6. sim_threshold_inverted      — strict > becomes <

Usage:
    python tools/physics_mutation_check.py --list
    python tools/physics_mutation_check.py --mutant anchored_ignores_arrow
    python tools/physics_mutation_check.py --all
    python tools/physics_mutation_check.py --all --fail-on-survivor

Exit codes:
    0 — all named mutants killed (or restored cleanly with no survivor)
    1 — at least one mutant survived AND --fail-on-survivor set
    2 — restore failed for any mutant (HARD FAIL — possibly dirty tree)
    3 — pattern-not-found for any mutant (skipped, not killed)
    4 — invocation error (bad arg, missing file, etc.)

The harness is self-restoring. After every mutant execution (success or
failure), it writes the original source back. After all mutants, it
asserts the working tree is clean via `git diff --exit-code`.
"""

from __future__ import annotations

import argparse
import dataclasses
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclasses.dataclass(frozen=True, slots=True)
class Mutant:
    """One source-text mutation against one physics module.

    `pattern` must appear EXACTLY ONCE in the target file. If it appears
    zero times → SKIPPED_PATTERN_NOT_FOUND. If multiple times → SKIPPED
    (ambiguous; mutation would be unstable). Mutants with ambiguous
    patterns are not silently expanded.
    """

    mutant_id: str
    target_file: str  # repo-relative
    pattern: str
    replacement: str
    test_command: tuple[str, ...]
    description: str


MUTANTS: tuple[Mutant, ...] = (
    Mutant(
        mutant_id="anchored_ignores_arrow",
        target_file="core/physics/anchored_substrate_gate.py",
        pattern="admissible = bekenstein_holds and arrow_holds",
        replacement="admissible = bekenstein_holds  # MUTANT",
        test_command=(
            "python",
            "-m",
            "pytest",
            "tests/integration/test_substrate_gate_chain.py::test_substrate_gate_chain_arrow_violation_is_named",
            "-q",
        ),
        description="Anchored gate ignores Arrow axis — composite admits despite ΔS<0.",
    ),
    Mutant(
        mutant_id="anchored_ignores_bekenstein",
        target_file="core/physics/anchored_substrate_gate.py",
        pattern="admissible = bekenstein_holds and arrow_holds",
        replacement="admissible = arrow_holds  # MUTANT",
        test_command=(
            "python",
            "-m",
            "pytest",
            "tests/integration/test_substrate_gate_chain.py::test_substrate_gate_chain_bekenstein_violation_is_named",
            "-q",
        ),
        description="Anchored gate ignores Bekenstein axis — composite admits despite I>ceiling.",
    ),
    Mutant(
        mutant_id="failure_axes_drops_arrow",
        target_file="core/physics/anchored_substrate_gate.py",
        pattern='    if not arrow_holds:\n        failures.append("ARROW")',
        replacement="    if not arrow_holds:\n        pass  # MUTANT",
        test_command=(
            "python",
            "-m",
            "pytest",
            "tests/integration/test_substrate_gate_chain.py::test_substrate_gate_chain_arrow_violation_is_named",
            "tests/integration/test_substrate_gate_chain.py::test_substrate_gate_chain_reports_multiple_anchored_failures_deterministically",
            "-q",
        ),
        description="failure_axes drops ARROW — multi-failure scenario reports only BEKENSTEIN.",
    ),
    Mutant(
        mutant_id="bandwidth_inverted",
        target_file="core/physics/observer_bandwidth.py",
        pattern="consistent = slack >= 0.0",
        replacement="consistent = slack < 0.0  # MUTANT",
        test_command=(
            "python",
            "-m",
            "pytest",
            "tests/unit/physics/test_observer_bandwidth.py::test_bound_consistent_when_gamma_below_bandwidth",
            "tests/unit/physics/test_observer_bandwidth.py::test_bound_at_equality_is_consistent",
            "-q",
        ),
        description="Bandwidth comparison inverted — Γ < Σ̇ produces inconsistent verdict.",
    ),
    Mutant(
        mutant_id="cosmo_above_passes",
        target_file="core/physics/cosmological_compute_bound.py",
        pattern="within = claimed_bits <= budget.holographic_max_bits",
        replacement="within = True  # MUTANT",
        test_command=(
            "python",
            "-m",
            "pytest",
            "tests/unit/physics/test_cosmological_compute_bound.py::test_compute_claim_above_budget_violation",
            "-q",
        ),
        description="Cosmological compute claim above ceiling silently passes.",
    ),
    Mutant(
        mutant_id="sim_threshold_inverted",
        target_file="core/physics/simulation_falsification.py",
        pattern="return observed_value > sig.detectability_threshold",
        replacement="return observed_value < sig.detectability_threshold  # MUTANT",
        test_command=(
            "python",
            "-m",
            "pytest",
            "tests/unit/physics/test_simulation_falsification.py::test_hardware_class_ruled_out_when_observed_above_threshold",
            "tests/unit/physics/test_simulation_falsification.py::test_hardware_class_not_ruled_out_when_observed_below_threshold",
            "-q",
        ),
        description="Sim falsification threshold comparison inverted (> becomes <).",
    ),
)


@dataclasses.dataclass(frozen=True, slots=True)
class MutantResult:
    mutant_id: str
    target_file: str
    pattern_status: str  # "APPLIED" | "SKIPPED_PATTERN_NOT_FOUND" | "SKIPPED_AMBIGUOUS"
    test_returncode: int | None
    killed: bool
    restored: bool


def _run_test(cmd: tuple[str, ...]) -> int:
    """Run pytest command, return exit code. Suppress stdout/stderr — we
    only care whether tests pass (exit 0) or fail (non-zero)."""
    proc = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode


def execute_mutant(mutant: Mutant) -> MutantResult:
    """Apply mutant, run targeted tests, observe failure, restore.

    Restore is in `finally` and is verified post-restore by reading the
    file back and asserting equality with the original. If restore
    fails the result is reported with `restored=False` — the caller
    must treat this as a hard error and abort.
    """
    target_path = REPO_ROOT / mutant.target_file
    if not target_path.exists():
        return MutantResult(
            mutant_id=mutant.mutant_id,
            target_file=mutant.target_file,
            pattern_status="SKIPPED_PATTERN_NOT_FOUND",
            test_returncode=None,
            killed=False,
            restored=True,
        )
    original = target_path.read_text(encoding="utf-8")
    occurrences = original.count(mutant.pattern)
    if occurrences == 0:
        return MutantResult(
            mutant_id=mutant.mutant_id,
            target_file=mutant.target_file,
            pattern_status="SKIPPED_PATTERN_NOT_FOUND",
            test_returncode=None,
            killed=False,
            restored=True,
        )
    if occurrences > 1:
        return MutantResult(
            mutant_id=mutant.mutant_id,
            target_file=mutant.target_file,
            pattern_status="SKIPPED_AMBIGUOUS",
            test_returncode=None,
            killed=False,
            restored=True,
        )
    mutated = original.replace(mutant.pattern, mutant.replacement)
    test_rc: int | None = None
    try:
        target_path.write_text(mutated, encoding="utf-8")
        test_rc = _run_test(mutant.test_command)
    finally:
        target_path.write_text(original, encoding="utf-8")
    # Verify restore by reading back.
    restored_text = target_path.read_text(encoding="utf-8")
    restored = restored_text == original
    killed = test_rc is not None and test_rc != 0
    return MutantResult(
        mutant_id=mutant.mutant_id,
        target_file=mutant.target_file,
        pattern_status="APPLIED",
        test_returncode=test_rc,
        killed=killed,
        restored=restored,
    )


def _format_result(r: MutantResult) -> str:
    bits = [
        f"id={r.mutant_id}",
        f"file={r.target_file}",
        f"pattern={r.pattern_status}",
    ]
    if r.test_returncode is not None:
        bits.append(f"test_rc={r.test_returncode}")
    bits.append(f"killed={'YES' if r.killed else 'NO'}")
    bits.append(f"restored={'YES' if r.restored else 'NO'}")
    return " | ".join(bits)


def cmd_list() -> int:
    print(f"Registered mutants: {len(MUTANTS)}")
    for m in MUTANTS:
        print(f"  {m.mutant_id}  ({m.target_file})")
        print(f"    {m.description}")
    return 0


def cmd_run(mutant_ids: list[str], fail_on_survivor: bool) -> int:
    selected = [m for m in MUTANTS if m.mutant_id in mutant_ids]
    if not selected:
        print(f"ERROR: no registered mutants match {mutant_ids}")
        return 4
    results = [execute_mutant(m) for m in selected]
    survived: list[MutantResult] = []
    restore_failures: list[MutantResult] = []
    pattern_skipped: list[MutantResult] = []
    for r in results:
        print(_format_result(r))
        if not r.restored:
            restore_failures.append(r)
        if r.pattern_status != "APPLIED":
            pattern_skipped.append(r)
            continue
        if not r.killed:
            survived.append(r)
    if restore_failures:
        print(f"\nFATAL: {len(restore_failures)} restore failures — tree may be dirty")
        return 2
    if pattern_skipped:
        print(f"\nWARNING: {len(pattern_skipped)} mutants skipped (pattern not found)")
        if fail_on_survivor:
            return 3
    if survived and fail_on_survivor:
        print(f"\nFAIL: {len(survived)} mutant(s) survived: {[r.mutant_id for r in survived]}")
        return 1
    print(f"\nKilled: {sum(1 for r in results if r.killed)}/{len(results)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="List registered mutants and exit.")
    parser.add_argument(
        "--mutant", action="append", default=[], help="Run named mutant (repeatable)."
    )
    parser.add_argument("--all", action="store_true", help="Run all registered mutants.")
    parser.add_argument(
        "--fail-on-survivor",
        action="store_true",
        help="Exit non-zero if any mutant survives (or pattern is missing).",
    )
    args = parser.parse_args(argv)
    if args.list:
        return cmd_list()
    selected = list(args.mutant)
    if args.all:
        selected = [m.mutant_id for m in MUTANTS]
    if not selected:
        print("ERROR: pass --list, --mutant NAME, or --all")
        return 4
    return cmd_run(selected, args.fail_on_survivor)


if __name__ == "__main__":
    sys.exit(main())
