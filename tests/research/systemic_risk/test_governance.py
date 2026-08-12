# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the self-checking governance gates."""

from __future__ import annotations

from pathlib import Path

import pytest

from research.systemic_risk.governance import (
    FORBIDDEN_OVERCLAIM_TERMS,
    assert_claim_tier,
    build_validation_readiness_report,
    run_premerge_science_gate,
)


class TestBuildValidationReadinessReport:
    def test_no_evidence_caps_at_hypothesis(self) -> None:
        r = build_validation_readiness_report(
            score_level_executable=False,
            end_to_end_executable=False,
            real_data_run_executed=False,
            null_audit_executable=False,
            replication_independent=False,
        )
        assert r.max_allowed_tier == "HYPOTHESIS"

    def test_score_only_caps_at_instrumented(self) -> None:
        r = build_validation_readiness_report(
            score_level_executable=True,
            end_to_end_executable=False,
            real_data_run_executed=False,
            null_audit_executable=False,
            replication_independent=False,
        )
        assert r.max_allowed_tier == "INSTRUMENTED"

    def test_full_evidence_reaches_validated(self) -> None:
        r = build_validation_readiness_report(
            score_level_executable=True,
            end_to_end_executable=True,
            real_data_run_executed=True,
            null_audit_executable=True,
            replication_independent=True,
        )
        assert r.max_allowed_tier == "VALIDATED"


class TestAssertClaimTier:
    def test_accepts_supported_claim(self) -> None:
        readiness = build_validation_readiness_report(
            score_level_executable=True,
            end_to_end_executable=False,
            real_data_run_executed=False,
            null_audit_executable=False,
            replication_independent=False,
        )
        assert_claim_tier(claimed="HYPOTHESIS", evidence=readiness)
        assert_claim_tier(claimed="INSTRUMENTED", evidence=readiness)

    def test_rejects_overclaim(self) -> None:
        readiness = build_validation_readiness_report(
            score_level_executable=True,
            end_to_end_executable=False,
            real_data_run_executed=False,
            null_audit_executable=False,
            replication_independent=False,
        )
        with pytest.raises(AssertionError, match="exceeds available evidence"):
            assert_claim_tier(claimed="MEASURED", evidence=readiness)
        with pytest.raises(AssertionError):
            assert_claim_tier(claimed="VALIDATED", evidence=readiness)


class TestRunPremergeScienceGate:
    def test_passes_on_clean_module(self, tmp_path: Path) -> None:
        # Synthetic clean tree — no overclaim terms.
        (tmp_path / "README.md").write_text(
            "# Hypothesis instrument. Score-level falsification scaffold.\n",
            encoding="utf-8",
        )
        readiness = build_validation_readiness_report(
            score_level_executable=True,
            end_to_end_executable=False,
            real_data_run_executed=False,
            null_audit_executable=False,
            replication_independent=False,
        )
        report = run_premerge_science_gate(docs_root=tmp_path, readiness=readiness)
        assert report.passed
        assert report.overclaim_hits == ()

    def test_catches_overclaim(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text(
            "# This is production-ready and trading signal\n",
            encoding="utf-8",
        )
        readiness = build_validation_readiness_report(
            score_level_executable=True,
            end_to_end_executable=False,
            real_data_run_executed=False,
            null_audit_executable=False,
            replication_independent=False,
        )
        report = run_premerge_science_gate(docs_root=tmp_path, readiness=readiness)
        assert not report.passed
        terms = {hit[1].lower().replace("-", "") for hit in report.overclaim_hits}
        assert "productionready" in terms
        assert "trading signal" in {hit[1].lower() for hit in report.overclaim_hits}

    def test_catches_inconsistent_readiness(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# Hypothesis instrument\n", encoding="utf-8")
        readiness = build_validation_readiness_report(
            score_level_executable=True,
            end_to_end_executable=True,
            real_data_run_executed=True,
            null_audit_executable=True,
            replication_independent=True,
        )
        report = run_premerge_science_gate(docs_root=tmp_path, readiness=readiness)
        assert not report.passed
        # Synthetic VALIDATED claim with no real evidence on disk → fail.
        assert any("over-claiming" in r for r in report.failure_reasons)

    def test_real_module_passes_overclaim_grep(self) -> None:
        # The actual research/systemic_risk/ tree under main MUST pass
        # the overclaim grep at the HYPOTHESIS / INSTRUMENTED tier.
        # This is the canonical CI gate for the module.
        readiness = build_validation_readiness_report(
            score_level_executable=True,
            end_to_end_executable=False,
            real_data_run_executed=False,
            null_audit_executable=False,
            replication_independent=False,
        )
        module_root = Path(__file__).resolve().parents[3] / "research" / "systemic_risk"
        report = run_premerge_science_gate(
            docs_root=module_root,
            readiness=readiness,
            grep_extensions=(".md", ".py"),
        )
        if report.overclaim_hits:
            details = "\n".join(f"  {p}: '{t}'" for p, t in report.overclaim_hits[:10])
            raise AssertionError(
                f"INV-OVERCLAIM VIOLATED: {len(report.overclaim_hits)} "
                f"overclaim term(s) found in research/systemic_risk/:\n{details}"
            )
        assert report.passed


class TestForbiddenTermsContent:
    def test_canonical_terms_present(self) -> None:
        joined = " ".join(FORBIDDEN_OVERCLAIM_TERMS).lower()
        for needle in (
            "production",
            "empirically established",
            "trading edge",
            "trading signal",
            "predictive system",
            "predicts crisis",
            "early-warning system",
            "proven",
            "confirmed",
        ):
            assert needle in joined, f"missing canonical term: {needle}"
