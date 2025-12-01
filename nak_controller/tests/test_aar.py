"""Tests for AAR (Acceptor of Action Result) module.

This module tests the core AAR functionality:
- Error computation formulas
- Error normalization
- Sign detection
- Aggregation
- Memory/tracker lifecycle
- Integration with neuro-controllers
"""

from __future__ import annotations

import time

import pytest

from nak_controller.aar import (
    AARAdaptationConfig,
    AARAdaptationResult,
    AARAdaptationState,
    AARTracker,
    ActionEvent,
    AggregateStats,
    ErrorSignal,
    ModeAggregator,
    Outcome,
    Prediction,
    SlidingWindowAggregator,
    StrategyAggregator,
    aar_dopamine_modulation,
    aar_serotonin_modulation,
    absolute_error,
    compute_aar_adaptation,
    compute_error,
    compute_risk_reduction,
    create_action_event,
    error_sign,
    normalize_error,
    relative_error,
    should_freeze_adaptation,
    update_adaptation_state,
)


class TestAbsoluteError:
    """Tests for absolute_error function."""

    def test_positive_difference(self) -> None:
        assert absolute_error(10.0, 8.0) == pytest.approx(2.0)

    def test_negative_difference(self) -> None:
        assert absolute_error(5.0, 10.0) == pytest.approx(5.0)

    def test_zero_difference(self) -> None:
        assert absolute_error(5.0, 5.0) == pytest.approx(0.0)

    def test_with_negative_values(self) -> None:
        assert absolute_error(-5.0, -10.0) == pytest.approx(5.0)

    def test_with_zero(self) -> None:
        assert absolute_error(0.0, 5.0) == pytest.approx(5.0)


class TestRelativeError:
    """Tests for relative_error function."""

    def test_basic_relative_error(self) -> None:
        assert relative_error(100.0, 90.0, 50.0) == pytest.approx(0.2)

    def test_negative_relative_error(self) -> None:
        assert relative_error(50.0, 100.0, 50.0) == pytest.approx(-1.0)

    def test_zero_difference(self) -> None:
        assert relative_error(50.0, 50.0, 50.0) == pytest.approx(0.0)

    def test_invalid_scale_raises(self) -> None:
        with pytest.raises(ValueError, match="scale must be positive"):
            relative_error(10.0, 5.0, 0.0)

    def test_negative_scale_raises(self) -> None:
        with pytest.raises(ValueError, match="scale must be positive"):
            relative_error(10.0, 5.0, -1.0)


class TestNormalizeError:
    """Tests for normalize_error function."""

    def test_zero_error(self) -> None:
        assert abs(normalize_error(0.0)) < 1e-9

    def test_positive_error_bounded(self) -> None:
        result = normalize_error(1.0)
        assert 0.7 < result < 0.8

    def test_negative_error_bounded(self) -> None:
        result = normalize_error(-1.0)
        assert -0.8 < result < -0.7

    def test_large_error_saturates(self) -> None:
        result = normalize_error(100.0)
        assert 0.99 < result <= 1.0

    def test_large_negative_error_saturates(self) -> None:
        result = normalize_error(-100.0)
        assert -1.0 <= result < -0.99

    def test_scale_affects_curve(self) -> None:
        # Larger scale compresses the curve
        result_small = normalize_error(1.0, scale=0.5)
        result_large = normalize_error(1.0, scale=2.0)
        assert result_small > result_large


class TestErrorSign:
    """Tests for error_sign function."""

    def test_better_than_expected_higher_is_better(self) -> None:
        assert error_sign(100.0, 110.0, higher_is_better=True) == 1

    def test_worse_than_expected_higher_is_better(self) -> None:
        assert error_sign(100.0, 90.0, higher_is_better=True) == -1

    def test_within_tolerance(self) -> None:
        assert error_sign(100.0, 102.0, tolerance=5.0) == 0

    def test_better_when_lower_is_better(self) -> None:
        # For latency, lower is better
        assert error_sign(10.0, 5.0, higher_is_better=False) == 1

    def test_worse_when_lower_is_better(self) -> None:
        assert error_sign(10.0, 15.0, higher_is_better=False) == -1


