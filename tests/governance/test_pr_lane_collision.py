# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""WP-01 guards — PR lane-collision detection.

The acceptance gate: the #1120 / #1121 Task-2 dependency-all-strict pair MUST be
flagged as a collision (they cannot both be merge-ready). The remaining tests
pin the detector against false positives and draft/closed exclusion.
"""

from __future__ import annotations

from tools.governance.check_pr_lane_collision import (
    PullRequest,
    detect_collisions,
    lane_tokens,
)

# The real pair this WP exists to catch (changed files observed on the PRs).
PR_1120 = PullRequest(
    number=1120,
    title="security(deps): promote manifest-consistency gate to all-strict (P0-1 / Task 2)",
    files=(
        "tools/security/check_dependency_manifest_consistency.py",
        "tests/security/test_dependency_manifest_consistency.py",
        "docs/security/dependency_policy.md",
        "requirements.txt",
    ),
)
PR_1121 = PullRequest(
    number=1121,
    title="fix(security): close Task 2 dependency all-strict floor consistency",
    files=(
        "tools/security/check_dependency_manifest_consistency.py",
        "tests/security/test_dependency_manifest_consistency.py",
        "docs/security/dependency_policy.md",
        "requirements.txt",
    ),
)


def test_real_task2_pair_is_flagged() -> None:
    collisions = detect_collisions([PR_1120, PR_1121])
    assert len(collisions) == 1
    c = collisions[0]
    assert {c.a, c.b} == {1120, 1121}
    # Caught on BOTH axes: shared source-of-truth file and shared lane token.
    assert "tools/security/check_dependency_manifest_consistency.py" in c.shared_critical_files
    assert "requirements.txt" in c.shared_critical_files
    assert "task2" in c.shared_lane_tokens


def test_disjoint_lanes_do_not_collide() -> None:
    a = PullRequest(2001, "feat(physics): reliability contract", ("tools/physics/check_physics_reliability.py",))
    b = PullRequest(2002, "fix(ui): button color", ("frontend/app.tsx",))
    assert detect_collisions([a, b]) == []


def test_shared_noncritical_file_alone_is_not_a_collision() -> None:
    # Two PRs both touching a README but in different lanes, no shared token.
    a = PullRequest(3001, "feat: alpha", ("README.md", "core/alpha.py"))
    b = PullRequest(3002, "feat: beta", ("README.md", "core/beta.py"))
    assert detect_collisions([a, b]) == []


def test_shared_token_without_file_overlap_is_not_a_collision() -> None:
    a = PullRequest(4001, "feat: Task 9 part A", ("core/a.py",))
    b = PullRequest(4002, "feat: Task 9 part B", ("core/b.py",))
    assert detect_collisions([a, b]) == []


def test_shared_token_with_file_overlap_collides() -> None:
    a = PullRequest(5001, "feat: Task 9 alpha", ("core/shared.py", "core/a.py"))
    b = PullRequest(5002, "feat: Task 9 beta", ("core/shared.py", "core/b.py"))
    collisions = detect_collisions([a, b])
    assert len(collisions) == 1
    assert "task9" in collisions[0].shared_lane_tokens


def test_draft_and_closed_prs_are_excluded() -> None:
    draft = PullRequest(6001, "Task 2 deps", ("requirements.txt",), is_draft=True)
    closed = PullRequest(6002, "Task 2 deps", ("requirements.txt",), state="CLOSED")
    assert detect_collisions([draft, closed, PR_1120]) == []


def test_lane_token_parsing() -> None:
    assert "task2" in lane_tokens("close Task 2 floor consistency")
    assert "p0-1" in lane_tokens("promote gate (P0-1 / Task 2)")
    assert lane_tokens("just a normal title") == set()
