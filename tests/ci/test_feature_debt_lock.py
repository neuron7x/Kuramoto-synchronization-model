# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the feature-debt lock gate (process-level fail-closed).

The gate blocks a PR that adds new production feature code to a tracked surface
while a deficit surface (backtest/, analytics/) gets no test paydown and no
explicit exemption. These tests exercise the pure ``decide`` policy with
synthetic diffs so the rule is verified without a git checkout.
"""
from __future__ import annotations

from scripts.ci.check_feature_debt_lock import FEATURE_THRESHOLD, decide

_SURFACES = ["core/", "backtest/", "execution/", "analytics/", "risk/"]
_DEFICIT = ["backtest/", "analytics/"]


def _numstat(rows: list[tuple[int, str]]) -> str:
    return "\n".join(f"{added}\t0\t{path}" for added, path in rows)


def test_feature_without_paydown_is_blocked() -> None:
    """A large new feature in a surface, no deficit-surface tests, no exemption -> BLOCK."""
    diff = _numstat([(FEATURE_THRESHOLD + 50, "core/new_feature.py")])
    verdict = decide(diff, "feat: add a shiny new core feature", _SURFACES, _DEFICIT)
    assert verdict["verdict"] == "BLOCK", verdict
    assert verdict["feature_lines_added"] == FEATURE_THRESHOLD + 50
    assert verdict["debt_paydown_lines"] == 0


def test_feature_with_backtest_paydown_passes() -> None:
    """The same feature, but with added tests for backtest/, pays the debt -> PASS."""
    diff = _numstat(
        [
            (FEATURE_THRESHOLD + 50, "core/new_feature.py"),
            (40, "tests/backtest/test_new_replay_path.py"),
        ]
    )
    verdict = decide(diff, "feat: add core feature + backtest tests", _SURFACES, _DEFICIT)
    assert verdict["verdict"] == "PASS", verdict
    assert verdict["debt_paydown_lines"] == 40


def test_feature_with_nested_analytics_paydown_passes() -> None:
    """Nested analytics test trees count as structural paydown."""
    diff = _numstat(
        [
            (FEATURE_THRESHOLD + 50, "execution/feature.py"),
            (40, "tests/unit/analytics/test_signal_quality.py"),
        ]
    )
    verdict = decide(diff, "feat: execution feature + analytics tests", _SURFACES, _DEFICIT)
    assert verdict["verdict"] == "PASS", verdict
    assert verdict["debt_paydown_lines"] == 40


def test_feature_with_explicit_exemption_passes() -> None:
    """An audited 'Debt-Exempt:' trailer permits a feature without paydown."""
    diff = _numstat([(FEATURE_THRESHOLD + 50, "execution/oms_refactor.py")])
    log = "refactor: rename OMS states\n\nDebt-Exempt: pure rename, no new behaviour"
    verdict = decide(diff, log, _SURFACES, _DEFICIT)
    assert verdict["verdict"] == "PASS", verdict
    assert verdict["exempt"] is True
    assert verdict["exempt_reasons"] == ["pure rename, no new behaviour"]


def test_incidental_exemption_token_in_prose_does_not_pass() -> None:
    """Mentioning the trailer text inside prose is not an audited exemption."""
    diff = _numstat([(FEATURE_THRESHOLD + 50, "core/new_feature.py")])
    log = "docs: explain that Debt-Exempt: <reason> is required for overrides"
    verdict = decide(diff, log, _SURFACES, _DEFICIT)
    assert verdict["verdict"] == "BLOCK", verdict
    assert verdict["exempt"] is False
    assert verdict["exempt_reasons"] == []


def test_empty_exemption_trailer_does_not_pass() -> None:
    """A trailer with no reason is not auditable and must remain fail-closed."""
    diff = _numstat([(FEATURE_THRESHOLD + 50, "core/new_feature.py")])
    verdict = decide(diff, "feat: feature\n\nDebt-Exempt:", _SURFACES, _DEFICIT)
    assert verdict["verdict"] == "BLOCK", verdict
    assert verdict["exempt"] is False


def test_small_change_below_threshold_passes() -> None:
    """A change at or below the feature threshold is not 'a new feature' -> PASS."""
    diff = _numstat([(FEATURE_THRESHOLD, "core/tiny_tweak.py")])
    verdict = decide(diff, "fix: tiny tweak", _SURFACES, _DEFICIT)
    assert verdict["verdict"] == "PASS", verdict


def test_tests_and_docs_only_pass() -> None:
    """A PR touching only tests/docs/CI adds no feature surface -> PASS."""
    diff = _numstat(
        [
            (200, "tests/core/test_more.py"),
            (50, "docs/notes.md"),
            (30, "scripts/ci/check_feature_debt_lock.py"),
        ]
    )
    verdict = decide(diff, "test: more coverage", _SURFACES, _DEFICIT)
    assert verdict["verdict"] == "PASS", verdict
    assert verdict["feature_lines_added"] == 0


def test_paydown_must_target_a_deficit_surface() -> None:
    """Tests for a NON-deficit surface (core) do not count as backtest/analytics paydown."""
    diff = _numstat(
        [
            (FEATURE_THRESHOLD + 50, "execution/feature.py"),
            (40, "tests/core/test_unrelated.py"),  # not a deficit surface
        ]
    )
    verdict = decide(diff, "feat: execution feature + unrelated core tests", _SURFACES, _DEFICIT)
    assert verdict["verdict"] == "BLOCK", verdict
    assert verdict["debt_paydown_lines"] == 0


def test_deficit_surface_name_in_filename_does_not_count_as_paydown() -> None:
    """A deficit-surface token in a filename is not structural coverage paydown."""
    diff = _numstat(
        [
            (FEATURE_THRESHOLD + 50, "core/new_feature.py"),
            (40, "tests/core/test_analytics_helpers.py"),
        ]
    )
    verdict = decide(diff, "feat: feature + misleading test filename", _SURFACES, _DEFICIT)
    assert verdict["verdict"] == "BLOCK", verdict
    assert verdict["debt_paydown_lines"] == 0
