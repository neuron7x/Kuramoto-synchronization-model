# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for geosync_hpc.coherence.composite_binding_structure."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

import pytest

from geosync_hpc.coherence.composite_binding_structure import (
    BindingInput,
    BindingStatus,
    BindingWitness,
    assess_composite_binding,
)


def _input(
    *,
    asset_cluster: tuple[str, ...] = ("BTC", "ETH"),
    correlation_window: tuple[float, ...] = (0.9, 0.85, 0.92, 0.88, 0.91),
    correlation_threshold: float = 0.7,
    persistence_window: int = 3,
    perturbation_response: tuple[float, ...] = (0.82, 0.79, 0.84),
) -> BindingInput:
    return BindingInput(
        asset_cluster=asset_cluster,
        correlation_window=correlation_window,
        correlation_threshold=correlation_threshold,
        persistence_window=persistence_window,
        perturbation_response=perturbation_response,
    )


# ---------------------------------------------------------------------------
# Brief-required deterministic scenarios
# ---------------------------------------------------------------------------


def test_persistent_correlation_across_window_returns_persistent_binding() -> None:
    """1. Persistent correlation across window AND surviving perturbation → PERSISTENT_BINDING."""
    witness = assess_composite_binding(_input())
    assert witness.binding_status is BindingStatus.PERSISTENT_BINDING
    assert witness.persistent_binding is True
    assert witness.transient_correlation is False
    assert witness.persistent_slice_count == 5
    assert witness.perturbation_median >= witness.threshold_used


def test_transient_correlation_that_dissolves_under_perturbation() -> None:
    """2. Persistent in window, dissolves under perturbation → TRANSIENT_CORRELATION.

    This is the test the falsifier must break.
    """
    witness = assess_composite_binding(
        _input(
            correlation_window=(0.9, 0.85, 0.92, 0.88, 0.91),
            correlation_threshold=0.7,
            persistence_window=3,
            perturbation_response=(0.2, 0.1, 0.15),
        )
    )
    assert witness.binding_status is BindingStatus.TRANSIENT_CORRELATION
    assert witness.transient_correlation is True
    assert witness.persistent_binding is False
    assert witness.perturbation_median < witness.threshold_used


def test_insufficient_persistence_slices() -> None:
    """Window has too few in-cluster slices → INSUFFICIENT_PERSISTENCE."""
    witness = assess_composite_binding(
        _input(
            correlation_window=(0.9, 0.2, 0.3, 0.1, 0.15),
            correlation_threshold=0.7,
            persistence_window=3,
        )
    )
    assert witness.binding_status is BindingStatus.INSUFFICIENT_PERSISTENCE
    assert witness.persistent_slice_count == 1


def test_empty_cluster_rejected() -> None:
    """3. Empty asset_cluster rejected at construction."""
    with pytest.raises(ValueError, match="asset_cluster must be non-empty"):
        BindingInput(
            asset_cluster=(),
            correlation_window=(0.9,),
            correlation_threshold=0.7,
            persistence_window=1,
            perturbation_response=(0.8,),
        )


def test_empty_correlation_window_returns_unknown() -> None:
    """Empty correlation_window → UNKNOWN."""
    witness = assess_composite_binding(_input(correlation_window=(), persistence_window=1))
    assert witness.binding_status is BindingStatus.UNKNOWN


def test_empty_perturbation_response_returns_unknown() -> None:
    """Empty perturbation_response → UNKNOWN."""
    witness = assess_composite_binding(_input(perturbation_response=()))
    assert witness.binding_status is BindingStatus.UNKNOWN


def test_correlation_value_outside_unit_range_rejected() -> None:
    """4. Correlation values outside [-1, 1] rejected (validation by shape)."""
    with pytest.raises(ValueError, match=r"correlation_window\[0\] must be in"):
        BindingInput(
            asset_cluster=("BTC",),
            correlation_window=(1.5,),
            correlation_threshold=0.7,
            persistence_window=1,
            perturbation_response=(0.8,),
        )
    with pytest.raises(ValueError, match=r"perturbation_response\[1\] must be in"):
        BindingInput(
            asset_cluster=("BTC",),
            correlation_window=(0.9,),
            correlation_threshold=0.7,
            persistence_window=1,
            perturbation_response=(0.8, -1.5),
        )


def test_persistence_window_zero_rejected() -> None:
    """5. persistence_window <= 0 rejected."""
    with pytest.raises(ValueError, match="persistence_window must be > 0"):
        BindingInput(
            asset_cluster=("BTC",),
            correlation_window=(0.9,),
            correlation_threshold=0.7,
            persistence_window=0,
            perturbation_response=(0.8,),
        )


