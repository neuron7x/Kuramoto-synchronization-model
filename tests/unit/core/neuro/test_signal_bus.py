# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for NeuroSignalBus — cross-system neuromodulator coordination."""

import pytest

from core.neuro.signal_bus import (
    BusConfig,
    NeuroSignalBus,
    StressRegime,
)

pytestmark = pytest.mark.L3


@pytest.fixture
def bus():
    return NeuroSignalBus()


@pytest.fixture
def configured_bus():
    cfg = BusConfig(
        kelly_coherence_floor=0.3,
        kelly_coherence_ceil=0.8,
        serotonin_hold_threshold=0.7,
        crisis_rpe_threshold=-0.3,
        crisis_serotonin_threshold=0.8,
    )
    return NeuroSignalBus(config=cfg)


class TestPublishAndSnapshot:
    def test_default_signals(self, bus):
        s = bus.snapshot()
        assert s.dopamine_rpe == 0.0
        assert s.serotonin_level == 0.0
        assert s.gaba_inhibition == 0.0
        assert s.nak_energy == 0.5
        assert s.kuramoto_R == 0.5
        assert s.hpc_pwpe == 0.0
        assert s.stress_regime == StressRegime.NORMAL

    def test_publish_dopamine_bounded(self, bus):
        bus.publish_dopamine(rpe=5.0)
        assert bus.snapshot().dopamine_rpe == 1.0
        bus.publish_dopamine(rpe=-5.0)
        assert bus.snapshot().dopamine_rpe == -1.0

    def test_publish_serotonin_bounded(self, bus):
        bus.publish_serotonin(level=2.0)
        assert bus.snapshot().serotonin_level == 1.0
        bus.publish_serotonin(level=-1.0)
        assert bus.snapshot().serotonin_level == 0.0

    def test_publish_gaba_bounded(self, bus):
        bus.publish_gaba(inhibition=1.5)
        assert bus.snapshot().gaba_inhibition == 1.0

    def test_publish_kuramoto_bounded(self, bus):
        bus.publish_kuramoto(R=1.5)
        assert bus.snapshot().kuramoto_R == 1.0

    def test_publish_hpc_non_negative(self, bus):
        bus.publish_hpc(pwpe=-3.0)
        assert bus.snapshot().hpc_pwpe == 0.0

    def test_snapshot_is_independent_copy(self, bus):
        s1 = bus.snapshot()
        bus.publish_dopamine(rpe=0.9)
        s2 = bus.snapshot()
        assert s1.dopamine_rpe != s2.dopamine_rpe

    def test_to_dict(self, bus):
        bus.publish_dopamine(rpe=0.5)
        d = bus.snapshot().to_dict()
        assert d["dopamine_rpe"] == 0.5
        assert d["stress_regime"] == "normal"


class TestRegimeDetection:
    def test_normal_regime_default(self, bus):
        assert bus.snapshot().stress_regime == StressRegime.NORMAL

    def test_elevated_on_negative_rpe(self, bus):
        bus.publish_dopamine(rpe=-0.1)
        assert bus.snapshot().stress_regime == StressRegime.ELEVATED

    def test_elevated_on_moderate_serotonin(self, configured_bus):
        configured_bus.publish_serotonin(level=0.6)
        assert configured_bus.snapshot().stress_regime == StressRegime.ELEVATED

    def test_crisis_on_large_negative_rpe_and_high_serotonin(self, configured_bus):
        configured_bus.publish_serotonin(level=0.9)
        configured_bus.publish_dopamine(rpe=-0.5)
        assert configured_bus.snapshot().stress_regime == StressRegime.CRISIS

    def test_recovery_after_crisis(self, configured_bus):
        # Enter crisis
        configured_bus.publish_serotonin(level=0.9)
        configured_bus.publish_dopamine(rpe=-0.5)
        assert configured_bus.snapshot().stress_regime == StressRegime.CRISIS
        # Free energy drops → recovery
        configured_bus.publish_ecs(free_energy=0.1)
        configured_bus.publish_serotonin(level=0.3)
        configured_bus.publish_dopamine(rpe=0.1)
        # Should transition to NORMAL (serotonin below elevated threshold)
        regime = configured_bus.snapshot().stress_regime
        assert regime in (StressRegime.RECOVERY, StressRegime.NORMAL)


