# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Bayesian evidence ledger tests."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from research.systemic_risk.evidence_ledger import (
    DEFAULT_PRIOR_LOG_ODDS,
    DOWNGRADE_TRIGGER_DELTA,
    KILL_TRIGGER_LOG_ODDS,
    Evidence,
    EvidenceLedger,
    auc_per_crisis_bayes_factor,
    baseline_dominance_bayes_factor,
    external_review_bayes_factor,
    replication_match_bayes_factor,
)


def _ts(offset_seconds: int = 0) -> str:
    base = datetime(2026, 5, 8, tzinfo=timezone.utc)
    return (base + timedelta(seconds=offset_seconds)).isoformat()


class TestBayesFactorCalculators:
    def test_auc_zero_five_yields_unity_bf(self) -> None:
        # AUC=0.5 is uninformative; BF must be 1.0.
        assert auc_per_crisis_bayes_factor(0.5, n_crises=10) == pytest.approx(1.0)

    def test_auc_above_half_favours_claim(self) -> None:
        bf = auc_per_crisis_bayes_factor(0.75, n_crises=4)
        assert bf > 1.0

    def test_auc_below_half_disfavours_claim(self) -> None:
        bf = auc_per_crisis_bayes_factor(0.25, n_crises=4)
        assert bf < 1.0

    def test_auc_invalid_rejected(self) -> None:
        with pytest.raises(ValueError, match="auc"):
            auc_per_crisis_bayes_factor(1.5, n_crises=4)
        with pytest.raises(ValueError, match="n_crises"):
            auc_per_crisis_bayes_factor(0.6, n_crises=0)

    def test_baseline_delta_zero_yields_unity(self) -> None:
        assert baseline_dominance_bayes_factor(0.0, n_pairs=4) == pytest.approx(1.0)

    def test_baseline_negative_delta_disfavours(self) -> None:
        # Candidate lost to baseline by 0.05 with n=4.
        bf = baseline_dominance_bayes_factor(-0.05, n_pairs=4)
        assert bf < 1.0

    def test_replication_match_is_strong(self) -> None:
        assert replication_match_bayes_factor(matched=True) == 100.0

    def test_replication_mismatch_is_zero_kill(self) -> None:
        assert replication_match_bayes_factor(matched=False) == 0.0

    def test_external_review_polarity(self) -> None:
        assert external_review_bayes_factor(positive=True) == 10.0
        assert external_review_bayes_factor(positive=False) == 0.1


class TestEvidenceConstruction:
    def test_negative_bf_rejected(self) -> None:
        with pytest.raises(ValueError, match="bayes_factor"):
            Evidence(
                timestamp_utc=_ts(),
                type="UNINFORMATIVE",
                bayes_factor=-0.1,
            )

    def test_inf_bf_rejected(self) -> None:
        with pytest.raises(ValueError, match="bayes_factor"):
            Evidence(
                timestamp_utc=_ts(),
                type="UNINFORMATIVE",
                bayes_factor=math.inf,
            )


