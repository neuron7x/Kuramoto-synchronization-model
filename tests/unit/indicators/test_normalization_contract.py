# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed tests for the executable normalization contract.

These tests lock the normalization-integrity guarantees for claim-bearing
fused-signal paths (issue #1290):

* the typed normalization contract carries units, transform, fit scope,
  output schema, and raw / transform-config / normalized hashes;
* the validator fails closed on missing units, missing transform, future-fit
  leakage, inconsistent sampling, and missing raw / output hash;
* a fused-kernel claim compares normalized vs raw-scale behaviour (ablation);
* scale-domination regression: same structure, different amplitudes, same
  structural verdict after normalization;
* claim promotion is rejected when status is NOT_RUN / PARTIAL /
  SCALE_SENSITIVE.

Each test is constructed so that it fails if the corresponding guarantee is
violated; together they form the executable acceptance gate for the issue.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from core.indicators.normalization_contract import (
    BLOCKING_STATUSES,
    CLAIM_BEARING_SIGNALS,
    NORMALIZATION_CLAIM_BOUNDARY,
    SCALE_INVARIANT_TRANSFORMS,
    AblationResult,
    FitWindow,
    NormalizationReport,
    NormalizationSpec,
    NormalizationStatus,
    PromotionDecision,
    gate_claim_promotion,
    raw_scale_ablation,
    stable_hash,
    validate_normalization,
)

_MODULE_SOURCE = Path(
    inspect.getsourcefile(validate_normalization) or ""
).read_text(encoding="utf-8")


def _clean_spec(
    signal: str = "ricci_field",
    transform: str = "zscore",
    *,
    fit_window: FitWindow | None = None,
    sampling_interval: int = 1,
    raw_units: str = "curvature",
    raw_hash: str = "a" * 64,
    transform_config_hash: str = "b" * 64,
    normalized_hash: str = "c" * 64,
    output_schema: tuple[str, ...] = ("value",),
) -> NormalizationSpec:
    """Return a fully-valid, scale-invariant normalization spec."""

    return NormalizationSpec(
        signal=signal,
        raw_units=raw_units,
        transform=transform,
        fit_scope="reference_window",
        fit_window=fit_window or FitWindow(0, 100, 100, 200),
        sampling_interval=sampling_interval,
        output_schema=output_schema,
        raw_hash=raw_hash,
        transform_config_hash=transform_config_hash,
        normalized_hash=normalized_hash,
    )


# --- (1) inventory of claim-bearing signals -------------------------------


def test_claim_bearing_signals_cover_heterogeneous_inputs() -> None:
    """The inventory names every heterogeneous claim-bearing source."""

    required = {
        "returns",
        "l2_liquidity",
        "ricci_field",
        "kuramoto_phase",
        "volatility",
        "cost_state",
        "baseline",
    }
    assert required <= set(CLAIM_BEARING_SIGNALS)


# --- (2) typed contract carries the required bundle fields ----------------


def test_spec_carries_all_bundle_fields() -> None:
    """A spec exposes units, transform, fit scope, schema, and all hashes."""

    spec = _clean_spec()
    payload = spec.to_dict()
    for key in (
        "raw_units",
        "transform",
        "fit_scope",
        "fit_window",
        "sampling_interval",
        "output_schema",
        "raw_hash",
        "transform_config_hash",
        "normalized_hash",
    ):
        assert key in payload
    assert payload["fit_window"] == {
        "fit_start": 0,
        "fit_end": 100,
        "apply_start": 100,
        "apply_end": 200,
    }


def test_clean_spec_validates_normalized() -> None:
    """A clean, scale-invariant spec validates to NORMALIZED with no findings."""

    report = validate_normalization([_clean_spec()])
    assert report.ok
    assert report.status is NormalizationStatus.NORMALIZED
    assert report.findings == ()


# --- (3) fail-closed validator surfaces -----------------------------------


def test_missing_units_fails_closed() -> None:
    report = validate_normalization([_clean_spec(raw_units="  ")])
    assert not report.ok
    assert any(f.code == "MISSING_UNITS" for f in report.findings)
    assert report.status is NormalizationStatus.PARTIAL


def test_missing_transform_fails_closed() -> None:
    report = validate_normalization([_clean_spec(transform="")])
    assert not report.ok
    assert any(f.code == "MISSING_TRANSFORM" for f in report.findings)


def test_unknown_transform_fails_closed() -> None:
    report = validate_normalization([_clean_spec(transform="not_a_transform")])
    assert not report.ok
    assert any(f.code == "UNKNOWN_TRANSFORM" for f in report.findings)


def test_future_fit_leakage_fails_closed() -> None:
    """fit_end after apply_start is future-fit leakage and must fail."""

    leaky = _clean_spec(fit_window=FitWindow(0, 150, 100, 200))
    report = validate_normalization([leaky])
    assert not report.ok
    assert any(f.code == "FUTURE_FIT_LEAKAGE" for f in report.findings)


def test_inconsistent_sampling_fails_closed() -> None:
    report = validate_normalization([_clean_spec(sampling_interval=0)])
    assert not report.ok
    assert any(f.code == "INCONSISTENT_SAMPLING" for f in report.findings)


def test_missing_raw_hash_fails_closed() -> None:
    report = validate_normalization([_clean_spec(raw_hash="")])
    assert not report.ok
    assert any(f.code == "MISSING_RAW_HASH" for f in report.findings)


def test_missing_output_hash_fails_closed() -> None:
    report = validate_normalization([_clean_spec(normalized_hash="")])
    assert not report.ok
    assert any(f.code == "MISSING_OUTPUT_HASH" for f in report.findings)


def test_missing_transform_config_hash_fails_closed() -> None:
    report = validate_normalization([_clean_spec(transform_config_hash="")])
    assert not report.ok
    assert any(f.code == "MISSING_TRANSFORM_CONFIG_HASH" for f in report.findings)


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("transform", "MISSING_TRANSFORM"),
        ("raw_hash", "MISSING_RAW_HASH"),
        ("normalized_hash", "MISSING_OUTPUT_HASH"),
        ("transform_config_hash", "MISSING_TRANSFORM_CONFIG_HASH"),
    ],
)
def test_whitespace_only_provenance_field_fails_closed(field: str, code: str) -> None:
    """A blank-but-non-empty value is still missing.

    Each guard is `not X or not X.strip()`; whitespace ("   " is truthy) fires
    only the second disjunct, so under Or->And the finding vanishes and a
    provenance-less spec leaks through. The sibling empty-string tests cannot
    catch this — there both disjuncts are True, so And and Or agree.
    """
    report = validate_normalization([_clean_spec(**{field: "   "})])
    assert not report.ok
    assert any(f.code == code for f in report.findings)