class TestShouldHold:
    def test_no_hold_at_rest(self, configured_bus):
        assert not configured_bus.should_hold()

    def test_hold_on_high_serotonin(self, configured_bus):
        configured_bus.publish_serotonin(level=0.8)
        assert configured_bus.should_hold()

    def test_hold_in_crisis(self, configured_bus):
        configured_bus.publish_serotonin(level=0.9)
        configured_bus.publish_dopamine(rpe=-0.5)
        assert configured_bus.should_hold()

    def test_no_hold_below_threshold(self, configured_bus):
        configured_bus.publish_serotonin(level=0.5)
        assert not configured_bus.should_hold()


class TestPositionMultiplier:
    def test_default_multiplier(self, bus):
        mult = bus.compute_position_multiplier(kelly_base=1.0)
        assert 0.0 < mult <= 1.0

    def test_low_kuramoto_reduces_size(self, configured_bus):
        configured_bus.publish_kuramoto(R=0.1)
        mult = configured_bus.compute_position_multiplier()
        assert mult < 0.3

    def test_high_kuramoto_increases_size(self, configured_bus):
        configured_bus.publish_kuramoto(R=0.9)
        mult = configured_bus.compute_position_multiplier()
        assert mult > 0.5

    def test_gaba_inhibition_reduces_size(self, configured_bus):
        configured_bus.publish_kuramoto(R=0.9)
        no_gaba = configured_bus.compute_position_multiplier()
        configured_bus.publish_gaba(inhibition=0.8)
        with_gaba = configured_bus.compute_position_multiplier()
        assert with_gaba < no_gaba

    def test_crisis_regime_halts_position(self, configured_bus):
        # Crisis is a Protector veto (INV-YV1 L2): it HALTS sizing, not dampens.
        configured_bus.publish_serotonin(level=0.9)
        configured_bus.publish_dopamine(rpe=-0.5)
        assert configured_bus.should_hold() is True
        mult = configured_bus.compute_position_multiplier()
        assert mult == 0.0

    def test_protector_veto_overrides_generator(self, configured_bus):
        """INV-YV1 L2: a firing Protector zeroes the position even when the
        Generator wants maximum size (Protectors > Generators, unconditional).

        High Kuramoto coherence + zero GABA means the Generator asks for a
        large Kelly fraction; a serotonin level above the hold threshold is a
        Protector veto that must HALT (multiplier 0), not merely dampen. The
        prior code ignored should_hold() inside the multiplier and returned a
        large positive size — the precedence was violated and the production
        oracle (which multiplies this value) sized into an aversive state.
        """
        configured_bus.publish_kuramoto(R=0.95)  # Generator: full size
        configured_bus.publish_gaba(inhibition=0.0)  # no braking
        assert configured_bus.should_hold() is False
        generator_size = configured_bus.compute_position_multiplier()
        assert generator_size > 0.5  # Generator genuinely wants size

        configured_bus.publish_serotonin(level=0.8)  # Protector veto fires
        assert configured_bus.should_hold() is True
        vetoed = configured_bus.compute_position_multiplier()
        assert vetoed == 0.0, (
            f"INV-YV1 VIOLATED: Protector veto active (should_hold) yet "
            f"multiplier={vetoed:.4f} != 0. Protectors have unconditional "
            f"priority over the Generator; a firing veto must zero the position. "
            f"At R=0.95, gaba=0, serotonin=0.8 > hold_threshold=0.7."
        )

    def test_multiplier_never_negative(self, bus):
        bus.publish_gaba(inhibition=1.0)
        bus.publish_kuramoto(R=0.0)
        mult = bus.compute_position_multiplier()
        assert mult >= 0.0

    def test_position_scales_with_kelly_base(self, configured_bus):
        configured_bus.publish_kuramoto(R=0.9)
        m1 = configured_bus.compute_position_multiplier(kelly_base=1.0)
        m2 = configured_bus.compute_position_multiplier(kelly_base=2.0)
        assert abs(m2 - 2.0 * m1) < 1e-9


