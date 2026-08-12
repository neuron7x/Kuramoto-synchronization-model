# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the temporal-exposure-panel boundary validator."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from research.systemic_risk.errors import (
    InvalidExposureMatrixError,
    InvalidNodeLabelsError,
    InvalidTemporalPanelError,
)
from research.systemic_risk.temporal_panel import validate_temporal_exposure_panel


def _good_panel() -> tuple[dict[date, np.ndarray], tuple[str, ...]]:
    labels = ("a", "b", "c")
    panel = {
        date(2020, 1, 1): np.array(
            [[0.0, 1.0, 2.0], [3.0, 0.0, 0.0], [0.0, 0.0, 0.0]], dtype=np.float64
        ),
        date(2020, 2, 1): np.array(
            [[0.0, 0.0, 4.0], [3.0, 0.0, 1.0], [0.0, 2.0, 0.0]], dtype=np.float64
        ),
    }
    return panel, labels


class TestValidateTemporalExposurePanel:
    def test_valid_panel_passes(self) -> None:
        panel, labels = _good_panel()
        validate_temporal_exposure_panel(panel, labels)

    def test_empty_panel_rejected(self) -> None:
        with pytest.raises(InvalidTemporalPanelError, match="non-empty"):
            validate_temporal_exposure_panel({}, ("a", "b"))

    def test_duplicate_labels_rejected(self) -> None:
        panel, _ = _good_panel()
        with pytest.raises(InvalidNodeLabelsError, match="unique"):
            validate_temporal_exposure_panel(panel, ("a", "a", "c"))

    def test_empty_label_rejected(self) -> None:
        panel, _ = _good_panel()
        with pytest.raises(InvalidNodeLabelsError, match="empty or whitespace"):
            validate_temporal_exposure_panel(panel, ("a", "", "c"))

    def test_whitespace_label_rejected(self) -> None:
        panel, _ = _good_panel()
        with pytest.raises(InvalidNodeLabelsError, match="empty or whitespace"):
            validate_temporal_exposure_panel(panel, ("a", "  ", "c"))

    def test_size_mismatch_rejected(self) -> None:
        labels = ("a", "b", "c")
        panel = {date(2020, 1, 1): np.zeros((4, 4), dtype=np.float64)}
        with pytest.raises(InvalidTemporalPanelError, match="node_labels length"):
            validate_temporal_exposure_panel(panel, labels)

    def test_non_square_snapshot_rejected(self) -> None:
        labels = ("a", "b", "c")
        panel = {date(2020, 1, 1): np.zeros((3, 4), dtype=np.float64)}
        with pytest.raises(InvalidExposureMatrixError, match="square 2-D"):
            validate_temporal_exposure_panel(panel, labels)

    def test_nan_snapshot_rejected(self) -> None:
        labels = ("a", "b")
        bad = np.array([[0.0, np.nan], [0.0, 0.0]], dtype=np.float64)
        panel = {date(2020, 1, 1): bad}
        with pytest.raises(InvalidExposureMatrixError, match="non-finite"):
            validate_temporal_exposure_panel(panel, labels)

    def test_negative_snapshot_rejected(self) -> None:
        labels = ("a", "b")
        bad = np.array([[0.0, -1.0], [0.0, 0.0]], dtype=np.float64)
        panel = {date(2020, 1, 1): bad}
        with pytest.raises(InvalidExposureMatrixError, match="negative"):
            validate_temporal_exposure_panel(panel, labels)
