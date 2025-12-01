"""Tests for AAR (Acceptor of Action Result) module.

This module tests the core AAR functionality:
- Error computation formulas
- Error normalization
- Sign detection
- Aggregation
- Memory/tracker lifecycle
"""

from __future__ import annotations

import math
import time

import pytest

from nak_controller.aar import (
    AARTracker,
    ActionEvent,
    AggregateStats,
    ErrorSignal,
    ModeAggregator,
    Outcome,
    Prediction,
    SlidingWindowAggregator,
    StrategyAggregator,
    absolute_error,
    compute_error,
    create_action_event,
    error_sign,
    normalize_error,
    relative_error,
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
            tracker.record_prediction(
                Prediction(action_id=str(i), expected_pnl=100.0)
            )
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
            tracker.record_outcome(
                Outcome(action_id=action.action_id, actual_pnl=50.0)
            )

        stats = tracker.get_strategy_stats("bad_strat")
        assert stats.negative_count == 10
        assert stats.positive_count == 0
        assert stats.mean < 0
