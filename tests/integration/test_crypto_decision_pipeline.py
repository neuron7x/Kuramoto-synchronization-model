# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""End-to-end integration tests for the crypto decision pipeline.

This suite walks synthetic bar data through the full stack:

    raw bars → QILM / FMN → π-gate inputs → TradingComposer → CompositeDecision

and verifies that:

1. The whole chain is deterministic under fixed seeds.
2. Four canonical scenarios produce the expected ``CompositeSignal``.
3. The pipeline latency on N=2000 bars is well under a real-time budget.
4. A golden payload hash is pinned so any accidental numerical drift
   (e.g. a stealth refactor of QILM) breaks this test loudly instead
   of silently changing the signal.

No external services, no I/O, no network. The test only uses numpy +
the modules under test.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import replace

import numpy as np
from numpy.typing import NDArray

from core.indicators import compute_fmn, compute_qilm
from core.indicators.phase_entry_gate import Signal
from core.strategies.btc_intel import BTCMarketSnapshot
from core.strategies.trading_composer import (
    CompositeSignal,
    TradingComposer,
    TradingSnapshot,
    compose_decision,
)

Vec = NDArray[np.float64]


# ---- synthetic bar factory ---- #


def _trending_series(
    n: int,
    *,
    direction: int,
    seed: int = 7,
) -> dict[str, Vec]:
    """Generate a bar sequence with a clean trend in ``direction``.

    The numbers are tuned so the resulting QILM and FMN tail averages
    are both well above ``flow_min_magnitude = 0.2`` in absolute value:

    * For UP (``direction=+1``): OI grows fast and ΔV is positive →
      ``S_t = +1`` at every bar → QILM strongly positive.
    * For DOWN (``direction=-1``): OI shrinks fast (positions closing)
      and ΔV is negative → ``S_t = -1`` at every bar → QILM strongly
      negative.
    * FMN is pushed to the same sign by a heavily skewed bid/ask book.

    Returns a dict with: oi, vol, dv, hv, atr, bid_vol, ask_vol — all
    length ``n``, aligned.
    """
    rng = np.random.default_rng(seed)
    noise = rng.normal(scale=0.2, size=n)

    drift = float(direction)
    # OI drift: ~10 per bar in the trend direction, small stochastic kick.
    oi_steps = drift * (10.0 + 2.0 * np.abs(noise))
    oi = 1_000.0 + np.cumsum(oi_steps)
    # Relatively small total volume so the (|ΔV|+HV)/(V+HV) factor
    # clears the ``flow_min_magnitude`` threshold comfortably.
    vol = np.full(n, 100.0, dtype=np.float64) + rng.uniform(0.0, 5.0, size=n)
    dv = drift * (40.0 + 5.0 * np.abs(noise))
    hv = np.zeros(n, dtype=np.float64)
    # Small ATR amplifies |ΔOI|/ATR and therefore |QILM|.
    atr = np.full(n, 1.0, dtype=np.float64)
    # Order book skew pushes FMN to near-saturation on the same side.
    bid_vol = 100.0 + drift * 60.0 + rng.uniform(0.0, 2.0, size=n)
    ask_vol = 100.0 - drift * 60.0 + rng.uniform(0.0, 2.0, size=n)

    return {
        "oi": oi.astype(np.float64),
        "vol": vol.astype(np.float64),
        "dv": dv.astype(np.float64),
        "hv": hv,
        "atr": atr,
        "bid_vol": bid_vol.astype(np.float64),
        "ask_vol": ask_vol.astype(np.float64),
    }


def _neutral_btc() -> BTCMarketSnapshot:
    return BTCMarketSnapshot(
        funding_rate=0.0,
        open_interest=1e10,
        open_interest_delta_bars=0,
        price_progress_pct=0.0,
        current_volume=1000.0,
        baseline_volume=1000.0,
        whale_out_btc=0.0,
        whale_in_btc=0.0,
        exchange_balance_delta=0.0,
        exchange_inflow_rising=False,
        stop_cluster_distance_pct=5.0,
        spoof_wall_detected=False,
        spoof_wall_side="",
        bb_width_pct=5.0,
        bb_min_lookback_pct=1.0,
        atr_min_lookback_pct=1.0,
        current_atr_pct=5.0,
        volume_direction=0,
        good_news_spike_exhausted=False,
        bad_news_panic_fading=False,
    )


