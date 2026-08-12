# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
# no-bio-claim
"""Tests for the PNCC evidence ledger.

Invariants exercised:

- ``INV-NO-BIO-CLAIM`` (P0, universal) — naked cognitive-performance
  language without an associated EvidenceClaim or disclaimer is a
  contract violation.
- ``INV-HPC1`` (universal) — claim hashing is deterministic and
  collision-resistant on field changes.
- Validation is fail-closed (n < 30, NaN/Inf, inverted CI, p∉[0,1]).

The file itself is allow-listed (``no-bio-claim`` header line) and is
also a test file under ``tests/`` — the AST-grep guard skips both by
construction.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tacl.evidence_ledger import (
    DEFAULT_DISCLAIMER_PHRASES,
    DEFAULT_FORBIDDEN_PATTERNS,
    BioClaimViolation,
    DecisionSignalKind,
    EvidenceClaim,
    EvidenceRegistry,
    HypothesisId,
    StatTest,
    claim_hash,
    scan_source_for_bio_claims,
    validate_claim,
)

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


_FIXED_TS: Final[int] = 1_700_000_000_000_000_000


def _stat_test(p: float = 0.01, t: float = 4.2, df: float | None = 60.0) -> StatTest:
    return StatTest(test_name="two-sample t-test", test_statistic=t, p_value=p, df=df)


def _claim(
    *,
    hypothesis: HypothesisId = HypothesisId.HYP_1_DECISION_LATENCY,
    baseline_mean: float = 100.0,
    baseline_std: float = 12.0,
    baseline_n: int = 32,
    intervention_mean: float = 92.0,
    intervention_std: float = 11.0,
    intervention_n: int = 33,
    effect_size: float = -0.7,
    ci_95_low: float = -1.1,
    ci_95_high: float = -0.3,
    stat_test: StatTest | None = None,
    registered_at_ns: int = _FIXED_TS,
    pre_registered: bool = True,
    notes: str | None = None,
    substrate_criticality_at_decision: float | None = None,
    criticality_window_confirmed: bool = False,
    signal: DecisionSignalKind = "NORMAL",
) -> EvidenceClaim:
    return EvidenceClaim(
        hypothesis=hypothesis,
        baseline_mean=baseline_mean,
        baseline_std=baseline_std,
        baseline_n=baseline_n,
        intervention_mean=intervention_mean,
        intervention_std=intervention_std,
        intervention_n=intervention_n,
        effect_size=effect_size,
        ci_95_low=ci_95_low,
        ci_95_high=ci_95_high,
        stat_test=stat_test if stat_test is not None else _stat_test(),
        registered_at_ns=registered_at_ns,
        pre_registered=pre_registered,
        notes=notes,
        substrate_criticality_at_decision=substrate_criticality_at_decision,
        criticality_window_confirmed=criticality_window_confirmed,
        signal=signal,
    )


# ---------------------------------------------------------------------------
# Hashing — INV-HPC1
# ---------------------------------------------------------------------------


def test_claim_hash_deterministic() -> None:
    """INV-HPC1: identical EvidenceClaim inputs yield identical hashes (3 reps)."""
    claim = _claim()
    h1 = claim_hash(claim)
    h2 = claim_hash(claim)
    h3 = claim_hash(_claim())
    msg_repeat = (
        f"INV-HPC1 VIOLATED: hash(claim) not deterministic on repeated call h1={h1} h2={h2}"
    )
    assert h1 == h2, msg_repeat
    msg_rebuild = (
        "INV-HPC1 VIOLATED: hash(claim) not deterministic across "
        f"identical re-construction h1={h1} h3={h3}"
    )
    assert h1 == h3, msg_rebuild
    assert len(h1) == 64
    assert all(c in "0123456789abcdef" for c in h1)


def test_claim_hash_changes_on_field_change() -> None:
    """Hash must differ for any single-field change (collision resistance)."""
    base = _claim()
    base_h = claim_hash(base)
    perturbed = (
        _claim(baseline_mean=100.5),
        _claim(baseline_std=12.5),
        _claim(baseline_n=33),
        _claim(intervention_mean=92.5),
        _claim(intervention_std=11.5),
        _claim(intervention_n=34),
        _claim(effect_size=-0.71),
        _claim(ci_95_low=-1.2),
        _claim(ci_95_high=-0.29),
        _claim(stat_test=_stat_test(p=0.02)),
        _claim(stat_test=_stat_test(t=4.3)),
        _claim(stat_test=_stat_test(df=61.0)),
        _claim(registered_at_ns=_FIXED_TS + 1),
        _claim(pre_registered=False),
        _claim(notes="alt"),
        _claim(hypothesis=HypothesisId.HYP_2_ERROR_RECOVERY),
    )
    seen: set[str] = {base_h}
    for variant in perturbed:
        h = claim_hash(variant)
        assert h != base_h, f"hash collision: variant matched base ({h})"
        assert h not in seen, f"hash collision among variants: {h}"
        seen.add(h)


# ---------------------------------------------------------------------------
# Validation — fail-closed
# ---------------------------------------------------------------------------


def test_validate_rejects_n_below_threshold() -> None:
    """Universal: any arm with n < 30 is rejected."""
    too_small_baseline = _claim(baseline_n=29)
    ok_b, reason_b = validate_claim(too_small_baseline)
    assert not ok_b, "validate accepted baseline_n=29 < 30"
    assert reason_b is not None and "baseline_n" in reason_b

    too_small_intervention = _claim(intervention_n=29)
    ok_i, reason_i = validate_claim(too_small_intervention)
    assert not ok_i, "validate accepted intervention_n=29 < 30"
    assert reason_i is not None and "intervention_n" in reason_i

    valid = _claim(baseline_n=30, intervention_n=30)
    ok_v, _ = validate_claim(valid)
    assert ok_v, "validate rejected n=30 at floor"


def test_validate_rejects_nan_inf() -> None:
    """Universal: any non-finite numeric in the claim is rejected."""
    nan = float("nan")
    inf = float("inf")
    bad_means = (
        _claim(baseline_mean=nan),
        _claim(intervention_mean=inf),
        _claim(baseline_std=nan),
        _claim(intervention_std=inf),
        _claim(effect_size=nan),
        _claim(ci_95_low=-inf),
        _claim(ci_95_high=inf),
        _claim(stat_test=_stat_test(t=nan)),
        _claim(stat_test=_stat_test(p=nan)),
        _claim(stat_test=_stat_test(df=inf)),
    )
    for c in bad_means:
        ok, reason = validate_claim(c)
        assert not ok, f"validate accepted non-finite claim: {c}"
        assert reason is not None and "non-finite" in reason


def test_validate_rejects_inverted_ci() -> None:
    """Universal: ci_95_low > ci_95_high is invalid."""
    inverted = _claim(ci_95_low=0.5, ci_95_high=-0.5)
    ok, reason = validate_claim(inverted)
    assert not ok, "validate accepted inverted CI"
    assert reason is not None and "inverted CI" in reason


def test_validate_rejects_p_value_out_of_unit_interval() -> None:
    """Universal: p_value must be in [0, 1]."""
    for p in (-0.0001, -1.0, 1.0001, 5.0):
        c = _claim(stat_test=_stat_test(p=p))
        ok, reason = validate_claim(c)
        assert not ok, f"validate accepted p_value={p}"
        assert reason is not None and "p_value" in reason

    for p in (0.0, 0.5, 1.0):
        c = _claim(stat_test=_stat_test(p=p))
        ok, _ = validate_claim(c)
        assert ok, f"validate rejected legal p_value={p}"


def test_validate_accepts_negative_effect_size() -> None:
    """Qualitative: negative effect sizes (HYP rejection) are valid claims.

    The ledger MUST persist refuted hypotheses; refusing them would
    bias the corpus toward positive findings.
    """
    rejected = _claim(effect_size=-1.5, ci_95_low=-2.0, ci_95_high=-1.0)
    ok, reason = validate_claim(rejected)
    assert ok, f"validate rejected negative-effect (HYP rejection) claim: {reason}"


def test_validate_rejects_zero_std_with_nonzero_effect() -> None:
    """Universal: a degenerate constant arm cannot anchor a non-zero effect."""
    c = _claim(baseline_std=0.0, effect_size=-0.5)
    ok, reason = validate_claim(c)
    assert not ok, "validate accepted zero std with non-zero effect"
    assert reason is not None and "zero std" in reason


# ---------------------------------------------------------------------------
# Registry behaviour
# ---------------------------------------------------------------------------


def test_register_appends_immutable_entry() -> None:
    """Universal: register returns a frozen LedgerEntry referencing the claim."""
    registry = EvidenceRegistry()
    claim = _claim()
    entry = registry.register(claim)
    assert entry.claim is claim
    assert entry.claim_hash == claim_hash(claim)
    assert entry.appended_at_ns > 0
    # Frozen: cannot mutate
    with pytest.raises(Exception):
        entry.claim_hash = "tampered"  # type: ignore[misc]
    # Idempotent on re-register
    entry2 = registry.register(claim)
    assert entry2 is entry
    assert len(registry) == 1


def test_register_rejects_invalid_claim() -> None:
    """Universal: invalid claims raise ValueError on register (fail-closed)."""
    registry = EvidenceRegistry()
    bad = _claim(baseline_n=5)
    with pytest.raises(ValueError, match="baseline_n"):
        registry.register(bad)
    assert len(registry) == 0


def test_query_returns_only_matching_hypothesis() -> None:
    """Algebraic: query is exact selection by HypothesisId."""
    registry = EvidenceRegistry()
    h1 = registry.register(_claim(hypothesis=HypothesisId.HYP_1_DECISION_LATENCY))
    h2 = registry.register(
        _claim(
            hypothesis=HypothesisId.HYP_2_ERROR_RECOVERY,
            registered_at_ns=_FIXED_TS + 1,
        )
    )
    h3 = registry.register(
        _claim(
            hypothesis=HypothesisId.HYP_3_CNS_SCHEDULING,
            registered_at_ns=_FIXED_TS + 2,
        )
    )

    got_1 = registry.query(HypothesisId.HYP_1_DECISION_LATENCY)
    assert got_1 == (h1,)
    got_2 = registry.query(HypothesisId.HYP_2_ERROR_RECOVERY)
    assert got_2 == (h2,)
    got_3 = registry.query(HypothesisId.HYP_3_CNS_SCHEDULING)
    assert got_3 == (h3,)
    got_4 = registry.query(HypothesisId.HYP_4_COMPUTE_COST)
    assert got_4 == ()


def test_to_json_from_json_roundtrip_byte_identical() -> None:
    """Algebraic: serialize → deserialize → serialize is byte-identical."""
    registry = EvidenceRegistry(horizon_days=90)
    registry.register(_claim(hypothesis=HypothesisId.HYP_1_DECISION_LATENCY))
    registry.register(
        _claim(
            hypothesis=HypothesisId.HYP_5_COMBINED_LOOP,
            registered_at_ns=_FIXED_TS + 7,
        )
    )

    payload_a = registry.to_json()
    rebuilt = EvidenceRegistry.from_json(payload_a)
    payload_b = rebuilt.to_json()
    msg_roundtrip = f"roundtrip not byte-identical:\n  a={payload_a}\n  b={payload_b}"
    assert payload_a == payload_b, msg_roundtrip
    # Hashes preserved exactly
    a_entries = registry.snapshot().entries
    b_entries = rebuilt.snapshot().entries
    assert len(a_entries) == len(b_entries) == 2
    for ea, eb in zip(a_entries, b_entries, strict=True):
        assert ea.claim_hash == eb.claim_hash
        assert ea.claim == eb.claim


def test_from_json_detects_tampered_hash() -> None:
    """Universal: tampering with claim_hash on disk is detected on load."""
    registry = EvidenceRegistry()
    registry.register(_claim())
    payload = registry.to_json()
    tampered = payload.replace(
        '"claim_hash":"',
        '"claim_hash":"00',
        1,
    )
    if tampered == payload:
        pytest.skip("could not synthesize tampered payload")
    with pytest.raises(ValueError, match="claim_hash mismatch"):
        EvidenceRegistry.from_json(tampered)


# ---------------------------------------------------------------------------
# AST-grep guard — INV-NO-BIO-CLAIM
# ---------------------------------------------------------------------------


def test_scan_source_detects_naked_cognitive_claim(tmp_path: Path) -> None:
    """Universal: a naked claim in non-test source is flagged."""
    target = tmp_path / "marketing_copy.py"
    target.write_text(
        '"""Module copy."""\nMESSAGE = \'enhance focus by 30 percent\'\n',
        encoding="utf-8",
    )
    violations = scan_source_for_bio_claims([target])
    assert len(violations) >= 1
    v = violations[0]
    assert isinstance(v, BioClaimViolation)
    assert v.line_no == 2
    assert "enhance" in v.snippet.lower()


def test_scan_source_skips_disclaimer_lines(tmp_path: Path) -> None:
    """Universal: lines containing an allowed disclaimer phrase are ignored."""
    target = tmp_path / "honest_copy.py"
    # Each line contains BOTH a forbidden pattern AND a disclaimer.
    body = (
        '"""Module copy."""\n'
        "MSG_A = 'this product does NOT enhance focus'  # disclaimer present\n"
        "MSG_B = 'we make no claim of improving cognition'\n"
        "MSG_C = 'no causal: enhance memory in users'\n"
    )
    target.write_text(body, encoding="utf-8")
    violations = scan_source_for_bio_claims([target])
    assert violations == [], f"disclaimer lines were flagged: {violations}"


def test_scan_source_skips_test_files(tmp_path: Path) -> None:
    """Universal: any file under a tests/ tree or named test_*.py is skipped."""
    nested_test = tmp_path / "tests" / "test_module.py"
    nested_test.parent.mkdir()
    nested_test.write_text(
        "TEST_INPUT = 'enhance focus 5x productivity'\n",
        encoding="utf-8",
    )
    flat_test = tmp_path / "test_other.py"
    flat_test.write_text(
        "TEST_INPUT_2 = 'boost memory'\n",
        encoding="utf-8",
    )
    violations = scan_source_for_bio_claims([nested_test, flat_test])
    assert violations == []


def test_scan_source_skips_evidence_claim_referenced_lines(tmp_path: Path) -> None:
    """Algebraic: a forbidden phrase within ``reference_window`` lines of an
    EvidenceClaim/HypothesisId/HYP-N reference is treated as anchored."""
    target = tmp_path / "anchored.py"
    target.write_text(
        '"""Anchored copy."""\n'
        "# See EvidenceClaim for HYP-1 below.\n"
        "MSG = 'enhance focus measurement'\n"
        "# claim object instantiated above; HYP-1 ref already in window\n",
        encoding="utf-8",
    )
    violations = scan_source_for_bio_claims([target])
    assert violations == [], f"anchored claim was flagged: {violations}"


def test_scan_source_default_patterns_and_phrases_nonempty() -> None:
    """Sanity: defaults are populated (would otherwise vacuously pass)."""
    assert len(DEFAULT_FORBIDDEN_PATTERNS) >= 5
    assert len(DEFAULT_DISCLAIMER_PHRASES) >= 5


# ---------------------------------------------------------------------------
# Self-scan meta-test
# ---------------------------------------------------------------------------


_SIBLING_PNCC_FILES: Final[tuple[str, ...]] = (
    "core/physics/thermodynamic_budget.py",
    "core/physics/mpemba_initializer.py",
    "core/physics/reversible_gate.py",
    "tacl/cns_proxy_adapter.py",
)


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "tacl" / "evidence_ledger.py").is_file():
            return parent
    raise RuntimeError("could not locate repo root from test file")


def test_self_scan_finds_zero_naked_violations_in_pncc_modules() -> None:
    """Universal: every PNCC source file is either disclaimer-anchored
    or claim-anchored. Sibling modules may not exist yet (branch ordering)
    — this is the ONLY skip allowed in the suite.
    """
    root = _repo_root()
    targets: list[Path] = [root / "tacl" / "evidence_ledger.py"]
    for rel in _SIBLING_PNCC_FILES:
        candidate = root / rel
        if candidate.is_file():
            targets.append(candidate)

    if len(targets) == 1:
        # Only this PR's file exists — still a meaningful single-target check,
        # but flag the sibling-pre-existence skip explicitly.
        pytest.skip(
            "sibling PNCC modules not present yet (branch ordering); "
            "self-scan exercised over evidence_ledger.py only"
        )

    violations = scan_source_for_bio_claims(targets)
    assert violations == [], (
        "INV-NO-BIO-CLAIM VIOLATED: "
        f"{len(violations)} naked claims in PNCC modules {targets}: "
        f"{violations}"
    )


def test_self_scan_evidence_ledger_module_clean() -> None:
    """Universal: this PR's evidence_ledger.py is free of naked claims."""
    root = _repo_root()
    target = root / "tacl" / "evidence_ledger.py"
    assert target.is_file()
    violations = scan_source_for_bio_claims([target])
    assert violations == [], (
        "INV-NO-BIO-CLAIM VIOLATED in evidence_ledger.py: "
        f"{len(violations)} naked claims: {violations}"
    )


