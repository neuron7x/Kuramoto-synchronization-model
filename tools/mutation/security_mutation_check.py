"""Security / calibration-layer mutation kill harness.

Companion to `tools/physics_mutation_check.py`. The physics harness owns
the physics-invariant mutants (Arrow / Bekenstein / failure_axes / etc.).
This harness owns the mutants that prove the calibration layer's own
gates fail closed when their core logic is broken.

Mutants registered:

  4. dep_policy_accepts_torch_drift
       Mutates `tools/deps/validate_dependency_truth.py` to accept the
       F01 case (requirements.txt torch>=2.1.0 vs pyproject torch>=2.11.0).
       Expected killer:
         tests/unit/governance/test_dependency_floor_alignment.py::test_torch_floor_is_strict
         tests/deps/test_validate_dependency_truth.py::test_repo_has_no_torch_drift
       Pattern: replace the comparison so D1 detection no longer fires
       on torch.

  5. dep_policy_accepts_strawberry_below_fix
       Same idea for strawberry-graphql / 0.312.3.
       Expected killer:
         tests/unit/governance/test_dependency_floor_alignment.py::test_strawberry_floor_is_strict
         tests/deps/test_validate_dependency_truth.py::test_repo_has_no_strawberry_drift

  6. evidence_validator_allows_scanner_to_imply_exploit
       Mutates `.claude/evidence/validate_evidence.py` to accept
       SCANNER_OUTPUT as supporting EXPLOIT_PATH_CONFIRMED.
       Expected killer:
         tests/unit/evidence/test_validate_evidence.py::test_inject_scanner_reachability_refused

  7. claim_ledger_allows_fact_with_no_falsifier
       Mutates `.claude/claims/validate_claims.py` to remove the
       NO_FALSIFIER rule.
       Expected killer:
         tests/unit/claims/test_validate_claims.py::test_inject_no_falsifier_fails

Usage:
    python tools/mutation/security_mutation_check.py --list
    python tools/mutation/security_mutation_check.py --mutant <id>
    python tools/mutation/security_mutation_check.py --all
    python tools/mutation/security_mutation_check.py --all --fail-on-survivor

The harness mirrors the physics harness shape: each mutant is a
text-substitution patch + an expected killer test. After every run,
the source file is restored, then `git diff --exit-code` is asserted.
"""

from __future__ import annotations

import argparse
import dataclasses
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclasses.dataclass(frozen=True)
class Mutant:
    mutant_id: str
    target_file: str
    description: str
    pattern: str
    replacement: str
    killer_test: str
    replace_all: bool = False


MUTANTS: tuple[Mutant, ...] = (
    Mutant(
        mutant_id="dep_policy_accepts_torch_drift",
        target_file="tools/deps/validate_dependency_truth.py",
        description=(
            "validate_dependency_truth treats requirements.txt floor below "
            "pyproject as fine — F01 regression slips past the gate."
        ),
        pattern="if _parse_version(req[name]) < _parse_version(pyp[name]):",
        replacement="if False and _parse_version(req[name]) < _parse_version(pyp[name]):",
        killer_test=(
            "tests/deps/test_validate_dependency_truth.py::"
            "test_d1_detects_pyproject_above_requirements"
        ),
    ),
    Mutant(
        mutant_id="dep_policy_accepts_strawberry_below_fix",
        target_file="tools/deps/validate_dependency_truth.py",
        description=(
            "validate_dependency_truth ignores lockfile pins below the "
            "manifest floor — F03 regression slips past the gate."
        ),
        pattern="if _parse_version(version) < _parse_version(floor):",
        replacement="if False and _parse_version(version) < _parse_version(floor):",
        killer_test=(
            "tests/deps/test_validate_dependency_truth.py::test_d2_detects_lock_below_floor"
        ),
    ),
    Mutant(
        mutant_id="evidence_validator_allows_scanner_to_imply_exploit",
        target_file=".claude/evidence/validate_evidence.py",
        description=(
            "Evidence matrix validator drops BOTH OVERCLAIM_REFUSED checks, "
            "so SCANNER_OUTPUT can falsely support RUNTIME_REACHABILITY / "
            "EXPLOIT_PATH_CONFIRMED."
        ),
        # The two `if not ev_set & supporting:` lines (per-category at L266
        # and cross-category at L302) BOTH guard the same overclaim. Either
        # alone catches the bad case, so the mutation must drop both.
        pattern="if not ev_set & supporting:",
        replacement="if False and not ev_set & supporting:",
        replace_all=True,
        killer_test=(
            "tests/unit/evidence/test_validate_evidence.py::"
            "test_inject_scanner_reachability_refused"
        ),
    ),
    Mutant(
        mutant_id="claim_ledger_allows_fact_with_no_falsifier",
        target_file=".claude/claims/validate_claims.py",
        description=(
            "Claim validator removes the NO_FALSIFIER rule — a FACT-tier "
            "claim with no falsifier slips past the gate."
        ),
        pattern="if not falsifier:",
        replacement="if False and not falsifier:",
        killer_test=("tests/unit/claims/test_validate_claims.py::test_inject_no_falsifier_fails"),
    ),
)


# Exit codes mirror the physics harness.
EXIT_OK = 0
EXIT_SURVIVOR = 1
EXIT_RESTORE_FAILED = 2
EXIT_PATTERN_NOT_FOUND = 3
EXIT_INVOCATION = 4


def _list(argv_unused: object) -> int:
    print(f"Registered mutants: {len(MUTANTS)}")
    for m in MUTANTS:
        print(f"  {m.mutant_id}  ({m.target_file})")
        print(f"    {m.description}")
    return EXIT_OK


