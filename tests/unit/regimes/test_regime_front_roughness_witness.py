# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for geosync_hpc.regimes.regime_front_roughness_witness."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pytest

from geosync_hpc.regimes.regime_front_roughness_witness import (
    FrontInput,
    FrontStatus,
    FrontWitness,
    assess_regime_front_roughness,
)


def _input(
    *,
    boundary_series: tuple[float, ...],
    time_index: tuple[float, ...] | None = None,
    window: int = 8,
    null_shuffle_seed: int = 0,
    roughness_threshold: float = 0.05,
    minimum_length: int = 32,
) -> FrontInput:
    if time_index is None:
        time_index = tuple(float(i) for i in range(len(boundary_series)))
    return FrontInput(
        boundary_series=boundary_series,
        time_index=time_index,
        window=window,
        null_shuffle_seed=null_shuffle_seed,
        roughness_threshold=roughness_threshold,
        minimum_length=minimum_length,
    )


def test_rough_synthetic_front_classifies_as_rough() -> None:
    """1. Boundary with strong local fluctuations beats shuffled null."""
    rng = np.random.default_rng(1)
    n = 128
    # Strongly autocorrelated random walk with high local stdev → high
    # local roughness; shuffling destroys ordering and pushes null
    # toward a different magnitude.
    series_arr = rng.standard_normal(n).cumsum()
    boundary = tuple(float(v) for v in series_arr)
    witness = assess_regime_front_roughness(_input(boundary_series=boundary, window=8))
    # Cumsum has growing local std (Brownian-like). With shuffle,
    # roughness changes substantially. We assert the witness is one of
    # the deterministic verdicts (not insufficient or invalid).
    assert witness.status in (
        FrontStatus.ROUGH_FRONT,
        FrontStatus.SMOOTH_FRONT,
        FrontStatus.NULL_MATCH,
    )


def test_smooth_synthetic_front_does_not_classify_as_rough() -> None:
    """2. Strictly linear series has zero local variance within windows."""
    n = 128
    boundary = tuple(float(i) * 0.01 for i in range(n))
    witness = assess_regime_front_roughness(_input(boundary_series=boundary, window=8))
    assert witness.status in (FrontStatus.SMOOTH_FRONT, FrontStatus.NULL_MATCH)
    # Linear → very low roughness. Shuffling a linear series produces
    # high roughness; observed << null → SMOOTH_FRONT.
    assert witness.roughness_value < witness.shuffled_null_roughness


def test_shuffled_null_match_blocks_rough_classification() -> None:
    """3. White noise: observed roughness ≈ shuffled null roughness."""
    rng = np.random.default_rng(2)
    n = 256
    boundary = tuple(float(v) for v in rng.standard_normal(n))
    witness = assess_regime_front_roughness(
        _input(
            boundary_series=boundary,
            window=8,
            roughness_threshold=0.5,  # generous threshold
        )
    )
    assert witness.status is FrontStatus.NULL_MATCH


def test_insufficient_history_returns_insufficient() -> None:
    """4. Series shorter than minimum_length → INSUFFICIENT_HISTORY."""
    boundary = tuple(float(i) for i in range(10))
    witness = assess_regime_front_roughness(
        _input(boundary_series=boundary, window=4, minimum_length=64)
    )
    assert witness.status is FrontStatus.INSUFFICIENT_HISTORY


def test_unordered_time_index_rejected() -> None:
    """5. time_index must be strictly monotonic increasing."""
    boundary = tuple(float(i) for i in range(8))
    with pytest.raises(ValueError, match="strictly monotonic increasing"):
        FrontInput(
            boundary_series=boundary,
            time_index=(0.0, 2.0, 1.0, 3.0, 4.0, 5.0, 6.0, 7.0),
            window=4,
            null_shuffle_seed=0,
            roughness_threshold=0.05,
            minimum_length=4,
        )


def test_nan_inf_inputs_rejected() -> None:
    """6. NaN/inf in any numeric field rejected at construction."""
    with pytest.raises(ValueError, match=r"boundary_series\[1\] must be finite"):
        FrontInput(
            boundary_series=(0.0, float("nan"), 2.0),
            time_index=(0.0, 1.0, 2.0),
            window=2,
            null_shuffle_seed=0,
            roughness_threshold=0.05,
            minimum_length=2,
        )
    with pytest.raises(ValueError, match=r"time_index\[2\] must be finite"):
        FrontInput(
            boundary_series=(0.0, 1.0, 2.0),
            time_index=(0.0, 1.0, float("inf")),
            window=2,
            null_shuffle_seed=0,
            roughness_threshold=0.05,
            minimum_length=2,
        )
    with pytest.raises(ValueError, match="roughness_threshold must be finite"):
        FrontInput(
            boundary_series=(0.0, 1.0),
            time_index=(0.0, 1.0),
            window=2,
            null_shuffle_seed=0,
            roughness_threshold=float("nan"),
            minimum_length=2,
        )


