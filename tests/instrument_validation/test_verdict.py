# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""G3, G4 — emit_verdict OUT_OF_SCOPE / INVALID_INSTRUMENT chokepoints."""

from __future__ import annotations

from instrument_validation.discrimination import (
    DiscriminationReport,
    DiscriminationVerdict,
)
from instrument_validation.negative_control import (
    REQUIRED_NULLS,
    NegativeControlCertificate,
)
from instrument_validation.positive_control import PosControlCertificate
from instrument_validation.scope import country_aggregate_default_scope
from instrument_validation.verdict import (
    ClaimTier,
    ClaimType,
    Verdict,
    emit_verdict,
)


def _ok_pos(scope_id: str) -> PosControlCertificate:
    return PosControlCertificate(
        instrument_id=scope_id,
        n_runs=500,
        detection_power={
            "BA_vs_ER": 0.85,
            "BA_vs_CM": 0.7,
            "BA_vs_HUB": 0.6,
            "BA_vs_GINI": 0.5,
        },
        false_positive_rate={"ER": 0.04, "CM": 0.03},
        passed=True,
        failure_reason=None,
        cert_id="a" * 64,
    )


def _ok_neg(scope_id: str) -> NegativeControlCertificate:
    return NegativeControlCertificate(
        instrument_id=scope_id,
        n_runs_per_family=500,
        fpr_per_family={k: 0.01 for k in REQUIRED_NULLS},
        max_observed_fpr=0.01,
        families=REQUIRED_NULLS,
        passed=True,
        failure_reason=None,
        cert_id="b" * 64,
    )


def _empty_report() -> DiscriminationReport:
    return DiscriminationReport(
        metrics=tuple(),
        n_metrics_favor_ba=0,
        n_metrics_favor_er=0,
        n_metrics_not_distinguished=0,
        n_metrics_insufficient=0,
        bonferroni_k=6,
        aggregate_verdict=DiscriminationVerdict.NOT_DISTINGUISHED,
    )


def test_emit_out_of_scope_when_n_too_large() -> None:
    """G4."""
    scope = country_aggregate_default_scope()
    out = emit_verdict(
        scope=scope,
        pos_cert=_ok_pos(scope.instrument_id),
        neg_cert=_ok_neg(scope.instrument_id),
        discrimination=None,
        runtime_substrate=scope.valid_for_substrate,
        runtime_n=8000,
        runtime_density=0.15,
    )
    assert out.verdict is Verdict.OUT_OF_SCOPE
    assert out.claim_tier is ClaimTier.INVALID_INSTRUMENT


def test_emit_out_of_scope_on_substrate_mismatch() -> None:
    scope = country_aggregate_default_scope()
    out = emit_verdict(
        scope=scope,
        pos_cert=_ok_pos(scope.instrument_id),
        neg_cert=_ok_neg(scope.instrument_id),
        discrimination=None,
        runtime_substrate="bank_level",
        runtime_n=31,
        runtime_density=0.15,
    )
    assert out.verdict is Verdict.OUT_OF_SCOPE


def test_emit_invalid_instrument_when_pos_cert_missing() -> None:
    """G3."""
    scope = country_aggregate_default_scope()
    out = emit_verdict(
        scope=scope,
        pos_cert=None,
        neg_cert=_ok_neg(scope.instrument_id),
        discrimination=None,
        runtime_substrate=scope.valid_for_substrate,
        runtime_n=31,
        runtime_density=0.15,
    )
    assert out.verdict is Verdict.INVALID_INSTRUMENT


def test_emit_invalid_instrument_when_neg_cert_missing() -> None:
    scope = country_aggregate_default_scope()
    out = emit_verdict(
        scope=scope,
        pos_cert=_ok_pos(scope.instrument_id),
        neg_cert=None,
        discrimination=None,
        runtime_substrate=scope.valid_for_substrate,
        runtime_n=31,
        runtime_density=0.15,
    )
    assert out.verdict is Verdict.INVALID_INSTRUMENT