class TestEvidenceLedger:
    def test_unseeded_claim_rejected(self) -> None:
        ledger = EvidenceLedger()
        with pytest.raises(ValueError, match="not seeded"):
            ledger.with_evidence(
                "C-X",
                Evidence(
                    timestamp_utc=_ts(),
                    type="UNINFORMATIVE",
                    bayes_factor=1.0,
                ),
            )

    def test_duplicate_seed_rejected(self) -> None:
        ledger = EvidenceLedger().with_claim("C-X")
        with pytest.raises(ValueError, match="already present"):
            ledger.with_claim("C-X")

    def test_seed_initialises_at_prior(self) -> None:
        ledger = EvidenceLedger().with_claim("C-X")
        entry = ledger.get("C-X")
        assert entry is not None
        assert entry.posterior_log_odds == DEFAULT_PRIOR_LOG_ODDS
        assert entry.evidence == ()
        assert entry.tier_action == "NONE"

    def test_uninformative_evidence_does_not_move_posterior(self) -> None:
        ledger = (
            EvidenceLedger()
            .with_claim("C-X")
            .with_evidence(
                "C-X",
                Evidence(timestamp_utc=_ts(), type="UNINFORMATIVE", bayes_factor=1.0),
            )
        )
        entry = ledger.get("C-X")
        assert entry is not None
        assert entry.posterior_log_odds == pytest.approx(DEFAULT_PRIOR_LOG_ODDS)

    def test_positive_auc_evidence_raises_posterior(self) -> None:
        bf = auc_per_crisis_bayes_factor(0.8, n_crises=3)
        ledger = (
            EvidenceLedger()
            .with_claim("C-X")
            .with_evidence(
                "C-X",
                Evidence(
                    timestamp_utc=_ts(),
                    type="AUC_PER_CRISIS",
                    bayes_factor=bf,
                    payload={"auc": 0.8, "n_crises": 3},
                ),
            )
        )
        entry = ledger.get("C-X")
        assert entry is not None
        assert entry.posterior_log_odds > DEFAULT_PRIOR_LOG_ODDS

    def test_kill_trigger_on_zero_bayes_factor(self) -> None:
        # Replication-mismatch evidence (BF=0) immediately kills the claim.
        ledger = (
            EvidenceLedger()
            .with_claim("C-X")
            .with_evidence(
                "C-X",
                Evidence(
                    timestamp_utc=_ts(),
                    type="REPLICATION_MISMATCH",
                    bayes_factor=0.0,
                ),
            )
        )
        entry = ledger.get("C-X")
        assert entry is not None
        assert entry.tier_action == "KILL"
        assert entry.posterior_probability == 0.0

    def test_demote_trigger_when_posterior_drops_below_prior(self) -> None:
        # Apply a slightly-disfavouring evidence: BF < 1 by a margin
        # that exceeds DOWNGRADE_TRIGGER_DELTA.
        bf = math.exp(-DOWNGRADE_TRIGGER_DELTA - 0.5)
        ledger = (
            EvidenceLedger()
            .with_claim("C-X")
            .with_evidence(
                "C-X",
                Evidence(
                    timestamp_utc=_ts(),
                    type="BASELINE_DOMINANCE",
                    bayes_factor=bf,
                ),
            )
        )
        entry = ledger.get("C-X")
        assert entry is not None
        assert entry.tier_action == "DEMOTE"

    def test_kill_trigger_at_low_posterior(self) -> None:
        # Apply a string of disfavouring evidence to drive the posterior
        # below KILL_TRIGGER_LOG_ODDS.
        ledger = EvidenceLedger().with_claim("C-X")
        for i in range(5):
            ledger = ledger.with_evidence(
                "C-X",
                Evidence(
                    timestamp_utc=_ts(i),
                    type="BASELINE_DOMINANCE",
                    bayes_factor=math.exp(-2.0),
                ),
            )
        entry = ledger.get("C-X")
        assert entry is not None
        assert entry.posterior_log_odds <= KILL_TRIGGER_LOG_ODDS
        assert entry.tier_action == "KILL"

    def test_chronological_order_enforced(self) -> None:
        ledger = (
            EvidenceLedger()
            .with_claim("C-X")
            .with_evidence(
                "C-X",
                Evidence(timestamp_utc=_ts(10), type="UNINFORMATIVE", bayes_factor=1.0),
            )
        )
        with pytest.raises(ValueError, match="strictly succeed"):
            ledger.with_evidence(
                "C-X",
                Evidence(
                    timestamp_utc=_ts(5),
                    type="UNINFORMATIVE",
                    bayes_factor=1.0,
                ),
            )

    def test_immutability_under_update(self) -> None:
        # The original ledger is not mutated; with_evidence returns a new one.
        original = EvidenceLedger().with_claim("C-X")
        assert original.get("C-X") is not None
        updated = original.with_evidence(
            "C-X",
            Evidence(timestamp_utc=_ts(), type="UNINFORMATIVE", bayes_factor=1.0),
        )
        assert original.get("C-X") is not None
        assert original.get("C-X").evidence == ()  # type: ignore[union-attr]
        assert len(updated.get("C-X").evidence) == 1  # type: ignore[union-attr]

    def test_posterior_probability_logistic_transform(self) -> None:
        ledger = EvidenceLedger().with_claim("C-X", prior_log_odds=0.0)
        entry = ledger.get("C-X")
        assert entry is not None
        assert entry.posterior_probability == pytest.approx(0.5)
