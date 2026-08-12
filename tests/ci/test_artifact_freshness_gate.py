# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""The deterministic evidence-artifact freshness gate must have teeth (P0-7).

Proves the committed deterministic evidence artifacts equal their regenerated
output, and that a hand-edit (the exact failure mode the gate exists to catch)
is detected. The negative test restores the original bytes in ``finally`` so it
never leaves the tree dirty.
"""

from __future__ import annotations

from scripts.ci.check_artifact_freshness import (
    DETERMINISTIC_ARTIFACTS,
    MANIFEST,
    ROOT,
    build_manifest,
    check,
)


def test_committed_artifacts_are_fresh() -> None:
    """All declared deterministic artifacts match their regenerated output."""
    assert check() == []


def test_manifest_is_consistent_with_artifacts() -> None:
    """Tracked manifest equals the freshly-built manifest (no drift)."""
    import json

    committed = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert committed == build_manifest()


def test_hand_edit_is_detected() -> None:
    """A tampered artifact is flagged STALE by check() (the gate's reason to exist).

    Uses a single check() pass (one regeneration of the deterministic set) rather
    than repeated regenerations, to keep this off the hot path of the repo's
    contract-test step.
    """
    entry = DETERMINISTIC_ARTIFACTS[0]
    path = ROOT / entry.artifact
    original = path.read_bytes()
    try:
        path.write_bytes(original + b'\n{"hand_edited": true}\n')  # corrupt
        errors = check()
        assert any("STALE" in e and entry.artifact in e for e in errors), (
            f"tampered artifact must be flagged STALE; got {errors}"
        )
    finally:
        path.write_bytes(original)  # leave the tree clean
