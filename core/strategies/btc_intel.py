# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""BTC Market Intelligence — deterministic IF-THEN rule engine.

This module is the formal encoding of the author's ``BTC_Field_Order_v3_2``
specification (``06_РИЗИК_ТА_ФОРМАЛІЗАЦІЯ/BTC_Field_Order_v3_2_fixed.pdf``
in the crypto-research archive). That document was not a vague strategy
sketch — it was a strict prompt contract with a deterministic IF-THEN
§7 that operates on a narrow, well-typed market snapshot.

Here it becomes executable Python:

* ``BTCMarketSnapshot`` — the frozen, slotted data class holding exactly
  the fields the spec expects (funding rate, OI, price, whale flows,
  volume regime, BB/ATR squeeze state, news flags).
* ``BTCRule`` — enum naming each §7 rule so diagnostics and audit
  trails are human-readable and grep-able.
* ``BTCSignal`` — the decision enum (``LONG``, ``SHORT``, ``NEUTRAL``,
  ``AVOID``). ``AVOID`` is distinct from ``NEUTRAL``: it means the rule
  engine refuses to emit a signal because the market is in a known
  trap geometry (OI squeeze pending, spoofed walls, etc).
* ``BTCRuleResult`` — result type with signal + fired rules + rationale.
  The caller always gets a full audit trail.
* ``evaluate_btc_rules`` — pure function: snapshot + config → result.

Priority
--------
Rules are evaluated in priority order. First conclusive match wins. If
no rule fires, the result is ``NEUTRAL`` with an empty ``fired_rules``
list. The priority order mirrors the spec's §7 ordering:

1. ``R01_EXTREME_FUNDING_CONTRARIAN`` — |FR| ≥ FR_extreme AND volume fading
2. ``R02_OI_PRICE_DIVERGENCE_TRAP`` — OI rising ≥ min_bars without price progress
3. ``R03_STOP_CLUSTER_SPOOF`` — stop cluster near a spoofed wall
4. ``R04_WHALE_DISTRIBUTION_SHORT`` — whale_out ≥ 500 BTC + exch_in↑
5. ``R05_WHALE_ACCUMULATION_LONG`` — whale_in ≥ 500 BTC + exch balance↓
6. ``R06_VOL_SQUEEZE_BREAKOUT`` — BB/ATR minimum + volume direction
7. ``R07_NEWS_EXHAUSTION`` — good-news spike exhausted OR bad-news panic fading

Fail-closed honesty
-------------------
A snapshot containing NaN in any load-bearing numeric field forces
``NEUTRAL`` with ``refusal_reason`` populated. The module does not
silently coerce missing data into a decision — this matches
``agent/invariants.INV_004_nan_policy``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Final

__all__ = [
    "BTCRule",
    "BTCSignal",
    "BTCMarketSnapshot",
    "BTCRuleConfig",
    "BTCRuleResult",
    "DEFAULT_BTC_RULE_CONFIG",
    "evaluate_btc_rules",
]


class BTCRule(Enum):
    """Named IF-THEN rules from §7 of BTC Field Order v3.2."""

    R01_EXTREME_FUNDING_CONTRARIAN = "R01_extreme_funding_contrarian"
    R02_OI_PRICE_DIVERGENCE_TRAP = "R02_oi_price_divergence_trap"
    R03_STOP_CLUSTER_SPOOF = "R03_stop_cluster_spoof"
    R04_WHALE_DISTRIBUTION_SHORT = "R04_whale_distribution_short"
    R05_WHALE_ACCUMULATION_LONG = "R05_whale_accumulation_long"
    R06_VOL_SQUEEZE_BREAKOUT = "R06_vol_squeeze_breakout"
    R07_NEWS_EXHAUSTION = "R07_news_exhaustion"


class BTCSignal(Enum):
    """Four-state decision output."""

    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"
    AVOID = "avoid"


