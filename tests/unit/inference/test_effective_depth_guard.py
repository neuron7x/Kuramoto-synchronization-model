# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for geosync_hpc.inference.effective_depth_guard."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

import pytest

from geosync_hpc.inference.effective_depth_guard import (
    DepthInput,
    DepthStatus,
    DepthWitness,
    assess_effective_depth,
)


def _input(
    *,
    outputs_by_depth: dict[int, tuple[float, ...]],
    tolerance: float = 0.05,
    noise_level: float = 0.01,
    minimum_depth: int | None = None,
    maximum_depth: int | None = None,
) -> DepthInput:
    if minimum_depth is None:
        minimum_depth = min(outputs_by_depth)
    if maximum_depth is None:
        maximum_depth = max(outputs_by_depth)
    return DepthInput(
        outputs_by_depth=outputs_by_depth,
        tolerance=tolerance,
        noise_level=noise_level,
        minimum_depth=minimum_depth,
        maximum_depth=maximum_depth,
    )


def test_effective_depth_found_when_pairs_diverge() -> None:
    """1. Each depth produces strictly different output beyond tolerance."""
    witness = assess_effective_depth(
        _input(
            outputs_by_depth={
                1: (1.0, 0.0),
                2: (1.0, 1.0),
                3: (1.0, 2.0),
            },
            tolerance=0.1,
        )
    )
    assert witness.status is DepthStatus.EFFECTIVE_DEPTH_FOUND
    assert witness.effective_depth == 1
    assert witness.redundant_depths == ()


def test_redundant_depth_detected_within_tolerance() -> None:
    """2. Depth 2 within tolerance of depth 1 → REDUNDANT_DEPTH.

    This is the test the falsifier must break.
    """
    witness = assess_effective_depth(
        _input(
            outputs_by_depth={
                1: (1.0, 1.0),
                2: (1.001, 1.001),
                3: (5.0, 5.0),
            },
            tolerance=0.05,
        )
    )
    assert witness.status is DepthStatus.REDUNDANT_DEPTH
    assert 2 in witness.redundant_depths


def test_no_stable_depth_when_range_degenerate() -> None:
    """3. With single depth no equivalence pair possible → EFFECTIVE_DEPTH_FOUND.

    A single-depth range cannot be REDUNDANT (no shallower comparison).
    """
    witness = assess_effective_depth(
        _input(
            outputs_by_depth={5: (1.0, 2.0)},
            tolerance=0.1,
            minimum_depth=5,
            maximum_depth=5,
        )
    )
    assert witness.status is DepthStatus.EFFECTIVE_DEPTH_FOUND
    assert witness.effective_depth == 5


def test_invalid_depth_range_rejected() -> None:
    """4. maximum_depth < minimum_depth rejected at construction."""
    with pytest.raises(ValueError, match="maximum_depth must be >= minimum_depth"):
        DepthInput(
            outputs_by_depth={1: (0.0,)},
            tolerance=0.1,
            noise_level=0.0,
            minimum_depth=5,
            maximum_depth=2,
        )


def test_missing_depth_in_range_rejected() -> None:
    """5. A depth in [min, max] that is not in outputs_by_depth is rejected."""
    with pytest.raises(ValueError, match="missing required depth 2"):
        DepthInput(
            outputs_by_depth={1: (0.0,), 3: (1.0,)},
            tolerance=0.1,
            noise_level=0.0,
            minimum_depth=1,
            maximum_depth=3,
        )


def test_nan_inf_rejected() -> None:
    """6. NaN/inf in any numeric field rejected at construction."""
    with pytest.raises(ValueError, match=r"outputs_by_depth\[1\]\[0\] must be finite"):
        DepthInput(
            outputs_by_depth={1: (float("nan"),), 2: (1.0,)},
            tolerance=0.1,
            noise_level=0.0,
            minimum_depth=1,
            maximum_depth=2,
        )
    with pytest.raises(ValueError, match="tolerance must be finite"):
        DepthInput(
            outputs_by_depth={1: (0.0,)},
            tolerance=float("nan"),
            noise_level=0.0,
            minimum_depth=1,
            maximum_depth=1,
        )
    with pytest.raises(ValueError, match="noise_level must be finite"):
        DepthInput(
            outputs_by_depth={1: (0.0,)},
            tolerance=0.1,
            noise_level=float("inf"),
            minimum_depth=1,
            maximum_depth=1,
        )


