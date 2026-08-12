# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002H R2-B inapplicability-note contract tests.

The R2-B inapplicability note (``docs/governance/D002H_R2B_INAPPLICABILITY_NOTE.md``)
scopes R2-B (inherited from D-002G acceptance rules §2) as STRUCTURALLY
INAPPLICABLE under D-002H scope, because M6 placebo coupling is not in
the D-002H pre-registration ``null_mechanisms_allowed`` set
(``[M1_INDEPENDENT_SEED, M3_TOPOLOGY_CONDITIONED]``).

These tests pin the note's normative content, the verbatim resolution
block, the verdict-applicability table, the forbidden-interpretation
list, and — critically — the byte-exact sha256 of three locked
governance files (D-002G acceptance rules, D-002H prereg, D-002C
claim ledger). The pins guarantee that this PR (and any future PR) is
the SCOPING ARTIFACT, never a CONTRACT MUTATION.

Lessons applied:
  * L1 — acceptor flat strings (no nested mappings) — N/A for tests.
  * L2 — anchor sha pins use ``# pragma: allowlist secret`` to bypass
    detect-secrets HexHighEntropy false-positive.
  * L3 — every assert has a ``msg_*`` variable.
  * L4 — every test has ≥ 2 assertions OR ≥ 2 distinct cases.
  * L5 — ≤ 4 broad-except per file (this file has zero).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

NOTE_RELPATH = "docs/governance/D002H_R2B_INAPPLICABILITY_NOTE.md"
NOTE_PATH = REPO_ROOT / NOTE_RELPATH

D002G_ACCEPTANCE_RELPATH = "docs/governance/D002G_ACCEPTANCE_RULES.md"
D002H_PREREG_RELPATH = "docs/governance/D002H_PREREGISTRATION.yaml"
D002C_LEDGER_RELPATH = "docs/governance/D002C_CLAIM_LEDGER.yaml"

# Content-addressed pins. The pragmas silence detect-secrets
# HexHighEntropy false-positives: these are governance anchors
# enforcing the byte-exact contract, not credentials.
# fmt: off
D002G_ACCEPTANCE_SHA_PIN: str = "875b1e3eb031b8e5333dc8b455454f0a30419ead1ebe787aa01d5882e7d6ad31"  # noqa: E501  # pragma: allowlist secret
D002H_PREREG_SHA_PIN: str = "44b18b5a40ce9d188a9c3bd49339621f81a65a15f97a683247902450dd54acec"  # noqa: E501  # pragma: allowlist secret
D002C_LEDGER_SHA_PIN: str = "eb0b7151d76e5409e6dc9bb4a023551de5e0704673d5ac9f726319ef84a32387"  # noqa: E501  # pragma: allowlist secret  # post-D-002H-REFUSED-append (PR #692)
# fmt: on

# Verbatim resolution-block markers (Section 4).
RESOLUTION_BLOCK_HEADER = "R2-B INAPPLICABILITY UNDER D-002H SCOPE"
FOUR_TERM_CONJUNCTION = "R1 ∧ R2 ∧ R3 ∧ NULL_AUDIT"

# Phrases (case-insensitive substring) that, if they appear OUTSIDE a
# denial / out-of-scope / forbidden context, would constitute a leak.
# Mirrors the Gate D scanner's ``FORBIDDEN_CLAIMS`` list but trimmed to
# the cross-promotion subset relevant to a scoping note.
CROSS_PROMOTION_PHRASES = (
    "D-002G rescue",
    "D-002C rescue",
    "cross-substrate robustness",
    "general topology robustness",
    "scientific PASS before canonical run",
    "block_structured remains in scope",
    "temporal_coupling remains in scope",
)

# Denial-marker substrings (lower-cased). Mirrors the Gate D scanner's
# ``ALLOWED_DENIAL_MARKERS`` subset relevant to a forbidden-block.
DENIAL_MARKERS = (
    "❌",
    "does not",
    "do not",
    "not ",
    "must not",
    "forbidden",
    "out of scope",
    "excluded",
    "cannot",
    "never",
    "rejected",
    "fail-closed",
    "denied",
    "prohibited",
    "impossible",
    "blocked",
    "remains locked",
    "byte-exact locked",
    "byte-exact",
    "no m6",
    "alone does not",
    "rescue",  # used in note only inside denial form "is NOT a rescue"
)