# ---------------------------------------------------------------------------
# INV-CRITICALITY (P0, universal)
# γ = 2H+1 (DFA-1). Substrate intelligence-capable iff γ ∈ [1−ε, 1+ε].
# Outside the metastable window any non-DORMANT signal is rejected.
# Refs: Bak 1996; Langton 1990; Mora-Bialek 2011; Beggs-Plenz 2003.
# ---------------------------------------------------------------------------


def test_legacy_claim_without_criticality_field_validates() -> None:
    """Legacy: γ=None ⇒ INV-CRITICALITY bypassed; pre-existing claims still valid."""
    claim = _claim()
    ok, reason = validate_claim(claim)
    assert ok is True, reason
    assert claim.substrate_criticality_at_decision is None
    assert claim.criticality_window_confirmed is False
    assert claim.signal == "NORMAL"


def test_criticality_confirmed_with_normal_signal_valid() -> None:
    """γ in window AND confirmed=True ⇒ NORMAL signal is admissible."""
    claim = _claim(
        substrate_criticality_at_decision=1.0,
        criticality_window_confirmed=True,
        signal="NORMAL",
    )
    ok, reason = validate_claim(claim)
    assert ok is True, reason


def test_criticality_not_confirmed_dormant_signal_valid() -> None:
    """Outside-window claim is admissible iff signal=DORMANT (fail-closed exit)."""
    claim = _claim(
        substrate_criticality_at_decision=1.7,
        criticality_window_confirmed=False,
        signal="DORMANT",
    )
    ok, reason = validate_claim(claim)
    assert ok is True, reason


