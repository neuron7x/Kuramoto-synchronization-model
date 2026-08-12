# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""G11, G12 — claim boundary catches forbidden phrases across newlines."""

from __future__ import annotations

import pytest

from instrument_validation.claim_boundary import (
    ClaimBoundaryViolation,
    claim_boundary_check,
    find_forbidden_phrases,
    normalize_claim_text,
)
from instrument_validation.verdict import ClaimType


def test_normalize_claim_text_collapses_whitespace() -> None:
    assert normalize_claim_text("foo\nbar\t\tBAZ\nQUX") == "foo bar baz qux"


def test_find_forbidden_catches_split_across_newlines() -> None:
    """G11."""
    text = "the network reflects bank-to-bank\nexposures of major banks"
    found = find_forbidden_phrases(text)
    assert ("bank-to-bank exposures", ClaimType.LIQUIDITY_CONTAGION_MODEL) in found


def test_find_forbidden_catches_preferential_attachment() -> None:
    """G12."""
    found = find_forbidden_phrases("evidence of preferential\nattachment dynamics")
    assert any(p == "preferential attachment" for p, _ in found)


def test_find_forbidden_does_not_match_substring_in_other_word() -> None:
    """A safe sentence about repositories should not trigger 'repo' partial."""
    safe = "Validated repository for liquidity tests is available."
    found = find_forbidden_phrases(safe)
    assert all(p != "validated repo liquidity" for p, _ in found)


def test_claim_boundary_check_raises_without_certificate() -> None:
    text = "The network shows preferential\nattachment dynamics. [F-CONC-CORE]"
    with pytest.raises(ClaimBoundaryViolation):
        claim_boundary_check(
            text,
            certified_claim_types=(),  # NO mechanism cert
            validated_finding_ids=("F-CONC-CORE",),
            require_anchor_per_sentence=False,
        )


def test_claim_boundary_check_passes_when_cert_present() -> None:
    text = "The graph is preferential-attachment-like. [F-CONC-CORE]"
    claim_boundary_check(
        text,
        certified_claim_types=(ClaimType.GENERATIVE_MECHANISM,),
        validated_finding_ids=("F-CONC-CORE",),
        require_anchor_per_sentence=False,
    )


def test_claim_boundary_anchor_rule_requires_finding_or_exploratory() -> None:
    text = "This sentence has no anchor."
    with pytest.raises(ClaimBoundaryViolation):
        claim_boundary_check(
            text,
            certified_claim_types=(),
            validated_finding_ids=(),
            require_anchor_per_sentence=True,
        )


def test_claim_boundary_anchor_rule_passes_with_exploratory_tag() -> None:
    text = "[EXPLORATORY] This sentence is exploratory only."
    claim_boundary_check(
        text,
        certified_claim_types=(),
        validated_finding_ids=(),
        require_anchor_per_sentence=True,
    )


def test_claim_boundary_anchor_rule_passes_with_finding_id() -> None:
    text = "Concentration of strength is observed [F-CONC-CORE]."
    claim_boundary_check(
        text,
        certified_claim_types=(),
        validated_finding_ids=("F-CONC-CORE",),
        require_anchor_per_sentence=True,
    )


def test_find_forbidden_catches_unicode_dashes() -> None:
    """Iter-4 audit fix — em-dash, en-dash, etc. were silently bypassing
    the registry which uses ASCII hyphens.
    """
    for dash in ("—", "–", "‐", "‑", "‒", "―", "−"):
        text = f"the network exhibits preferential{dash}attachment dynamics"
        found = find_forbidden_phrases(text)
        assert any(
            p == "preferential-attachment" for p, _ in found
        ), f"unicode dash U+{ord(dash):04X} bypassed the forbidden filter"
