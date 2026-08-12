# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the BTC Field Order v3.2 rule engine."""

from __future__ import annotations

import math

import pytest

from core.strategies.btc_intel import (
    DEFAULT_BTC_RULE_CONFIG,
    BTCMarketSnapshot,
    BTCRule,
    BTCRuleConfig,
    BTCSignal,
    evaluate_btc_rules,
)

# ---- snapshot fixtures ---- #


def _flat_snapshot(**overrides: object) -> BTCMarketSnapshot:
    """A neutral market that fires no rule by default."""
    base: dict[str, object] = {
        "funding_rate": 0.0,
        "open_interest": 1e10,
        "open_interest_delta_bars": 0,
        "price_progress_pct": 0.0,
        "current_volume": 1000.0,
        "baseline_volume": 1000.0,
        "whale_out_btc": 0.0,
        "whale_in_btc": 0.0,
        "exchange_balance_delta": 0.0,
        "exchange_inflow_rising": False,
        "stop_cluster_distance_pct": 5.0,
        "spoof_wall_detected": False,
        "spoof_wall_side": "",
        "bb_width_pct": 5.0,
        "bb_min_lookback_pct": 1.0,
        "atr_min_lookback_pct": 1.0,
        "current_atr_pct": 5.0,
        "volume_direction": 0,
        "good_news_spike_exhausted": False,
        "bad_news_panic_fading": False,
    }
    base.update(overrides)
    return BTCMarketSnapshot(**base)  # type: ignore[arg-type]


def test_default_config_fields() -> None:
    cfg = DEFAULT_BTC_RULE_CONFIG
    assert cfg.fr_extreme == 0.05
    assert cfg.whale_threshold_btc == 500.0
    assert cfg.oi_trap_min_bars == 3
    assert cfg.exchange_drain_threshold < 0.0


def test_flat_snapshot_is_neutral() -> None:
    result = evaluate_btc_rules(_flat_snapshot())
    assert result.signal is BTCSignal.NEUTRAL
    assert result.fired_rules == tuple()


# ---- R01: extreme funding contrarian ---- #


def test_r01_positive_funding_with_fading_volume_shorts() -> None:
    snap = _flat_snapshot(
        funding_rate=0.08,
        current_volume=500.0,
        baseline_volume=1000.0,
    )
    result = evaluate_btc_rules(snap)
    assert result.signal is BTCSignal.SHORT
    assert result.fired_rules == (BTCRule.R01_EXTREME_FUNDING_CONTRARIAN,)
    assert "R01" in result.rationale[0]


def test_r01_negative_funding_with_fading_volume_longs() -> None:
    snap = _flat_snapshot(
        funding_rate=-0.07,
        current_volume=400.0,
        baseline_volume=1000.0,
    )
    result = evaluate_btc_rules(snap)
    assert result.signal is BTCSignal.LONG
    assert result.fired_rules == (BTCRule.R01_EXTREME_FUNDING_CONTRARIAN,)


def test_r01_does_not_fire_with_healthy_volume() -> None:
    """Same extreme FR but volume is still strong → no contrarian trigger."""
    snap = _flat_snapshot(
        funding_rate=0.08,
        current_volume=950.0,
        baseline_volume=1000.0,
    )
    result = evaluate_btc_rules(snap)
    assert result.signal is BTCSignal.NEUTRAL


def test_r01_ignored_when_funding_below_threshold() -> None:
    snap = _flat_snapshot(
        funding_rate=0.02,
        current_volume=100.0,
        baseline_volume=1000.0,
    )
    result = evaluate_btc_rules(snap)
    assert result.signal is BTCSignal.NEUTRAL


# ---- R02: OI/price divergence trap ---- #


def test_r02_oi_rising_no_price_progress_is_avoid() -> None:
    snap = _flat_snapshot(
        open_interest_delta_bars=4,
        price_progress_pct=0.1,
    )
    result = evaluate_btc_rules(snap)
    assert result.signal is BTCSignal.AVOID
    assert result.fired_rules == (BTCRule.R02_OI_PRICE_DIVERGENCE_TRAP,)