class TestComputeError:
    """Tests for compute_error function."""

    def test_basic_error_computation(self) -> None:
        pred = Prediction(
            action_id="test-1",
            expected_pnl=100.0,
            expected_latency_ms=5.0,
            expected_slippage=0.0001,
        )
        out = Outcome(
            action_id="test-1",
            actual_pnl=80.0,
            actual_latency_ms=7.0,
            actual_slippage=0.00015,
        )
        error = compute_error(pred, out)

        assert error.action_id == "test-1"
        assert error.absolute_error > 0
        # PnL was worse (80 < 100), so normalized error should be negative
        assert error.components["pnl_sign"] == -1

    def test_perfect_prediction(self) -> None:
        pred = Prediction(
            action_id="test-2",
            expected_pnl=100.0,
            expected_latency_ms=5.0,
            expected_slippage=0.0001,
        )
        out = Outcome(
            action_id="test-2",
            actual_pnl=100.0,
            actual_latency_ms=5.0,
            actual_slippage=0.0001,
        )
        error = compute_error(pred, out)

        assert error.absolute_error == pytest.approx(0.0)
        assert error.normalized_error == pytest.approx(0.0)
        assert error.sign == 0

    def test_better_than_expected(self) -> None:
        pred = Prediction(
            action_id="test-3",
            expected_pnl=100.0,
            expected_latency_ms=10.0,
            expected_slippage=0.001,
        )
        out = Outcome(
            action_id="test-3",
            actual_pnl=150.0,  # Better PnL
            actual_latency_ms=5.0,  # Better latency
            actual_slippage=0.0005,  # Better slippage
        )
        error = compute_error(pred, out)

        assert error.sign == 1
        assert error.normalized_error > 0

    def test_mismatched_action_id_raises(self) -> None:
        pred = Prediction(action_id="id-1", expected_pnl=100.0)
        out = Outcome(action_id="id-2", actual_pnl=80.0)

        with pytest.raises(ValueError, match="same action_id"):
            compute_error(pred, out)

    def test_error_components_present(self) -> None:
        pred = Prediction(action_id="test-4", expected_pnl=100.0)
        out = Outcome(action_id="test-4", actual_pnl=80.0)
        error = compute_error(pred, out)

        expected_keys = [
            "pnl_absolute",
            "pnl_relative",
            "pnl_normalized",
            "pnl_sign",
            "latency_absolute",
            "latency_relative",
            "latency_normalized",
            "latency_sign",
            "slippage_absolute",
            "slippage_relative",
            "slippage_normalized",
            "slippage_sign",
        ]
        for key in expected_keys:
            assert key in error.components