def _apply(
    target: Path,
    pattern: str,
    replacement: str,
    replace_all: bool = False,
) -> tuple[bool, bytes | None]:
    """Apply the mutation in-place. Returns (applied, original_bytes).

    The original byte content is returned so the caller can restore it
    deterministically — independent of git HEAD state on CI runners
    (PR-merge commits, detached HEADs, autocrlf settings).
    """
    original = target.read_bytes()
    text = original.decode("utf-8")
    if pattern not in text:
        return False, original
    count = -1 if replace_all else 1
    target.write_text(text.replace(pattern, replacement, count), encoding="utf-8")
    return True, original


def _restore(target: Path, original: bytes | None) -> bool:
    """Restore the file from the in-memory original captured by _apply.

    Falls back to ``git checkout HEAD -- <path>`` if no original is
    supplied. Returns True if the on-disk bytes match the original
    afterwards.
    """
    if original is not None:
        target.write_bytes(original)
        return target.read_bytes() == original

    subprocess.run(
        ["git", "checkout", "HEAD", "--", str(target)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
    )
    diff = subprocess.run(
        ["git", "diff", "--exit-code", "--", str(target)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
    )
    return diff.returncode == 0


def _run_test(test_id: str) -> int:
    """Run the killer test. Return pytest's exit code."""
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", test_id],
        cwd=REPO_ROOT,
        check=False,
    ).returncode


def _execute(mutant: Mutant) -> dict[str, str]:
    """Run a single mutant. Returns a result dict.

    status:  KILLED / SURVIVED / NOT_FOUND / RESTORE_FAILED
    """
    target = REPO_ROOT / mutant.target_file
    if not target.exists():
        return {"status": "NOT_FOUND", "detail": f"target file missing: {target}"}

    applied, original = _apply(target, mutant.pattern, mutant.replacement, mutant.replace_all)
    if not applied:
        # Pattern absent — file untouched. Verify the bytes still match.
        if original is not None and target.read_bytes() != original:
            return {"status": "RESTORE_FAILED", "detail": str(target)}
        return {"status": "NOT_FOUND", "detail": "pattern not found"}

    test_rc = _run_test(mutant.killer_test)

    if not _restore(target, original):
        return {"status": "RESTORE_FAILED", "detail": str(target)}

    if test_rc != 0:
        return {"status": "KILLED", "detail": f"killer test exit {test_rc}"}
    return {"status": "SURVIVED", "detail": "killer test passed despite mutation"}


def _all(args: argparse.Namespace) -> int:
    results: list[tuple[str, str, str]] = []
    for m in MUTANTS:
        r = _execute(m)
        results.append((m.mutant_id, r["status"], r["detail"]))
        print(f"[{r['status']:>16}] {m.mutant_id}  ({r['detail']})")
    if not _git_clean():
        print("HARD FAIL: working tree dirty after mutation run", file=sys.stderr)
        return EXIT_RESTORE_FAILED
    if any(s == "RESTORE_FAILED" for _, s, _ in results):
        return EXIT_RESTORE_FAILED
    if any(s == "NOT_FOUND" for _, s, _ in results):
        return EXIT_PATTERN_NOT_FOUND
    if args.fail_on_survivor and any(s == "SURVIVED" for _, s, _ in results):
        return EXIT_SURVIVOR
    return EXIT_OK


def _one(args: argparse.Namespace) -> int:
    target_id = args.mutant
    for m in MUTANTS:
        if m.mutant_id == target_id:
            r = _execute(m)
            print(f"[{r['status']}] {m.mutant_id}  ({r['detail']})")
            if not _git_clean():
                return EXIT_RESTORE_FAILED
            if r["status"] == "RESTORE_FAILED":
                return EXIT_RESTORE_FAILED
            if r["status"] == "NOT_FOUND":
                return EXIT_PATTERN_NOT_FOUND
            if r["status"] == "SURVIVED":
                return EXIT_SURVIVOR if args.fail_on_survivor else EXIT_OK
            return EXIT_OK
    print(f"unknown mutant id: {target_id}", file=sys.stderr)
    return EXIT_INVOCATION


def _git_clean(targets: tuple[str, ...] | None = None) -> bool:
    """Verify the working tree is clean — scoped to mutator targets only.

    A global ``git diff --exit-code`` was historically used here, but it
    falsely flags the tree dirty whenever ANY tracked file is modified
    elsewhere (active development on the harness itself, CI runner CRLF
    rewrites, pre-commit hook side-effects, etc.). Scoping the check to
    the mutator's own target files isolates the contract: every file the
    harness touched must end up byte-identical to its captured pre-mutation
    snapshot.
    """
    paths = targets if targets is not None else tuple(m.target_file for m in MUTANTS)
    if not paths:
        return True
    diff = subprocess.run(
        ["git", "diff", "--exit-code", "--", *paths],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
    )
    return diff.returncode == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Security / calibration-layer mutation kill harness",
    )
    parser.add_argument("--list", action="store_true", help="list registered mutants")
    parser.add_argument("--mutant", help="run a single mutant by id")
    parser.add_argument("--all", action="store_true", help="run all mutants")
    parser.add_argument(
        "--fail-on-survivor",
        action="store_true",
        help="exit non-zero if any mutant survived",
    )
    args = parser.parse_args(argv)

    if args.list:
        return _list(args)
    if args.mutant:
        return _one(args)
    if args.all:
        return _all(args)
    parser.print_help()
    return EXIT_INVOCATION


if __name__ == "__main__":
    raise SystemExit(main())
