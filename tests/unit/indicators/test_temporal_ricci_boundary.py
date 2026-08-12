# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Claim-boundary regression tests for the temporal-Ricci descriptor.

These tests lock the additive, descriptor-only claim-boundary metadata of
``core.indicators.temporal_ricci``.  They assert that the module declares an
explicit ``descriptor_only_not_predictor`` boundary, exposes provenance and
input-count metadata on its public result surface, and that none of this
metadata leaks predictive / trading / financial-advice semantics.  Every test
here would fail if the descriptor boundary were silently relaxed or if the
metadata surface were removed.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd
import pytest

from core.indicators.temporal_ricci import (
    CLAIM_BOUNDARY,
    TemporalRicciAnalyzer,
    TemporalRicciResult,
)


def _series(n: int = 240, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    prices = 100.0 + np.cumsum(rng.normal(0.0, 1.0, size=n))
    volumes = np.abs(rng.normal(1000.0, 50.0, size=n))
    index = pd.date_range("2024-01-01", periods=n, freq="h")
    return pd.DataFrame({"close": prices, "volume": volumes}, index=index)


def test_claim_boundary_constant_declares_descriptor_only() -> None:
    assert CLAIM_BOUNDARY["claim_boundary"] == "descriptor_only_not_predictor"
    assert CLAIM_BOUNDARY["method"] == "ollivier_ricci_lite_temporal_summariser"
    assert CLAIM_BOUNDARY["not_predictive_claim"] is True
    assert CLAIM_BOUNDARY["not_financial_advice"] is True
    assert CLAIM_BOUNDARY["not_a_trading_signal"] is True


def test_claim_boundary_constant_is_read_only() -> None:
    # MappingProxyType must reject mutation so the boundary cannot be relaxed
    # at runtime. Route through an ``Any`` handle so the runtime immutability
    # is exercised without a static subscript-assignment error.
    handle: Any = CLAIM_BOUNDARY

    def _mutate() -> None:
        handle["claim_boundary"] = "predictor"

    with pytest.raises(TypeError):
        _mutate()


def test_descriptor_metadata_mirrors_boundary_and_adds_counts() -> None:
    analyzer = TemporalRicciAnalyzer(window_size=60, n_snapshots=5, n_levels=12)
    result = analyzer.analyze(_series())
    meta = result.descriptor_metadata()

    # Boundary fields are carried through verbatim.
    for key, value in CLAIM_BOUNDARY.items():
        assert meta[key] == value

    # Input-derived provenance counts are present and non-negative.
    assert "n_snapshots" in meta
    assert "n_edges_observed" in meta
    assert isinstance(meta["n_snapshots"], int)
    assert isinstance(meta["n_edges_observed"], int)
    assert meta["n_snapshots"] >= 0
    assert meta["n_edges_observed"] >= 0
    assert meta["n_snapshots"] == len(result.graph_snapshots)


def test_descriptor_metadata_is_copy_not_shared_state() -> None:
    analyzer = TemporalRicciAnalyzer(window_size=60, n_snapshots=4, n_levels=10)
    result = analyzer.analyze(_series(seed=11))
    meta_a = result.descriptor_metadata()
    meta_a["n_snapshots"] = -999
    meta_b = result.descriptor_metadata()
    # Mutating one returned dict must not corrupt the next call.
    assert meta_b["n_snapshots"] != -999


def test_metadata_carries_no_predictive_or_trading_language() -> None:
    analyzer = TemporalRicciAnalyzer(window_size=60, n_snapshots=4, n_levels=10)
    result = analyzer.analyze(_series(seed=3))
    meta = result.descriptor_metadata()
    # The negation flags must explicitly disclaim predictive / trading framing.
    assert meta["not_predictive_claim"] is True
    assert meta["not_financial_advice"] is True
    assert meta["not_a_trading_signal"] is True
    # No metadata *value* may carry a positive predictive/trading promotion.
    blob = " ".join(str(v) for v in meta.values()).lower()
    for banned in ("forecast", "predictor_yes", "buy", "sell", "alpha", "trade signal"):
        assert banned not in blob


def test_curvature_bound_declared_le_one() -> None:
    # The descriptor must advertise the universal κ ≤ 1 (INV-RC1) structural
    # bound, anchoring it as geometry, not a market claim.
    assert CLAIM_BOUNDARY["curvature_bound"] == "kappa_le_1_INV_RC1"
    assert CLAIM_BOUNDARY["descriptor_kind"] == "structural_graph_curvature"


def test_metadata_does_not_change_runtime_result_fields() -> None:
    # Calling the metadata accessor must be side-effect free with respect to
    # the runtime math fields of the result.
    analyzer = TemporalRicciAnalyzer(window_size=60, n_snapshots=5, n_levels=12)
    result = analyzer.analyze(_series(seed=21))
    before = (
        result.temporal_curvature,
        result.topological_transition_score,
        result.structural_stability,
        result.edge_persistence,
        len(result.graph_snapshots),
    )
    _ = result.descriptor_metadata()
    after = (
        result.temporal_curvature,
        result.topological_transition_score,
        result.structural_stability,
        result.edge_persistence,
        len(result.graph_snapshots),
    )
    assert before == after


def test_empty_result_metadata_is_well_formed() -> None:
    # A short series yields a zero-snapshot result; metadata must still be the
    # full boundary declaration with zero counts (no crash, no leak).
    empty = TemporalRicciResult(
        temporal_curvature=0.0,
        topological_transition_score=0.0,
        graph_snapshots=[],
        structural_stability=1.0,
        edge_persistence=1.0,
    )
    meta = empty.descriptor_metadata()
    assert meta["n_snapshots"] == 0
    assert meta["n_edges_observed"] == 0
    assert meta["claim_boundary"] == "descriptor_only_not_predictor"


def test_short_series_through_analyzer_has_descriptor_boundary() -> None:
    analyzer = TemporalRicciAnalyzer(window_size=200, n_snapshots=5, n_levels=12)
    short = _series(n=50)
    result = analyzer.analyze(short)
    meta = result.descriptor_metadata()
    assert meta["claim_boundary"] == "descriptor_only_not_predictor"
    assert meta["n_snapshots"] == 0
    # Sanity: index spacing intact, no exception on the descriptor path.
    assert short.index[1] - short.index[0] == timedelta(hours=1)
