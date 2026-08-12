# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the unified trading decision composer."""

from __future__ import annotations

import math

import pytest

from core.strategies.btc_intel import BTCMarketSnapshot
from core.strategies.trading_composer import (
    DEFAULT_TRADING_COMPOSER_CONFIG,
    CompositeDecision,
    CompositeSignal,
    TradingComposer,
    TradingComposerConfig,
    TradingSnapshot,
    compose_decision,
)

# ---- fixtures ---- #


def _flat_btc(
    *,
    funding_rate: float = 0.0,
    open_interest: float = 1e10,
    open_interest_delta_bars: int = 0,
    price_progress_pct: float = 0.0,
    current_volume: float = 1000.0,
    baseline_volume: float = 1000.0,
    whale_out_btc: float = 0.0,
    whale_in_btc: float = 0.0,
    exchange_balance_delta: float = 0.0,
    exchange_inflow_rising: bool = False,
    stop_cluster_distance_pct: float = 5.0,
    spoof_wall_detected: bool = False,
    spoof_wall_side: str = "",
    bb_width_pct: float = 5.0,
    bb_min_lookback_pct: float = 1.0,
    atr_min_lookback_pct: float = 1.0,
    current_atr_pct: float = 5.0,
    volume_direction: int = 0,
    good_news_spike_exhausted: bool = False,
    bad_news_panic_fading: bool = False,
) -> BTCMarketSnapshot:
    """BTC snapshot that fires no rule unless overrides are supplied."""
    return BTCMarketSnapshot(
        funding_rate=funding_rate,
        open_interest=open_interest,
        open_interest_delta_bars=open_interest_delta_bars,
        price_progress_pct=price_progress_pct,
        current_volume=current_volume,
        baseline_volume=baseline_volume,
        whale_out_btc=whale_out_btc,
        whale_in_btc=whale_in_btc,
        exchange_balance_delta=exchange_balance_delta,
        exchange_inflow_rising=exchange_inflow_rising,
        stop_cluster_distance_pct=stop_cluster_distance_pct,
        spoof_wall_detected=spoof_wall_detected,
        spoof_wall_side=spoof_wall_side,
        bb_width_pct=bb_width_pct,
        bb_min_lookback_pct=bb_min_lookback_pct,
        atr_min_lookback_pct=atr_min_lookback_pct,
        current_atr_pct=current_atr_pct,
        volume_direction=volume_direction,
        good_news_spike_exhausted=good_news_spike_exhausted,
        bad_news_panic_fading=bad_news_panic_fading,
    )


def _snapshot(
    *,
    r: float = 0.5,
    dh: float = 0.0,
    kappa: float = 0.0,
    h: float = 0.5,
    qilm: float = 0.0,
    fmn: float = 0.0,
    btc: BTCMarketSnapshot | None = None,
) -> TradingSnapshot:
    return TradingSnapshot(
        r_kuramoto=r,
        delta_h=dh,
        kappa_mean=kappa,
        hurst=h,
        qilm_latest=qilm,
        fmn_latest=fmn,
        btc_snapshot=btc or _flat_btc(),
    )


# ---- baseline ---- #


def test_default_config_creates() -> None:
    cfg = DEFAULT_TRADING_COMPOSER_CONFIG
    assert cfg.flow_min_magnitude == 0.20


def test_fully_neutral_snapshot_is_neutral() -> None:
    result = compose_decision(_snapshot())
    assert result.signal is CompositeSignal.NEUTRAL
    assert result.source_layer == "neutral"
    assert result.flow_sign == 0
    assert not result.conflict_detected


# ---- Layer 1: BTC rules dominance ---- #


def test_btc_r02_avoid_wins_over_everything() -> None:
    """Trap geometry overrides a simultaneously-triggered π-gate LONG."""
    trap = _flat_btc(open_interest_delta_bars=5, price_progress_pct=0.0)
    snap = _snapshot(
        r=0.85,
        dh=-0.15,
        kappa=-0.25,
        h=0.65,
        qilm=0.50,
        fmn=0.50,
        btc=trap,
    )
    result = compose_decision(snap)
    assert result.signal is CompositeSignal.AVOID
    assert result.source_layer == "btc_rules"
    assert "R02" in " ".join(result.rationale)


def test_btc_directional_signal_outranks_phase_gate() -> None:
    """BTC R01 SHORT wins even when the π-gate would say LONG."""
    crowded = _flat_btc(
        funding_rate=0.08,
        current_volume=400.0,
        baseline_volume=1000.0,
    )
    snap = _snapshot(
        r=0.85,
        dh=-0.15,
        kappa=-0.25,
        h=0.65,
        qilm=0.50,
        fmn=0.50,
        btc=crowded,
    )
    result = compose_decision(snap)
    assert result.signal is CompositeSignal.SHORT
    assert result.source_layer == "btc_rules"


# ---- Layer 2: phase gate + flow confirmation ---- #


def test_phase_long_confirmed_by_flow_is_long() -> None:
    snap = _snapshot(
        r=0.85,
        dh=-0.15,
        kappa=-0.25,
        h=0.65,
        qilm=0.30,
        fmn=0.30,
    )
    result = compose_decision(snap)
    assert result.signal is CompositeSignal.LONG
    assert result.source_layer == "phase_gate"
    assert result.flow_sign == 1
    assert not result.conflict_detected


def test_phase_short_confirmed_by_flow_is_short() -> None:
    snap = _snapshot(
        r=0.85,
        dh=-0.15,
        kappa=-0.25,
        h=0.30,
        qilm=-0.30,
        fmn=-0.30,
    )
    result = compose_decision(snap)
    assert result.signal is CompositeSignal.SHORT
    assert result.source_layer == "phase_gate"
    assert result.flow_sign == -1