class TestSlidingWindowAggregator:
    """Tests for SlidingWindowAggregator."""

    def test_empty_stats(self) -> None:
        agg = SlidingWindowAggregator()
        stats = agg.get_stats()
        assert stats.count == 0
        assert stats.mean == 0.0

    def test_single_entry(self) -> None:
        agg = SlidingWindowAggregator()
        error = ErrorSignal(
            action_id="1",
            normalized_error=0.5,
            sign=1,
            absolute_error=0.3,
        )
        agg.add(error)
        stats = agg.get_stats()

        assert stats.count == 1
        assert stats.mean == pytest.approx(0.5)
        assert stats.positive_count == 1
        assert stats.negative_count == 0

    def test_multiple_entries(self) -> None:
        agg = SlidingWindowAggregator()
        for i in range(10):
            error = ErrorSignal(
                action_id=str(i),
                normalized_error=0.1 * i,
                sign=1 if i % 2 == 0 else -1,
                absolute_error=0.05 * i,
            )
            agg.add(error)

        stats = agg.get_stats()
        assert stats.count == 10
        assert stats.positive_count == 5
        assert stats.negative_count == 5

    def test_window_eviction(self) -> None:
        agg = SlidingWindowAggregator(window_size=5)
        for i in range(10):
            error = ErrorSignal(
                action_id=str(i),
                normalized_error=float(i),
                sign=1,
                absolute_error=float(i),
            )
            agg.add(error)

        stats = agg.get_stats()
        assert stats.count == 5
        # Should only have entries 5-9
        assert stats.mean == pytest.approx(7.0)  # (5+6+7+8+9)/5

    def test_catastrophic_count(self) -> None:
        agg = SlidingWindowAggregator(catastrophic_threshold=0.5)
        for i in range(5):
            error = ErrorSignal(
                action_id=str(i),
                normalized_error=-0.8,
                sign=-1,
                absolute_error=0.6 if i < 3 else 0.3,  # 3 catastrophic
            )
            agg.add(error)

        stats = agg.get_stats()
        assert stats.catastrophic_count == 3
        assert stats.catastrophic_rate == pytest.approx(0.6)

    def test_clear(self) -> None:
        agg = SlidingWindowAggregator()
        agg.add(ErrorSignal(action_id="1", normalized_error=0.5, sign=1))
        agg.clear()
        stats = agg.get_stats()
        assert stats.count == 0


class TestStrategyAggregator:
    """Tests for StrategyAggregator."""

    def test_separate_strategies(self) -> None:
        from nak_controller.aar.types import AAREntry

        agg = StrategyAggregator()

        # Add entries for two strategies
        for i in range(5):
            entry_a = AAREntry(
                action_id=f"a-{i}",
                action=ActionEvent(
                    action_id=f"a-{i}",
                    action_type="trade",
                    strategy_id="strategy_a",
                    timestamp=time.time(),
                ),
                prediction=Prediction(action_id=f"a-{i}"),
                outcome=Outcome(action_id=f"a-{i}"),
                error_signal=ErrorSignal(
                    action_id=f"a-{i}",
                    normalized_error=0.5,
                    sign=1,
                ),
            )
            entry_b = AAREntry(
                action_id=f"b-{i}",
                action=ActionEvent(
                    action_id=f"b-{i}",
                    action_type="trade",
                    strategy_id="strategy_b",
                    timestamp=time.time(),
                ),
                prediction=Prediction(action_id=f"b-{i}"),
                outcome=Outcome(action_id=f"b-{i}"),
                error_signal=ErrorSignal(
                    action_id=f"b-{i}",
                    normalized_error=-0.3,
                    sign=-1,
                ),
            )
            agg.add(entry_a)
            agg.add(entry_b)

        stats_a = agg.get_stats("strategy_a")
        stats_b = agg.get_stats("strategy_b")

        assert stats_a.count == 5
        assert stats_b.count == 5
        assert stats_a.mean == pytest.approx(0.5)
        assert stats_b.mean == pytest.approx(-0.3)

    def test_unknown_strategy_returns_empty(self) -> None:
        agg = StrategyAggregator()
        stats = agg.get_stats("unknown")
        assert stats.count == 0

    def test_get_all_stats(self) -> None:
        from nak_controller.aar.types import AAREntry

        agg = StrategyAggregator()
        entry = AAREntry(
            action_id="1",
            action=ActionEvent(
                action_id="1",
                action_type="trade",
                strategy_id="strat1",
                timestamp=time.time(),
            ),
            prediction=Prediction(action_id="1"),
            outcome=Outcome(action_id="1"),
            error_signal=ErrorSignal(action_id="1", normalized_error=0.2, sign=1),
        )
        agg.add(entry)

        all_stats = agg.get_all_stats()
        assert "strat1" in all_stats
        assert all_stats["strat1"].count == 1