def test_r02_ignored_when_price_moved_enough() -> None:
    snap = _flat_snapshot(
        open_interest_delta_bars=5,
        price_progress_pct=1.5,
    )
    result = evaluate_btc_rules(snap)
    assert result.signal is BTCSignal.NEUTRAL


def test_r02_ignored_when_too_few_bars() -> None:
    snap = _flat_snapshot(
        open_interest_delta_bars=1,
        price_progress_pct=0.0,
    )
    result = evaluate_btc_rules(snap)
    assert result.signal is BTCSignal.NEUTRAL


# ---- R03: stop cluster + spoof ---- #


def test_r03_ask_wall_predicts_long_breakout() -> None:
    snap = _flat_snapshot(
        spoof_wall_detected=True,
        spoof_wall_side="ask",
        stop_cluster_distance_pct=0.2,
    )
    result = evaluate_btc_rules(snap)
    assert result.signal is BTCSignal.LONG
    assert result.fired_rules == (BTCRule.R03_STOP_CLUSTER_SPOOF,)


def test_r03_bid_wall_predicts_short_breakout() -> None:
    snap = _flat_snapshot(
        spoof_wall_detected=True,
        spoof_wall_side="bid",
        stop_cluster_distance_pct=0.3,
    )
    result = evaluate_btc_rules(snap)
    assert result.signal is BTCSignal.SHORT


def test_r03_ignored_when_cluster_far() -> None:
    snap = _flat_snapshot(
        spoof_wall_detected=True,
        spoof_wall_side="ask",
        stop_cluster_distance_pct=3.0,
    )
    result = evaluate_btc_rules(snap)
    assert result.signal is BTCSignal.NEUTRAL


# ---- R04: whale distribution ---- #


def test_r04_whale_out_plus_inflow_rising_shorts() -> None:
    snap = _flat_snapshot(
        whale_out_btc=800.0,
        exchange_inflow_rising=True,
    )
    result = evaluate_btc_rules(snap)
    assert result.signal is BTCSignal.SHORT
    assert result.fired_rules == (BTCRule.R04_WHALE_DISTRIBUTION_SHORT,)


def test_r04_ignored_below_whale_threshold() -> None:
    snap = _flat_snapshot(
        whale_out_btc=400.0,
        exchange_inflow_rising=True,
    )
    result = evaluate_btc_rules(snap)
    assert result.signal is BTCSignal.NEUTRAL


# ---- R05: whale accumulation ---- #


def test_r05_whale_in_plus_exchange_drain_longs() -> None:
    snap = _flat_snapshot(
        whale_in_btc=600.0,
        exchange_balance_delta=-2000.0,
    )
    result = evaluate_btc_rules(snap)
    assert result.signal is BTCSignal.LONG
    assert result.fired_rules == (BTCRule.R05_WHALE_ACCUMULATION_LONG,)


def test_r05_ignored_without_drain() -> None:
    snap = _flat_snapshot(
        whale_in_btc=600.0,
        exchange_balance_delta=0.0,
    )
    result = evaluate_btc_rules(snap)
    assert result.signal is BTCSignal.NEUTRAL


# ---- R06: vol squeeze breakout ---- #


def test_r06_bb_atr_squeeze_with_buy_flow_longs() -> None:
    snap = _flat_snapshot(
        bb_width_pct=1.05,
        bb_min_lookback_pct=1.0,
        atr_min_lookback_pct=1.0,
        current_atr_pct=1.05,
        volume_direction=1,
    )
    result = evaluate_btc_rules(snap)
    assert result.signal is BTCSignal.LONG
    assert result.fired_rules == (BTCRule.R06_VOL_SQUEEZE_BREAKOUT,)


def test_r06_squeeze_with_sell_flow_shorts() -> None:
    snap = _flat_snapshot(
        bb_width_pct=1.05,
        bb_min_lookback_pct=1.0,
        atr_min_lookback_pct=1.0,
        current_atr_pct=1.05,
        volume_direction=-1,
    )
    result = evaluate_btc_rules(snap)
    assert result.signal is BTCSignal.SHORT


def test_r06_squeeze_without_direction_is_neutral() -> None:
    """Squeeze without a flow direction must not emit a signal."""
    snap = _flat_snapshot(
        bb_width_pct=1.05,
        bb_min_lookback_pct=1.0,
        atr_min_lookback_pct=1.0,
        current_atr_pct=1.05,
        volume_direction=0,
    )
    result = evaluate_btc_rules(snap)
    assert result.signal is BTCSignal.NEUTRAL


