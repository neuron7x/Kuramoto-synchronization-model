"""Tests for component benchmarking infrastructure."""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

import pytest

from scripts.performance.benchmark_components import (
    PercentileMetrics,
    BenchmarkResult,
    load_budgets,
    benchmark_function,
    validate_against_budget,
)


class TestPercentileMetrics:
    """Test percentile metrics calculation."""
    
    def test_from_timings_basic(self):
        """Test basic percentile calculation."""
        timings = [1.0, 2.0, 3.0, 4.0, 5.0]
        metrics = PercentileMetrics.from_timings(timings)
        
        assert metrics.p50 == pytest.approx(3.0, rel=0.1)
        assert metrics.min == 1.0
        assert metrics.max == 5.0
        assert metrics.samples == 5
        assert metrics.mean == 3.0
    
    def test_from_timings_percentiles(self):
        """Test p95 and p99 calculation."""
        # 100 samples: 1, 2, 3, ..., 100
        timings = [float(i) for i in range(1, 101)]
        metrics = PercentileMetrics.from_timings(timings)
        
        # p50 should be around 50
        assert 49 <= metrics.p50 <= 51
        # p95 should be around 95
        assert 94 <= metrics.p95 <= 96
        # p99 should be around 99
        assert 98 <= metrics.p99 <= 100
    
    def test_from_timings_empty_raises(self):
        """Test that empty timings raise ValueError."""
        with pytest.raises(ValueError, match="empty timings"):
            PercentileMetrics.from_timings([])
    
    def test_single_value(self):
        """Test with single timing value."""
        metrics = PercentileMetrics.from_timings([5.0])
        
        assert metrics.p50 == 5.0
        assert metrics.p95 == 5.0
        assert metrics.p99 == 5.0
        assert metrics.std == 0.0


class TestBenchmarkResult:
    """Test benchmark result formatting."""
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        metrics = PercentileMetrics(
            p50=0.050,
            p95=0.090,
            p99=0.110,
            mean=0.055,
            std=0.015,
            min=0.040,
            max=0.120,
            samples=100,
        )
        
        result = BenchmarkResult(
            component="test_component",
            metrics=metrics,
            budget_p50=60.0,
            budget_p95=100.0,
            budget_p99=120.0,
            passed=True,
            violations=[],
        )
        
        data = result.to_dict()
        
        assert data["component"] == "test_component"
        assert data["passed"] is True
        assert data["metrics"]["p50_ms"] == pytest.approx(50.0)
        assert data["budgets"]["p50_ms"] == 60.0


class TestBudgetLoading:
    """Test budget configuration loading."""
    
    def test_load_budgets(self, tmp_path: Path):
        """Test loading budgets from YAML."""
        config = tmp_path / "test_budgets.yaml"
        config.write_text("""
components:
  test_component:
    observed_ms: 50.0
    budget_ms: 60.0
    percentiles:
      p50_ms: 55.0
      p95_ms: 70.0
      p99_ms: 85.0
""")
        
        budgets = load_budgets(config)
        
        assert "test_component" in budgets
        assert budgets["test_component"]["percentiles"]["p50_ms"] == 55.0


class TestBenchmarkFunction:
    """Test benchmark execution."""
    
    def test_benchmark_function_basic(self):
        """Test basic benchmarking."""
        counter = {"value": 0}
        
        def workload():
            counter["value"] += 1
            return counter["value"]
        
        timings = benchmark_function(workload, iterations=10, warmup=2)
        
        # Should run warmup + iterations times
        assert counter["value"] == 12
        assert len(timings) == 10
        
        # All timings should be positive
        assert all(t > 0 for t in timings)
    
    def test_benchmark_function_captures_time(self):
        """Test that benchmarking captures execution time."""
        import time
        
        def slow_workload():
            time.sleep(0.001)  # 1ms
        
        timings = benchmark_function(slow_workload, iterations=5, warmup=1)
        
        # Each timing should be at least 1ms
        assert all(t >= 0.001 for t in timings)