class TestModeAggregator:
    """Tests for ModeAggregator."""

    def test_separate_modes(self) -> None:
        from nak_controller.aar.types import AAREntry

        agg = ModeAggregator()

        entry = AAREntry(
            action_id="1",
            action=ActionEvent(
                action_id="1",
                action_type="trade",
                strategy_id="strat",
                timestamp=time.time(),
            ),
            prediction=Prediction(action_id="1"),
            outcome=Outcome(action_id="1"),
            error_signal=ErrorSignal(action_id="1", normalized_error=0.5, sign=1),
        )
        agg.add(entry, "GREEN")

        entry2 = AAREntry(
            action_id="2",
            action=ActionEvent(
                action_id="2",
                action_type="trade",
                strategy_id="strat",
                timestamp=time.time(),
            ),
            prediction=Prediction(action_id="2"),
            outcome=Outcome(action_id="2"),
            error_signal=ErrorSignal(action_id="2", normalized_error=-0.8, sign=-1),
        )
        agg.add(entry2, "RED")

        green_stats = agg.get_stats("GREEN")
        red_stats = agg.get_stats("RED")

        assert green_stats.count == 1
        assert green_stats.mean == pytest.approx(0.5)
        assert red_stats.count == 1
        assert red_stats.mean == pytest.approx(-0.8)


class TestAARTracker:
    """Tests for AARTracker."""

    def test_full_lifecycle(self) -> None:
        tracker = AARTracker()

        action = create_action_event("trade", "strat1", {"side": "buy"})
        tracker.record_action(action)

        pred = Prediction(
            action_id=action.action_id,
            expected_pnl=100.0,
            timestamp=time.time(),
        )
        tracker.record_prediction(pred)

        out = Outcome(
            action_id=action.action_id,
            actual_pnl=90.0,
            timestamp=time.time(),
        )
        entry = tracker.record_outcome(out)

        assert entry is not None
        assert entry.action_id == action.action_id
        assert entry.error_signal.absolute_error > 0

    def test_duplicate_action_raises(self) -> None:
        tracker = AARTracker()
        action = create_action_event("trade", "strat1")
        tracker.record_action(action)

        with pytest.raises(ValueError, match="already pending"):
            tracker.record_action(action)

    def test_prediction_without_action_raises(self) -> None:
        tracker = AARTracker()
        pred = Prediction(action_id="unknown")

        with pytest.raises(ValueError, match="No pending action"):
            tracker.record_prediction(pred)

    def test_outcome_without_action_raises(self) -> None:
        tracker = AARTracker()
        out = Outcome(action_id="unknown")

        with pytest.raises(ValueError, match="No pending action"):
            tracker.record_outcome(out)

    def test_outcome_without_prediction_uses_default(self) -> None:
        tracker = AARTracker()
        action = create_action_event("trade", "strat1")
        tracker.record_action(action)

        # Skip prediction
        out = Outcome(action_id=action.action_id, actual_pnl=50.0)
        entry = tracker.record_outcome(out)

        assert entry is not None
        assert entry.prediction.expected_pnl == 0.0  # Default
        assert entry.prediction.confidence == 0.0  # Default

    def test_get_recent_entries(self) -> None:
        tracker = AARTracker()

        for i in range(5):
            action = create_action_event("trade", "strat1", action_id=str(i))
            tracker.record_action(action)
            tracker.record_prediction(Prediction(action_id=str(i)))
            tracker.record_outcome(Outcome(action_id=str(i)))

        recent = tracker.get_recent_entries(3)
        assert len(recent) == 3
        assert recent[0].action_id == "4"  # Most recent first
        assert recent[2].action_id == "2"

    def test_get_entries_by_strategy(self) -> None:
        tracker = AARTracker()

        for i in range(3):
            action = create_action_event("trade", f"strat{i % 2}", action_id=str(i))
            tracker.record_action(action)
            tracker.record_outcome(Outcome(action_id=str(i)))

        strat0_entries = tracker.get_entries_by_strategy("strat0")
        strat1_entries = tracker.get_entries_by_strategy("strat1")

        assert len(strat0_entries) == 2  # ids 0 and 2
        assert len(strat1_entries) == 1  # id 1

    def test_pending_count(self) -> None:
        tracker = AARTracker()

        for i in range(3):
            action = create_action_event("trade", "strat", action_id=str(i))
            tracker.record_action(action)

        assert tracker.pending_count() == 3

        tracker.record_outcome(Outcome(action_id="0"))
        assert tracker.pending_count() == 2

    def test_max_pending_eviction(self) -> None:
        tracker = AARTracker(max_pending=3)

        for i in range(5):
            action = create_action_event("trade", "strat", action_id=str(i))
            tracker.record_action(action)

        # Should have evicted oldest two
        assert tracker.pending_count() == 3

    def test_clear(self) -> None:
        tracker = AARTracker()

        action = create_action_event("trade", "strat")
        tracker.record_action(action)
        tracker.record_outcome(Outcome(action_id=action.action_id))

        tracker.clear()

        assert tracker.pending_count() == 0
        assert tracker.entry_count() == 0

    def test_strategy_stats_integration(self) -> None:
        tracker = AARTracker()

        for i in range(10):
            action = create_action_event("trade", "momentum", action_id=str(i))
            tracker.record_action(action)
            tracker.record_prediction(Prediction(action_id=str(i), expected_pnl=100.0))
            tracker.record_outcome(
                Outcome(action_id=str(i), actual_pnl=90.0),
                mode="GREEN",
            )

        stats = tracker.get_strategy_stats("momentum")
        assert stats.count == 10
        assert stats.negative_count > 0  # PnL was worse than expected


