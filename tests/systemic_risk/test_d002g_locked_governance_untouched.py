# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Strike R8 — pre-registration and locked governance files MUST NOT change.

The implementation PR is forbidden from mutating the seven anchor files
listed in the commit acceptor's ``forbidden_paths``. This test pins the
sha256 of each at HEAD-of-anchor-commit (3e92ce5) and refuses any drift.

If the test fails after a legitimate intentional update, the
pre-registration has been edited — that constitutes a FRESH
pre-registration (D-002H or similar), not a D-002G implementation
change, and the locked shas must be reset in a separate documentation
PR that the acceptor approves explicitly.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# Each sha256 below is a content-anchor over a locked governance file at
# the merge commit of #676 (3e92ce5). They are NOT credentials. Inline
# pragma silences detect-secrets HexHighEntropy; fmt: off keeps the
# table aligned so a reviewer can diff anchors at a glance.
# fmt: off
LOCKED_FILE_SHAS: dict[str, str] = {
    "docs/governance/D002G_PREREGISTRATION.yaml":                                       "1ab91f09370e4705a8b0849467bc1f56df2e58d58d5623d3b6d905cbd110bb04",  # noqa: E501  # pragma: allowlist secret
    "docs/governance/D002G_NONDEGENERATE_NULL_DESIGN.md":                               "9cef2db7f5d1f90eb9ec71524193c079efff024c35de0ea9758e4f6c747bd8bb",  # noqa: E501  # pragma: allowlist secret
    "docs/governance/D002G_ACCEPTANCE_RULES.md":                                        "875b1e3eb031b8e5333dc8b455454f0a30419ead1ebe787aa01d5882e7d6ad31",  # noqa: E501  # pragma: allowlist secret
    ".claude/commit_acceptors/x10r-d002g-nondegenerate-null-redesign.yaml":             "eaa704722cd113997fac58d52de3ec38ac7197c70d80389e4197d52d8ce93327",  # noqa: E501  # pragma: allowlist secret
    "docs/governance/D002C_PREREGISTRATION.yaml":                                       "b1561ddde08a60a8eed416f2103655e0f3ee1ecd4e2b2037f4e7193c424a154e",  # noqa: E501  # pragma: allowlist secret
    "docs/governance/D002C_CLAIM_LEDGER.yaml":                                          "eb0b7151d76e5409e6dc9bb4a023551de5e0704673d5ac9f726319ef84a32387",  # noqa: E501  # pragma: allowlist secret  # post-append (D-002H REFUSED entry, PR #692)
    "docs/governance/D002C_CANONICAL_RUN_REPORT.md":                                    "f03ed1c6e96f62dc7ff061b48fc44a6dce0679a13ca6bf449e3785f0a4833ed0",  # noqa: E501  # pragma: allowlist secret
    "docs/governance/D002C_ATTEMPT_2_NULL_AUDIT_FALSIFICATION_REPORT.md":               "83164744e223f236a49111c6411630ff54332285ab871896bfc8921fcd4b0b34",  # noqa: E501  # pragma: allowlist secret
}
# fmt: on

REPO_ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def test_locked_governance_files_unchanged() -> None:
    """Every locked file present and bit-identical to the pinned sha."""
    for rel, expected_sha in LOCKED_FILE_SHAS.items():
        p = REPO_ROOT / rel
        assert p.exists(), f"locked file missing: {rel}"
        actual = _sha256(p)
        assert actual == expected_sha, (
            f"locked file mutated: {rel}\n"
            f"  expected sha256={expected_sha}\n"
            f"  actual   sha256={actual}\n"
            "This violates the D-002G non-mutation contract. The implementation "
            "PR is forbidden from editing pre-registration/governance artefacts."
        )