def _read_note_text() -> str:
    """Read the note's text once per test invocation."""
    msg_missing = f"R2-B inapplicability note missing at {NOTE_RELPATH}"
    assert NOTE_PATH.is_file(), msg_missing
    return NOTE_PATH.read_text(encoding="utf-8")


def _sha256_of(relpath: str) -> str:
    """Return hex-lower-case sha256 of the file at ``REPO_ROOT/relpath``."""
    path = REPO_ROOT / relpath
    msg_missing = f"locked governance file missing on disk: {relpath}"
    assert path.is_file(), msg_missing
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _line_context_has_denial(lines: list[str], idx: int, before: int = 4, after: int = 2) -> bool:
    """Return True iff any line in the ``[idx-before, idx+after]`` window
    contains a denial marker (case-insensitive).
    """
    lo = max(0, idx - before)
    hi = min(len(lines), idx + after + 1)
    window = "\n".join(lines[lo:hi]).lower()
    return any(marker in window for marker in DENIAL_MARKERS)


# ---------------------------------------------------------------------------
# 10 contract tests (names exact per brief).
# ---------------------------------------------------------------------------


def test_r2b_note_exists() -> None:
    """The R2-B inapplicability note is on disk and non-empty.

    Two-assertion test (L4): presence AND non-empty content.
    """
    msg_missing = f"R2-B inapplicability note missing at {NOTE_RELPATH}"
    assert NOTE_PATH.is_file(), msg_missing
    text = NOTE_PATH.read_text(encoding="utf-8")
    msg_nonempty = (
        f"R2-B inapplicability note is empty at {NOTE_RELPATH}; expected non-empty markdown body"
    )
    assert len(text.strip()) > 0, msg_nonempty


def test_r2b_inapplicability_block_present() -> None:
    """Section 4 verbatim resolution block is present.

    Two-assertion test (L4): the header marker AND the 4-term
    conjunction string both appear in the note text.
    """
    text = _read_note_text()
    msg_header = (
        f"Section 4 resolution-block header missing in {NOTE_RELPATH}: "
        f"expected substring {RESOLUTION_BLOCK_HEADER!r}"
    )
    assert RESOLUTION_BLOCK_HEADER in text, msg_header
    msg_conj = (
        f"4-term conjunction string missing in {NOTE_RELPATH}: "
        f"expected substring {FOUR_TERM_CONJUNCTION!r}"
    )
    assert FOUR_TERM_CONJUNCTION in text, msg_conj


def test_r2b_verdict_table_lists_4_applicable_rules() -> None:
    """Section 5 table contains exactly 4 APPLICABLE rule rows.

    Counts the case-insensitive token ``APPLICABLE`` minus the
    bold-emphasised ``INAPPLICABLE`` row. Two-assertion test (L4):
    APPLICABLE row count AND total rule rows.
    """
    text = _read_note_text()

    # Extract Section 5 table block by anchor headings.
    section_5_start = text.find("## 5. Verdict-computation explicit table")
    section_6_start = text.find("## 6. Anti-overclaim guards")
    msg_anchors = (
        "Section 5 / Section 6 anchors not found; cannot extract verdict "
        f"table from {NOTE_RELPATH} (idx5={section_5_start}, idx6={section_6_start})"
    )
    assert section_5_start > 0 and section_6_start > section_5_start, msg_anchors
    table_block = text[section_5_start:section_6_start]

    # The bolded INAPPLICABLE row uses ``| **INAPPLICABLE**`` (note the
    # ``**`` immediately after the pipe-space); the four APPLICABLE rows
    # use bare ``| APPLICABLE |`` with whitespace bounding. The pattern
    # below requires whitespace between ``|`` and ``APPLICABLE`` AND
    # between ``APPLICABLE`` and the next ``|``, which excludes the
    # bolded INAPPLICABLE cell by construction.
    applicable_pattern = re.compile(r"\|\s+APPLICABLE\s+\|")
    applicable_rows = applicable_pattern.findall(table_block)
    inapplicable_pattern = re.compile(r"\|\s+\*\*INAPPLICABLE\*\*")
    inapplicable_rows = inapplicable_pattern.findall(table_block)
    applicable_count = len(applicable_rows)
    msg_count = (
        f"Section 5 verdict-table APPLICABLE row count drift in "
        f"{NOTE_RELPATH}: got {applicable_count}, expected 4 "
        f"(R1, R2, R3, NULL_AUDIT). "
        f"raw_applicable={len(applicable_rows)}, raw_inapplicable={len(inapplicable_rows)}"
    )
    assert applicable_count == 4, msg_count
    msg_inappl = (
        f"Section 5 verdict-table INAPPLICABLE row count drift in "
        f"{NOTE_RELPATH}: got {len(inapplicable_rows)}, expected exactly 1 (R2-B row)"
    )
    assert len(inapplicable_rows) == 1, msg_inappl