class TestLearningRate:
    def test_base_lr_at_rest(self, bus):
        lr = bus.compute_learning_rate(base_lr=1e-4)
        # With default nak_energy=0.5, lr should be slightly above base
        assert lr > 1e-4

    def test_high_rpe_increases_lr(self, bus):
        lr_calm = bus.compute_learning_rate(base_lr=1e-4)
        bus.publish_dopamine(rpe=0.9)
        lr_surprise = bus.compute_learning_rate(base_lr=1e-4)
        assert lr_surprise > lr_calm

    def test_high_pwpe_decreases_lr(self, bus):
        lr_low = bus.compute_learning_rate(base_lr=1e-4)
        bus.publish_hpc(pwpe=50.0)
        lr_uncertain = bus.compute_learning_rate(base_lr=1e-4)
        assert lr_uncertain < lr_low

    def test_high_nak_increases_lr(self, bus):
        bus.publish_nak(energy=0.1)
        lr_low = bus.compute_learning_rate(base_lr=1e-4)
        bus.publish_nak(energy=0.9)
        lr_high = bus.compute_learning_rate(base_lr=1e-4)
        assert lr_high > lr_low


class TestSubscription:
    def test_subscribe_notified(self, bus):
        received = []
        bus.subscribe("dopamine", lambda s: received.append(s.dopamine_rpe))
        bus.publish_dopamine(rpe=0.42)
        assert len(received) == 1
        assert received[0] == pytest.approx(0.42)

    def test_multiple_subscribers(self, bus):
        count = [0]
        bus.subscribe("serotonin", lambda s: count.__setitem__(0, count[0] + 1))
        bus.subscribe("serotonin", lambda s: count.__setitem__(0, count[0] + 1))
        bus.publish_serotonin(level=0.5)
        assert count[0] == 2


class TestHistory:
    def test_history_recorded(self, bus):
        bus.publish_dopamine(rpe=0.1)
        bus.publish_dopamine(rpe=0.2)
        bus.publish_dopamine(rpe=0.3)
        history = bus.get_history(n=10)
        assert len(history) >= 3

    def test_reset_clears(self, bus):
        bus.publish_dopamine(rpe=0.5)
        bus.reset()
        s = bus.snapshot()
        assert s.dopamine_rpe == 0.0
        assert bus.get_history() == []


class TestCrossSytemIntegration:
    """End-to-end scenario: simulate market crash → recovery."""

    def test_crash_to_recovery_sequence(self, configured_bus):
        bus = configured_bus

        # Phase 1: Normal trading
        bus.publish_kuramoto(R=0.7)
        bus.publish_dopamine(rpe=0.1)
        bus.publish_serotonin(level=0.2)
        assert bus.snapshot().stress_regime == StressRegime.NORMAL
        assert not bus.should_hold()
        normal_mult = bus.compute_position_multiplier()

        # Phase 2: Market shock — RPE crashes, serotonin spikes
        bus.publish_dopamine(rpe=-0.8)
        bus.publish_serotonin(level=0.95)
        bus.publish_kuramoto(R=0.1)
        bus.publish_gaba(inhibition=0.9)
        assert bus.snapshot().stress_regime == StressRegime.CRISIS
        assert bus.should_hold()
        crisis_mult = bus.compute_position_multiplier()
        assert crisis_mult < normal_mult * 0.2

        # Phase 3: Recovery — signals normalize
        bus.publish_dopamine(rpe=0.05)
        bus.publish_serotonin(level=0.3)
        bus.publish_kuramoto(R=0.5)
        bus.publish_gaba(inhibition=0.2)
        bus.publish_ecs(free_energy=0.1)
        assert not bus.should_hold()
        recovery_mult = bus.compute_position_multiplier()
        assert recovery_mult > crisis_mult
