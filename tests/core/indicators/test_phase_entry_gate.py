# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the π-system composite phase-entry gate."""

from __future__ import annotations

import math

import pytest

from core.indicators import (
    DEFAULT_PHASE_ENTRY_CONFIG,
    PhaseEntryGate,
    PhaseEntryGateConfig,
    Signal,
)


def _gate() -> PhaseEntryGate:
    return PhaseEntryGate()


def test_default_config_is_canonical() -> None:
    cfg = DEFAULT_PHASE_ENTRY_CONFIG
    assert cfg.r_threshold == 0.75
    assert cfg.delta_h_threshold == -0.05
    assert cfg.kappa_threshold == -0.1
    assert cfg.hurst_long_threshold == 0.55
    assert cfg.hurst_short_threshold == 0.45


def test_long_signal_when_all_conditions_met() -> None:
    reading = _gate().evaluate(
        r_kuramoto=0.80,
        delta_h=-0.10,
        kappa_mean=-0.20,
        hurst=0.60,
    )
    assert reading.signal is Signal.LONG
    conds = reading.conditions
    assert conds.r_sync
    assert conds.entropy_decreasing
    assert conds.curvature_focusing
    assert conds.persistent_long
    assert not conds.mean_reverting_short


def test_short_signal_when_hurst_antipersistent() -> None:
    reading = _gate().evaluate(
        r_kuramoto=0.80,
        delta_h=-0.10,
        kappa_mean=-0.20,
        hurst=0.30,
    )
    assert reading.signal is Signal.SHORT
    assert reading.conditions.mean_reverting_short
    assert not reading.conditions.persistent_long


def test_neutral_when_r_below_threshold() -> None:
    reading = _gate().evaluate(
        r_kuramoto=0.50,
        delta_h=-0.10,
        kappa_mean=-0.20,
        hurst=0.60,
    )
    assert reading.signal is Signal.NEUTRAL
    assert not reading.conditions.r_sync


def test_neutral_when_entropy_increasing() -> None:
    reading = _gate().evaluate(
        r_kuramoto=0.80,
        delta_h=0.01,  # entropy going up → system de-ordering
        kappa_mean=-0.20,
        hurst=0.60,
    )
    assert reading.signal is Signal.NEUTRAL
    assert not reading.conditions.entropy_decreasing


def test_neutral_when_curvature_not_focusing() -> None:
    reading = _gate().evaluate(
        r_kuramoto=0.80,
        delta_h=-0.10,
        kappa_mean=0.05,
        hurst=0.60,
    )
    assert reading.signal is Signal.NEUTRAL
    assert not reading.conditions.curvature_focusing


def test_neutral_when_hurst_in_ambiguous_middle() -> None:
    """0.45 < H < 0.55 → neither persistent nor mean-reverting."""
    reading = _gate().evaluate(
        r_kuramoto=0.80,
        delta_h=-0.10,
        kappa_mean=-0.20,
        hurst=0.50,
    )
    assert reading.signal is Signal.NEUTRAL
    assert not reading.conditions.persistent_long
    assert not reading.conditions.mean_reverting_short


def test_nan_input_forces_neutral() -> None:
    """Honesty contract: NaN in any input → NEUTRAL out."""
    for field in ("r_kuramoto", "delta_h", "kappa_mean", "hurst"):
        kwargs = {
            "r_kuramoto": 0.80,
            "delta_h": -0.10,
            "kappa_mean": -0.20,
            "hurst": 0.60,
        }
        kwargs[field] = math.nan
        reading = _gate().evaluate(**kwargs)
        assert reading.signal is Signal.NEUTRAL, f"NaN in {field} should be NEUTRAL"


def test_infinity_input_forces_neutral() -> None:
    reading = _gate().evaluate(
        r_kuramoto=math.inf,
        delta_h=-0.10,
        kappa_mean=-0.20,
        hurst=0.60,
    )
    assert reading.signal is Signal.NEUTRAL


def test_diagnostics_record_raw_inputs() -> None:
    reading = _gate().evaluate(
        r_kuramoto=0.77,
        delta_h=-0.06,
        kappa_mean=-0.15,
        hurst=0.58,
    )
    diag = reading.diagnostics
    assert diag["r_kuramoto"] == pytest.approx(0.77)
    assert diag["delta_h"] == pytest.approx(-0.06)
    assert diag["kappa_mean"] == pytest.approx(-0.15)
    assert diag["hurst"] == pytest.approx(0.58)


def test_to_dict_round_trip() -> None:
    reading = _gate().evaluate(
        r_kuramoto=0.80,
        delta_h=-0.10,
        kappa_mean=-0.20,
        hurst=0.60,
    )
    payload = reading.to_dict()
    assert payload["signal"] == "long"
    conditions = payload["conditions"]
    assert isinstance(conditions, dict)
    assert conditions["r_sync"] is True
    diagnostics = payload["diagnostics"]
    assert isinstance(diagnostics, dict)
    assert "r_kuramoto" in diagnostics


def test_config_rejects_invalid_r_threshold() -> None:
    with pytest.raises(ValueError, match="r_threshold"):
        PhaseEntryGateConfig(r_threshold=1.5)


def test_config_rejects_overlapping_hurst_bands() -> None:
    with pytest.raises(ValueError, match="hurst_short_threshold"):
        PhaseEntryGateConfig(hurst_long_threshold=0.40, hurst_short_threshold=0.50)


def test_custom_config_applied() -> None:
    cfg = PhaseEntryGateConfig(
        r_threshold=0.60,
        delta_h_threshold=-0.01,
        kappa_threshold=0.0,
        hurst_long_threshold=0.52,
        hurst_short_threshold=0.48,
    )
    gate = PhaseEntryGate(cfg)
    # Looser thresholds: a borderline reading now qualifies as LONG.
    reading = gate.evaluate(
        r_kuramoto=0.65,
        delta_h=-0.02,
        kappa_mean=-0.001,
        hurst=0.53,
    )
    assert reading.signal is Signal.LONG


def test_edge_r_at_exact_threshold_is_neutral() -> None:
    """Rule uses strict ``>`` — exact equality should NOT trigger."""
    reading = _gate().evaluate(
        r_kuramoto=0.75,  # == threshold, not >
        delta_h=-0.10,
        kappa_mean=-0.20,
        hurst=0.60,
    )
    assert reading.signal is Signal.NEUTRAL
    assert not reading.conditions.r_sync