class TestCreateActionEvent:
    """Tests for create_action_event helper."""

    def test_auto_id_generation(self) -> None:
        action = create_action_event("trade", "strat1")
        assert action.action_id is not None
        assert len(action.action_id) > 0

    def test_explicit_id(self) -> None:
        action = create_action_event("trade", "strat1", action_id="my-id")
        assert action.action_id == "my-id"

    def test_timestamp_set(self) -> None:
        before = time.time()
        action = create_action_event("trade", "strat1")
        after = time.time()
        assert before <= action.timestamp <= after

    def test_parameters_preserved(self) -> None:
        params = {"side": "buy", "size": 100}
        action = create_action_event("trade", "strat1", params)
        assert action.parameters == params


class TestAARIntegration:
    """Integration tests for AAR decision loop simulation."""

    def test_prediction_to_outcome_to_adaptation_loop(self) -> None:
        """Simulate a full cycle: predict → act → outcome → error → adapt."""
        tracker = AARTracker()

        # Simulate 20 actions with varying prediction accuracy
        for i in range(20):
            action = create_action_event("trade", "momentum", action_id=f"action-{i}")
            tracker.record_action(action, context={"market_vol": 0.3 + i * 0.01})

            # Prediction
            expected_pnl = 100.0
            tracker.record_prediction(
                Prediction(
                    action_id=action.action_id,
                    expected_pnl=expected_pnl,
                    expected_latency_ms=5.0,
                    confidence=0.8,
                    timestamp=time.time(),
                )
            )

            # Simulate outcome - gradually getting worse
            actual_pnl = expected_pnl - i * 5  # Degrading performance
            tracker.record_outcome(
                Outcome(
                    action_id=action.action_id,
                    actual_pnl=actual_pnl,
                    actual_latency_ms=5.0,
                    timestamp=time.time(),
                ),
                mode="GREEN" if i < 10 else "AMBER",
            )

        # Check that error trend is captured
        stats = tracker.get_strategy_stats("momentum")
        assert stats.count == 20
        assert stats.negative_count > stats.positive_count  # Degrading performance

        # Check mode stats
        green_stats = tracker.get_mode_stats("GREEN")
        amber_stats = tracker.get_mode_stats("AMBER")
        assert green_stats.count == 10
        assert amber_stats.count == 10

    def test_positive_errors_reinforce_behavior(self) -> None:
        """Test that positive error series produces positive aggregate."""
        tracker = AARTracker()

        # 10 actions all better than expected
        for i in range(10):
            action = create_action_event("trade", "good_strat", action_id=f"good-{i}")
            tracker.record_action(action)
            tracker.record_prediction(
                Prediction(action_id=action.action_id, expected_pnl=100.0)
            )
            # Outcome better than expected
            tracker.record_outcome(
                Outcome(action_id=action.action_id, actual_pnl=120.0)
            )

        stats = tracker.get_strategy_stats("good_strat")
        assert stats.positive_count == 10
        assert stats.negative_count == 0
        assert stats.mean > 0

    def test_negative_errors_suppress_behavior(self) -> None:
        """Test that negative error series produces negative aggregate."""
        tracker = AARTracker()

        # 10 actions all worse than expected
        for i in range(10):
            action = create_action_event("trade", "bad_strat", action_id=f"bad-{i}")
            tracker.record_action(action)
            tracker.record_prediction(
                Prediction(action_id=action.action_id, expected_pnl=100.0)
            )
            # Outcome worse than expected
            tracker.record_outcome(Outcome(action_id=action.action_id, actual_pnl=50.0))

        stats = tracker.get_strategy_stats("bad_strat")
        assert stats.negative_count == 10
        assert stats.positive_count == 0
        assert stats.mean < 0


