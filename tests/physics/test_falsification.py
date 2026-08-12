# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Witnesses for the empirical_synthetic_only_rejection law."""

from __future__ import annotations

import numpy as np

from core.physics.falsification import (
    empirical_witness,
    leakage_detector,
    negative_control,
    rejection_report,
    synthetic_witness,
)


def test_clean_empirical_witness_passes() -> None:
    """Positive witness: a provenanced, unleaked, sufficiently large empirical effect is admitted."""
    w = empirical_witness(0.42, dataset_id="ds-eurusd-2026Q1")
    report = rejection_report(w, min_effect=0.1)
    assert report["admitted"] is True, report


def test_synthetic_only_cannot_validate_empirical() -> None:
    """Negative control: a synthetic-only witness can never validate an empirical claim."""
    w = synthetic_witness(0.99)  # huge effect, but synthetic
    report = rejection_report(w, min_effect=0.1)
    assert report["admitted"] is False
    assert any("non-empirical" in r for r in report["reasons"])


def test_shuffled_labels_fail() -> None:
    """A label-shuffled null is rejected as a negative control, not a claim."""
    rng = np.random.default_rng(0)
    values = rng.normal(size=200)
    labels = values + rng.normal(scale=0.1, size=200)  # genuinely correlated
    null = negative_control(values, labels, seed=1)
    report = rejection_report(null, min_effect=0.1)
    assert report["admitted"] is False
    assert any("shuffled" in r for r in report["reasons"])


def test_leakage_injected_data_fails() -> None:
    """A leaked train/test split marks the witness leaked, which is rejected."""
    leaked = leakage_detector([0, 1, 5], [5, 6])  # adjacency leak
    assert leaked is True
    w = empirical_witness(0.5, dataset_id="ds", leaked=leaked)
    report = rejection_report(w, min_effect=0.1)
    assert report["admitted"] is False
    assert any("leakage" in r for r in report["reasons"])


def test_missing_provenance_fails() -> None:
    """An empirical witness without a dataset id is rejected (no provenance)."""
    w = empirical_witness(0.5, dataset_id="")
    report = rejection_report(w, min_effect=0.1)
    assert report["admitted"] is False
    assert any("provenance" in r for r in report["reasons"])


def test_clean_split_is_not_flagged_leaked() -> None:
    """A clean split is not flagged by the leakage detector."""
    assert leakage_detector([0, 1, 2], [4, 5]) is False