class TestValidation:
    """Test budget validation."""
    
    def test_validate_within_budget(self):
        """Test validation when within budget."""
        metrics = PercentileMetrics(
            p50=0.050,  # 50ms
            p95=0.080,  # 80ms
            p99=0.100,  # 100ms
            mean=0.055,
            std=0.010,
            min=0.040,
            max=0.110,
            samples=100,
        )
        
        budget = {
            "percentiles": {
                "p50_ms": 60.0,
                "p95_ms": 90.0,
                "p99_ms": 120.0,
            },
            "stability": {
                "max_variance": 0.20,
            },
        }
        
        result = validate_against_budget("test", metrics, budget)
        
        assert result.passed is True
        assert len(result.violations) == 0
    
    def test_validate_exceeds_budget(self):
        """Test validation when exceeding budget."""
        metrics = PercentileMetrics(
            p50=0.070,  # 70ms
            p95=0.095,  # 95ms
            p99=0.130,  # 130ms
            mean=0.075,
            std=0.015,
            min=0.050,
            max=0.140,
            samples=100,
        )
        
        budget = {
            "percentiles": {
                "p50_ms": 60.0,
                "p95_ms": 90.0,
                "p99_ms": 120.0,
            },
            "stability": {
                "max_variance": 0.10,
            },
        }
        
        result = validate_against_budget("test", metrics, budget)
        
        assert result.passed is False
        assert len(result.violations) > 0
        
        # Check that violations mention exceeded budgets
        violations_text = " ".join(result.violations)
        assert "exceeds budget" in violations_text
    
    def test_validate_stability_violation(self):
        """Test validation with high variance when performance is near budget."""
        metrics = PercentileMetrics(
            p50=0.050,  # 50ms
            p95=0.080,  # 80ms
            p99=0.100,  # 100ms
            mean=0.050,
            std=0.025,  # High std dev relative to mean (CoV = 0.5)
            min=0.010,
            max=0.150,
            samples=100,
        )
        
        budget = {
            "percentiles": {
                "p50_ms": 55.0,  # Close to actual (50ms / 55ms = 0.91 > 0.8)
                "p95_ms": 90.0,
                "p99_ms": 120.0,
            },
            "stability": {
                "max_variance": 0.10,  # Max CoV of 0.10
            },
        }
        
        result = validate_against_budget("test", metrics, budget)
        
        # CoV = 0.025 / 0.050 = 0.5, which exceeds 0.10
        # Should fail because performance is > 80% of budget (50/55 = 0.91)
        assert result.passed is False
        assert any("Stability" in v for v in result.violations)
    
    def test_validate_stability_ok_when_far_from_budget(self):
        """Test that stability violations are ignored when performance is good."""
        metrics = PercentileMetrics(
            p50=0.010,  # 10ms - far from budget
            p95=0.015,  # 15ms
            p99=0.020,  # 20ms
            mean=0.010,
            std=0.005,  # High CoV = 0.5
            min=0.005,
            max=0.030,
            samples=100,
        )
        
        budget = {
            "percentiles": {
                "p50_ms": 100.0,  # Far from actual (10ms / 100ms = 0.1 < 0.8)
                "p95_ms": 150.0,
                "p99_ms": 200.0,
            },
            "stability": {
                "max_variance": 0.10,  # Would fail if checked
            },
        }
        
        result = validate_against_budget("test", metrics, budget)
        
        # Should PASS because performance is well within budget
        # even though CoV (0.5) exceeds threshold (0.10)
        assert result.passed is True
        assert len(result.violations) == 0


class TestIntegration:
    """Integration tests for the benchmarking system."""
    
    def test_benchmark_order_router(self):
        """Test that order_router benchmark runs."""
        from scripts.performance.benchmark_components import benchmark_order_router
        
        timings = benchmark_order_router()
        
        assert len(timings) > 0
        assert all(t > 0 for t in timings)
    
    def test_benchmark_link_activator(self):
        """Test that link_activator benchmark runs."""
        from scripts.performance.benchmark_components import benchmark_link_activator
        
        timings = benchmark_link_activator()
        
        assert len(timings) > 0
        assert all(t > 0 for t in timings)
    
    def test_benchmark_thermo_validator(self):
        """Test that thermo_validator benchmark runs."""
        from scripts.performance.benchmark_components import benchmark_thermo_validator
        
        timings = benchmark_thermo_validator()
        
        assert len(timings) > 0
        assert all(t > 0 for t in timings)