def test_criticality_not_confirmed_non_dormant_signal_rejected() -> None:
    """INV-CRITICALITY VIOLATED: confirmed=False with NORMAL signal ⇒ rejected."""
    claim = _claim(
        substrate_criticality_at_decision=1.7,
        criticality_window_confirmed=False,
        signal="NORMAL",
    )
    ok, reason = validate_claim(claim)
    assert ok is False
    assert reason is not None and "INV-CRITICALITY" in reason


def test_criticality_warning_signal_also_rejected_when_unconfirmed() -> None:
    """Only DORMANT is admissible when window is unconfirmed; WARNING is not."""
    claim = _claim(
        substrate_criticality_at_decision=1.7,
        criticality_window_confirmed=False,
        signal="WARNING",
    )
    ok, reason = validate_claim(claim)
    assert ok is False
    assert reason is not None and "INV-CRITICALITY" in reason


def test_criticality_nan_or_non_positive_rejected() -> None:
    """γ must be finite and strictly positive (γ = 2H+1 with H >= 0)."""
    for bad in (float("nan"), float("inf"), -1.0, 0.0):
        claim = _claim(
            substrate_criticality_at_decision=bad,
            criticality_window_confirmed=True,
            signal="NORMAL",
        )
        ok, reason = validate_claim(claim)
        assert ok is False, f"γ={bad!r} should have been rejected"
        assert reason is not None


