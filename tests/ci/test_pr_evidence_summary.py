# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Release-evidence attestation logic (Task 1) — pure, gh-free tests."""

from __future__ import annotations

from scripts.ci.write_pr_evidence_summary import build_summary, render_comment


def _checks(*states: str) -> list[dict[str, object]]:
    return [{"state": s} for s in states]


def test_all_success_is_attested() -> None:
    s = build_summary(1316, "abc123", _checks("SUCCESS", "SUCCESS", "SKIPPED"), "2026-06-23T00:00Z")
    assert s["attested"] is True
    assert s["pass_count"] == 2
    assert s["fail_count"] == 0
    assert s["pending_count"] == 0
    assert s["skipped_count"] == 1
    assert s["head_sha"] == "abc123"


def test_any_failure_blocks_attestation() -> None:
    s = build_summary(1, "h", _checks("SUCCESS", "FAILURE"), "t")
    assert s["attested"] is False
    assert s["fail_count"] == 1


def test_any_pending_blocks_attestation() -> None:
    s = build_summary(1, "h", _checks("SUCCESS", "IN_PROGRESS"), "t")
    assert s["attested"] is False
    assert s["pending_count"] == 1


def test_empty_checks_not_attested() -> None:
    s = build_summary(1, "h", [], "t")
    assert s["attested"] is False
    assert s["pass_count"] == 0


def test_checkrun_shape_conclusion_is_counted() -> None:
    """gh statusCheckRollup CheckRun rows use status+conclusion, not state."""
    checks = [
        {"status": "COMPLETED", "conclusion": "SUCCESS"},
        {"status": "COMPLETED", "conclusion": "SUCCESS"},
        {"status": "COMPLETED", "conclusion": "SKIPPED"},
        {"state": "SUCCESS"},  # StatusContext shape
    ]
    s = build_summary(1316, "sha", checks, "t")
    assert s["pass_count"] == 3
    assert s["skipped_count"] == 1
    assert s["pending_count"] == 0
    assert s["attested"] is True


def test_incomplete_checkrun_is_pending_not_success() -> None:
    s = build_summary(1, "h", [{"status": "IN_PROGRESS", "conclusion": None}], "t")
    assert s["pending_count"] == 1
    assert s["attested"] is False


def test_render_comment_marks_state_and_sha() -> None:
    attested = render_comment(build_summary(7, "deadbeef", _checks("SUCCESS"), "t"))
    assert "ATTESTED" in attested
    assert "deadbeef" in attested
    not_attested = render_comment(build_summary(7, "x", _checks("FAILURE"), "t"))
    assert "NOT ATTESTED" in not_attested
