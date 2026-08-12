# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""External-agent surface-encoding eval (Task 7) — the canonical surface must
encode the right answers and carry no forbidden claim."""

from __future__ import annotations

from scripts.eval_repo_agent_behavior import (
    DEFAULT_CASES,
    ROOT,
    evaluate_case,
    load_cases,
    run,
)


def test_all_repo_agent_cases_pass_on_current_surface() -> None:
    report = run(load_cases(DEFAULT_CASES), ROOT)
    failing = [v for v in report["verdicts"] if not v["passed"]]
    assert report["all_passed"], f"surface fails to encode answers: {failing}"
    assert report["case_count"] >= 8


def test_missing_surface_phrase_is_detected() -> None:
    case = {
        "id": "neg-missing",
        "required_file_refs": ["PRODUCT_CATEGORY.md"],
        "expect_in": [["PRODUCT_CATEGORY.md", "this exact phrase does not exist xyzzy"]],
        "forbidden_phrases": [],
    }
    v = evaluate_case(case, ROOT)
    assert v["passed"] is False
    assert any("does not encode" in m for m in v["missing"])


def test_forbidden_phrase_is_detected() -> None:
    # README is real; assert a phrase it genuinely contains is caught as forbidden.
    case = {
        "id": "neg-forbidden",
        "required_file_refs": ["README.md"],
        "expect_in": [],
        "forbidden_phrases": ["GeoSync"],
    }
    v = evaluate_case(case, ROOT)
    assert v["passed"] is False
    assert v["forbidden_hits"]


def test_adversarial_overclaim_phrase_absent_from_surface() -> None:
    """The adversarial 'fully runtime enforced' overclaim must not appear in the
    docs an agent reads (the honest claim is 'NOT yet wired')."""
    case = {
        "id": "adversarial-ac-overclaim",
        "required_file_refs": ["docs/phd/13_physics_runtime_hardening.md"],
        "expect_in": [["docs/phd/13_physics_runtime_hardening.md", "NOT yet wired"]],
        "forbidden_phrases": ["AdaptiveCriticalityGate is fully runtime enforced"],
    }
    v = evaluate_case(case, ROOT)
    assert v["passed"] is True