@dataclass(frozen=True, slots=True)
class BTCMarketSnapshot:
    """Strict market snapshot — every field the §4 STRICT input demands.

    All numeric fields must be finite; NaN is treated as "unknown" and
    forces ``NEUTRAL`` with a refusal. News flag booleans default to
    ``False`` — the absence of a flag means "no news event in scope".
    """

    # Core derivatives + spot
    funding_rate: float  # latest 8h funding rate
    open_interest: float  # current OI notional
    open_interest_delta_bars: int  # consecutive bars OI has been rising
    price_progress_pct: float  # % change over `open_interest_delta_bars`
    current_volume: float  # rolling volume over the last look-back
    baseline_volume: float  # rolling baseline volume
    # Whale / on-chain
    whale_out_btc: float  # sum of exchange outflows (positive = outflow)
    whale_in_btc: float  # sum of exchange inflows
    exchange_balance_delta: float  # Δ total exchange balance (negative = drain)
    exchange_inflow_rising: bool  # is exchange inflow trending up?
    # Order book microstructure
    stop_cluster_distance_pct: float  # distance of nearest stop cluster (%)
    spoof_wall_detected: bool  # is there a spoofed wall near the cluster?
    spoof_wall_side: str  # "bid" / "ask" / "" (empty = none)
    # Volatility regime
    bb_width_pct: float  # Bollinger band width as % of mid
    bb_min_lookback_pct: float  # minimum BB width over lookback
    atr_min_lookback_pct: float  # minimum ATR over lookback
    current_atr_pct: float  # current ATR %
    volume_direction: int  # +1 buy-dominant, −1 sell-dominant, 0 flat
    # News
    good_news_spike_exhausted: bool = False
    bad_news_panic_fading: bool = False

    def has_nan(self) -> bool:
        """Return True iff any numeric field is non-finite."""
        for value in (
            self.funding_rate,
            self.open_interest,
            self.price_progress_pct,
            self.current_volume,
            self.baseline_volume,
            self.whale_out_btc,
            self.whale_in_btc,
            self.exchange_balance_delta,
            self.stop_cluster_distance_pct,
            self.bb_width_pct,
            self.bb_min_lookback_pct,
            self.atr_min_lookback_pct,
            self.current_atr_pct,
        ):
            if not math.isfinite(value):
                return True
        return False


@dataclass(frozen=True, slots=True)
class BTCRuleConfig:
    """Thresholds for the §7 rule engine.

    Defaults are lifted verbatim from the Field Order spec where the
    spec gives a number, and chosen to match common crypto-desk practice
    otherwise. Every knob is explicit so a backtest can sweep them.
    """

    #: |funding rate| threshold for contrarian trigger (R01).
    fr_extreme: float = 0.05
    #: Volume fade ratio: current/baseline below this → "fading" (R01).
    volume_fade_ratio: float = 0.7
    #: Minimum consecutive OI-rising bars without price progress (R02).
    oi_trap_min_bars: int = 3
    #: Maximum |price_progress| that still counts as "no progress" (R02).
    oi_trap_max_price_progress_pct: float = 0.3
    #: Max distance of stop cluster considered "near" (R03), as % of price.
    stop_cluster_near_pct: float = 0.5
    #: Whale outflow / inflow threshold in BTC (R04/R05).
    whale_threshold_btc: float = 500.0
    #: Exchange balance drain considered "significant" (R05), negative.
    exchange_drain_threshold: float = -1000.0
    #: Ratio of BB-width to lookback minimum for "squeeze" (R06).
    bb_squeeze_ratio: float = 1.1
    #: Same for ATR.
    atr_squeeze_ratio: float = 1.1

    def __post_init__(self) -> None:
        if self.fr_extreme <= 0:
            raise ValueError(f"fr_extreme must be > 0, got {self.fr_extreme}")
        if not 0.0 < self.volume_fade_ratio <= 1.0:
            raise ValueError(
                f"volume_fade_ratio must be in (0, 1], got {self.volume_fade_ratio}",
            )
        if self.oi_trap_min_bars < 1:
            raise ValueError(
                f"oi_trap_min_bars must be >= 1, got {self.oi_trap_min_bars}",
            )
        if self.whale_threshold_btc <= 0:
            raise ValueError(
                f"whale_threshold_btc must be > 0, got {self.whale_threshold_btc}",
            )
        if self.exchange_drain_threshold >= 0:
            raise ValueError(
                "exchange_drain_threshold must be < 0 (drain = negative), "
                f"got {self.exchange_drain_threshold}",
            )
        if self.bb_squeeze_ratio < 1.0:
            raise ValueError(
                f"bb_squeeze_ratio must be >= 1.0, got {self.bb_squeeze_ratio}",
            )
        if self.atr_squeeze_ratio < 1.0:
            raise ValueError(
                f"atr_squeeze_ratio must be >= 1.0, got {self.atr_squeeze_ratio}",
            )