def test_descriptive_topology_passes_when_certs_present() -> None:
    scope = country_aggregate_default_scope()
    out = emit_verdict(
        scope=scope,
        pos_cert=_ok_pos(scope.instrument_id),
        neg_cert=_ok_neg(scope.instrument_id),
        discrimination=None,
        runtime_substrate=scope.valid_for_substrate,
        runtime_n=31,
        runtime_density=0.15,
        claim_type=ClaimType.DESCRIPTIVE_TOPOLOGY,
    )
    assert out.verdict is Verdict.PASS
    assert out.claim_tier is ClaimTier.EXPLORATORY_DESCRIPTIVE


def test_generative_mechanism_requires_discrimination_report() -> None:
    scope = country_aggregate_default_scope()
    out = emit_verdict(
        scope=scope,
        pos_cert=_ok_pos(scope.instrument_id),
        neg_cert=_ok_neg(scope.instrument_id),
        discrimination=None,
        runtime_substrate=scope.valid_for_substrate,
        runtime_n=31,
        runtime_density=0.15,
        claim_type=ClaimType.GENERATIVE_MECHANISM,
    )
    assert out.verdict is Verdict.INVALID_INSTRUMENT


def test_generative_mechanism_not_distinguished() -> None:
    scope = country_aggregate_default_scope()
    out = emit_verdict(
        scope=scope,
        pos_cert=_ok_pos(scope.instrument_id),
        neg_cert=_ok_neg(scope.instrument_id),
        discrimination=_empty_report(),
        runtime_substrate=scope.valid_for_substrate,
        runtime_n=31,
        runtime_density=0.15,
        claim_type=ClaimType.GENERATIVE_MECHANISM,
    )
    assert out.verdict is Verdict.NOT_DISTINGUISHED
    assert out.claim_tier is ClaimTier.NOT_DISTINGUISHED


def test_descriptive_emission_blocked_when_pos_cert_failed() -> None:
    """Iter-4 hardening: even DESCRIPTIVE_TOPOLOGY claims require a
    pos_cert with passed=True. A failed certificate means the instrument
    has not proven discriminative capacity and must NOT emit any verdict.
    """
    scope = country_aggregate_default_scope()
    failed_pos = PosControlCertificate(
        instrument_id=scope.instrument_id,
        n_runs=500,
        detection_power={
            "BA_vs_ER": 0.10,  # below 0.80
            "BA_vs_CM": 0.10,
            "BA_vs_HUB": 0.10,
            "BA_vs_GINI": 0.10,
        },
        false_positive_rate={"ER": 0.04, "CM": 0.03},
        passed=False,
        failure_reason="detection_power < 0.80 on every contrast",
        cert_id="c" * 64,
    )
    out = emit_verdict(
        scope=scope,
        pos_cert=failed_pos,
        neg_cert=_ok_neg(scope.instrument_id),
        discrimination=None,
        runtime_substrate=scope.valid_for_substrate,
        runtime_n=31,
        runtime_density=0.15,
        claim_type=ClaimType.DESCRIPTIVE_TOPOLOGY,
    )
    assert out.verdict is Verdict.INVALID_INSTRUMENT
    assert out.claim_tier is ClaimTier.INVALID_INSTRUMENT


def test_liquidity_contagion_blocked_under_country_aggregate() -> None:
    scope = country_aggregate_default_scope()
    out = emit_verdict(
        scope=scope,
        pos_cert=_ok_pos(scope.instrument_id),
        neg_cert=_ok_neg(scope.instrument_id),
        discrimination=None,
        runtime_substrate=scope.valid_for_substrate,
        runtime_n=31,
        runtime_density=0.15,
        claim_type=ClaimType.LIQUIDITY_CONTAGION_MODEL,
    )
    assert out.verdict is Verdict.OUT_OF_SCOPE
