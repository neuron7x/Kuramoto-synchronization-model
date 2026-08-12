# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""summary_compiler — anchor + forbidden-wording invariants."""

from __future__ import annotations

from instrument_validation.claim_boundary import find_forbidden_phrases
from tools.disha_artifact.summary_compiler import (
    RETRACTED_CLAIMS,
    VALIDATED_FINDINGS,
    compile_safe_summary,
)


def test_compile_safe_summary_round_trip() -> None:
    summary = compile_safe_summary(
        article_grade_countries=["GB", "DE", "FR", "LU", "US", "IE", "NL", "BE"],
        excluded_noise_nodes=["CL", "MO", "JE", "IM", "TW"],
        target_only_nodes=["ES", "IT", "HK", "PH", "ZA"],
    )
    assert summary.findings_used == tuple(VALIDATED_FINDINGS.keys())
    assert summary.exploratory_sentence_count >= 2
    # No forbidden phrases by construction (claim_boundary_check inside compile)
    assert find_forbidden_phrases(summary.body_md) == []


def test_compile_safe_summary_uses_default_countries_when_none_supplied() -> None:
    summary = compile_safe_summary(
        article_grade_countries=[],
        excluded_noise_nodes=[],
        target_only_nodes=[],
    )
    assert summary.body_md.startswith("## Article-safe summary")
    assert "GB" in summary.body_md
    assert "DE" in summary.body_md
    assert "FR" in summary.body_md
    assert "LU" in summary.body_md
    assert "US" in summary.body_md
    assert "IE" in summary.body_md
    assert "NL" in summary.body_md
    assert "BE" in summary.body_md
    assert summary.exploratory_sentence_count >= 1
    assert "Validated findings ledger" in summary.body_md


def test_retracted_claims_listed() -> None:
    assert any("BA mechanism" in s for s in RETRACTED_CLAIMS)
    assert any("Lehman 4-quarter" in s for s in RETRACTED_CLAIMS)
    assert any("risk concentration" in s.lower() for s in RETRACTED_CLAIMS)
