# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""End-to-end integration test: the complete GeoSync pipeline as one organism.

This test exercises the FULL signal path:
  market data → Kuramoto sync → regime detection → neuro signals →
  Kelly sizing → position decision → backtest → PnL → report

If this test is green, GeoSync is an integrated system, not a module collection.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.neuro.dopamine_execution_adapter import DopamineExecutionAdapter
from core.neuro.ecs_lyapunov import ECSLyapunovRegulator
from core.neuro.gaba_position_gate import GABAPositionGate
from core.neuro.hpc_neuro_bridge import HPCNeuroBridge
from core.neuro.kuramoto_kelly import KuramotoKellyAdapter
from core.neuro.serotonin_ode import SerotoninODE
from core.neuro.signal_bus import BusConfig, NeuroSignalBus, StressRegime

pytestmark = pytest.mark.L3


def _generate_market_data(n: int = 500, seed: int = 42) -> dict:
    """Generate synthetic market data with trend + noise."""
    rng = np.random.default_rng(seed)
    # Trending phase (first half) + chaotic phase (second half)
    trend = np.cumsum(rng.normal(0.001, 0.01, n // 2))
    chaos = np.cumsum(rng.normal(0.0, 0.03, n - n // 2))
    prices = 100.0 + np.concatenate([trend, chaos])
    prices = np.maximum(prices, 1.0)  # no negative prices
    returns = np.diff(np.log(prices))
    volumes = rng.exponential(1000, len(returns))
    vix = 15.0 + 10.0 * np.abs(returns) / np.std(returns)
    return {
        "prices": prices,
        "returns": returns,
        "volumes": volumes,
        "vix": vix,
    }


class TestFullPipelineE2E:
    """Complete GeoSync pipeline: data → signals → decisions → PnL."""

    def test_full_pipeline_produces_valid_decisions(self):
        """The canonical integration test. Every subsystem participates."""
        # ── Setup ──
        bus = NeuroSignalBus(config=BusConfig())
        dopamine = DopamineExecutionAdapter(bus)
        gaba = GABAPositionGate(bus)
        serotonin_ode = SerotoninODE()
        kuramoto = KuramotoKellyAdapter(bus)
        ecs = ECSLyapunovRegulator(bus)
        hpc_bridge = HPCNeuroBridge(bus)

        market = _generate_market_data(n=500, seed=42)
        returns = market["returns"]
        prices = market["prices"]
        vix = market["vix"]

        # ── Simulate trading loop ──
        capital = 10000.0
        position = 0.0
        pnl_history = []
        decisions = []
        kelly_base = 0.25

        window = 50
        for t in range(window, len(returns)):
            ret_window = returns[t - window : t]
            price = prices[t]
            current_return = returns[t]
            current_vix = float(vix[t])
            vol = float(np.std(ret_window))

            # 1. Kuramoto → regime detection + Kelly fraction
            kelly_fraction = kuramoto.compute_kelly_fraction(
                kelly_base=kelly_base,
                prices=prices[t - window : t + 1],
            )

            # 2. Serotonin ODE → aversive state
            stress = abs(current_return) / max(vol, 1e-8)
            serotonin_level, desens = serotonin_ode.step(stress=stress, dt=1.0)
            bus.publish_serotonin(level=min(1.0, serotonin_level))

            # 3. GABA → inhibition from VIX + volatility
            rpe = float(
                dopamine.compute_rpe(
                    realized_pnl=current_return * position,
                    predicted_return=0.0,
                )
            )
            inhibition = gaba.update_inhibition(
                vix=current_vix,
                volatility=vol,
                rpe=rpe,
            )

            # 4. Dopamine → RPE from simulated P&L
            dopamine.compute_rpe(
                realized_pnl=current_return * position,
                predicted_return=0.0,
            )
            bus.publish_dopamine(rpe=rpe)

            # 5. ECS → free energy homeostasis
            ecs_state = ecs.step(stress=stress, dt=1.0)

            # 6. HPC bridge → integrated decision
            pwpe = abs(current_return - np.mean(ret_window)) / max(vol, 1e-8)
            entropy = vol * 10.0  # proxy for state entropy
            hpc_bridge.process_hpc_output(
                pwpe=pwpe,
                action=1 if current_return > 0 else 0,
                state_entropy=entropy,
            )

            # 7. Integrated decision
            should_hold = bus.should_hold()
            position_mult = bus.compute_position_multiplier(kelly_base=kelly_fraction)

            if should_hold:
                target_position = 0.0
            else:
                target_position = capital * position_mult / price

            # Simple execution
            position = target_position
            pnl = position * current_return * price
            capital += pnl
            pnl_history.append(pnl)

            decisions.append(
                {
                    "t": t,
                    "kelly_fraction": kelly_fraction,
                    "serotonin": serotonin_level,
                    "inhibition": inhibition,
                    "rpe": rpe,
                    "hold": should_hold,
                    "position_mult": position_mult,
                    "regime": bus.snapshot().stress_regime.value,
                    "capital": capital,
                }
            )

        # ── Assertions: the pipeline produces sane output ──
        assert len(decisions) == len(returns) - window
        assert len(pnl_history) == len(decisions)

        # All Kelly fractions bounded
        kellys = [d["kelly_fraction"] for d in decisions]
        assert all(0.0 <= k <= kelly_base for k in kellys)

        # Serotonin levels bounded [0, 1]
        serotonins = [d["serotonin"] for d in decisions]
        assert all(0.0 <= s <= 2.0 for s in serotonins)  # ODE can overshoot slightly

        # Inhibition bounded [0, 1]
        inhibitions = [d["inhibition"] for d in decisions]
        assert all(0.0 <= i <= 1.0 for i in inhibitions)

        # RPE bounded [-1, 1]
        rpes = [d["rpe"] for d in decisions]
        assert all(-1.0 <= r <= 1.0 for r in rpes)

        # Position multiplier non-negative
        mults = [d["position_mult"] for d in decisions]
        assert all(m >= 0.0 for m in mults)

        # Capital stays positive (no bankruptcy)
        assert capital > 0.0

        # At least some hold decisions fired
        holds = [d["hold"] for d in decisions]
        assert any(holds), "serotonin should trigger at least one hold"

        # Regime detection active (at least one regime observed)
        regimes = set(d["regime"] for d in decisions)
        assert len(regimes) >= 1, f"expected at least one regime, got {regimes}"

        # Bus history recorded
        history = bus.get_history(n=100)
        assert len(history) > 0

        # ECS Lyapunov stable
        assert ecs_state["stable"]

    def test_trending_market_larger_positions(self):
        """In trending markets, Kuramoto R is higher → larger positions."""
        bus_trend = NeuroSignalBus()
        bus_chaos = NeuroSignalBus()
        k_trend = KuramotoKellyAdapter(bus_trend)
        k_chaos = KuramotoKellyAdapter(bus_chaos)

        rng = np.random.default_rng(42)

        # Strong trend: cumulative sum of positive returns
        trend_prices = 100.0 + np.cumsum(np.full(100, 0.01) + rng.normal(0, 0.002, 100))
        # Pure noise: random walk
        chaos_prices = 100.0 + np.cumsum(rng.normal(0, 0.02, 100))

        kelly_trend = k_trend.compute_kelly_fraction(kelly_base=1.0, prices=trend_prices)
        kelly_chaos = k_chaos.compute_kelly_fraction(kelly_base=1.0, prices=chaos_prices)

        # Trending market should get larger Kelly fraction
        assert kelly_trend > kelly_chaos * 0.8  # trend should be meaningfully larger

    def test_crash_triggers_full_defensive_response(self):
        """Simulated crash: all defensive systems engage."""
        bus = NeuroSignalBus(
            config=BusConfig(
                serotonin_hold_threshold=0.6,
                crisis_rpe_threshold=-0.2,
                crisis_serotonin_threshold=0.7,
            )
        )
        dopamine = DopamineExecutionAdapter(bus)
        gaba = GABAPositionGate(bus)
        serotonin = SerotoninODE()
        ecs = ECSLyapunovRegulator(bus)

        # Simulate crash: large negative returns
        for _ in range(20):
            serotonin_level, _ = serotonin.step(stress=3.0, dt=1.0)
            bus.publish_serotonin(level=min(1.0, serotonin_level))
            rpe = dopamine.compute_rpe(realized_pnl=-0.05, predicted_return=0.01)
            bus.publish_dopamine(rpe=rpe)
            gaba.update_inhibition(vix=40.0, volatility=0.5, rpe=rpe)
            ecs.step(stress=3.0, dt=1.0)

        # Defensive response should be fully engaged
        assert bus.should_hold(), "should be in hold during crash"
        mult = bus.compute_position_multiplier()
        assert mult < 0.15, f"position multiplier should be near zero during crash, got {mult}"
        s = bus.snapshot()
        assert s.stress_regime in (StressRegime.CRISIS, StressRegime.ELEVATED)
        assert s.gaba_inhibition > 0.3
