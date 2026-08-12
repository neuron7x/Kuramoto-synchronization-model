# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002G-P2/M2 — locked governance must not change.

The M2 PR is forbidden from mutating any of the ten anchor files
pinned below. The shas are content-anchors over each file at the
P1 merge commit (`d3400c2e981d947449c7457fd163c71e7abc0dab`).

This test is **separate** from the P1 locked-governance test
(`test_d002g_locked_governance_untouched.py`) — the P1 test was
written before this PR existed and is bound to a different acceptor.
Mirroring the file rather than mutating it preserves the P1 contract
intact while adding M2-specific pinning.

If a future PR legitimately needs to update a locked anchor (a
fresh pre-registration), the shas here must be reset in that
documentation PR explicitly; the M2 PR itself MUST not edit them.

RE-ANCHOR LOG
-------------
* 2026-06-18 (#1183) — ``x10r-d002g-p1-strike-scaffolding.yaml`` re-anchored
  from ``4a65261f…d735e9608`` (P1 merge d3400c2e) to
  ``55889886…2aa88415``. Cause: PR #1174 ("repair 139 corrupted commands")
  rewrote the acceptor's inline ``measurement_command`` / ``falsifier`` /
  ``rollback`` commands from folded ``>-`` to literal ``|-`` block scalars to
  satisfy the new ``check_acceptor_command_syntax`` gate. The mutation is
  **purely syntactic and semantics-preserving** (identical R1..R5+R7 strike
  test set, identical pytest invocation, identical exit codes 1/2, identical
  rollback target). Reverting would re-introduce the folded scalar the #1174
  gate rejects — two required gates cannot both pass under revert. This is
  the explicit, documented re-anchor the lock contract above requires; the
  semantic invariant is independently pinned by
  ``test_d002g_strike_scaffolding_semantic_invariant.py``.
  Decision record: docs/governance/D002G_M2_REANCHOR_2026-06-18.md
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# Each sha256 below is a content-anchor over a locked governance / acceptor
# file at the merge commit of #677 (d3400c2e). They are NOT credentials.
# Inline pragma silences detect-secrets HexHighEntropy; fmt: off keeps the
# table aligned so a reviewer can diff anchors at a glance.
# fmt: off
LOCKED_FILE_SHAS_AT_P1_MERGE: dict[str, str] = {
    "docs/governance/D002G_PREREGISTRATION.yaml":                                       "1ab91f09370e4705a8b0849467bc1f56df2e58d58d5623d3b6d905cbd110bb04",  # noqa: E501  # pragma: allowlist secret
    "docs/governance/D002G_NONDEGENERATE_NULL_DESIGN.md":                               "9cef2db7f5d1f90eb9ec71524193c079efff024c35de0ea9758e4f6c747bd8bb",  # noqa: E501  # pragma: allowlist secret
    "docs/governance/D002G_ACCEPTANCE_RULES.md":                                        "875b1e3eb031b8e5333dc8b455454f0a30419ead1ebe787aa01d5882e7d6ad31",  # noqa: E501  # pragma: allowlist secret
    ".claude/commit_acceptors/x10r-d002g-nondegenerate-null-redesign.yaml":             "eaa704722cd113997fac58d52de3ec38ac7197c70d80389e4197d52d8ce93327",  # noqa: E501  # pragma: allowlist secret
    "docs/governance/D002C_PREREGISTRATION.yaml":                                       "b1561ddde08a60a8eed416f2103655e0f3ee1ecd4e2b2037f4e7193c424a154e",  # noqa: E501  # pragma: allowlist secret
    "docs/governance/D002C_CLAIM_LEDGER.yaml":                                          "eb0b7151d76e5409e6dc9bb4a023551de5e0704673d5ac9f726319ef84a32387",  # noqa: E501  # pragma: allowlist secret  # post-D-002H-REFUSED-append (PR #692)
    "docs/governance/D002C_CANONICAL_RUN_REPORT.md":                                    "f03ed1c6e96f62dc7ff061b48fc44a6dce0679a13ca6bf449e3785f0a4833ed0",  # noqa: E501  # pragma: allowlist secret
    "docs/governance/D002C_ATTEMPT_2_NULL_AUDIT_FALSIFICATION_REPORT.md":               "83164744e223f236a49111c6411630ff54332285ab871896bfc8921fcd4b0b34",  # noqa: E501  # pragma: allowlist secret
    ".claude/commit_acceptors/x10r-d002g-p1-implementation.yaml":                       "83d6f6bcfc276d9acb381c39c439ad669836a6a14ed123c3a78bd3920f526199",  # noqa: E501  # pragma: allowlist secret
    ".claude/commit_acceptors/x10r-d002g-p1-strike-scaffolding.yaml":                   "55889886a93b21dced2b2c4060b1c65f66e5521ba67d06882ec0b9672aa88415",  # noqa: E501  # pragma: allowlist secret  # RE-ANCHORED 2026-06-18 (#1183): #1174 syntactic-only command-repair; semantics pinned by test_d002g_strike_scaffolding_semantic_invariant.py
}
# fmt: on

REPO_ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def test_locked_governance_files_unchanged_at_m2_anchor() -> None:
    """Every locked file at the P1 merge anchor must be byte-identical."""
    for rel, expected_sha in LOCKED_FILE_SHAS_AT_P1_MERGE.items():
        p = REPO_ROOT / rel
        assert p.exists(), f"locked file missing: {rel}"
        actual = _sha256(p)
        assert actual == expected_sha, (
            f"locked file mutated by D-002G-P2/M2 PR: {rel}\n"
            f"  expected sha256={expected_sha} (P1 merge anchor d3400c2e)\n"
            f"  actual   sha256={actual}\n"
            "The D-002G-P2/M2 PR is forbidden from editing any "
            "pre-registration / governance / P1 acceptor file."
        )