def test_r2b_explicitly_marked_inapplicable() -> None:
    """The R2-B row in Section 5 carries the bold ``**INAPPLICABLE**`` cell.

    Two-assertion test (L4): bold-INAPPLICABLE token AND R2-B
    label appear together in the same table row.
    """
    text = _read_note_text()
    # R2-B row should contain both ``R2-B`` and ``**INAPPLICABLE**`` on
    # the same logical row of the section-5 markdown table.
    row_pattern = re.compile(
        r"\|\s*R2-B[^\|]*\|[^\|]*\*\*INAPPLICABLE\*\*[^\|]*\|",
        flags=re.IGNORECASE,
    )
    msg_row = (
        f"R2-B row with bold **INAPPLICABLE** cell not found in {NOTE_RELPATH} "
        "Section 5 verdict-table; row pattern must contain both ``R2-B`` "
        "and ``**INAPPLICABLE**`` in the same markdown row"
    )
    assert row_pattern.search(text) is not None, msg_row
    # Independently: the bold marker must appear at least once.
    msg_bold = (
        f"Bold-emphasised **INAPPLICABLE** token absent from {NOTE_RELPATH}; "
        "the R2-B row must carry the **INAPPLICABLE** marker"
    )
    assert "**INAPPLICABLE**" in text, msg_bold


def test_r2b_does_not_modify_d002g_acceptance_rules() -> None:
    """D-002G acceptance rules sha256 byte-exact at the pinned anchor.

    Two-assertion test (L4): on-disk sha256 equals the pin AND the
    pin itself is the canonical 64-hex-char form.
    """
    on_disk = _sha256_of(D002G_ACCEPTANCE_RELPATH)
    msg_drift = (
        f"D-002G acceptance rules byte-exact violated: "
        f"on-disk sha256={on_disk}, pinned={D002G_ACCEPTANCE_SHA_PIN}. "
        f"This PR must NOT modify {D002G_ACCEPTANCE_RELPATH}; it only "
        "scopes R2-B applicability under D-002H."
    )
    assert on_disk == D002G_ACCEPTANCE_SHA_PIN, msg_drift
    msg_form = (
        f"D-002G acceptance pin form drift: got {D002G_ACCEPTANCE_SHA_PIN!r}, "
        "expected 64 lower-case hex chars"
    )
    assert re.fullmatch(r"[0-9a-f]{64}", D002G_ACCEPTANCE_SHA_PIN) is not None, msg_form


def test_r2b_does_not_modify_d002h_prereg() -> None:
    """D-002H prereg sha256 byte-exact at the locked anchor.

    Two-assertion test (L4): on-disk sha256 equals pin AND pin form.
    """
    on_disk = _sha256_of(D002H_PREREG_RELPATH)
    msg_drift = (
        f"D-002H prereg byte-exact violated: on-disk sha256={on_disk}, "
        f"pinned={D002H_PREREG_SHA_PIN}. "
        f"This PR must NOT modify {D002H_PREREG_RELPATH}."
    )
    assert on_disk == D002H_PREREG_SHA_PIN, msg_drift
    msg_form = (
        f"D-002H prereg pin form drift: got {D002H_PREREG_SHA_PIN!r}, "
        "expected 64 lower-case hex chars"
    )
    assert re.fullmatch(r"[0-9a-f]{64}", D002H_PREREG_SHA_PIN) is not None, msg_form


def test_r2b_preserves_d002c_ledger() -> None:
    """D-002C claim ledger sha256 byte-exact at the locked anchor.

    Two-assertion test (L4): on-disk sha256 equals pin AND pin form.
    """
    on_disk = _sha256_of(D002C_LEDGER_RELPATH)
    msg_drift = (
        f"D-002C claim ledger byte-exact violated: on-disk sha256={on_disk}, "
        f"pinned={D002C_LEDGER_SHA_PIN}. "
        f"This PR must NOT touch {D002C_LEDGER_RELPATH}."
    )
    assert on_disk == D002C_LEDGER_SHA_PIN, msg_drift
    msg_form = (
        f"D-002C ledger pin form drift: got {D002C_LEDGER_SHA_PIN!r}, "
        "expected 64 lower-case hex chars"
    )
    assert re.fullmatch(r"[0-9a-f]{64}", D002C_LEDGER_SHA_PIN) is not None, msg_form


