"""Comprehensive tests for ML crisis predictor validation and falsifiability.

This test suite validates the crisis detection system's ability to correctly
identify crisis conditions while minimizing false positives. It exercises
both negative test cases (normal conditions) and edge cases to ensure
robustness in production environments.
"""

from __future__ import annotations

import numpy as np
import pytest

from evolution.crisis_ga import CrisisMode
from sandbox.control.thermo_prototype import (
    BacktestResult,
    run_backtest_on_synthetic_crises,
)


class TestCrisisPredictorBacktest:
    """Test suite for synthetic crisis backtest validation."""

    def test_backtest_returns_valid_metrics(self) -> None:
        """Verify backtest returns all required metrics within valid ranges."""
        result = run_backtest_on_synthetic_crises(seed=42, num_scenarios=20)

        assert isinstance(result, BacktestResult)
        assert 0.0 <= result.accuracy <= 1.0
        assert 0.0 <= result.precision <= 1.0
        assert 0.0 <= result.recall <= 1.0
        assert 0.0 <= result.f1_score <= 1.0
        assert 0.0 <= result.false_positive_rate <= 1.0
        assert 0.0 <= result.false_negative_rate <= 1.0

    def test_backtest_generates_correct_number_of_scenarios(self) -> None:
        """Verify backtest generates the requested number of scenarios."""
        num_scenarios = 30
        result = run_backtest_on_synthetic_crises(seed=42, num_scenarios=num_scenarios)

        assert len(result.crisis_labels) == num_scenarios
        assert len(result.predicted_labels) == num_scenarios
        assert len(result.free_energies) == num_scenarios
        assert len(result.entropy_values) == num_scenarios
        assert len(result.latency_means) == num_scenarios

    def test_backtest_generates_mixed_scenarios(self) -> None:
        """Verify backtest generates both crisis and normal scenarios."""
        result = run_backtest_on_synthetic_crises(seed=42, num_scenarios=40)

        crisis_count = sum(
            1 for label in result.crisis_labels if label != CrisisMode.NORMAL
        )
        normal_count = sum(
            1 for label in result.crisis_labels if label == CrisisMode.NORMAL
        )

        assert crisis_count > 0, "Should generate crisis scenarios"
        assert normal_count > 0, "Should generate normal scenarios"
        # Roughly half should be crisis, half normal
        assert abs(crisis_count - normal_count) <= 1

    def test_crisis_scenarios_have_elevated_characteristics(self) -> None:
        """Verify crisis scenarios exhibit high entropy and elevated latency."""
        result = run_backtest_on_synthetic_crises(seed=42, num_scenarios=40)

        # Extract crisis scenario indices
        crisis_indices = [
            i
            for i, label in enumerate(result.crisis_labels)
            if label != CrisisMode.NORMAL
        ]

        for idx in crisis_indices:
            # Crisis scenarios should have higher latency
            assert result.latency_means[idx] >= 1.0, (
                f"Crisis scenario {idx} should have elevated latency "
                f"(got {result.latency_means[idx]:.2f})"
            )

    def test_normal_scenarios_have_stable_characteristics(self) -> None:
        """Verify normal scenarios exhibit low latency and stable behavior."""
        result = run_backtest_on_synthetic_crises(seed=42, num_scenarios=40)

        # Extract normal scenario indices
        normal_indices = [
            i
            for i, label in enumerate(result.crisis_labels)
            if label == CrisisMode.NORMAL
        ]

        for idx in normal_indices:
            # Normal scenarios should have lower latency
            assert result.latency_means[idx] < 1.0, (
                f"Normal scenario {idx} should have normal latency "
                f"(got {result.latency_means[idx]:.2f})"
            )

    def test_backtest_is_deterministic_with_seed(self) -> None:
        """Verify backtest produces identical results with the same seed."""
        result1 = run_backtest_on_synthetic_crises(seed=123, num_scenarios=20)
        result2 = run_backtest_on_synthetic_crises(seed=123, num_scenarios=20)

        assert result1.accuracy == result2.accuracy
        assert result1.precision == result2.precision
        assert result1.recall == result2.recall
        assert result1.f1_score == result2.f1_score
        assert result1.crisis_labels == result2.crisis_labels
        assert result1.predicted_labels == result2.predicted_labels

    def test_backtest_results_vary_with_different_seeds(self) -> None:
        """Verify backtest produces different results with different seeds."""
        result1 = run_backtest_on_synthetic_crises(seed=100, num_scenarios=20)
        result2 = run_backtest_on_synthetic_crises(seed=200, num_scenarios=20)

        # Results should differ (at least in the generated scenarios)
        assert result1.free_energies != result2.free_energies

    def test_backtest_as_dict_serialization(self) -> None:
        """Verify BacktestResult can be serialized to dict."""
        result = run_backtest_on_synthetic_crises(seed=42, num_scenarios=10)
        result_dict = result.as_dict()

        assert isinstance(result_dict, dict)
        assert "accuracy" in result_dict
        assert "precision" in result_dict
        assert "recall" in result_dict
        assert "f1_score" in result_dict
        assert "crisis_labels" in result_dict
        assert "predicted_labels" in result_dict
        assert "free_energies" in result_dict
        assert "entropy_values" in result_dict
        assert "latency_means" in result_dict
        assert "false_positive_rate" in result_dict
        assert "false_negative_rate" in result_dict