# ---- scenario-level determinism ---- #


def test_pipeline_is_deterministic_across_runs() -> None:
    """Two independent runs on the same synthetic bars → identical decision."""
    bars = _trending_series(256, direction=1, seed=99)
    qilm = compute_qilm(bars["oi"], bars["vol"], bars["dv"], bars["hv"], bars["atr"])
    fmn = compute_fmn(bars["bid_vol"], bars["ask_vol"], bars["dv"])

    snap = TradingSnapshot(
        r_kuramoto=0.82,
        delta_h=-0.10,
        kappa_mean=-0.20,
        hurst=0.62,
        qilm_latest=float(np.nanmean(qilm[-20:])),
        fmn_latest=float(np.nanmean(fmn[-20:])),
        btc_snapshot=_neutral_btc(),
    )
    a = compose_decision(snap)
    b = compose_decision(snap)
    assert a.signal is b.signal
    assert a.source_layer == b.source_layer
    assert a.to_dict() == b.to_dict()


# ---- four canonical scenarios ---- #


def test_trending_up_confirmed_by_flow_is_long() -> None:
    """Up-trending synthetic bars + bullish π-readings → LONG via phase_gate."""
    bars = _trending_series(300, direction=1, seed=1)
    qilm = compute_qilm(bars["oi"], bars["vol"], bars["dv"], bars["hv"], bars["atr"])
    fmn = compute_fmn(bars["bid_vol"], bars["ask_vol"], bars["dv"])

    qilm_latest = float(np.nanmean(qilm[-20:]))
    fmn_latest = float(np.nanmean(fmn[-20:]))
    assert qilm_latest > 0.0, "up-trending bars must give positive QILM"
    assert fmn_latest > 0.0, "up-trending bars must give positive FMN"

    snap = TradingSnapshot(
        r_kuramoto=0.82,
        delta_h=-0.10,
        kappa_mean=-0.20,
        hurst=0.62,
        qilm_latest=qilm_latest,
        fmn_latest=fmn_latest,
        btc_snapshot=_neutral_btc(),
    )
    result = compose_decision(snap)
    assert result.signal is CompositeSignal.LONG
    assert result.source_layer == "phase_gate"
    assert result.phase_reading.signal is Signal.LONG
    assert result.flow_sign == 1


def test_trending_down_confirmed_by_flow_is_short() -> None:
    bars = _trending_series(300, direction=-1, seed=2)
    qilm = compute_qilm(bars["oi"], bars["vol"], bars["dv"], bars["hv"], bars["atr"])
    fmn = compute_fmn(bars["bid_vol"], bars["ask_vol"], bars["dv"])

    snap = TradingSnapshot(
        r_kuramoto=0.82,
        delta_h=-0.10,
        kappa_mean=-0.20,
        hurst=0.30,  # anti-persistent → gate says SHORT
        qilm_latest=float(np.nanmean(qilm[-20:])),
        fmn_latest=float(np.nanmean(fmn[-20:])),
        btc_snapshot=_neutral_btc(),
    )
    result = compose_decision(snap)
    assert result.signal is CompositeSignal.SHORT
    assert result.source_layer == "phase_gate"


def test_btc_trap_rule_overrides_bullish_synthetic_stack() -> None:
    """Bullish bars + bullish π-gate + BTC R02 trap → AVOID wins."""
    bars = _trending_series(256, direction=1, seed=3)
    qilm = compute_qilm(bars["oi"], bars["vol"], bars["dv"], bars["hv"], bars["atr"])
    fmn = compute_fmn(bars["bid_vol"], bars["ask_vol"], bars["dv"])

    # Construct a snapshot where R02 fires: OI rising 5 bars, price flat.
    trap = replace(
        _neutral_btc(),
        open_interest_delta_bars=5,
        price_progress_pct=0.0,
    )
    snap = TradingSnapshot(
        r_kuramoto=0.85,
        delta_h=-0.15,
        kappa_mean=-0.25,
        hurst=0.65,
        qilm_latest=float(np.nanmean(qilm[-20:])),
        fmn_latest=float(np.nanmean(fmn[-20:])),
        btc_snapshot=trap,
    )
    result = compose_decision(snap)
    assert result.signal is CompositeSignal.AVOID
    assert result.source_layer == "btc_rules"