def test_phase_long_without_flow_support_is_neutral() -> None:
    """π-gate alone is not enough — flow must agree in sign."""
    snap = _snapshot(
        r=0.85,
        dh=-0.15,
        kappa=-0.25,
        h=0.65,
        qilm=0.0,
        fmn=0.0,
    )
    result = compose_decision(snap)
    assert result.signal is CompositeSignal.NEUTRAL
    assert result.source_layer == "phase_gate"
    # Flow sign is 0, so no active conflict
    assert not result.conflict_detected


def test_phase_long_vs_bearish_flow_flags_conflict() -> None:
    """π-gate LONG but QILM+FMN strongly negative → NEUTRAL + conflict."""
    snap = _snapshot(
        r=0.85,
        dh=-0.15,
        kappa=-0.25,
        h=0.65,
        qilm=-0.40,
        fmn=-0.40,
    )
    result = compose_decision(snap)
    assert result.signal is CompositeSignal.NEUTRAL
    assert result.source_layer == "phase_gate"
    assert result.conflict_detected


# ---- Layer 3: flow-only fallback ---- #


def test_flow_only_long_when_both_metrics_positive() -> None:
    snap = _snapshot(
        r=0.50,  # below threshold → π-gate silent
        qilm=0.50,
        fmn=0.40,
    )
    result = compose_decision(snap)
    assert result.signal is CompositeSignal.LONG
    assert result.source_layer == "flow_metrics"
    assert result.flow_sign == 1


def test_flow_only_short_when_both_metrics_negative() -> None:
    snap = _snapshot(r=0.50, qilm=-0.30, fmn=-0.30)
    result = compose_decision(snap)
    assert result.signal is CompositeSignal.SHORT
    assert result.flow_sign == -1


def test_flow_disagreement_is_neutral() -> None:
    snap = _snapshot(r=0.50, qilm=0.50, fmn=-0.40)
    result = compose_decision(snap)
    assert result.signal is CompositeSignal.NEUTRAL
    assert result.flow_sign == 0


def test_flow_below_magnitude_threshold_is_neutral() -> None:
    """One metric below ``flow_min_magnitude`` → downgrade."""
    snap = _snapshot(r=0.50, qilm=0.10, fmn=0.30)
    result = compose_decision(snap)
    assert result.signal is CompositeSignal.NEUTRAL
    assert result.flow_sign == 0


# ---- Honesty contract ---- #


def test_nan_in_scalar_refuses() -> None:
    snap = _snapshot(r=math.nan)
    result = compose_decision(snap)
    assert result.signal is CompositeSignal.NEUTRAL
    assert result.refusal_reason != ""


def test_nan_in_btc_snapshot_refuses() -> None:
    trap = _flat_btc(funding_rate=math.nan)
    snap = _snapshot(qilm=0.5, fmn=0.5, btc=trap)
    result = compose_decision(snap)
    assert result.signal is CompositeSignal.NEUTRAL
    assert result.refusal_reason != ""


def test_inf_in_qilm_refuses() -> None:
    snap = _snapshot(qilm=math.inf)
    result = compose_decision(snap)
    assert result.signal is CompositeSignal.NEUTRAL
    assert result.refusal_reason != ""


# ---- Composer facade ---- #


def test_composer_facade_preserves_config() -> None:
    cfg = TradingComposerConfig(flow_min_magnitude=0.50)
    composer = TradingComposer(cfg)
    assert composer.config.flow_min_magnitude == 0.50


def test_composer_facade_threshold_strictness() -> None:
    """Tighter ``flow_min_magnitude`` must silence a marginal signal."""
    cfg = TradingComposerConfig(flow_min_magnitude=0.60)
    snap = _snapshot(r=0.50, qilm=0.40, fmn=0.40)
    result = TradingComposer(cfg).compose(snap)
    assert result.signal is CompositeSignal.NEUTRAL


def test_composer_invalid_config_raises() -> None:
    with pytest.raises(ValueError, match="flow_min_magnitude"):
        TradingComposerConfig(flow_min_magnitude=0.0)


# ---- to_dict round-trip ---- #


def test_decision_to_dict_exposes_subsystem_provenance() -> None:
    trap = _flat_btc(funding_rate=0.08, current_volume=400.0, baseline_volume=1000.0)
    snap = _snapshot(qilm=0.5, fmn=0.5, btc=trap)
    result = compose_decision(snap)
    payload = result.to_dict()
    assert payload["signal"] == "short"
    assert payload["source_layer"] == "btc_rules"
    assert isinstance(payload["btc_result"], dict)
    assert isinstance(payload["phase_reading"], dict)


def test_decision_is_frozen_dataclass() -> None:
    from dataclasses import FrozenInstanceError

    result = compose_decision(_snapshot())
    with pytest.raises(FrozenInstanceError):
        # Frozen dataclass must reject attribute assignment via setattr,
        # which exercises the __setattr__ guard installed by @dataclass(frozen=True).
        setattr(result, "signal", CompositeSignal.LONG)  # noqa: B010


# ---- Determinism ---- #


def test_compose_is_deterministic() -> None:
    snap = _snapshot(
        r=0.85,
        dh=-0.15,
        kappa=-0.25,
        h=0.65,
        qilm=0.30,
        fmn=0.30,
    )
    a = compose_decision(snap)
    b = compose_decision(snap)
    assert a.signal is b.signal
    assert a.source_layer == b.source_layer
    assert a.to_dict() == b.to_dict()


def test_flat_composite_decision_instance_shape() -> None:
    result = compose_decision(_snapshot())
    assert isinstance(result, CompositeDecision)
    assert isinstance(result.btc_result.to_dict(), dict)
    assert isinstance(result.phase_reading.to_dict(), dict)