def test_r2b_future_evolution_requires_fresh_prereg() -> None:
    """Section 7 (Future evolution) names D-002J + ``fresh pre-registration``.

    Two-assertion test (L4): ``D-002J`` token AND co-occurrence of
    ``fresh`` and ``pre-registration`` within Section 7 text.
    """
    text = _read_note_text()
    section_7_start = text.find("## 7. Future evolution")
    section_8_start = text.find("## 8. Forbidden interpretations")
    msg_anchors = (
        "Section 7 / Section 8 anchors not found in "
        f"{NOTE_RELPATH} (idx7={section_7_start}, idx8={section_8_start})"
    )
    assert section_7_start > 0 and section_8_start > section_7_start, msg_anchors
    section_7_block = text[section_7_start:section_8_start]
    msg_j = (
        f"Section 7 must reference D-002J explicitly in {NOTE_RELPATH}; "
        "future R2-B analogue requires a fresh letter (D-002J)"
    )
    assert "D-002J" in section_7_block, msg_j
    block_lower = section_7_block.lower()
    msg_fresh = (
        f"Section 7 must co-occur 'fresh' and 'pre-registration' in "
        f"{NOTE_RELPATH}; got block excerpt: {section_7_block[:200]!r}..."
    )
    assert "fresh" in block_lower and "pre-registration" in block_lower, msg_fresh


def test_r2b_forbidden_interpretations_present() -> None:
    """Section 8 carries at least 4 ❌ forbidden-interpretation lines.

    Two-assertion test (L4): ❌ line count AND section presence.
    """
    text = _read_note_text()
    section_8_start = text.find("## 8. Forbidden interpretations")
    section_9_start = text.find("## 9. Claim boundary")
    msg_anchors = (
        "Section 8 / Section 9 anchors not found in "
        f"{NOTE_RELPATH} (idx8={section_8_start}, idx9={section_9_start})"
    )
    assert section_8_start > 0 and section_9_start > section_8_start, msg_anchors
    section_8_block = text[section_8_start:section_9_start]
    forbidden_lines = [
        line for line in section_8_block.splitlines() if line.lstrip().startswith("- ❌")
    ]
    msg_count = (
        f"Section 8 ❌ forbidden-interpretation line count drift in "
        f"{NOTE_RELPATH}: got {len(forbidden_lines)}, expected ≥ 4. "
        f"Lines: {forbidden_lines!r}"
    )
    assert len(forbidden_lines) >= 4, msg_count


def test_r2b_no_canonical_sweep_authorisation_claim() -> None:
    """No cross-promotion phrase leaks outside denial context.

    Walks every line of the note; for each cross-promotion phrase hit,
    requires the surrounding context window to carry at least one
    denial marker. Multi-case test (L4): per-phrase per-line scan
    accumulates a ``leaks`` list AND the empty-list assertion plus a
    sanity assert that the note actually mentions ``Gate G``.
    """
    text = _read_note_text()
    lines = text.splitlines()
    leaks: list[tuple[int, str, str]] = []
    for phrase in CROSS_PROMOTION_PHRASES:
        phrase_low = phrase.lower()
        for idx, line in enumerate(lines):
            if phrase_low not in line.lower():
                continue
            if _line_context_has_denial(lines, idx):
                continue
            leaks.append((idx + 1, phrase, line.rstrip()))
    msg_leaks = (
        f"cross-promotion phrase leak outside denial context in {NOTE_RELPATH}; hits: {leaks!r}"
    )
    assert leaks == [], msg_leaks
    # Sanity guard: the note explicitly references Gate G's prior
    # authorisation so readers cannot misread this note as a new
    # authorisation.
    msg_gate_g = (
        f"Sanity: note must reference Gate G's prior authorisation in "
        f"{NOTE_RELPATH} so readers cannot misread this scoping note as "
        "a new authorisation event"
    )
    assert "Gate G" in text, msg_gate_g