def test_r06_no_squeeze_when_bb_far_from_min() -> None:
    snap = _flat_snapshot(
        bb_width_pct=5.0,
        bb_min_lookback_pct=1.0,
        atr_min_lookback_pct=1.0,
        current_atr_pct=1.05,
        volume_direction=1,
    )
    result = evaluate_btc_rules(snap)
    assert result.signal is BTCSignal.NEUTRAL


# ---- R07: news exhaustion ---- #


def test_r07_good_news_exhausted_shorts() -> None:
    snap = _flat_snapshot(good_news_spike_exhausted=True)
    result = evaluate_btc_rules(snap)
    assert result.signal is BTCSignal.SHORT
    assert result.fired_rules == (BTCRule.R07_NEWS_EXHAUSTION,)


def test_r07_bad_news_fading_longs() -> None:
    snap = _flat_snapshot(bad_news_panic_fading=True)
    result = evaluate_btc_rules(snap)
    assert result.signal is BTCSignal.LONG


# ---- Priority order ---- #


def test_priority_r01_beats_r04() -> None:
    """Both fire → R01 wins because it is earlier in the pipeline."""
    snap = _flat_snapshot(
        funding_rate=0.08,
        current_volume=400.0,
        baseline_volume=1000.0,
        whale_out_btc=800.0,
        exchange_inflow_rising=True,
    )
    result = evaluate_btc_rules(snap)
    assert result.fired_rules == (BTCRule.R01_EXTREME_FUNDING_CONTRARIAN,)


def test_priority_r02_avoid_beats_later_long() -> None:
    """Avoid trap overrides any subsequent long bias."""
    snap = _flat_snapshot(
        open_interest_delta_bars=5,
        price_progress_pct=0.0,
        whale_in_btc=800.0,
        exchange_balance_delta=-2000.0,
    )
    result = evaluate_btc_rules(snap)
    assert result.signal is BTCSignal.AVOID
    assert result.fired_rules == (BTCRule.R02_OI_PRICE_DIVERGENCE_TRAP,)


# ---- Honesty contract ---- #


def test_nan_in_numeric_field_refuses() -> None:
    snap = _flat_snapshot(funding_rate=math.nan)
    result = evaluate_btc_rules(snap)
    assert result.signal is BTCSignal.NEUTRAL
    assert result.refusal_reason != ""
    assert result.fired_rules == tuple()


def test_to_dict_round_trip() -> None:
    snap = _flat_snapshot(
        funding_rate=0.08,
        current_volume=500.0,
        baseline_volume=1000.0,
    )
    result = evaluate_btc_rules(snap)
    payload = result.to_dict()
    assert payload["signal"] == "short"
    fired = payload["fired_rules"]
    assert isinstance(fired, list)
    assert fired[0] == "R01_extreme_funding_contrarian"


# ---- Config validation ---- #


def test_config_rejects_non_positive_fr_extreme() -> None:
    with pytest.raises(ValueError, match="fr_extreme"):
        BTCRuleConfig(fr_extreme=0.0)


def test_config_rejects_bad_volume_fade_ratio() -> None:
    with pytest.raises(ValueError, match="volume_fade_ratio"):
        BTCRuleConfig(volume_fade_ratio=1.5)


def test_config_rejects_positive_exchange_drain_threshold() -> None:
    with pytest.raises(ValueError, match="exchange_drain_threshold"):
        BTCRuleConfig(exchange_drain_threshold=500.0)


def test_config_rejects_small_squeeze_ratio() -> None:
    with pytest.raises(ValueError, match="bb_squeeze_ratio"):
        BTCRuleConfig(bb_squeeze_ratio=0.9)


def test_custom_config_loosens_threshold() -> None:
    cfg = BTCRuleConfig(whale_threshold_btc=100.0)
    snap = _flat_snapshot(
        whale_in_btc=200.0,
        exchange_balance_delta=-2000.0,
    )
    result = evaluate_btc_rules(snap, cfg)
    assert result.signal is BTCSignal.LONG