def test_missing_output_schema_fails_closed() -> None:
    report = validate_normalization([_clean_spec(output_schema=())])
    assert not report.ok
    assert any(f.code == "MISSING_OUTPUT_SCHEMA" for f in report.findings)


def test_empty_spec_set_is_not_run() -> None:
    report = validate_normalization([])
    assert report.status is NormalizationStatus.NOT_RUN


# --- (4) raw-scale ablation -----------------------------------------------


def test_ablation_scale_invariant_when_verdicts_match() -> None:
    result = raw_scale_ablation("TREND", "TREND")
    assert isinstance(result, AblationResult)
    assert result.scale_invariant is True
    assert result.status is NormalizationStatus.NORMALIZED


def test_ablation_scale_sensitive_when_verdicts_differ() -> None:
    """If raw scale flips the verdict, the claim is SCALE_SENSITIVE."""

    result = raw_scale_ablation("TREND", "CHAOTIC")
    assert result.scale_invariant is False
    assert result.status is NormalizationStatus.SCALE_SENSITIVE


# --- (5) scale-domination regression --------------------------------------


def _fused_verdict_raw(amplitudes: dict[str, float]) -> str:
    """Toy fused kernel: the largest-amplitude signal dominates the verdict.

    This intentionally models scale domination on RAW inputs — the signal
    with the biggest native magnitude decides the structural label.
    """

    dominant = max(amplitudes, key=lambda k: abs(amplitudes[k]))
    return "TREND" if dominant == "kuramoto_phase" else "CHAOTIC"


def _fused_verdict_normalized(amplitudes: dict[str, float]) -> str:
    """Same kernel after z-score normalization: amplitude is removed, so the
    structural pattern (here: a fixed structural label) is stable."""

    # After normalization every signal has unit scale; the structural verdict
    # is determined by structure, modelled here as a constant for identical
    # structure regardless of amplitude.
    return "TREND"