def test_negative_tolerance_rejected() -> None:
    with pytest.raises(ValueError, match="tolerance must be >= 0"):
        DepthInput(
            outputs_by_depth={1: (0.0,)},
            tolerance=-0.01,
            noise_level=0.0,
            minimum_depth=1,
            maximum_depth=1,
        )


def test_negative_noise_level_rejected() -> None:
    with pytest.raises(ValueError, match="noise_level must be >= 0"):
        DepthInput(
            outputs_by_depth={1: (0.0,)},
            tolerance=0.1,
            noise_level=-0.01,
            minimum_depth=1,
            maximum_depth=1,
        )


def test_negative_depth_rejected() -> None:
    with pytest.raises(ValueError, match=r"outputs_by_depth keys must be >= 0"):
        DepthInput(
            outputs_by_depth={-1: (0.0,)},
            tolerance=0.1,
            noise_level=0.0,
            minimum_depth=0,
            maximum_depth=0,
        )


def test_empty_outputs_rejected() -> None:
    with pytest.raises(ValueError, match="outputs_by_depth must be non-empty"):
        DepthInput(
            outputs_by_depth={},
            tolerance=0.1,
            noise_level=0.0,
            minimum_depth=0,
            maximum_depth=0,
        )


def test_non_tuple_output_rejected() -> None:
    with pytest.raises(TypeError, match=r"outputs_by_depth\[1\] must be a tuple"):
        DepthInput(
            outputs_by_depth={1: [0.0]},  # type: ignore[dict-item]
            tolerance=0.1,
            noise_level=0.0,
            minimum_depth=1,
            maximum_depth=1,
        )


def test_deterministic_repeated_calls_equal() -> None:
    """7. Identical inputs produce byte-identical witnesses."""
    inp = _input(
        outputs_by_depth={
            1: (1.0, 2.0),
            2: (1.001, 2.001),
            3: (5.0, 6.0),
        },
        tolerance=0.05,
    )
    a = assess_effective_depth(inp)
    b = assess_effective_depth(inp)
    assert a == b
    assert a.status is b.status
    assert a.evidence_fields == b.evidence_fields


def test_witness_is_frozen() -> None:
    inp = _input(outputs_by_depth={1: (1.0,), 2: (2.0,)}, tolerance=0.1)
    witness = assess_effective_depth(inp)
    with pytest.raises(Exception):  # noqa: B017
        witness.status = DepthStatus.INVALID_INPUT  # type: ignore[misc]


def test_evidence_fields_immutable() -> None:
    inp = _input(outputs_by_depth={1: (1.0,), 2: (2.0,)}, tolerance=0.1)
    witness = assess_effective_depth(inp)
    assert isinstance(witness.evidence_fields, Mapping)
    with pytest.raises(TypeError):
        witness.evidence_fields["x"] = 1  # type: ignore[index]


def test_witness_carries_no_prediction_class_field() -> None:
    forbidden = {"prediction", "signal", "forecast", "target_price", "recommended_action"}
    fields = set(DepthWitness.__dataclass_fields__.keys())
    assert fields.isdisjoint(forbidden)


def test_falsifier_text_non_empty() -> None:
    inp = _input(outputs_by_depth={1: (1.0,), 2: (2.0,)}, tolerance=0.1)
    witness = assess_effective_depth(inp)
    assert isinstance(witness.falsifier, str)
    assert len(witness.falsifier) > 80


_MODULE_PATH = (
    Path(__file__).resolve().parents[3] / "geosync_hpc" / "inference" / "effective_depth_guard.py"
)


def test_module_does_not_use_predictive_or_intelligence_language() -> None:
    """8. No forbidden phrases including intelligence/depth-improves claims."""
    text = _MODULE_PATH.read_text(encoding="utf-8").lower()
    forbidden = (
        r"\bprediction\b",
        r"\buniversal\b",
        r"physical equivalence",
        r"new law of physics",
        r"noise improves intelligence",
        r"longer reasoning is always",
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
        assert tainted not in text, f"{tainted!r} would couple this guard to runtime layers"