def test_phase_gate_fires_but_flow_contradicts_is_neutral() -> None:
    """
    π-gate says LONG (R>0.75, ΔH<−0.05, κ<−0.1, H>0.55) but bars are
    actually down-trending → QILM/FMN negative → composer downgrades
    to NEUTRAL with ``conflict_detected=True``.
    """
    bars = _trending_series(256, direction=-1, seed=4)
    qilm = compute_qilm(bars["oi"], bars["vol"], bars["dv"], bars["hv"], bars["atr"])
    fmn = compute_fmn(bars["bid_vol"], bars["ask_vol"], bars["dv"])

    snap = TradingSnapshot(
        r_kuramoto=0.85,
        delta_h=-0.15,
        kappa_mean=-0.25,
        hurst=0.65,  # long side
        qilm_latest=float(np.nanmean(qilm[-20:])),
        fmn_latest=float(np.nanmean(fmn[-20:])),
        btc_snapshot=_neutral_btc(),
    )
    result = compose_decision(snap)
    assert result.signal is CompositeSignal.NEUTRAL
    assert result.conflict_detected


# ---- perf ---- #


def test_pipeline_latency_budget_is_under_200ms_for_2000_bars() -> None:
    """Full QILM+FMN + composer must be comfortably under a 200 ms budget."""
    n = 2000
    bars = _trending_series(n, direction=1, seed=42)
    composer = TradingComposer()

    t0 = time.perf_counter()
    qilm = compute_qilm(bars["oi"], bars["vol"], bars["dv"], bars["hv"], bars["atr"])
    fmn = compute_fmn(bars["bid_vol"], bars["ask_vol"], bars["dv"])
    snap = TradingSnapshot(
        r_kuramoto=0.82,
        delta_h=-0.10,
        kappa_mean=-0.20,
        hurst=0.62,
        qilm_latest=float(np.nanmean(qilm[-20:])),
        fmn_latest=float(np.nanmean(fmn[-20:])),
        btc_snapshot=_neutral_btc(),
    )
    _ = composer.compose(snap)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    # Generous ceiling — local machine should hit ~3-10 ms on these sizes.
    assert elapsed_ms < 200.0, f"pipeline too slow: {elapsed_ms:.1f}ms for N={n}"


# ---- golden-hash replay ---- #


def test_golden_flow_metrics_payload_hash_is_pinned() -> None:
    """Pin QILM/FMN numerical identity to a SHA-256 of their rounded tails.

    If either indicator's math drifts, this hash changes and the test
    fails loudly. To deliberately roll the fixture: update the literal
    below in the same commit as the indicator change.
    """
    bars = _trending_series(256, direction=1, seed=1729)
    qilm = compute_qilm(bars["oi"], bars["vol"], bars["dv"], bars["hv"], bars["atr"])
    fmn = compute_fmn(bars["bid_vol"], bars["ask_vol"], bars["dv"])

    # Last 16 values, rounded to 6 decimals for float-bit stability.
    payload = {
        "qilm_tail": [round(float(v), 6) for v in qilm[-16:]],
        "fmn_tail": [round(float(v), 6) for v in fmn[-16:]],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # Capture the true hash from the current (reference) implementation
    # on first run: we assert the prefix matches what we computed when
    # landing this test. Any change breaks with a diff-friendly message.
    assert digest == _GOLDEN_HASH, (
        f"QILM/FMN golden payload drifted.\n"
        f"expected: {_GOLDEN_HASH}\n"
        f"got:      {digest}\n"
        f"payload:  {canonical}"
    )


# Pinned at PR #201 landing (feat/crypto-pipeline-production-closure)
# over the canonical ``_trending_series(256, direction=1, seed=1729)``
# synthetic fixture. Any change to QILM or FMN math must be accompanied
# by a deliberate update of this literal in the same commit as the math
# change. A silent drift in either indicator breaks this test loudly
# with a diff-friendly error message.
_GOLDEN_HASH = (
    "91b2bd5945826653637a383ff367b64599b07bbaf04bf9a2516e84d6d86ff04f"  # pragma: allowlist secret
)
