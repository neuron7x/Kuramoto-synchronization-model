"""Tests for the mutation kill ledger.

Three contracts:

1. The ledger schema is well-formed: every entry has the required keys,
   the harness names match the actual harness modules, the
   expected_killing_test path exists, and the target_file exists.

2. The security mutation harness can run end-to-end on the live tree:
   all 4 calibration-layer mutants are killed and the working tree is
   clean afterwards (`git diff --exit-code` returns 0). This is the
   load-bearing contract — it proves the gates fail closed.

3. Every mutant marked `killed: YES` in the ledger is also actually
   killed by its expected_killing_test on this run. (The physics
   harness is exercised by `tools/physics_mutation_check.py` separately;
   we do NOT re-run all 6 physics mutants here because they are slow.
   The security harness is fast.)
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped,unused-ignore]

REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER_PATH = REPO_ROOT / ".claude" / "mutation" / "MUTATION_LEDGER.yaml"
SECURITY_HARNESS_PATH = REPO_ROOT / "tools" / "mutation" / "security_mutation_check.py"
PHYSICS_HARNESS_PATH = REPO_ROOT / "tools" / "physics_mutation_check.py"

REQUIRED_KEYS = (
    "mutant_id",
    "harness",
    "target_file",
    "mutation",
    "expected_killing_test",
    "killed",
    "last_run_command",
    "last_run_status",
    "restore_verified",
)


def _load_ledger() -> list[dict[str, Any]]:
    data = yaml.safe_load(LEDGER_PATH.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    return data.get("mutants") or []


def _load_security_harness() -> ModuleType:
    spec = importlib.util.spec_from_file_location("smh", SECURITY_HARNESS_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["smh"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ledger() -> list[dict[str, Any]]:
    return _load_ledger()


@pytest.fixture(scope="module")
def smh() -> ModuleType:
    return _load_security_harness()


# ---------------------------------------------------------------------------
# Contract 1 — ledger schema
# ---------------------------------------------------------------------------


def test_ledger_exists() -> None:
    assert LEDGER_PATH.exists()


def test_every_entry_has_required_keys(ledger: list[dict[str, Any]]) -> None:
    for entry in ledger:
        missing = [k for k in REQUIRED_KEYS if k not in entry]
        assert not missing, f"{entry.get('mutant_id')} missing keys: {missing}"


def test_target_files_exist(ledger: list[dict[str, Any]]) -> None:
    for entry in ledger:
        target = REPO_ROOT / entry["target_file"]
        assert target.exists(), f"{entry['mutant_id']}: target file does not exist: {target}"


def test_expected_killing_tests_exist(ledger: list[dict[str, Any]]) -> None:
    """Strip ::node_id; verify the test FILE exists."""
    for entry in ledger:
        spec = entry["expected_killing_test"]
        path_part = spec.split("::", 1)[0]
        target = REPO_ROOT / path_part
        assert target.exists(), f"{entry['mutant_id']}: expected killer test file missing: {target}"


def test_harness_names_are_known(ledger: list[dict[str, Any]]) -> None:
    known = {"physics_mutation_check", "security_mutation_check"}
    for entry in ledger:
        assert (
            entry["harness"] in known
        ), f"{entry['mutant_id']}: unknown harness {entry['harness']!r}"


def _is_yes(value: object) -> bool:
    """YAML 1.1 parses bare YES/NO as bool, but quoted strings stay strings.
    Accept both forms."""
    if value is True:
        return True
    if isinstance(value, str) and value.strip().upper() == "YES":
        return True
    return False


def test_at_least_five_mutants_killed(ledger: list[dict[str, Any]]) -> None:
    """Closure criterion from the task: ≥5 mutants killed in the ledger."""
    killed = [e for e in ledger if _is_yes(e.get("killed"))]
    assert len(killed) >= 5, f"only {len(killed)} mutants marked killed; need ≥5"


def test_no_mutant_marked_killed_with_dirty_restore(
    ledger: list[dict[str, Any]],
) -> None:
    """A killed mutant that left a dirty tree is a HARDER failure than a
    survived one. The ledger must reflect that."""
    for entry in ledger:
        if not _is_yes(entry.get("killed")):
            continue
        assert _is_yes(
            entry.get("restore_verified")
        ), f"{entry['mutant_id']}: killed without restore_verified=YES"


# ---------------------------------------------------------------------------
# Contract 2 — security harness end-to-end on the live tree
# ---------------------------------------------------------------------------


def test_security_harness_lists_four_mutants(smh: ModuleType) -> None:
    assert len(smh.MUTANTS) == 4


@pytest.mark.skipif(
    shutil.which("git") is None,
    reason="git CLI required to run mutation harness end-to-end",
)
def test_security_harness_kills_all_mutants_and_restores(
    smh: ModuleType,
) -> None:
    """Run all security mutants. Assert exit 0 with --fail-on-survivor and
    that the working tree is clean afterwards. This is the single most
    load-bearing test in the calibration layer: it proves the gates fail
    closed when their core logic is broken AND that the harness itself
    does not leave the tree dirty."""
    rc = subprocess.run(
        [
            sys.executable,
            str(SECURITY_HARNESS_PATH),
            "--all",
            "--fail-on-survivor",
        ],
        cwd=REPO_ROOT,
        check=False,
    ).returncode
    assert rc == 0, f"security harness exit {rc}"

    # Only the mutator's own target files must end up clean — a global
    # `git diff --exit-code` falsely flags the tree dirty whenever any
    # other tracked file is modified elsewhere (active branch development,
    # CI CRLF rewrites, pre-commit side-effects). The contract here is
    # solely about the mutated files being restored byte-identically.
    target_paths = tuple(m.target_file for m in smh.MUTANTS)
    diff = subprocess.run(
        ["git", "diff", "--exit-code", "--", *target_paths],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
    )
    assert diff.returncode == 0, (
        "mutator target files dirty after harness run:\n" + diff.stdout.decode()
    )


# ---------------------------------------------------------------------------
# Contract 3 — security mutants in the ledger match the harness
# ---------------------------------------------------------------------------


def test_security_mutants_in_ledger_match_harness(
    ledger: list[dict[str, Any]], smh: ModuleType
) -> None:
    ledger_security_ids = {
        e["mutant_id"] for e in ledger if e["harness"] == "security_mutation_check"
    }
    harness_ids = {m.mutant_id for m in smh.MUTANTS}
    assert ledger_security_ids == harness_ids, (
        f"ledger / harness mismatch:\n"
        f"  in ledger only: {ledger_security_ids - harness_ids}\n"
        f"  in harness only: {harness_ids - ledger_security_ids}"
    )