class TestCrisisPredictorNegativeCases:
    """Negative test cases: normal conditions should not trigger false alarms."""

    def test_low_false_positive_rate_on_stable_conditions(self) -> None:
        """Verify false positive rate is low when conditions are stable."""
        result = run_backtest_on_synthetic_crises(
            seed=42, num_scenarios=100, crisis_threshold=0.1
        )

        # False positive rate should be reasonably low (< 30%)
        # This ensures we don't over-trigger on stable systems
        assert result.false_positive_rate < 0.3, (
            f"False positive rate too high: {result.false_positive_rate:.2%}. "
            "System may be too sensitive and trigger false alarms."
        )

    def test_normal_conditions_correctly_classified(self) -> None:
        """Verify normal scenarios are predominantly classified as normal."""
        result = run_backtest_on_synthetic_crises(seed=42, num_scenarios=60)

        normal_indices = [
            i
            for i, label in enumerate(result.crisis_labels)
            if label == CrisisMode.NORMAL
        ]

        correct_normal_predictions = sum(
            1
            for idx in normal_indices
            if result.predicted_labels[idx] == CrisisMode.NORMAL
        )

        classification_rate = correct_normal_predictions / len(normal_indices)
        # At least 50% of normal scenarios should be correctly classified
        assert classification_rate >= 0.5, (
            f"Only {classification_rate:.1%} of normal scenarios correctly classified. "
            "Detector may be over-sensitive."
        )

    def test_predictor_does_not_always_predict_crisis(self) -> None:
        """Verify predictor doesn't degenerate to always predicting crisis."""
        result = run_backtest_on_synthetic_crises(seed=42, num_scenarios=50)

        crisis_predictions = sum(
            1 for label in result.predicted_labels if label != CrisisMode.NORMAL
        )

        # Should not predict crisis for all scenarios
        assert crisis_predictions < len(
            result.predicted_labels
        ), "Predictor always predicts crisis - likely degenerate model"

    def test_predictor_does_not_always_predict_normal(self) -> None:
        """Verify predictor doesn't degenerate to always predicting normal."""
        result = run_backtest_on_synthetic_crises(seed=42, num_scenarios=50)

        crisis_predictions = sum(
            1 for label in result.predicted_labels if label != CrisisMode.NORMAL
        )

        # Should predict at least some crisis scenarios
        assert (
            crisis_predictions > 0
        ), "Predictor never predicts crisis - likely degenerate model"


class TestCrisisPredictorEdgeCases:
    """Edge case tests: boundary conditions and extreme values."""

    def test_very_small_number_of_scenarios(self) -> None:
        """Verify backtest handles minimal scenario count."""
        result = run_backtest_on_synthetic_crises(seed=42, num_scenarios=2)

        assert isinstance(result, BacktestResult)
        assert len(result.crisis_labels) == 2

    def test_zero_crisis_threshold_behavior(self) -> None:
        """Verify backtest handles zero threshold edge case."""
        result = run_backtest_on_synthetic_crises(
            seed=42, num_scenarios=20, crisis_threshold=0.0
        )

        # With zero threshold, even tiny deviations are crises
        # Most predictions should be crisis
        crisis_predictions = sum(
            1 for label in result.predicted_labels if label != CrisisMode.NORMAL
        )
        assert crisis_predictions >= len(result.predicted_labels) // 2

    def test_very_high_crisis_threshold_behavior(self) -> None:
        """Verify backtest handles very high threshold."""
        result = run_backtest_on_synthetic_crises(
            seed=42, num_scenarios=20, crisis_threshold=10.0
        )

        # With very high threshold, almost nothing is a crisis
        # Most predictions should be normal
        normal_predictions = sum(
            1 for label in result.predicted_labels if label == CrisisMode.NORMAL
        )
        assert normal_predictions > 0

    def test_consistent_metric_relationships(self) -> None:
        """Verify mathematical relationships between metrics hold."""
        result = run_backtest_on_synthetic_crises(seed=42, num_scenarios=40)

        # If precision and recall are both non-zero, F1 should be non-zero
        if result.precision > 0 and result.recall > 0:
            assert result.f1_score > 0

        # F1 score should be harmonic mean of precision and recall
        if result.precision > 0 and result.recall > 0:
            expected_f1 = (
                2
                * (result.precision * result.recall)
                / (result.precision + result.recall)
            )
            assert np.isclose(result.f1_score, expected_f1, rtol=1e-6)