class TestAARDopamineModulation:
    """Tests for aar_dopamine_modulation function."""

    def test_no_modulation_below_min_samples(self) -> None:
        stats = AggregateStats(count=5, mean=0.5, positive_count=5)
        config = AARAdaptationConfig(min_samples=10)
        result = aar_dopamine_modulation(stats, config)
        assert result == 0.0

    def test_positive_mean_increases_dopamine(self) -> None:
        stats = AggregateStats(count=20, mean=0.3, positive_count=15, negative_count=5)
        config = AARAdaptationConfig(positive_threshold=0.1)
        result = aar_dopamine_modulation(stats, config)
        assert result > 0

    def test_negative_mean_no_dopamine(self) -> None:
        stats = AggregateStats(count=20, mean=-0.3, positive_count=5, negative_count=15)
        config = AARAdaptationConfig()
        result = aar_dopamine_modulation(stats, config)
        assert result == 0.0

    def test_capped_at_max_step(self) -> None:
        stats = AggregateStats(count=20, mean=0.9, positive_count=20)
        config = AARAdaptationConfig(max_adaptation_step=0.1)
        result = aar_dopamine_modulation(stats, config)
        assert result <= 0.1


class TestAARSerotoninModulation:
    """Tests for aar_serotonin_modulation function."""

    def test_no_modulation_below_min_samples(self) -> None:
        stats = AggregateStats(count=5, mean=-0.5, negative_count=5)
        config = AARAdaptationConfig(min_samples=10)
        result = aar_serotonin_modulation(stats, config)
        assert result == 0.0

    def test_negative_mean_increases_serotonin(self) -> None:
        stats = AggregateStats(count=20, mean=-0.3, positive_count=5, negative_count=15)
        config = AARAdaptationConfig(negative_threshold=-0.1)
        result = aar_serotonin_modulation(stats, config)
        assert result > 0

    def test_positive_mean_no_serotonin(self) -> None:
        stats = AggregateStats(count=20, mean=0.3, positive_count=15, negative_count=5)
        config = AARAdaptationConfig()
        result = aar_serotonin_modulation(stats, config)
        assert result == 0.0

    def test_catastrophic_rate_increases_serotonin(self) -> None:
        stats = AggregateStats(
            count=20, mean=-0.1, catastrophic_rate=0.2, negative_count=10
        )
        config = AARAdaptationConfig()
        result = aar_serotonin_modulation(stats, config)
        assert result > 0

    def test_always_non_negative(self) -> None:
        stats = AggregateStats(count=20, mean=0.5, positive_count=20)
        config = AARAdaptationConfig()
        result = aar_serotonin_modulation(stats, config)
        assert result >= 0


