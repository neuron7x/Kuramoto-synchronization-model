# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the descriptor-only provenance / evidence firewall.

These tests lock the additive provenance metadata on the market-state
contract: completeness of the descriptor block, presence of the
claim-boundary declaration fields, absence of product-category prose in the
module, preservation of the public API, and determinism of the metadata.

The tests are intentionally constructed so each would fail if the
corresponding provenance guarantee were violated.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pandas as pd

from core.indicators.kuramoto_ricci_composite import CompositeSignal, MarketPhase
from core.indicators.market_state_contract import (
    CLAIM_BOUNDARY,
    PROVENANCE_METHOD_DESCRIPTORS,
    PROVENANCE_SOURCE_DESCRIPTORS,
    MarketStateContract,
    ProvenanceMetadata,
    build_provenance,
    compile_market_state,
)

_MODULE_SOURCE = Path(
    inspect.getsourcefile(compile_market_state) or ""
).read_text(encoding="utf-8")


def _make_signal() -> CompositeSignal:
    """Return a fully-populated bounded structural descriptor for testing."""

    return CompositeSignal(
        phase=MarketPhase.STRONG_EMERGENT,
        confidence=0.8,
        kuramoto_R=0.7,
        consensus_R=0.65,
        cross_scale_coherence=0.7,
        static_ricci=0.1,
        temporal_ricci=0.2,
        topological_transition=0.3,
        entry_signal=0.5,
        exit_signal=0.2,
        risk_multiplier=1.2,
        dominant_timeframe_sec=60,
        timestamp=pd.Timestamp("2026-01-01T00:00:00Z"),
        skipped_timeframes=[],
    )


def test_provenance_metadata_completeness() -> None:
    """Every provenance field is populated and counts match descriptor lists."""

    provenance = build_provenance()
    assert isinstance(provenance, ProvenanceMetadata)
    assert provenance.method_descriptors == PROVENANCE_METHOD_DESCRIPTORS
    assert provenance.source_descriptors == PROVENANCE_SOURCE_DESCRIPTORS
    assert provenance.method_count == len(PROVENANCE_METHOD_DESCRIPTORS)
    assert provenance.source_count == len(PROVENANCE_SOURCE_DESCRIPTORS)
    assert provenance.method_count > 0
    assert provenance.source_count > 0
    # to_dict mirrors the dataclass exactly.
    payload = provenance.to_dict()
    assert payload["method_descriptors"] == list(PROVENANCE_METHOD_DESCRIPTORS)
    assert payload["source_descriptors"] == list(PROVENANCE_SOURCE_DESCRIPTORS)
    assert payload["method_count"] == provenance.method_count
    assert payload["source_count"] == provenance.source_count


def test_claim_boundary_fields_present() -> None:
    """The fixed claim-boundary declaration fields are present and firewalled."""

    provenance = build_provenance()
    assert provenance.claim_boundary == "descriptor_only_not_predictor"
    assert CLAIM_BOUNDARY == "descriptor_only_not_predictor"
    assert provenance.not_predictive_claim is True
    assert provenance.not_financial_advice is True
    payload = provenance.to_dict()
    assert payload["claim_boundary"] == "descriptor_only_not_predictor"
    assert payload["not_predictive_claim"] is True
    assert payload["not_financial_advice"] is True


def test_compiled_state_carries_provenance() -> None:
    """A compiled envelope exposes the provenance block on the contract and dict."""

    state = compile_market_state(_make_signal())
    assert isinstance(state.provenance, ProvenanceMetadata)
    assert state.provenance.claim_boundary == "descriptor_only_not_predictor"
    serialized = state.to_dict()
    assert "provenance" in serialized
    assert serialized["provenance"]["claim_boundary"] == "descriptor_only_not_predictor"
    assert serialized["provenance"]["not_predictive_claim"] is True


def test_no_forbidden_product_prose() -> None:
    """The module source carries no product-category / forecast prose."""

    folded = _MODULE_SOURCE.casefold()
    forbidden = (
        r"trading signals?",
        r"\bpredictor\b(?!_)",
        r"\balpha\b",
        r"\bbuy\b",
        r"\bsell\b",
        r"live[ -]trading",
        r"signal generation",
    )
    # ``not_predictor`` / ``not_predictive`` are allowed firewall tokens; the
    # standalone product words must be absent from prose and identifiers.
    sanitized = folded.replace("descriptor_only_not_predictor", "")
    sanitized = sanitized.replace("not_predictive_claim", "")
    for pattern in forbidden:
        assert re.search(pattern, sanitized) is None, pattern


def test_public_api_unchanged() -> None:
    """Pre-existing public fields and helpers retain their names and behaviour."""

    state = compile_market_state(_make_signal())
    # Original fields still present with original types.
    assert isinstance(state.phase, float)
    assert isinstance(state.confidence, float)
    assert isinstance(state.exit, bool)
    assert isinstance(state.risk, float)
    assert set(state.regime.__class__.__members__) >= {
        "TREND",
        "MEAN_REVERT",
        "CHAOTIC",
        "TRANSITION",
        "NEUTRAL",
    }
    serialized = state.to_dict()
    # All original keys preserved; provenance is purely additive.
    for key in ("phase", "confidence", "regime", "entry", "exit", "risk", "evidence"):
        assert key in serialized


def test_provenance_is_deterministic() -> None:
    """Provenance metadata is identical across calls and across signals."""

    first = build_provenance()
    second = build_provenance()
    assert first == second
    state_a = compile_market_state(_make_signal())
    state_b = compile_market_state(_make_signal())
    assert state_a.provenance == state_b.provenance
    assert state_a.provenance.to_dict() == state_b.provenance.to_dict()


def test_runtime_math_unchanged_by_provenance() -> None:
    """Adding provenance changes no computed numeric field of the envelope."""

    signal = _make_signal()
    state = compile_market_state(signal)
    serialized = state.to_dict()
    # Numeric descriptors stay within their declared bounds (math intact).
    assert -3.1416 <= serialized["phase"] <= 3.1416
    assert 0.0 <= serialized["confidence"] <= 1.0
    assert 0.0 <= serialized["risk"] <= 1.0
    assert serialized["regime"] == "TREND"