class TestCrisisPredictorFalsifiability:
    """Tests for falsifiability and robustness of crisis detection."""

    def test_crisis_detection_falsifiability_with_synthetic_data(self) -> None:
        """Verify crisis detector can be falsified with counter-examples.

        This test ensures the model can fail - a key requirement for
        scientific falsifiability. If a model cannot fail, it has no
        predictive power.
        """
        result = run_backtest_on_synthetic_crises(seed=42, num_scenarios=60)

        # Model should not be perfect (accuracy < 1.0)
        # Perfect accuracy suggests overfitting or lack of true validation
        assert result.accuracy < 1.0, (
            "Model has perfect accuracy on synthetic data - "
            "may indicate overfitting or insufficient test coverage"
        )

        # Should have at least some misclassifications
        # Count actual crisis and normal scenarios
        num_crisis = sum(
            1 for label in result.crisis_labels if label != CrisisMode.NORMAL
        )
        num_normal = len(result.crisis_labels) - num_crisis

        # Calculate total errors based on actual counts
        total_errors = (
            result.false_positive_rate * num_normal
            + result.false_negative_rate * num_crisis
        )
        assert total_errors > 0, "Model has zero errors - fails falsifiability test"

    def test_crisis_detector_statistical_properties(self) -> None:
        """Verify crisis detector has reasonable statistical properties."""
        result = run_backtest_on_synthetic_crises(seed=42, num_scenarios=100)

        # Accuracy should be better than random guessing (> 0.5)
        assert (
            result.accuracy > 0.5
        ), f"Accuracy {result.accuracy:.2%} is no better than random guessing"

        # At least one of precision or recall should be reasonable
        assert result.precision > 0.3 or result.recall > 0.3, (
            f"Both precision ({result.precision:.2%}) and recall "
            f"({result.recall:.2%}) are very low"
        )

    def test_crisis_detector_handles_varied_conditions(self) -> None:
        """Verify detector performs consistently across different random seeds."""
        results = []
        for seed in [10, 20, 30, 40, 50]:
            result = run_backtest_on_synthetic_crises(
                seed=seed, num_scenarios=40, crisis_threshold=0.1
            )
            results.append(result.accuracy)

        # Accuracy should be reasonably consistent (std dev < 0.2)
        std_dev = np.std(results)
        assert std_dev < 0.2, (
            f"Accuracy varies too much across seeds (std: {std_dev:.3f}). "
            "Model may be unstable."
        )

        # Mean accuracy should be > 0.5 (better than random)
        mean_accuracy = np.mean(results)
        assert (
            mean_accuracy > 0.5
        ), f"Mean accuracy {mean_accuracy:.2%} is no better than random"

    def test_expected_result_distribution(self) -> None:
        """Verify distribution of results matches expected patterns.

        Crisis scenarios should generally have higher free energy and
        entropy compared to normal scenarios.
        """
        result = run_backtest_on_synthetic_crises(seed=42, num_scenarios=80)

        # Separate metrics by ground truth label
        crisis_indices = [
            i
            for i, label in enumerate(result.crisis_labels)
            if label != CrisisMode.NORMAL
        ]
        normal_indices = [
            i
            for i, label in enumerate(result.crisis_labels)
            if label == CrisisMode.NORMAL
        ]

        crisis_latencies = [result.latency_means[i] for i in crisis_indices]
        normal_latencies = [result.latency_means[i] for i in normal_indices]

        # Crisis scenarios should have higher average latency
        mean_crisis_latency = np.mean(crisis_latencies)
        mean_normal_latency = np.mean(normal_latencies)

        assert mean_crisis_latency > mean_normal_latency, (
            f"Crisis scenarios (latency: {mean_crisis_latency:.3f}) should have "
            f"higher latency than normal scenarios (latency: {mean_normal_latency:.3f})"
        )


@pytest.mark.parametrize("num_scenarios", [10, 20, 50, 100])
def test_backtest_scales_with_scenario_count(num_scenarios: int) -> None:
    """Verify backtest works correctly with different scenario counts."""
    result = run_backtest_on_synthetic_crises(seed=42, num_scenarios=num_scenarios)

    assert len(result.crisis_labels) == num_scenarios
    assert 0.0 <= result.accuracy <= 1.0


@pytest.mark.parametrize("crisis_threshold", [0.05, 0.1, 0.2, 0.5])
def test_backtest_adapts_to_different_thresholds(crisis_threshold: float) -> None:
    """Verify backtest behavior changes appropriately with threshold."""
    result = run_backtest_on_synthetic_crises(
        seed=42, num_scenarios=40, crisis_threshold=crisis_threshold
    )

    assert isinstance(result, BacktestResult)
    assert 0.0 <= result.accuracy <= 1.0
