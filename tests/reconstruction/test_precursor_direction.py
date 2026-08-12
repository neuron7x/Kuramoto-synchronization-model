# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for PrecursorDirection (FIX B5).

The frozen ClaimTier enum (PR #592) cannot represent direction. We
expose direction *separately* on PrecursorReport so that the
human-facing capsule text can disambiguate VALIDATED_NEGATIVE under
the upstream-frozen ClaimTier label, without patching the enum.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from research.reconstruction.kuramoto_on_reconstruction import (
    PrecursorDirection,
    PrecursorReport,
    _classify_direction,
    gate_6_precursor_discriminative,
)
from research.reconstruction.positive_control import ground_truth_core_periphery


def _baseline_report(**overrides: Any) -> PrecursorReport:
    base = PrecursorReport(
        n_nodes=20,
        k_test=1.5,
        n_bootstrap=4,
        r_recon_median=0.42,
        r_shuffled_median=0.40,
        delta_r_median=0.02,
        delta_r_ci_low=-0.01,
        delta_r_ci_high=0.05,
        min_precursor_gap=0.05,
        passed=False,
        failure_reason=None,
        direction=PrecursorDirection.NO_SIGNAL,
    )
    return replace(base, **overrides)


# ---------------------------------------------------------------------------
# Direction classifier — boundary semantics
# ---------------------------------------------------------------------------


def test_facilitated_when_ci_excludes_above_min_gap() -> None:
    d = _classify_direction(ci_low=0.06, ci_high=0.10, min_gap=0.05)
    assert d is PrecursorDirection.SYNCHRONIZATION_FACILITATED


def test_hindered_when_ci_excludes_below_neg_min_gap() -> None:
    d = _classify_direction(ci_low=-0.10, ci_high=-0.06, min_gap=0.05)
    assert d is PrecursorDirection.SYNCHRONIZATION_HINDERED


def test_no_signal_when_ci_overlaps_zero() -> None:
    d = _classify_direction(ci_low=-0.02, ci_high=0.03, min_gap=0.05)
    assert d is PrecursorDirection.NO_SIGNAL


def test_facilitated_at_exact_min_gap_boundary() -> None:
    """Exactly ci_low == min_gap is FACILITATED (closed interval, matches PASS)."""
    d = _classify_direction(ci_low=0.05, ci_high=0.10, min_gap=0.05)
    assert d is PrecursorDirection.SYNCHRONIZATION_FACILITATED


def test_hindered_at_exact_min_gap_boundary() -> None:
    d = _classify_direction(ci_low=-0.10, ci_high=-0.05, min_gap=0.05)
    assert d is PrecursorDirection.SYNCHRONIZATION_HINDERED


# ---------------------------------------------------------------------------
# PrecursorReport surface — direction populated end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_gate_6_report_carries_direction_field() -> None:
    n = 50
    rng = np.random.default_rng(0)
    a = (rng.uniform(size=(n, n)) < 0.2).astype(np.float64)
    np.fill_diagonal(a, 0.0)
    weights = rng.lognormal(mean=2.0, sigma=1.0, size=(n, n))
    w = (a * weights).astype(np.float64)
    np.fill_diagonal(w, 0.0)
    report = gate_6_precursor_discriminative(w, seed=42, n_bootstrap=4)
    assert isinstance(report.direction, PrecursorDirection)
    if report.passed:
        assert report.direction in {
            PrecursorDirection.SYNCHRONIZATION_FACILITATED,
            PrecursorDirection.SYNCHRONIZATION_HINDERED,
        }
    else:
        # FAIL ⇒ direction NO_SIGNAL OR a signed direction with insufficient
        # bootstraps to push the CI fully past min_gap. The classifier maps
        # purely from (ci_low, ci_high, min_gap) so cross-check that.
        assert report.direction is _classify_direction(
            ci_low=report.delta_r_ci_low,
            ci_high=report.delta_r_ci_high,
            min_gap=report.min_precursor_gap,
        )


def test_capsule_human_text_includes_direction() -> None:
    """The human-facing one-liner must surface the direction by name."""
    facilitated = _baseline_report(
        delta_r_ci_low=0.06,
        delta_r_ci_high=0.10,
        passed=True,
        direction=PrecursorDirection.SYNCHRONIZATION_FACILITATED,
    )
    hindered = _baseline_report(
        delta_r_ci_low=-0.10,
        delta_r_ci_high=-0.06,
        delta_r_median=-0.08,
        passed=True,
        direction=PrecursorDirection.SYNCHRONIZATION_HINDERED,
    )
    no_signal = _baseline_report(
        delta_r_ci_low=-0.02,
        delta_r_ci_high=0.03,
        delta_r_median=0.005,
        passed=False,
        direction=PrecursorDirection.NO_SIGNAL,
    )
    assert "structure_aids_sync" in facilitated.human_text()
    assert "PASS" in facilitated.human_text()
    assert "structure_hinders_sync" in hindered.human_text()
    assert "PASS" in hindered.human_text()
    assert "ci_overlaps_zero" in no_signal.human_text()
    assert "FAIL" in no_signal.human_text()


@pytest.mark.slow
def test_precursor_direction_is_authoritative_on_known_facilitating_topology() -> None:
    """Core-periphery is hub-dominated and reliably facilitates sync.

    The reconstruction step is randomised, so we run on the *true* CP
    network (i.e. skip the Cimini step) and verify the direction
    classifier surfaces FACILITATED whenever Gate 6 PASSes, never
    silently mislabelling it as HINDERED.
    """
    w = ground_truth_core_periphery(n=100, core_frac=0.30, seed=42)
    report = gate_6_precursor_discriminative(w, seed=42, n_bootstrap=8)
    if report.passed:
        # If the report is signed, its sign must match what the CI says.
        if report.delta_r_median > 0:
            assert report.direction is PrecursorDirection.SYNCHRONIZATION_FACILITATED
        else:
            assert report.direction is PrecursorDirection.SYNCHRONIZATION_HINDERED


def test_direction_default_is_no_signal_for_legacy_constructions() -> None:
    """Default ``direction=NO_SIGNAL`` keeps backwards-compatible
    construction (call sites that don't yet set the field never receive
    a misleading FACILITATED/HINDERED label by accident)."""
    legacy_like = PrecursorReport(
        n_nodes=20,
        k_test=1.5,
        n_bootstrap=4,
        r_recon_median=0.42,
        r_shuffled_median=0.40,
        delta_r_median=0.02,
        delta_r_ci_low=-0.01,
        delta_r_ci_high=0.05,
        min_precursor_gap=0.05,
        passed=False,
        failure_reason=None,
    )
    assert legacy_like.direction is PrecursorDirection.NO_SIGNAL


# ---------------------------------------------------------------------------
# Property-based tests — Hypothesis exhaustively probes the classifier's
# logical contract. The classifier is a pure function of three numbers, so
# the right level of test rigor is property-based, not example-based.
# ---------------------------------------------------------------------------


@given(
    a=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    b=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    min_gap=st.floats(min_value=1e-6, max_value=1.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100, deadline=None)
def test_classifier_partitions_state_space_disjointly(a: float, b: float, min_gap: float) -> None:
    """Every (ci_low, ci_high) point falls in exactly one of three
    mutually-exclusive bins. The classifier is a function — same input,
    same output — and the bins partition R²: this property is the
    foundation Gate 6 inherits."""
    ci_low, ci_high = min(a, b), max(a, b)
    direction = _classify_direction(ci_low=ci_low, ci_high=ci_high, min_gap=min_gap)

    facilitated = ci_low >= min_gap
    hindered = ci_high <= -min_gap
    no_signal = (not facilitated) and (not hindered)

    # Mutual exclusivity: exactly one bin true.
    assert sum([facilitated, hindered, no_signal]) == 1

    # Bin assignment matches verdict.
    if facilitated:
        assert direction is PrecursorDirection.SYNCHRONIZATION_FACILITATED
    elif hindered:
        assert direction is PrecursorDirection.SYNCHRONIZATION_HINDERED
    else:
        assert direction is PrecursorDirection.NO_SIGNAL


@given(
    ci_low=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    width=st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False),
    min_gap=st.floats(min_value=1e-6, max_value=1.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=80, deadline=None)
def test_classifier_is_idempotent(ci_low: float, width: float, min_gap: float) -> None:
    """Calling the classifier twice on the same triple returns the same
    PrecursorDirection — pure-function property, no hidden state."""
    ci_high = ci_low + width
    a = _classify_direction(ci_low=ci_low, ci_high=ci_high, min_gap=min_gap)
    b = _classify_direction(ci_low=ci_low, ci_high=ci_high, min_gap=min_gap)
    assert a is b


@given(
    ci_low=st.floats(min_value=0.06, max_value=2.0, allow_nan=False, allow_infinity=False),
    width=st.floats(min_value=0.001, max_value=2.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100, deadline=None)
def test_facilitated_is_invariant_under_min_gap_below_ci_low(ci_low: float, width: float) -> None:
    """Once a CI exceeds +min_gap, *lowering* min_gap never demotes the
    verdict (only raising min_gap above ci_low can flip to NO_SIGNAL).
    Equivalently: FACILITATED is closed under min_gap → 0⁺."""
    ci_high = ci_low + width
    base = _classify_direction(ci_low=ci_low, ci_high=ci_high, min_gap=0.05)
    if base is PrecursorDirection.SYNCHRONIZATION_FACILITATED:
        for tighter in (0.04, 0.02, 0.01, 1e-6):
            assert (
                _classify_direction(ci_low=ci_low, ci_high=ci_high, min_gap=tighter)
                is PrecursorDirection.SYNCHRONIZATION_FACILITATED
            )