@given(
    gamma=st.floats(
        min_value=0.01,
        max_value=10.0,
        allow_nan=False,
        allow_infinity=False,
    ),
    confirmed=st.booleans(),
    signal=st.sampled_from(("NORMAL", "WARNING", "DORMANT")),
)
def test_inv_criticality_property_random(
    gamma: float, confirmed: bool, signal: DecisionSignalKind
) -> None:
    """Property: validate accepts iff (confirmed) OR (signal == DORMANT)."""
    claim = _claim(
        substrate_criticality_at_decision=gamma,
        criticality_window_confirmed=confirmed,
        signal=signal,
    )
    ok, _reason = validate_claim(claim)
    expected = confirmed or signal == "DORMANT"
    assert ok is expected, (
        f"INV-CRITICALITY mismatch at γ={gamma}, confirmed={confirmed}, "
        f"signal={signal!r}: validate={ok}, expected={expected}"
    )


def test_serialization_round_trip_preserves_criticality_fields() -> None:
    """Round-trip via to_json/from_json preserves all three INV-CRITICALITY fields."""
    reg = EvidenceRegistry()
    reg.register(
        _claim(
            substrate_criticality_at_decision=1.0,
            criticality_window_confirmed=True,
            signal="NORMAL",
        )
    )
    payload = reg.to_json()
    reg2 = EvidenceRegistry.from_json(payload)
    [entry] = list(reg2.query(HypothesisId.HYP_1_DECISION_LATENCY))
    assert entry.claim.substrate_criticality_at_decision == 1.0
    assert entry.claim.criticality_window_confirmed is True
    assert entry.claim.signal == "NORMAL"


def test_in_memory_claim_omitting_criticality_fields_uses_defaults() -> None:
    """100% backward compat: constructing EvidenceClaim without the new fields
    yields defaults (γ=None, confirmed=False, signal=NORMAL); hash and
    validation work unchanged from the legacy schema's behaviour."""
    legacy_shape = EvidenceClaim(
        hypothesis=HypothesisId.HYP_1_DECISION_LATENCY,
        baseline_mean=100.0,
        baseline_std=12.0,
        baseline_n=32,
        intervention_mean=92.0,
        intervention_std=11.0,
        intervention_n=33,
        effect_size=-0.7,
        ci_95_low=-1.1,
        ci_95_high=-0.3,
        stat_test=_stat_test(),
        registered_at_ns=_FIXED_TS,
        pre_registered=True,
    )
    assert legacy_shape.substrate_criticality_at_decision is None
    assert legacy_shape.criticality_window_confirmed is False
    assert legacy_shape.signal == "NORMAL"
    ok, reason = validate_claim(legacy_shape)
    assert ok is True, reason
    assert isinstance(claim_hash(legacy_shape), str)
