# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Dedicated decision-boundary teeth for the π-system phase-entry gate.

The gate composes four scalars (R, ΔH, κ̄, H) into LONG / SHORT / NEUTRAL via a
conjunctive base trigger plus a regime split. Every comparison and boolean is
pinned here so a mutated operator flips a signal:

    LONG  ⟺ R > r_thr ∧ ΔH < ΔH_thr ∧ κ̄ < κ_thr ∧ H > H_long
    SHORT ⟺ (base trigger) ∧ H < H_short
    NEUTRAL otherwise; NaN in ⟹ NEUTRAL out (honesty contract).
"""

from __future__ import annotations

import math

from core.indicators.phase_entry_gate import (
    DEFAULT_PHASE_ENTRY_CONFIG,
    PhaseEntryGate,
    PhaseEntryGateConfig,
    Signal,
)

# Inputs that clear every base condition with margin; per-test overrides flip one.
_LONG = {"r_kuramoto": 0.90, "delta_h": -0.10, "kappa_mean": -0.20, "hurst": 0.70}
_SHORT = {**_LONG, "hurst": 0.30}


def _gate() -> PhaseEntryGate:
    return PhaseEntryGate()


def test_all_base_conditions_and_persistence_give_long() -> None:
    reading = _gate().evaluate(**_LONG)
    assert reading.signal is Signal.LONG
    assert reading.conditions.r_sync
    assert reading.conditions.entropy_decreasing
    assert reading.conditions.curvature_focusing
    assert reading.conditions.persistent_long


def test_base_conditions_with_mean_reversion_give_short() -> None:
    assert _gate().evaluate(**_SHORT).signal is Signal.SHORT


def test_hurst_in_dead_zone_is_neutral_despite_base_trigger() -> None:
    # base trigger holds, but 0.45 <= H <= 0.55 is neither persistent nor reverting
    assert _gate().evaluate(**{**_LONG, "hurst": 0.50}).signal is Signal.NEUTRAL


def test_weak_sync_blocks_long_even_when_persistent() -> None:
    """R at the threshold is NOT sync (strict >), so base trigger fails -> NEUTRAL.

    Kills the `base_trigger and persistent_long` guard: with base False but
    persistent True, an And->Or would wrongly emit LONG.
    """
    reading = _gate().evaluate(**{**_LONG, "r_kuramoto": 0.75})
    assert reading.conditions.r_sync is False
    assert reading.conditions.persistent_long is True
    assert reading.signal is Signal.NEUTRAL


def test_weak_sync_blocks_short_even_when_mean_reverting() -> None:
    """base False but mean_reverting True must stay NEUTRAL (kills base∧mean_rev)."""
    reading = _gate().evaluate(**{**_SHORT, "r_kuramoto": 0.75})
    assert reading.conditions.r_sync is False
    assert reading.conditions.mean_reverting_short is True
    assert reading.signal is Signal.NEUTRAL


def test_rising_entropy_blocks_trigger() -> None:
    reading = _gate().evaluate(**{**_LONG, "delta_h": 0.0})
    assert reading.conditions.entropy_decreasing is False
    assert reading.signal is Signal.NEUTRAL


def test_defocusing_curvature_blocks_trigger() -> None:
    reading = _gate().evaluate(**{**_LONG, "kappa_mean": 0.0})
    assert reading.conditions.curvature_focusing is False
    assert reading.signal is Signal.NEUTRAL


def test_persistent_and_mean_revert_are_mutually_exclusive_flags() -> None:
    long_read = _gate().evaluate(**_LONG)
    assert long_read.conditions.persistent_long and not long_read.conditions.mean_reverting_short
    short_read = _gate().evaluate(**_SHORT)
    assert short_read.conditions.mean_reverting_short and not short_read.conditions.persistent_long


def test_nan_in_yields_neutral_out() -> None:
    for bad in ("r_kuramoto", "delta_h", "kappa_mean", "hurst"):
        reading = _gate().evaluate(**{**_LONG, bad: math.nan})
        assert reading.signal is Signal.NEUTRAL, f"{bad}=NaN must force NEUTRAL"
    # Positive control: the same inputs finite DO fire (proves NaN is the cause).
    assert _gate().evaluate(**_LONG).signal is Signal.LONG


def test_infinity_in_yields_neutral_out() -> None:
    assert _gate().evaluate(**{**_LONG, "hurst": math.inf}).signal is Signal.NEUTRAL


def test_config_fallback_uses_default_but_keeps_a_custom_config() -> None:
    """`config or DEFAULT_PHASE_ENTRY_CONFIG` -- None falls back, a real one stays.

    Kills the Or->And fallback: under And a truthy custom config collapses to the
    default, silently discarding caller thresholds.
    """
    assert PhaseEntryGate().config is DEFAULT_PHASE_ENTRY_CONFIG
    custom = PhaseEntryGateConfig(r_threshold=0.5)
    assert PhaseEntryGate(custom).config is custom
    # And the custom threshold actually governs: R=0.6 is sync under 0.5, not 0.75.
    reading = PhaseEntryGate(custom).evaluate(**{**_LONG, "r_kuramoto": 0.60})
    assert reading.conditions.r_sync is True
    assert reading.signal is Signal.LONG