DEFAULT_BTC_RULE_CONFIG: Final[BTCRuleConfig] = BTCRuleConfig()


@dataclass(frozen=True, slots=True)
class BTCRuleResult:
    """Rule-engine output with full audit trail."""

    signal: BTCSignal
    fired_rules: tuple[BTCRule, ...]
    rationale: tuple[str, ...]
    diagnostics: dict[str, float | int | bool | str] = field(default_factory=dict)
    refusal_reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "signal": self.signal.value,
            "fired_rules": [r.value for r in self.fired_rules],
            "rationale": list(self.rationale),
            "diagnostics": dict(self.diagnostics),
            "refusal_reason": self.refusal_reason,
        }


def _diag(snapshot: BTCMarketSnapshot) -> dict[str, float | int | bool | str]:
    """Build a flat diagnostics dict for every result."""
    return {
        "funding_rate": snapshot.funding_rate,
        "oi_delta_bars": snapshot.open_interest_delta_bars,
        "price_progress_pct": snapshot.price_progress_pct,
        "volume_ratio": (
            snapshot.current_volume / snapshot.baseline_volume
            if snapshot.baseline_volume > 0.0
            else math.nan
        ),
        "whale_out_btc": snapshot.whale_out_btc,
        "whale_in_btc": snapshot.whale_in_btc,
        "exchange_balance_delta": snapshot.exchange_balance_delta,
        "stop_cluster_distance_pct": snapshot.stop_cluster_distance_pct,
        "spoof_wall_detected": snapshot.spoof_wall_detected,
        "spoof_wall_side": snapshot.spoof_wall_side,
        "bb_width_pct": snapshot.bb_width_pct,
        "bb_min_lookback_pct": snapshot.bb_min_lookback_pct,
        "atr_min_lookback_pct": snapshot.atr_min_lookback_pct,
        "current_atr_pct": snapshot.current_atr_pct,
        "volume_direction": snapshot.volume_direction,
        "good_news_spike_exhausted": snapshot.good_news_spike_exhausted,
        "bad_news_panic_fading": snapshot.bad_news_panic_fading,
    }


def _rule_01_extreme_funding(
    snap: BTCMarketSnapshot, cfg: BTCRuleConfig
) -> tuple[BTCSignal, str] | None:
    """R01: |FR| ≥ fr_extreme AND volume fading → contrarian trade."""
    if snap.baseline_volume <= 0.0:
        return None
    if abs(snap.funding_rate) < cfg.fr_extreme:
        return None
    vol_ratio = snap.current_volume / snap.baseline_volume
    if vol_ratio >= cfg.volume_fade_ratio:
        return None
    # Extreme positive funding + fading volume → longs overcrowded → SHORT.
    # Extreme negative funding + fading volume → shorts overcrowded → LONG.
    if snap.funding_rate >= cfg.fr_extreme:
        return (
            BTCSignal.SHORT,
            f"R01: FR={snap.funding_rate:+.4f} ≥ {cfg.fr_extreme} "
            f"and volume ratio {vol_ratio:.2f} < {cfg.volume_fade_ratio} "
            "→ long-side crowded, contrarian short",
        )
    return (
        BTCSignal.LONG,
        f"R01: FR={snap.funding_rate:+.4f} ≤ −{cfg.fr_extreme} "
        f"and volume ratio {vol_ratio:.2f} < {cfg.volume_fade_ratio} "
        "→ short-side crowded, contrarian long",
    )