def test_persistence_window_negative_rejected() -> None:
    with pytest.raises(ValueError, match="persistence_window must be > 0"):
        BindingInput(
            asset_cluster=("BTC",),
            correlation_window=(0.9,),
            correlation_threshold=0.7,
            persistence_window=-1,
            perturbation_response=(0.8,),
        )


# ---------------------------------------------------------------------------
# Validation contract
# ---------------------------------------------------------------------------


def test_nan_in_correlation_window_rejected() -> None:
    with pytest.raises(ValueError, match=r"correlation_window\[1\] must be finite"):
        BindingInput(
            asset_cluster=("BTC",),
            correlation_window=(0.9, float("nan")),
            correlation_threshold=0.7,
            persistence_window=1,
            perturbation_response=(0.8,),
        )


def test_threshold_outside_range_rejected() -> None:
    with pytest.raises(ValueError, match="correlation_threshold must be in"):
        BindingInput(
            asset_cluster=("BTC",),
            correlation_window=(0.9,),
            correlation_threshold=1.5,
            persistence_window=1,
            perturbation_response=(0.8,),
        )


def test_non_tuple_cluster_rejected() -> None:
    with pytest.raises(TypeError, match="asset_cluster must be a tuple"):
        BindingInput(
            asset_cluster=["BTC"],  # type: ignore[arg-type]
            correlation_window=(0.9,),
            correlation_threshold=0.7,
            persistence_window=1,
            perturbation_response=(0.8,),
        )


def test_empty_cluster_member_name_rejected() -> None:
    with pytest.raises(ValueError, match=r"asset_cluster\[0\] must be a non-empty string"):
        BindingInput(
            asset_cluster=("",),
            correlation_window=(0.9,),
            correlation_threshold=0.7,
            persistence_window=1,
            perturbation_response=(0.8,),
        )


# ---------------------------------------------------------------------------
# Determinism + structural
# ---------------------------------------------------------------------------


def test_deterministic_repeated_calls_equal() -> None:
    inp = _input(
        correlation_window=(0.9, 0.4, 0.85, 0.3, 0.91, 0.88),
        perturbation_response=(0.5, 0.45, 0.6),
    )
    a = assess_composite_binding(inp)
    b = assess_composite_binding(inp)
    assert a == b
    assert a.binding_status is b.binding_status
    assert a.evidence_fields == b.evidence_fields


def test_witness_is_frozen() -> None:
    witness = assess_composite_binding(_input())
    with pytest.raises(Exception):  # noqa: B017 — FrozenInstanceError
        witness.binding_status = BindingStatus.UNKNOWN  # type: ignore[misc]


def test_evidence_fields_immutable() -> None:
    witness = assess_composite_binding(_input())
    assert isinstance(witness.evidence_fields, Mapping)
    with pytest.raises(TypeError):
        witness.evidence_fields["x"] = 1  # type: ignore[index]


def test_falsifier_text_non_empty() -> None:
    witness = assess_composite_binding(_input())
    assert isinstance(witness.falsifier, str)
    assert len(witness.falsifier) > 80


def test_witness_carries_no_prediction_class_field() -> None:
    forbidden = {"prediction", "signal", "forecast", "target_price", "recommended_action"}
    fields = set(BindingWitness.__dataclass_fields__.keys())
    assert fields.isdisjoint(forbidden)


# ---------------------------------------------------------------------------
# No-overclaim guard
# ---------------------------------------------------------------------------


_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "geosync_hpc"
    / "coherence"
    / "composite_binding_structure.py"
)


def test_module_does_not_use_predictive_or_physics_equivalence_language() -> None:
    text = _MODULE_PATH.read_text(encoding="utf-8").lower()
    forbidden = (
        r"\bprediction\b",
        r"\buniversal\b",
        r"physical equivalence",
        r"market physics fact",
    )
    for pattern in forbidden:
        assert re.search(pattern, text) is None, f"forbidden phrase {pattern!r} present"


def test_module_does_not_import_market_or_trading_modules() -> None:
    text = _MODULE_PATH.read_text(encoding="utf-8")
    for tainted in (
        "from geosync_hpc.execution",
        "from geosync_hpc.policy",
        "from geosync_hpc.application",
    ):
        assert tainted not in text, f"{tainted!r} would couple this witness to runtime layers"
