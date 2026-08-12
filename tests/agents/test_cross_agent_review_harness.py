# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for tools/agents/cross_agent_review_harness.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.agents.cross_agent_review_harness import (
    AgentReview,
    ReviewVerdict,
    evaluate_review,
)


def _review(
    *,
    model_name: str = "claude",
    claim_text: str = "P3 dynamic-null witness blocks bounded-drift lie",
    evidence_paths: tuple[str, ...] = ("geosync_hpc/nulls/dynamic_null_model.py",),
    proposed_action: str = "merge dynamic_null_model.py with falsifier",
    confidence_text: str = "high",
) -> AgentReview:
    return AgentReview(
        model_name=model_name,
        claim_text=claim_text,
        evidence_paths=evidence_paths,
        proposed_action=proposed_action,
        confidence_text=confidence_text,
    )


def test_accept_when_evidence_exists_and_action_references_it() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    witness = evaluate_review(_review(), repo_root=repo_root)
    assert witness.verdict is ReviewVerdict.ACCEPT


def test_reject_high_confidence_no_evidence() -> None:
    """Falsifier surface from brief: confidence does NOT confer truth."""
    repo_root = Path(__file__).resolve().parents[2]
    witness = evaluate_review(
        _review(
            evidence_paths=(),
            confidence_text="absolutely certain, 100%, can't be wrong",
        ),
        repo_root=repo_root,
    )
    assert witness.verdict is ReviewVerdict.REJECT


def test_reject_forbidden_phrase_in_claim() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    witness = evaluate_review(
        _review(claim_text="this module predicts returns reliably"),
        repo_root=repo_root,
    )
    assert witness.verdict is ReviewVerdict.REJECT
    assert any("forbidden" in r.lower() for r in witness.reasons)


def test_reject_forbidden_phrase_in_action() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    witness = evaluate_review(
        _review(proposed_action="ship as production-ready trading signal"),
        repo_root=repo_root,
    )
    assert witness.verdict is ReviewVerdict.REJECT


def test_needs_evidence_when_paths_dont_exist() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    witness = evaluate_review(
        _review(evidence_paths=("does/not/exist.py", "missing/file.py")),
        repo_root=repo_root,
    )
    assert witness.verdict is ReviewVerdict.NEEDS_EVIDENCE


def test_downgrade_when_evidence_partial(tmp_path: Path) -> None:
    real = tmp_path / "real.py"
    real.write_text("# real", encoding="utf-8")
    witness = evaluate_review(
        AgentReview(
            model_name="any-model",
            claim_text="x",
            evidence_paths=("real.py", "fake.py"),
            proposed_action="merge real.py",
            confidence_text="med",
        ),
        repo_root=tmp_path,
    )
    assert witness.verdict is ReviewVerdict.DOWNGRADE


def test_downgrade_when_action_does_not_reference_evidence(tmp_path: Path) -> None:
    real = tmp_path / "evidence_a.py"
    real.write_text("# a", encoding="utf-8")
    witness = evaluate_review(
        AgentReview(
            model_name="any-model",
            claim_text="x",
            evidence_paths=("evidence_a.py",),
            proposed_action="do something completely unrelated",
            confidence_text="high",
        ),
        repo_root=tmp_path,
    )
    assert witness.verdict is ReviewVerdict.DOWNGRADE


def test_no_model_privilege_high_conf_no_evidence_still_rejected(tmp_path: Path) -> None:
    """Model name 'gpt-7-ultra' must not get more privilege than 'random'."""
    for name in ("claude", "gpt-5", "grok-3", "gemini-2", "human-reviewer"):
        witness = evaluate_review(
            AgentReview(
                model_name=name,
                claim_text="x",
                evidence_paths=(),
                proposed_action="merge it",
                confidence_text="extremely high",
            ),
            repo_root=tmp_path,
        )
        assert witness.verdict is ReviewVerdict.REJECT, name


def test_empty_claim_rejected(tmp_path: Path) -> None:
    witness = evaluate_review(
        AgentReview(
            model_name="m",
            claim_text="   ",
            evidence_paths=("x",),
            proposed_action="merge",
            confidence_text="",
        ),
        repo_root=tmp_path,
    )
    assert witness.verdict is ReviewVerdict.REJECT


def test_empty_model_name_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="model_name"):
        AgentReview(
            model_name="",
            claim_text="x",
            evidence_paths=("x",),
            proposed_action="m",
            confidence_text="",
        )


def test_witness_records_confidence_but_does_not_use_it(tmp_path: Path) -> None:
    """confidence_text is recorded for audit but never affects the verdict."""
    real = tmp_path / "x.py"
    real.write_text("# x", encoding="utf-8")
    high = evaluate_review(
        AgentReview(
            model_name="m",
            claim_text="x",
            evidence_paths=("x.py",),
            proposed_action="merge x.py",
            confidence_text="100% certain",
        ),
        repo_root=tmp_path,
    )
    low = evaluate_review(
        AgentReview(
            model_name="m",
            claim_text="x",
            evidence_paths=("x.py",),
            proposed_action="merge x.py",
            confidence_text="not sure",
        ),
        repo_root=tmp_path,
    )
    assert high.verdict is low.verdict
    assert high.recorded_confidence_text != low.recorded_confidence_text


def test_evaluate_many_returns_one_witness_per_review(tmp_path: Path) -> None:
    from tools.agents.cross_agent_review_harness import evaluate_many

    real = tmp_path / "x.py"
    real.write_text("# x", encoding="utf-8")
    reviews = [
        AgentReview(
            model_name="a",
            claim_text="ok",
            evidence_paths=("x.py",),
            proposed_action="merge x.py",
            confidence_text="",
        ),
        AgentReview(
            model_name="b",
            claim_text="bad",
            evidence_paths=(),
            proposed_action="ship as production-ready",
            confidence_text="",
        ),
    ]
    report = evaluate_many(reviews, repo_root=tmp_path)
    assert len(report.witnesses) == 2
    assert report.witnesses[0].verdict is ReviewVerdict.ACCEPT
    assert report.witnesses[1].verdict is ReviewVerdict.REJECT
