# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Offline unit tests for the advisory fake-closure scanner.

No live GitHub API is used: the canonical #1109/#1140 regression is encoded as
markdown fixtures under ``tests/fixtures/fake_closure/``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.governance.check_fake_closure_claims import (
    IssueVerdict,
    ScanState,
    evaluate_issue,
    extract_closure_refs,
    extract_refs_only,
    scan,
)

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "fake_closure"


def _read(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Keyword extraction
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("Closes #1109", {1109}),
        ("closes #1109", {1109}),
        ("CLOSES #1109", {1109}),
        ("Fixes #42 and Resolves #7", {42, 7}),
        ("fixed #3, closed #4, resolved #5", {3, 4, 5}),
        ("Closes: #99", {99}),
        ("Refs #1109", set()),  # non-closing form is not a closure ref
        ("see #1109 for context", set()),  # bare mention is not a closure
    ],
)
def test_extract_closure_refs_case_insensitive(body: str, expected: set[int]) -> None:
    assert set(extract_closure_refs(body)) == expected


def test_extract_refs_only() -> None:
    assert extract_refs_only("Refs #1109\nRef #7") == {1109, 7}
    assert extract_refs_only("Closes #1109") == set()


def test_closure_keyword_inside_code_span_is_ignored() -> None:
    # Regression: a correction note quoting "`Closes #1109`" must NOT be read as
    # a live closure directive (GitHub ignores keywords in code spans too).
    body = (
        "> Correction: `Closes #1109` was inaccurate; downgraded to `Refs #1109`.\n"
        "Closes #1101\n"
    )
    assert set(extract_closure_refs(body)) == {1101}


def test_closure_keyword_inside_fenced_block_is_ignored() -> None:
    body = "```\nCloses #999\n```\nFixes #1\n"
    assert set(extract_closure_refs(body)) == {1}


# --------------------------------------------------------------------------- #
# Per-issue verdicts
# --------------------------------------------------------------------------- #


def test_issue_with_global_nonwaivable_and_unchecked_fails() -> None:
    verdict, items = evaluate_issue(_read("issue_1109_non_waivable.md"))
    assert verdict is IssueVerdict.FAIL
    assert any("energy_like_drift" in i for i in items)
    assert len(items) == 5


def test_issue_all_checked_is_clean() -> None:
    verdict, items = evaluate_issue(_read("issue_all_checked.md"))
    assert verdict is IssueVerdict.CLEAN
    assert items == []


def test_normal_checklist_without_markers_is_clean() -> None:
    # False-positive guard: unchecked items without any non-waivable signal.
    verdict, items = evaluate_issue(_read("issue_normal_checklist.md"))
    assert verdict is IssueVerdict.CLEAN
    assert items == []


def test_ambiguous_marker_without_checkboxes_is_unknown() -> None:
    verdict, items = evaluate_issue(_read("issue_ambiguous_marker_no_boxes.md"))
    assert verdict is IssueVerdict.UNKNOWN
    assert items == []


def test_missing_issue_body_is_unknown() -> None:
    assert evaluate_issue(None)[0] is IssueVerdict.UNKNOWN
    assert evaluate_issue("   ")[0] is IssueVerdict.UNKNOWN


def test_per_item_requirement_marker_fails_without_global_marker() -> None:
    body = "- [ ] required: source-level contract\n- [ ] tidy docstring\n"
    verdict, items = evaluate_issue(body)
    assert verdict is IssueVerdict.FAIL
    assert items == ["required: source-level contract"]


# --------------------------------------------------------------------------- #
# Aggregate scan (the 8 required behaviours)
# --------------------------------------------------------------------------- #


def test_1_closes_with_unchecked_nonwaivable_is_advisory_fail() -> None:
    result = scan(_read("pr_body_closes_1109.md"), {1109: _read("issue_1109_non_waivable.md")})
    assert result.state is ScanState.ADVISORY_FAIL
    assert result.referenced_issues == [1109]
    assert result.closure_claims == ["Closes #1109"]
    assert result.unchecked_non_waivable_items
    assert result.blocking_recommended is False  # advisory phase never blocks


def test_2_refs_with_unchecked_is_out_of_scope() -> None:
    result = scan(_read("pr_body_refs_1109.md"), {1109: _read("issue_1109_non_waivable.md")})
    assert result.state is ScanState.OUT_OF_SCOPE


def test_3_closes_with_all_checked_is_pass() -> None:
    result = scan(_read("pr_body_closes_1109.md"), {1109: _read("issue_all_checked.md")})
    assert result.state is ScanState.PASS


def test_4_no_closure_keyword_is_out_of_scope() -> None:
    result = scan(_read("pr_body_no_closure.md"), {})
    assert result.state is ScanState.OUT_OF_SCOPE


def test_5_ambiguous_issue_body_is_unknown_not_pass() -> None:
    result = scan(_read("pr_body_closes_1109.md"), {1109: _read("issue_ambiguous_marker_no_boxes.md")})
    assert result.state is ScanState.UNKNOWN


def test_6_multiple_issues_one_clean_one_fake_is_advisory_fail() -> None:
    result = scan(
        _read("pr_body_closes_two.md"),
        {1101: _read("issue_1101_satisfied.md"), 1109: _read("issue_1109_non_waivable.md")},
    )
    assert result.state is ScanState.ADVISORY_FAIL
    assert result.referenced_issues == [1101, 1109]
    assert all(i["issue"] == "#1109" for i in result.unchecked_non_waivable_items)


def test_7_closure_keywords_are_case_insensitive_in_scan() -> None:
    result = scan("fixes #1109", {1109: _read("issue_1109_non_waivable.md")})
    assert result.state is ScanState.ADVISORY_FAIL


def test_8_false_positive_guard_normal_checklist_does_not_fail() -> None:
    result = scan(_read("pr_body_closes_1109.md"), {1109: _read("issue_normal_checklist.md")})
    assert result.state is ScanState.PASS


def test_unfetchable_issue_body_is_unknown_not_fail() -> None:
    result = scan(_read("pr_body_closes_1109.md"), {1109: None})
    assert result.state is ScanState.UNKNOWN


def test_scan_result_is_json_serialisable() -> None:
    result = scan(_read("pr_body_closes_1109.md"), {1109: _read("issue_1109_non_waivable.md")})
    text = result.to_json()
    assert '"state": "ADVISORY_FAIL"' in text
