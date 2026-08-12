# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002G P1 strike-scaffolding — semantic invariant of the locked acceptor.

Companion to ``test_d002g_m2_locked_governance_untouched.py``. That test pins
the *byte* sha256 of ``x10r-d002g-p1-strike-scaffolding.yaml``; a SHA lock alone
cannot distinguish a benign syntactic repair (e.g. PR #1174's folded ``>-`` →
literal ``|-`` block-scalar rewrite) from a malicious governance edit — both
flip the SHA, both demand the same re-anchor ceremony.

This module pins the *meaning* instead of the bytes. It parses the acceptor and
asserts the governance-relevant content is unchanged:

* the acceptor identity, status, and claim_type;
* the exact six executable adversarial-strike tests (R1..R5 + R7) referenced by
  every command (measurement / falsifier / rollback);
* the falsifier's fail-closed exit codes;
* the rollback target;
* the full forbidden-paths set;
* the empty required_python_symbols contract.

Consequence: the #1183 re-anchor was admissible *because* this test passes
across it — the bytes changed, the meaning did not. Any future re-anchor that
also mutates governance semantics (drops a strike rung, relaxes an exit code,
shrinks forbidden_paths) fails here even if the SHA lock is dutifully updated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ACCEPTOR_PATH = (
    REPO_ROOT / ".claude" / "commit_acceptors" / "x10r-d002g-p1-strike-scaffolding.yaml"
)

# The six executable adversarial-strike tests bound by this acceptor. R6 is a
# documented (non-executable) rung; R8 is bound to the sibling implementation
# acceptor. This set is the governance contract — it must not silently shrink.
CANONICAL_STRIKE_TESTS: tuple[str, ...] = (
    "tests/systemic_risk/test_d002g_strike_R1_spectral_identity.py",
    "tests/systemic_risk/test_d002g_strike_R2_m6_conditional_informativeness.py",
    "tests/systemic_risk/test_d002g_strike_R3_phase0b_robust.py",
    "tests/systemic_risk/test_d002g_strike_R4_phase0c_power.py",
    "tests/systemic_risk/test_d002g_strike_R5_seed_collision.py",
    "tests/systemic_risk/test_d002g_strike_R7_joint_distribution.py",
)

# The locked forbidden-paths set: production governance + ledger surfaces this
# scaffolding acceptor is forbidden from binding or mutating.
CANONICAL_FORBIDDEN_PATHS: frozenset[str] = frozenset(
    {
        "docs/governance/D002G_PREREGISTRATION.yaml",
        "docs/governance/D002G_NONDEGENERATE_NULL_DESIGN.md",
        "docs/governance/D002G_ACCEPTANCE_RULES.md",
        ".claude/commit_acceptors/x10r-d002g-nondegenerate-null-redesign.yaml",
        "docs/governance/D002C_PREREGISTRATION.yaml",
        "docs/governance/D002C_CLAIM_LEDGER.yaml",
        "docs/governance/D002C_CANONICAL_RUN_REPORT.md",
        "docs/governance/D002C_ATTEMPT_2_NULL_AUDIT_FALSIFICATION_REPORT.md",
        "application/governance/claim_ledger.py",
        "application/governance/commit_acceptor.py",
    }
)


def _load_acceptor() -> dict[str, Any]:
    assert ACCEPTOR_PATH.exists(), f"locked acceptor missing: {ACCEPTOR_PATH}"
    with ACCEPTOR_PATH.open("r", encoding="utf-8") as fh:
        data: Any = yaml.safe_load(fh)
    assert isinstance(data, dict), "acceptor YAML must parse to a mapping"
    return data


def test_acceptor_identity_unchanged() -> None:
    """Identity, status and claim_type are part of the locked contract."""
    data = _load_acceptor()
    assert data["id"] == "x10r-d002g-p1-strike-scaffolding"
    assert data["status"] == "ACTIVE"
    assert data["claim_type"] == "governance"
    # Scaffolding binds no production symbols — the contract must stay empty.
    assert data.get("required_python_symbols") == []


def test_every_command_references_all_six_strike_tests() -> None:
    """Each command must reference exactly the canonical strike-test set.

    Style-agnostic: works whether the command is a folded or literal scalar,
    because it matches on the test paths, not on whitespace.
    """
    data = _load_acceptor()
    commands = {
        "measurement_command": str(data["measurement_command"]),
        "falsifier.command": str(data["falsifier"]["command"]),
        "rollback_command": str(data["rollback_command"]),
    }
    for label, command in commands.items():
        for test_path in CANONICAL_STRIKE_TESTS:
            assert test_path in command, (
                f"D-002G strike contract broken: {label} no longer references "
                f"{test_path}. The adversarial-audit ladder must keep all six "
                f"executable rungs (R1..R5+R7)."
            )


def test_falsifier_is_fail_closed() -> None:
    """The falsifier must keep its fail-closed exit codes and existence guard."""
    data = _load_acceptor()
    command = str(data["falsifier"]["command"])
    # exit 1 == a strike test file is missing; exit 2 == a strike test is red.
    assert "exit 1" in command, "falsifier lost its missing-file fail-closed exit 1"
    assert "exit 2" in command, "falsifier lost its red-test fail-closed exit 2"
    assert 'test -f "$t"' in command, "falsifier lost its per-file existence guard"


def test_rollback_target_unchanged() -> None:
    """Rollback must still remove this acceptor and verify its own absence."""
    data = _load_acceptor()
    rollback = str(data["rollback_command"])
    verify = str(data["rollback_verification_command"])
    target = ".claude/commit_acceptors/x10r-d002g-p1-strike-scaffolding.yaml"
    assert f"rm -f {target}" in rollback, "rollback no longer removes the acceptor"
    assert f"test ! -f {target}" in verify, "rollback verification no longer checks it"


def test_forbidden_paths_set_unchanged() -> None:
    """The forbidden-paths governance fence must not silently shrink."""
    data = _load_acceptor()
    raw_paths = data["diff_scope"]["forbidden_paths"]
    actual = frozenset(str(p) for p in raw_paths)
    missing = CANONICAL_FORBIDDEN_PATHS - actual
    assert not missing, f"forbidden_paths fence shrank — dropped: {sorted(missing)}"
    assert actual == CANONICAL_FORBIDDEN_PATHS, (
        f"forbidden_paths drifted from the locked set; "
        f"added: {sorted(actual - CANONICAL_FORBIDDEN_PATHS)}"
    )