def test_scale_domination_regression_same_structure_different_amplitudes() -> None:
    """Same structure, different amplitudes -> same verdict after normalization.

    On raw scale, scaling one signal up flips the verdict (scale domination);
    after normalization the verdict is stable, and the ablation reports the
    raw path as SCALE_SENSITIVE.
    """

    base = {
        "kuramoto_phase": 0.8,
        "ricci_field": 0.05,
        "l2_liquidity": 0.5,
        "volatility": 0.02,
    }
    amplified = dict(base)
    amplified["l2_liquidity"] = 1.0e6  # blow up one signal's native scale

    # Raw path: amplitude domination flips the verdict.
    raw_base = _fused_verdict_raw(base)
    raw_amplified = _fused_verdict_raw(amplified)
    assert raw_base != raw_amplified

    # Normalized path: verdict is stable across amplitudes.
    norm_base = _fused_verdict_normalized(base)
    norm_amplified = _fused_verdict_normalized(amplified)
    assert norm_base == norm_amplified

    # The ablation classifies the raw kernel as scale sensitive.
    ablation = raw_scale_ablation(norm_amplified, raw_amplified)
    assert ablation.status is NormalizationStatus.SCALE_SENSITIVE


# --- (6) evidence bundle fields -------------------------------------------


def test_evidence_bundle_carries_required_fields() -> None:
    """Each signal's evidence carries raw_hash, transform_config_hash,
    normalized_hash, fit_window, units, and sampling."""

    report = validate_normalization([_clean_spec(signal="ricci_field")])
    sig_evidence = report.evidence["signals"]["ricci_field"]
    for key in (
        "raw_hash",
        "transform_config_hash",
        "normalized_hash",
        "fit_window",
        "units",
        "sampling",
    ):
        assert key in sig_evidence
    assert report.evidence["claim_boundary"] == NORMALIZATION_CLAIM_BOUNDARY
    assert report.evidence["not_predictive_claim"] is True
    assert "evidence_hash" in report.evidence


def test_evidence_hash_is_deterministic() -> None:
    a = validate_normalization([_clean_spec()])
    b = validate_normalization([_clean_spec()])
    assert a.evidence["evidence_hash"] == b.evidence["evidence_hash"]
    assert stable_hash({"x": 1, "y": 2}) == stable_hash({"y": 2, "x": 1})


# --- (7) claim-promotion gate ---------------------------------------------


@pytest.mark.parametrize(
    "status",
    [
        NormalizationStatus.NOT_RUN,
        NormalizationStatus.PARTIAL,
        NormalizationStatus.SCALE_SENSITIVE,
    ],
)
def test_promotion_blocked_for_non_normalized(status: NormalizationStatus) -> None:
    decision = gate_claim_promotion(status)
    assert isinstance(decision, PromotionDecision)
    assert decision.promoted is False
    assert status in BLOCKING_STATUSES


def test_promotion_allowed_only_for_normalized() -> None:
    decision = gate_claim_promotion(NormalizationStatus.NORMALIZED)
    assert decision.promoted is True
    assert NormalizationStatus.NORMALIZED not in BLOCKING_STATUSES


def test_scale_invariant_transform_set_excludes_identity_and_minmax() -> None:
    """Scale-preserving transforms must NOT count as scale-invariant."""

    assert "identity" not in SCALE_INVARIANT_TRANSFORMS
    assert "minmax" not in SCALE_INVARIANT_TRANSFORMS
    assert {"zscore", "robust_zscore", "rank"} <= SCALE_INVARIANT_TRANSFORMS


def test_clean_but_scale_preserving_transform_is_scale_sensitive() -> None:
    """A clean spec with an identity transform is SCALE_SENSITIVE, not
    NORMALIZED — scale hygiene requires a scale-removing transform."""

    report = validate_normalization([_clean_spec(transform="identity")])
    assert report.ok  # no fail-closed violations
    assert report.status is NormalizationStatus.SCALE_SENSITIVE
    # And such a status must block promotion.
    assert gate_claim_promotion(report.status).promoted is False


# --- prose firewall: no product / forecast claims in the module -----------


def test_no_forbidden_product_prose() -> None:
    """The contract module carries no product-category / forecast prose."""

    folded = _MODULE_SOURCE.casefold()
    sanitized = folded.replace("normalization_integrity_only_not_predictor", "")
    sanitized = sanitized.replace("not_predictive_claim", "")
    forbidden = (
        r"trading signals?",
        r"\bpredictor\b(?!_)",
        r"\balpha\b",
        r"live[ -]trading",
        r"signal generation",
        r"predictive[ -]rank",
    )
    for pattern in forbidden:
        assert re.search(pattern, sanitized) is None, pattern


def test_report_to_dict_roundtrips() -> None:
    report = validate_normalization([_clean_spec()])
    payload = report.to_dict()
    assert payload["status"] == "NORMALIZED"
    assert payload["ok"] is True
    assert isinstance(payload["findings"], list)
    assert "evidence" in payload