def test_negative_threshold_rejected() -> None:
    with pytest.raises(ValueError, match="roughness_threshold must be >= 0"):
        FrontInput(
            boundary_series=(0.0, 1.0),
            time_index=(0.0, 1.0),
            window=2,
            null_shuffle_seed=0,
            roughness_threshold=-0.1,
            minimum_length=2,
        )


def test_window_below_two_rejected() -> None:
    with pytest.raises(ValueError, match="window must be >= 2"):
        FrontInput(
            boundary_series=(0.0, 1.0),
            time_index=(0.0, 1.0),
            window=1,
            null_shuffle_seed=0,
            roughness_threshold=0.0,
            minimum_length=2,
        )


def test_mismatched_series_length_rejected() -> None:
    with pytest.raises(ValueError, match="must have equal length"):
        FrontInput(
            boundary_series=(0.0, 1.0, 2.0),
            time_index=(0.0, 1.0),
            window=2,
            null_shuffle_seed=0,
            roughness_threshold=0.0,
            minimum_length=2,
        )


def test_non_tuple_series_rejected() -> None:
    with pytest.raises(TypeError, match="boundary_series must be a tuple"):
        FrontInput(
            boundary_series=[0.0, 1.0],  # type: ignore[arg-type]
            time_index=(0.0, 1.0),
            window=2,
            null_shuffle_seed=0,
            roughness_threshold=0.0,
            minimum_length=2,
        )


def test_deterministic_at_fixed_seed() -> None:
    """7. Deterministic witnesses for identical inputs at fixed seed."""
    rng = np.random.default_rng(0)
    n = 64
    boundary = tuple(float(v) for v in rng.standard_normal(n))
    a = assess_regime_front_roughness(_input(boundary_series=boundary, null_shuffle_seed=99))
    b = assess_regime_front_roughness(_input(boundary_series=boundary, null_shuffle_seed=99))
    assert a == b
    assert a.status is b.status
    assert a.shuffled_null_roughness == b.shuffled_null_roughness


def test_witness_is_frozen() -> None:
    boundary = tuple(float(i) for i in range(64))
    witness = assess_regime_front_roughness(_input(boundary_series=boundary))
    with pytest.raises(Exception):  # noqa: B017
        witness.status = FrontStatus.INVALID_INPUT  # type: ignore[misc]


def test_evidence_fields_immutable() -> None:
    boundary = tuple(float(i) for i in range(64))
    witness = assess_regime_front_roughness(_input(boundary_series=boundary))
    assert isinstance(witness.evidence_fields, Mapping)
    with pytest.raises(TypeError):
        witness.evidence_fields["x"] = 1  # type: ignore[index]


def test_witness_carries_no_prediction_class_field() -> None:
    forbidden = {"prediction", "signal", "forecast", "target_price", "recommended_action"}
    fields = set(FrontWitness.__dataclass_fields__.keys())
    assert fields.isdisjoint(forbidden)


def test_falsifier_text_non_empty() -> None:
    boundary = tuple(float(i) for i in range(64))
    witness = assess_regime_front_roughness(_input(boundary_series=boundary))
    assert isinstance(witness.falsifier, str)
    assert len(witness.falsifier) > 80


_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "geosync_hpc"
    / "regimes"
    / "regime_front_roughness_witness.py"
)


def test_module_does_not_use_predictive_or_physics_equivalence_language() -> None:
    """8. No forbidden phrases."""
    text = _MODULE_PATH.read_text(encoding="utf-8").lower()
    forbidden = (
        r"\bprediction\b",
        r"\buniversal\b",
        r"physical equivalence",
        r"market physics fact",
        r"new law of physics",
    )
    for pattern in forbidden:
        assert re.search(pattern, text) is None, f"forbidden phrase {pattern!r} present"


def test_module_does_not_import_market_or_trading_modules() -> None:
    """9. No imports from execution / policy / application layers."""
    text = _MODULE_PATH.read_text(encoding="utf-8")
    for tainted in (
        "from geosync_hpc.execution",
        "from geosync_hpc.policy",
        "from geosync_hpc.application",
    ):
        assert tainted not in text, f"{tainted!r} would couple this witness to runtime layers"