def _rule_02_oi_price_divergence(
    snap: BTCMarketSnapshot, cfg: BTCRuleConfig
) -> tuple[BTCSignal, str] | None:
    """R02: OI rising ≥ N bars without price progress → trap (AVOID)."""
    if snap.open_interest_delta_bars < cfg.oi_trap_min_bars:
        return None
    if abs(snap.price_progress_pct) > cfg.oi_trap_max_price_progress_pct:
        return None
    return (
        BTCSignal.AVOID,
        f"R02: OI rising for {snap.open_interest_delta_bars} bars "
        f"(≥ {cfg.oi_trap_min_bars}) while price moved only "
        f"{snap.price_progress_pct:+.2f}% — squeeze pending, avoid entry",
    )


def _rule_03_stop_cluster_spoof(
    snap: BTCMarketSnapshot, cfg: BTCRuleConfig
) -> tuple[BTCSignal, str] | None:
    """R03: stop cluster near a spoofed wall → break toward liquidity."""
    if not snap.spoof_wall_detected:
        return None
    if snap.stop_cluster_distance_pct > cfg.stop_cluster_near_pct:
        return None
    # A spoof wall near a stop cluster telegraphs a hunt: price gets
    # pushed into the cluster, the wall pulls, and the market moves AWAY
    # from the wall once the stops fire.
    if snap.spoof_wall_side == "ask":
        # Ask-side wall → price pushed up into the wall; then wall pulls
        # → squeeze LONG.
        return (
            BTCSignal.LONG,
            "R03: spoof wall on ask + nearby stop cluster → stops hunt then breakout long",
        )
    if snap.spoof_wall_side == "bid":
        return (
            BTCSignal.SHORT,
            "R03: spoof wall on bid + nearby stop cluster → stops hunt then breakout short",
        )
    return None


def _rule_04_whale_distribution(
    snap: BTCMarketSnapshot, cfg: BTCRuleConfig
) -> tuple[BTCSignal, str] | None:
    """R04: whale_out ≥ 500 BTC AND exchange inflow rising → SHORT."""
    if snap.whale_out_btc < cfg.whale_threshold_btc:
        return None
    if not snap.exchange_inflow_rising:
        return None
    return (
        BTCSignal.SHORT,
        f"R04: whale outflow {snap.whale_out_btc:.0f} BTC "
        f"≥ {cfg.whale_threshold_btc:.0f} and exchange inflow rising "
        "→ distribution, short-bias",
    )


def _rule_05_whale_accumulation(
    snap: BTCMarketSnapshot, cfg: BTCRuleConfig
) -> tuple[BTCSignal, str] | None:
    """R05: whale_in ≥ 500 BTC AND exchange balance draining → LONG."""
    if snap.whale_in_btc < cfg.whale_threshold_btc:
        return None
    if snap.exchange_balance_delta > cfg.exchange_drain_threshold:
        return None
    return (
        BTCSignal.LONG,
        f"R05: whale inflow {snap.whale_in_btc:.0f} BTC "
        f"≥ {cfg.whale_threshold_btc:.0f} and exchange balance "
        f"Δ={snap.exchange_balance_delta:.0f} ≤ "
        f"{cfg.exchange_drain_threshold:.0f} → accumulation, long-bias",
    )