class TestShouldFreezeAdaptation:
    """Tests for should_freeze_adaptation function."""

    def test_no_freeze_below_min_samples(self) -> None:
        stats = AggregateStats(count=5, std=1.0)
        state = AARAdaptationState()
        config = AARAdaptationConfig(min_samples=10)
        should_freeze, reason = should_freeze_adaptation(stats, state, config)
        assert not should_freeze

    def test_freeze_on_high_variance(self) -> None:
        stats = AggregateStats(count=20, std=0.8)
        state = AARAdaptationState()
        config = AARAdaptationConfig(freeze_variance_threshold=0.5)
        should_freeze, reason = should_freeze_adaptation(stats, state, config)
        assert should_freeze
        assert "variance" in reason.lower()

    def test_freeze_on_mean_shift(self) -> None:
        stats = AggregateStats(count=20, mean=0.5, std=0.1)
        state = AARAdaptationState(historical_mean=0.0, historical_std=0.1)
        config = AARAdaptationConfig()
        should_freeze, reason = should_freeze_adaptation(stats, state, config)
        assert should_freeze
        assert "z-score" in reason.lower()

    def test_freeze_on_high_catastrophic_rate(self) -> None:
        stats = AggregateStats(count=20, catastrophic_rate=0.25)
        state = AARAdaptationState()
        config = AARAdaptationConfig()
        should_freeze, reason = should_freeze_adaptation(stats, state, config)
        assert should_freeze
        assert "catastrophic" in reason.lower()


class TestComputeRiskReduction:
    """Tests for compute_risk_reduction function."""

    def test_no_reduction_below_min_samples(self) -> None:
        stats = AggregateStats(count=5, mean=-0.5)
        config = AARAdaptationConfig(min_samples=10)
        factor = compute_risk_reduction(stats, config)
        assert factor == 1.0

    def test_reduction_on_negative_mean(self) -> None:
        stats = AggregateStats(count=20, mean=-0.3)
        config = AARAdaptationConfig(negative_threshold=-0.1)
        factor = compute_risk_reduction(stats, config)
        assert factor < 1.0
        assert factor >= 0.5

    def test_further_reduction_on_catastrophic(self) -> None:
        stats_no_cat = AggregateStats(count=20, mean=-0.3, catastrophic_rate=0.0)
        stats_cat = AggregateStats(count=20, mean=-0.3, catastrophic_rate=0.15)
        config = AARAdaptationConfig()
        factor_no_cat = compute_risk_reduction(stats_no_cat, config)
        factor_cat = compute_risk_reduction(stats_cat, config)
        assert factor_cat < factor_no_cat

    def test_never_below_minimum(self) -> None:
        stats = AggregateStats(count=20, mean=-0.9, catastrophic_rate=0.5)
        config = AARAdaptationConfig()
        factor = compute_risk_reduction(stats, config)
        assert factor >= 0.5


class TestComputeAARAdaptation:
    """Tests for compute_aar_adaptation function."""

    def test_returns_adaptation_result(self) -> None:
        stats = AggregateStats(count=20, mean=0.2, positive_count=15)
        state = AARAdaptationState()
        result = compute_aar_adaptation(stats, state)
        assert isinstance(result, AARAdaptationResult)
        assert "aar_error_mean" in result.metrics

    def test_frozen_state_propagates(self) -> None:
        stats = AggregateStats(count=20, std=0.8)  # High variance
        state = AARAdaptationState()
        config = AARAdaptationConfig(freeze_variance_threshold=0.5)
        result = compute_aar_adaptation(stats, state, config)
        assert result.is_frozen
        assert result.freeze_reason != ""

    def test_already_frozen_stays_frozen(self) -> None:
        stats = AggregateStats(count=20, mean=0.2)
        state = AARAdaptationState(is_frozen=True, freeze_reason="Manual freeze")
        result = compute_aar_adaptation(stats, state)
        assert result.is_frozen

    def test_positive_stats_produce_dopamine(self) -> None:
        stats = AggregateStats(count=20, mean=0.3, positive_count=18, negative_count=2)
        state = AARAdaptationState()
        result = compute_aar_adaptation(stats, state)
        assert result.dopamine_adjustment > 0
        assert result.serotonin_adjustment == 0.0

    def test_negative_stats_produce_serotonin(self) -> None:
        stats = AggregateStats(count=20, mean=-0.3, positive_count=2, negative_count=18)
        state = AARAdaptationState()
        result = compute_aar_adaptation(stats, state)
        assert result.serotonin_adjustment > 0
        assert result.should_reduce_risk


