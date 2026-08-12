# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Falsifier test for the ``ierd-phase0-yana-response`` claim.

The claim asserts:

1. ``docs/yana-response.md`` is published with tier-labeled answers
   to all seven questions Q1–Q7 of the 2026-05-02 external
   falsification audit.
2. The IERD directive (``docs/governance/IERD-PAI-FPS-UX-001.md``) is
   adopted as a binding standard via ADR 0020.
3. The forbidden-terminology lint
   (``scripts/ci/lint_forbidden_terms.py``) is runnable in warn mode
   and exits 0 on the current repository state (Phase-0 warn-only;
   strict mode lands at Phase-5).

Each test below asserts ONE of those three contract surfaces. A
failure on any one is sufficient to falsify the claim per ADR 0021
v3 falsifier shape (test_id pytest node + invariants_cited +
failure_signature). Cited invariant: INV-IERD-PHASE0.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404 — invoking a vendored script with literal argv only
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
YANA_RESPONSE_PATH = REPO_ROOT / "docs" / "yana-response.md"
DIRECTIVE_PATH = REPO_ROOT / "docs" / "governance" / "IERD-PAI-FPS-UX-001.md"
ADR_0020_PATH = REPO_ROOT / "docs" / "adr" / "0020-ierd-adoption.md"
LINT_SCRIPT_PATH = REPO_ROOT / "scripts" / "ci" / "lint_forbidden_terms.py"

_Q_HEADER_PATTERN = re.compile(r"^##\s+Q([1-7])\.", re.MULTILINE)
_TIER_MARKER_PATTERN = re.compile(
    r"\*\*Tier:\s*(ANCHORED|EXTRAPOLATED|SPECULATIVE|UNKNOWN)\b",
    re.IGNORECASE,
)


def test_yana_response_covers_q1_through_q7() -> None:
    """``yana-response.md`` declares one ``## Q{N}.`` heading per N ∈ 1..7."""
    if not YANA_RESPONSE_PATH.is_file():
        pytest.fail(
            f"INV-IERD-PHASE0 violated: {YANA_RESPONSE_PATH.relative_to(REPO_ROOT)} missing — "
            "the Phase-0 audit response is the canonical artefact backing the claim."
        )
    text = YANA_RESPONSE_PATH.read_text(encoding="utf-8")
    headings = sorted({int(match.group(1)) for match in _Q_HEADER_PATTERN.finditer(text)})
    expected = list(range(1, 8))
    assert headings == expected, (
        f"INV-IERD-PHASE0 violated: yana-response.md must declare Q1..Q7 headings; "
        f"found {headings}."
    )


def test_each_question_carries_a_tier_label() -> None:
    """Every Q{N} section opens with a bolded ``**Tier: <T>**`` declaration."""
    text = YANA_RESPONSE_PATH.read_text(encoding="utf-8")
    sections: list[tuple[int, str]] = []
    matches = list(_Q_HEADER_PATTERN.finditer(text))
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        sections.append((int(match.group(1)), text[start:end]))
    missing: list[int] = [q for q, body in sections if _TIER_MARKER_PATTERN.search(body) is None]
    assert not missing, (
        f"INV-IERD-PHASE0 violated: Q{missing} sections lack a `**Tier: <ANCHORED|"
        f"EXTRAPOLATED|SPECULATIVE|UNKNOWN>**` marker."
    )


def test_directive_published_and_adr_0020_decides_adoption() -> None:
    """IERD directive + ADR 0020 (decision binding) both exist and are non-trivial."""
    if not DIRECTIVE_PATH.is_file():
        pytest.fail(f"INV-IERD-PHASE0 violated: {DIRECTIVE_PATH.relative_to(REPO_ROOT)} missing.")
    if not ADR_0020_PATH.is_file():
        pytest.fail(f"INV-IERD-PHASE0 violated: {ADR_0020_PATH.relative_to(REPO_ROOT)} missing.")
    adr_text = ADR_0020_PATH.read_text(encoding="utf-8")
    assert "## Decision" in adr_text, (
        "INV-IERD-PHASE0 violated: ADR 0020 must declare a `## Decision` section "
        "to count as a binding adoption record."
    )
    assert len(adr_text.strip()) > 1000, (
        "INV-IERD-PHASE0 violated: ADR 0020 is too short to be a substantive "
        "adoption record (minimum 1000 chars expected)."
    )


def test_forbidden_terms_lint_script_runs_warn_only() -> None:
    """Phase-0 contract: lint script is runnable and exits 0 in warn mode.

    Strict mode is the Phase-5 entry. Phase-0 warn-only is the
    declared current state; the test therefore asserts exit-code 0.
    """
    if not LINT_SCRIPT_PATH.is_file():
        pytest.fail(f"INV-IERD-PHASE0 violated: {LINT_SCRIPT_PATH.relative_to(REPO_ROOT)} missing.")
    completed = subprocess.run(  # nosec B603 — argv is a literal list under our control
        [sys.executable, str(LINT_SCRIPT_PATH)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=60,
    )
    assert completed.returncode == 0, (
        "INV-IERD-PHASE0 violated: lint_forbidden_terms.py must exit 0 in warn mode "
        f"(Phase-0 contract); got rc={completed.returncode}\n"
        f"stderr tail:\n{completed.stderr[-400:]}"
    )