def _rule_06_vol_squeeze(
    snap: BTCMarketSnapshot, cfg: BTCRuleConfig
) -> tuple[BTCSignal, str] | None:
    """R06: BB width and ATR near their lookback minima → breakout.

    Direction comes from ``volume_direction`` — the squeeze itself is
    non-directional, so we refuse to signal when direction is flat.
    """
    if snap.bb_min_lookback_pct <= 0.0 or snap.atr_min_lookback_pct <= 0.0:
        return None
    bb_squeeze = snap.bb_width_pct <= snap.bb_min_lookback_pct * cfg.bb_squeeze_ratio
    atr_squeeze = snap.current_atr_pct <= snap.atr_min_lookback_pct * cfg.atr_squeeze_ratio
    if not (bb_squeeze and atr_squeeze):
        return None
    if snap.volume_direction > 0:
        return (
            BTCSignal.LONG,
            f"R06: BB width {snap.bb_width_pct:.3f}% near min "
            f"{snap.bb_min_lookback_pct:.3f}% + ATR squeeze + buy-dominant flow "
            "→ long breakout",
        )
    if snap.volume_direction < 0:
        return (
            BTCSignal.SHORT,
            f"R06: BB width {snap.bb_width_pct:.3f}% near min "
            f"{snap.bb_min_lookback_pct:.3f}% + ATR squeeze + sell-dominant flow "
            "→ short breakout",
        )
    return None


def _rule_07_news_exhaustion(
    snap: BTCMarketSnapshot, _cfg: BTCRuleConfig
) -> tuple[BTCSignal, str] | None:
    """R07: good-news spike exhausted → sell; bad-news panic fading → buy."""
    if snap.good_news_spike_exhausted:
        return (
            BTCSignal.SHORT,
            "R07: good-news spike exhausted → sell-the-news",
        )
    if snap.bad_news_panic_fading:
        return (
            BTCSignal.LONG,
            "R07: bad-news panic fading → buy-the-dip",
        )
    return None


def evaluate_btc_rules(
    snapshot: BTCMarketSnapshot,
    config: BTCRuleConfig | None = None,
) -> BTCRuleResult:
    """Evaluate the full §7 rule pipeline in priority order.

    Parameters
    ----------
    snapshot
        The strict market snapshot. NaN in any numeric field → refusal.
    config
        Optional threshold overrides. Defaults to
        ``DEFAULT_BTC_RULE_CONFIG``.

    Returns
    -------
    BTCRuleResult
        First conclusive rule match, or ``NEUTRAL`` if none fire.
    """
    cfg = config or DEFAULT_BTC_RULE_CONFIG
    diagnostics = _diag(snapshot)

    if snapshot.has_nan():
        return BTCRuleResult(
            signal=BTCSignal.NEUTRAL,
            fired_rules=tuple(),
            rationale=tuple(),
            diagnostics=diagnostics,
            refusal_reason="snapshot contains NaN in a numeric field",
        )

    pipeline = (
        (BTCRule.R01_EXTREME_FUNDING_CONTRARIAN, _rule_01_extreme_funding),
        (BTCRule.R02_OI_PRICE_DIVERGENCE_TRAP, _rule_02_oi_price_divergence),
        (BTCRule.R03_STOP_CLUSTER_SPOOF, _rule_03_stop_cluster_spoof),
        (BTCRule.R04_WHALE_DISTRIBUTION_SHORT, _rule_04_whale_distribution),
        (BTCRule.R05_WHALE_ACCUMULATION_LONG, _rule_05_whale_accumulation),
        (BTCRule.R06_VOL_SQUEEZE_BREAKOUT, _rule_06_vol_squeeze),
        (BTCRule.R07_NEWS_EXHAUSTION, _rule_07_news_exhaustion),
    )

    for rule, fn in pipeline:
        match = fn(snapshot, cfg)
        if match is not None:
            signal, rationale = match
            return BTCRuleResult(
                signal=signal,
                fired_rules=(rule,),
                rationale=(rationale,),
                diagnostics=diagnostics,
            )

    return BTCRuleResult(
        signal=BTCSignal.NEUTRAL,
        fired_rules=tuple(),
        rationale=("no §7 rule matched the snapshot",),
        diagnostics=diagnostics,
    )