class TestUpdateAdaptationState:
    """Tests for update_adaptation_state function."""

    def test_updates_historical_baseline(self) -> None:
        state = AARAdaptationState(historical_mean=0.0, historical_std=0.0)
        stats = AggregateStats(count=20, mean=0.5, std=0.2)
        result = AARAdaptationResult(dopamine_adjustment=0.1)

        update_adaptation_state(state, stats, result)

        assert state.historical_mean > 0
        assert state.historical_std > 0

    def test_tracks_cumulative_adjustments(self) -> None:
        state = AARAdaptationState()
        stats = AggregateStats(count=20)
        result = AARAdaptationResult(
            dopamine_adjustment=0.1,
            serotonin_adjustment=0.05,
        )

        update_adaptation_state(state, stats, result)

        assert state.cumulative_dopamine_adjustment == 0.1
        assert state.cumulative_serotonin_adjustment == 0.05
        assert state.adaptation_count == 1

    def test_no_tracking_when_frozen(self) -> None:
        state = AARAdaptationState()
        stats = AggregateStats(count=20)
        result = AARAdaptationResult(
            is_frozen=True,
            dopamine_adjustment=0.1,
        )

        update_adaptation_state(state, stats, result)

        assert state.cumulative_dopamine_adjustment == 0.0
        assert state.adaptation_count == 0


class TestAARControllerIntegration:
    """Integration tests for AAR with controller-like scenarios."""

    def test_full_adaptation_cycle(self) -> None:
        """Test a complete cycle: track → aggregate → adapt → update."""
        tracker = AARTracker()
        config = AARAdaptationConfig(min_samples=5)
        state = AARAdaptationState()

        # Simulate 10 positive trades
        for i in range(10):
            action = create_action_event("trade", "strat1", action_id=f"pos-{i}")
            tracker.record_action(action)
            tracker.record_prediction(
                Prediction(action_id=action.action_id, expected_pnl=100.0)
            )
            tracker.record_outcome(
                Outcome(action_id=action.action_id, actual_pnl=120.0)
            )

        # Get stats and compute adaptation
        stats = tracker.get_strategy_stats("strat1")
        result = compute_aar_adaptation(stats, state, config)

        # Should have positive dopamine, no serotonin
        assert result.dopamine_adjustment > 0
        assert result.serotonin_adjustment == 0.0
        assert not result.should_reduce_risk

        # Update state
        update_adaptation_state(state, stats, result)
        assert state.adaptation_count == 1

    def test_degrading_performance_triggers_caution(self) -> None:
        """Test that degrading performance triggers risk reduction."""
        tracker = AARTracker()
        config = AARAdaptationConfig(min_samples=5)
        state = AARAdaptationState()

        # Simulate 10 negative trades
        for i in range(10):
            action = create_action_event("trade", "strat2", action_id=f"neg-{i}")
            tracker.record_action(action)
            tracker.record_prediction(
                Prediction(action_id=action.action_id, expected_pnl=100.0)
            )
            tracker.record_outcome(Outcome(action_id=action.action_id, actual_pnl=50.0))

        stats = tracker.get_strategy_stats("strat2")
        result = compute_aar_adaptation(stats, state, config)

        # Should have serotonin, risk reduction
        assert result.serotonin_adjustment > 0
        assert result.should_reduce_risk
        assert result.risk_reduction_factor < 1.0
