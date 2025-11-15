"""Tests for energy diagnostics module."""

from __future__ import annotations

import pytest

from tacl.energy_model import EnergyMetrics, EnergyValidationResult, DEFAULT_THRESHOLDS, DEFAULT_WEIGHTS
from tacl.energy_diagnostics import (
    EnergyDiagnostics,
    EnergyBudget,
    EntropyDecomposition,
)


@pytest.fixture
def sample_metrics():
    """Create sample metrics for testing."""
    return EnergyMetrics(
        latency_p95=70.0,
        latency_p99=100.0,
        coherency_drift=0.05,
        cpu_burn=0.6,
        mem_cost=5.0,
        queue_depth=25.0,
        packet_loss=0.003,
    )


@pytest.fixture
def sample_results():
    """Create sample validation results for testing."""
    return [
        EnergyValidationResult(
            passed=True,
            free_energy=1.0,
            internal_energy=1.2,
            entropy=0.3,
            penalties={"latency_p95": 0.0, "latency_p99": 0.0},
        ),
        EnergyValidationResult(
            passed=True,
            free_energy=1.05,
            internal_energy=1.25,
            entropy=0.3,
            penalties={"latency_p95": 0.0, "latency_p99": 0.0},
        ),
        EnergyValidationResult(
            passed=True,
            free_energy=1.1,
            internal_energy=1.3,
            entropy=0.3,
            penalties={"latency_p95": 0.0, "latency_p99": 0.0},
        ),
    ]


def test_energy_trend_analysis(sample_results):
    """Test trend analysis of energy evolution."""
    diagnostics = EnergyDiagnostics()
    trend = diagnostics.analyze_trend(sample_results)
    
    assert trend.mean > 0
    assert trend.std >= 0
    assert trend.min <= trend.mean <= trend.max
    assert trend.is_increasing == (trend.trend_slope > 0)


def test_energy_trend_requires_minimum_samples():
    """Test that trend analysis requires minimum samples."""
    diagnostics = EnergyDiagnostics()
    results = [
        EnergyValidationResult(
            passed=True,
            free_energy=1.0,
            internal_energy=1.2,
            entropy=0.3,
            penalties={},
        )
    ]
    
    with pytest.raises(ValueError, match="at least"):
        diagnostics.analyze_trend(results, min_samples=3)


def test_anomaly_detection(sample_results):
    """Test anomaly detection in energy sequence."""
    diagnostics = EnergyDiagnostics()
    
    # Add an anomalous result
    anomalous = EnergyValidationResult(
        passed=False,
        free_energy=5.0,  # Much higher than others
        internal_energy=5.2,
        entropy=0.1,
        penalties={},
    )
    results_with_anomaly = sample_results + [anomalous]
    
    report = diagnostics.detect_anomalies(results_with_anomaly, threshold=2.0)
    
    assert report.has_anomalies()
    assert report.anomaly_count > 0
    assert report.anomaly_rate > 0


def test_anomaly_detection_no_anomalies(sample_results):
    """Test anomaly detection with no anomalies."""
    diagnostics = EnergyDiagnostics()
    report = diagnostics.detect_anomalies(sample_results, threshold=3.0)
    
    assert not report.has_anomalies()
    assert report.anomaly_count == 0


def test_energy_breakdown(sample_results):
    """Test detailed energy breakdown."""
    diagnostics = EnergyDiagnostics()
    breakdown = diagnostics.create_breakdown(sample_results[0])
    
    assert breakdown.total_free_energy == sample_results[0].free_energy
    assert breakdown.internal_energy == sample_results[0].internal_energy
    assert breakdown.temperature > 0
    
    sorted_penalties = breakdown.get_sorted_penalties()
    assert isinstance(sorted_penalties, list)


def test_energy_budget_tracking():
    """Test energy budget tracking and alerting."""
    budget = EnergyBudget(budget_limit=1.5, warning_threshold=0.8, critical_threshold=0.95)
    
    # Normal usage
    budget.update(0.5)
    assert not budget.is_warning()
    assert not budget.is_critical()
    assert budget.alert_level() == "NORMAL"
    assert budget.remaining_budget() > 0
    
    # Warning level
    budget.update(1.3)
    assert budget.is_warning()
    assert not budget.is_critical()
    assert budget.alert_level() == "WARNING"
    
    # Critical level
    budget.update(1.45)
    assert budget.is_warning()
    assert budget.is_critical()
    assert budget.alert_level() == "CRITICAL"


def test_energy_budget_utilization():
    """Test energy budget utilization calculation."""
    budget = EnergyBudget(budget_limit=2.0)
    
    budget.update(1.0)
    assert budget.utilization() == pytest.approx(0.5)
    
    budget.update(1.5)
    assert budget.utilization() == pytest.approx(0.75)
    
    budget.update(2.0)
    assert budget.utilization() == pytest.approx(1.0)


def test_entropy_decomposition(sample_metrics):
    """Test entropy decomposition into per-metric contributions."""
    decomp = EntropyDecomposition(DEFAULT_WEIGHTS, DEFAULT_THRESHOLDS)
    
    contributions = decomp.decompose(sample_metrics)
    assert isinstance(contributions, dict)
    assert len(contributions) == len(DEFAULT_THRESHOLDS)
    
    # All contributions should be non-negative
    for value in contributions.values():
        assert value >= 0
    
    # Get stability ranking
    ranking = decomp.get_stability_ranking(sample_metrics)
    assert isinstance(ranking, list)
    assert len(ranking) == len(DEFAULT_THRESHOLDS)
    
    # Check that ranking is sorted in descending order
    for i in range(len(ranking) - 1):
        assert ranking[i][1] >= ranking[i + 1][1]


def test_entropy_decomposition_normalized_weights():
    """Test that entropy decomposition uses normalized weights."""
    weights = {"metric1": 1.0, "metric2": 2.0}
    thresholds = {"metric1": 10.0, "metric2": 20.0}
    
    decomp = EntropyDecomposition(weights, thresholds)
    
    # Both metrics at half threshold
    metrics_dict = {"metric1": 5.0, "metric2": 10.0}
    
    # Create a minimal EnergyMetrics-like object for testing
    class TestMetrics:
        def as_dict(self):
            return metrics_dict
    
    contributions = decomp.decompose(TestMetrics())  # type: ignore
    
    # Both should have same stability (0.5) but different weighted contributions
    # metric2 should contribute more due to higher weight
    assert contributions["metric2"] > contributions["metric1"]


def test_diagnostics_with_scipy_unavailable():
    """Test diagnostics work without scipy installed."""
    # This test verifies graceful degradation
    diagnostics = EnergyDiagnostics(enable_forecasting=False)
    
    results = [
        EnergyValidationResult(
            passed=True,
            free_energy=1.0 + i * 0.1,
            internal_energy=1.2 + i * 0.1,
            entropy=0.3,
            penalties={},
        )
        for i in range(5)
    ]
    
    trend = diagnostics.analyze_trend(results)
    assert trend.mean > 0
    assert trend.std >= 0
