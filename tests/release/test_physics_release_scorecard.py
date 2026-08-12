# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""WP-03 guards — Physics Release Scorecard gate.

Acceptance: PARTIAL != READY. A scorecard claiming release-readiness while any
required dimension is below CI_VERIFIED must fail closed. A verified state with
no evidence must fail. The shipped (honest, not-ready) scorecard must pass.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.release.check_physics_release_scorecard import evaluate

REPO_ROOT = Path(__file__).resolve().parents[2]


def _base(dims: list[dict[str, Any]], *, claimed_ready: bool) -> dict[str, Any]:
    return {
        "version": 1,
        "min_state_for_ready": "CI_VERIFIED",
        "claimed_ready": claimed_ready,
        "dimensions": dims,
    }


def test_shipped_scorecard_is_honest_and_passes() -> None:
    import yaml

    data = yaml.safe_load((REPO_ROOT / "physics_release_scorecard.yml").read_text())
    result = evaluate(data)
    assert result.passed, result.hard_violations
    # It is honestly NOT ready (Scorecard_gate FALSE, negative_evidence UNTESTED, ...).
    assert result.computed_ready is False
    assert result.claimed_ready is False
    assert result.blocking_dimensions  # names its own blockers


def test_partial_claimed_ready_fails_closed() -> None:
    """The core anti-lie: a required PARTIAL dim with claimed_ready=true fails."""
    dims = [
        {"name": "a", "required": True, "state": "CI_VERIFIED", "evidence": "ci"},
        {"name": "b", "required": True, "state": "PARTIAL", "evidence": "wip"},
    ]
    result = evaluate(_base(dims, claimed_ready=True))
    assert result.passed is False
    assert any("PARTIAL != READY" in v for v in result.hard_violations)
    assert "b(PARTIAL)" in result.blocking_dimensions


def test_all_required_ci_verified_ready_passes() -> None:
    dims = [
        {"name": "a", "required": True, "state": "CI_VERIFIED", "evidence": "ci"},
        {"name": "b", "required": True, "state": "EVIDENCE_BEARING", "evidence": "ledger"},
        {"name": "c", "required": False, "state": "PARTIAL", "evidence": "wip"},
    ]
    result = evaluate(_base(dims, claimed_ready=True))
    assert result.passed is True
    assert result.computed_ready is True


def test_verified_state_without_evidence_fails() -> None:
    dims = [{"name": "a", "required": True, "state": "CI_VERIFIED", "evidence": ""}]
    result = evaluate(_base(dims, claimed_ready=False))
    assert result.passed is False
    assert any("evidence is empty" in v for v in result.hard_violations)


def test_unknown_state_fails() -> None:
    dims = [{"name": "a", "required": True, "state": "ALMOST_READY", "evidence": "x"}]
    result = evaluate(_base(dims, claimed_ready=False))
    assert result.passed is False
    assert any("unknown state" in v for v in result.hard_violations)


def test_no_required_dimension_is_decorative_and_fails() -> None:
    dims = [{"name": "a", "required": False, "state": "PARTIAL", "evidence": "x"}]
    result = evaluate(_base(dims, claimed_ready=False))
    assert result.passed is False
    assert any("decorative" in v for v in result.hard_violations)


def test_underclaiming_is_safe() -> None:
    """computed_ready=true but claimed_ready=false is honest under-claiming, not a lie."""
    dims = [{"name": "a", "required": True, "state": "CI_VERIFIED", "evidence": "ci"}]
    result = evaluate(_base(dims, claimed_ready=False))
    assert result.passed is True
    assert result.computed_ready is True
    assert result.claimed_ready is False
