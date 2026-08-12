# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Structured-exception contract tests (§ 5 Entry-Point Gate)."""

from __future__ import annotations

import numpy as np
import pytest

from research.systemic_risk.errors import (
    InvalidExposureMatrixError,
    InvalidNodeLabelsError,
    SystemicRiskInputError,
)
from research.systemic_risk.topology import from_exposure_matrix


class TestExceptionHierarchy:
    def test_root_inherits_value_error(self) -> None:
        # Backward-compat: every existing `except ValueError` site
        # must still catch the new typed errors.
        assert issubclass(SystemicRiskInputError, ValueError)
        assert issubclass(InvalidExposureMatrixError, SystemicRiskInputError)
        assert issubclass(InvalidNodeLabelsError, SystemicRiskInputError)

    def test_invalid_shape_raises_typed(self) -> None:
        with pytest.raises(InvalidExposureMatrixError, match="square 2-D"):
            from_exposure_matrix(np.zeros((3, 4), dtype=np.float64), ("a", "b", "c"))

    def test_label_length_mismatch_raises_typed(self) -> None:
        with pytest.raises(InvalidNodeLabelsError, match="!="):
            from_exposure_matrix(np.zeros((3, 3), dtype=np.float64), ("a", "b"))

    def test_duplicate_labels_raises_typed(self) -> None:
        with pytest.raises(InvalidNodeLabelsError, match="unique"):
            from_exposure_matrix(np.zeros((3, 3), dtype=np.float64), ("a", "a", "c"))

    def test_empty_label_raises_typed(self) -> None:
        with pytest.raises(InvalidNodeLabelsError, match="empty"):
            from_exposure_matrix(np.zeros((3, 3), dtype=np.float64), ("a", "", "c"))

    def test_whitespace_only_label_raises_typed(self) -> None:
        with pytest.raises(InvalidNodeLabelsError, match="empty or whitespace"):
            from_exposure_matrix(np.zeros((3, 3), dtype=np.float64), ("a", "  ", "c"))

    def test_none_label_raises_typed(self) -> None:
        # node_labels is typed `tuple[str, ...]` but runtime callers
        # may pass through dynamically-built tuples; defend at runtime.
        with pytest.raises(InvalidNodeLabelsError, match="None"):
            from_exposure_matrix(
                np.zeros((3, 3), dtype=np.float64),
                ("a", None, "c"),  # type: ignore[arg-type]
            )

    def test_nan_exposure_raises_typed(self) -> None:
        e = np.array([[0.0, np.nan], [0.0, 0.0]], dtype=np.float64)
        with pytest.raises(InvalidExposureMatrixError, match="finite"):
            from_exposure_matrix(e, ("a", "b"))

    def test_negative_exposure_raises_typed(self) -> None:
        e = np.array([[0.0, -1.0], [-1.0, 0.0]], dtype=np.float64)
        with pytest.raises(InvalidExposureMatrixError, match="non-negative"):
            from_exposure_matrix(e, ("a", "b"))

    def test_negative_threshold_raises_typed(self) -> None:
        e = np.zeros((2, 2), dtype=np.float64)
        with pytest.raises(InvalidExposureMatrixError, match="threshold"):
            from_exposure_matrix(e, ("a", "b"), threshold=-0.1)

    def test_typed_error_still_catchable_as_value_error(self) -> None:
        # New code should pattern-match on the typed class, but old
        # code must still work via the parent ``ValueError`` catch.
        e = np.zeros((2, 2), dtype=np.float64)
        try:
            from_exposure_matrix(e, ("a", "a"))
        except ValueError as exc:
            assert isinstance(exc, InvalidNodeLabelsError)
        else:
            raise AssertionError("expected InvalidNodeLabelsError")


class TestThresholdContract:
    def test_threshold_is_strict_cutoff(self) -> None:
        # Per the (corrected) docstring: threshold is a STRICT lower
        # cutoff. An entry equal to threshold is NOT an edge.
        e = np.array([[0.0, 0.5], [0.5, 0.0]], dtype=np.float64)
        topo = from_exposure_matrix(e, ("a", "b"), threshold=0.5)
        assert topo.adjacency[0, 1] == 0, (
            "INV-THRESHOLD-STRICT VIOLATED: entry equal to "
            "threshold=0.5 became an edge; topology threshold "
            "is documented as STRICT (>)"
        )

    def test_threshold_strict_above(self) -> None:
        e = np.array([[0.0, 0.51], [0.51, 0.0]], dtype=np.float64)
        topo = from_exposure_matrix(e, ("a", "b"), threshold=0.5)
        assert topo.adjacency[0, 1] == 1
